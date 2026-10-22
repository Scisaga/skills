#!/usr/bin/env python3
"""Replace embedded narration in PPTX files and expose one assembly entrypoint."""

from __future__ import annotations

import argparse
import os
import posixpath
import shlex
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Sequence

from production_common import (
    file_hash,
    load_object,
    load_project_config,
    load_state,
    project_paths,
    require_approvals,
    source_fingerprint,
    visual_fingerprint,
    write_object,
)


REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"


def current_visual_provenance(
    project: Path,
    pptx: Path,
    *,
    include_timing: bool = True,
) -> dict[str, Any]:
    config = load_project_config(project)
    paths = project_paths(project, config)
    manifest = load_object(paths["manifest"])
    return {
        "sha256": file_hash(pptx),
        "source_fingerprint": source_fingerprint(project, config),
        "visual_fingerprint": visual_fingerprint(
            project,
            config,
            manifest,
            include_timing=include_timing,
        ),
    }


def record_visual_baseline(
    project: Path,
    pptx: Path,
    *,
    artifact_key: str = "animated_pptx",
    include_timing: bool = True,
) -> dict[str, Any]:
    paths = project_paths(project)
    provenance = current_visual_provenance(
        project,
        pptx,
        include_timing=include_timing,
    )
    state = load_state(paths["build_state"])
    state["artifacts"][artifact_key] = provenance
    write_object(paths["build_state"], state)
    return provenance


def require_current_visual_baseline(
    project: Path,
    pptx: Path,
    *,
    artifact_key: str = "animated_pptx",
    include_timing: bool = True,
) -> dict[str, Any]:
    paths = project_paths(project)
    state = load_state(paths["build_state"])
    recorded = state.get("artifacts", {}).get(artifact_key)
    current = current_visual_provenance(
        project,
        pptx,
        include_timing=include_timing,
    )
    if not isinstance(recorded, dict) or any(
        recorded.get(key) != value for key, value in current.items()
    ):
        raise RuntimeError(
            f"{artifact_key} visual baseline is missing or stale; rerun the "
            "visual assembler before replacing audio"
        )
    return current


def slide_audio_target(archive: zipfile.ZipFile, page: int) -> str:
    rels_name = f"ppt/slides/_rels/slide{page}.xml.rels"
    try:
        payload = archive.read(rels_name)
    except KeyError as exc:
        raise ValueError(f"Missing {rels_name}") from exc
    try:
        from lxml import etree
    except ImportError as exc:
        raise RuntimeError("Missing lxml; run bootstrap first") from exc
    root = etree.fromstring(payload)
    targets: set[str] = set()
    for relationship in root.findall(f"{{{REL_NS}}}Relationship"):
        target = relationship.get("Target", "")
        relationship_type = relationship.get("Type", "")
        if (
            target.lower().endswith(".mp3")
            and relationship.get("TargetMode") != "External"
            and (
                relationship_type.endswith("/audio")
                or relationship_type.endswith("/media")
            )
        ):
            targets.add(
                posixpath.normpath(
                    posixpath.join("ppt/slides", target)
                )
            )
    if len(targets) != 1:
        raise ValueError(
            f"Slide {page} must reference exactly one internal MP3; "
            f"found {sorted(targets)}"
        )
    return targets.pop()


def update_slide_timing(payload: bytes, advance_ms: int) -> bytes:
    try:
        from lxml import etree
    except ImportError as exc:
        raise RuntimeError("Missing lxml; run bootstrap first") from exc
    parser = etree.XMLParser(remove_blank_text=False)
    root = etree.fromstring(payload, parser)
    transition = root.find(f"{{{P_NS}}}transition")
    if transition is None:
        transition = etree.Element(f"{{{P_NS}}}transition")
        children = list(root)
        insert_at = len(children)
        for index, child in enumerate(children):
            if child.tag in {f"{{{P_NS}}}timing", f"{{{P_NS}}}extLst"}:
                insert_at = index
                break
        root.insert(insert_at, transition)
    transition.set("advClick", "0")
    transition.set("advTm", str(advance_ms))
    if len(transition) == 0:
        transition.append(etree.Element(f"{{{P_NS}}}fade"))
    return etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone=True,
    )


def timeline_rows(timeline: dict[str, Any]) -> list[dict[str, Any]]:
    rows = timeline.get("slides")
    if not isinstance(rows, list) or not rows:
        raise ValueError("audio_timeline.slides must be a non-empty array")
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(f"audio_timeline.slides[{index - 1}] is invalid")
        page = row.get("page")
        audio_file = row.get("audio_file")
        advance_ms = row.get("advance_ms")
        if (
            isinstance(page, bool)
            or not isinstance(page, int)
            or page != index
        ):
            raise ValueError("Audio timeline pages must be contiguous from 1")
        if not isinstance(audio_file, str) or not audio_file:
            raise ValueError(f"Audio timeline page {page} has no audio_file")
        if (
            isinstance(advance_ms, bool)
            or not isinstance(advance_ms, int)
            or advance_ms <= 0
        ):
            raise ValueError(f"Audio timeline page {page} has invalid advance_ms")
        normalized.append(row)
    return normalized


def replace_audio(
    project: Path,
    *,
    input_pptx: Path,
    output_pptx: Path,
) -> dict[str, Any]:
    paths = project_paths(project)
    timeline = load_object(paths["audio_timeline"])
    rows = timeline_rows(timeline)
    if not input_pptx.is_file():
        raise FileNotFoundError(input_pptx)
    visual_baseline = require_current_visual_baseline(project, input_pptx)

    replacements: dict[str, bytes] = {}
    changed_members: list[str] = []
    audio_targets: dict[int, str] = {}
    output_pptx.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=output_pptx.parent,
        prefix=f".{output_pptx.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
    try:
        with zipfile.ZipFile(input_pptx) as source:
            for row in rows:
                page = int(row["page"])
                target = slide_audio_target(source, page)
                if target in audio_targets.values():
                    raise ValueError(
                        f"Embedded media target {target} is shared across slides"
                    )
                try:
                    source.read(target)
                except KeyError as exc:
                    raise ValueError(
                        f"Slide {page} embedded MP3 is missing: {target}"
                    ) from exc
                audio_targets[page] = target
                audio_file = (
                    paths["audio_timeline"].parent / row["audio_file"]
                ).resolve()
                if not audio_file.is_file():
                    raise FileNotFoundError(audio_file)
                replacements[target] = audio_file.read_bytes()
                slide_name = f"ppt/slides/slide{page}.xml"
                replacements[slide_name] = update_slide_timing(
                    source.read(slide_name),
                    int(row["advance_ms"]),
                )

            with zipfile.ZipFile(
                temporary,
                "w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=6,
            ) as target_archive:
                for info in source.infolist():
                    payload = replacements.get(info.filename)
                    if payload is None:
                        payload = source.read(info.filename)
                    elif payload != source.read(info.filename):
                        changed_members.append(info.filename)
                    target_archive.writestr(info, payload)
            with zipfile.ZipFile(temporary) as check:
                bad_member = check.testzip()
                if bad_member is not None:
                    raise ValueError(f"Corrupt PPTX member after replacement: {bad_member}")
        os.replace(temporary, output_pptx)
    finally:
        if temporary.exists():
            temporary.unlink()

    report = {
        "schema_version": 1,
        "input_pptx": str(input_pptx),
        "output_pptx": str(output_pptx),
        "output_sha256": file_hash(output_pptx),
        "slides": len(rows),
        "audio_targets": {
            str(page): target for page, target in sorted(audio_targets.items())
        },
        "changed_members": sorted(changed_members),
        "allowed_change_only": set(changed_members).issubset(
            {
                *audio_targets.values(),
                *(
                    f"ppt/slides/slide{page}.xml"
                    for page in audio_targets
                ),
            }
        ),
    }
    if not report["allowed_change_only"]:
        raise ValueError("PPTX replacement changed members outside audio and timing")
    report_path = project / "video" / "replace_audio_report.json"
    write_object(report_path, report)
    state = load_state(paths["build_state"])
    state["artifacts"]["narrated_pptx"] = {
        "sha256": report["output_sha256"],
        "visual_baseline": visual_baseline,
        "audio_timeline_sha256": file_hash(paths["audio_timeline"]),
    }
    state["artifacts"].pop("video", None)
    state["powerpoint"]["opened"] = None
    state["powerpoint"]["video_exported"] = None
    state["powerpoint"]["human_watch"] = None
    write_object(paths["build_state"], state)
    return report


def replace_command(args: argparse.Namespace) -> int:
    project = args.project.expanduser().resolve()
    config = load_project_config(project)
    if config["deliverable"] not in {"narrated_pptx", "video"}:
        raise RuntimeError(
            "Audio replacement is allowed only for narrated_pptx or video projects"
        )
    require_approvals(project, ("content", "visual", "narration"))
    paths = project_paths(project)
    input_pptx = (
        args.input_pptx.expanduser().resolve()
        if args.input_pptx
        else paths["animated_pptx"]
    )
    output_pptx = (
        args.output_pptx.expanduser().resolve()
        if args.output_pptx
        else paths["narrated_pptx"]
    )
    if input_pptx != paths["animated_pptx"].resolve():
        raise ValueError(
            "--input-pptx must be the configured animated PPTX baseline"
        )
    if output_pptx != paths["narrated_pptx"].resolve():
        raise ValueError(
            "--output-pptx must be the configured narrated PPTX output"
        )
    report = replace_audio(
        project,
        input_pptx=input_pptx,
        output_pptx=output_pptx,
    )
    print(
        f"OK  {output_pptx}: replaced {report['slides']} narration files; "
        f"changed {len(report['changed_members'])} package members"
    )
    return 0


def run_adapter(adapter: str, project: Path) -> None:
    command = shlex.split(adapter)
    if not command:
        raise ValueError("Assembly adapter command is empty")
    command.extend(["--project", str(project)])
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"Assembly adapter failed with exit code {result.returncode}"
        )


def assemble_command(args: argparse.Namespace) -> int:
    project = args.project.expanduser().resolve()
    config = load_project_config(project)
    paths = project_paths(project)
    deliverable = config["deliverable"]
    required_approvals = ("content", "visual")
    if deliverable in {"narrated_pptx", "video"}:
        required_approvals += ("narration",)
    require_approvals(project, required_approvals)
    production = config.get("production")
    configured_adapter = (
        production.get("assemble_command")
        if isinstance(production, dict)
        else None
    )
    adapter = args.adapter or configured_adapter
    if adapter:
        run_adapter(adapter, project)
    expected_visual = (
        paths["static_pptx"]
        if deliverable == "static_pptx"
        else paths["animated_pptx"]
    )
    if not expected_visual.is_file():
        raise RuntimeError(
            "Initial visual PPTX assembly requires --adapter or "
            "project.production.assemble_command, and the adapter must create "
            f"{expected_visual}."
        )
    baseline_key = (
        "static_pptx" if deliverable == "static_pptx" else "animated_pptx"
    )
    baseline_uses_timing = deliverable != "static_pptx"
    if adapter:
        record_visual_baseline(
            project,
            expected_visual,
            artifact_key=baseline_key,
            include_timing=baseline_uses_timing,
        )
    else:
        require_current_visual_baseline(
            project,
            expected_visual,
            artifact_key=baseline_key,
            include_timing=baseline_uses_timing,
        )
    if deliverable in {"narrated_pptx", "video"}:
        report = replace_audio(
            project,
            input_pptx=paths["animated_pptx"],
            output_pptx=paths["narrated_pptx"],
        )
        print(
            f"OK  assembled {paths['narrated_pptx']}: "
            f"{report['slides']} slides updated"
        )
        return 0

    state = load_state(paths["build_state"])
    artifact_key = (
        "static_pptx"
        if deliverable == "static_pptx"
        else "animated_pptx"
    )
    state["artifacts"][artifact_key] = current_visual_provenance(
        project,
        expected_visual,
        include_timing=artifact_key == "animated_pptx",
    )
    state["artifacts"].pop("narrated_pptx", None)
    state["artifacts"].pop("video", None)
    state["powerpoint"]["opened"] = None
    state["powerpoint"]["video_exported"] = None
    state["powerpoint"]["human_watch"] = None
    write_object(paths["build_state"], state)
    print(f"OK  assembled {expected_visual}: deliverable={deliverable}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    replace = subparsers.add_parser("replace-audio")
    replace.add_argument("--project", type=Path, required=True)
    replace.add_argument("--input-pptx", type=Path)
    replace.add_argument("--output-pptx", type=Path)
    replace.set_defaults(func=replace_command)

    assemble = subparsers.add_parser("assemble-pptx")
    assemble.add_argument("--project", type=Path, required=True)
    assemble.add_argument(
        "--adapter",
        help="Initial visual assembler command; receives --project",
    )
    assemble.set_defaults(func=assemble_command)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        FileNotFoundError,
        OSError,
        ValueError,
        RuntimeError,
        zipfile.BadZipFile,
    ) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        raise SystemExit(1)
