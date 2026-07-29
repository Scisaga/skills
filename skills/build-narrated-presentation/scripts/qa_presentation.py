#!/usr/bin/env python3
"""Run cached audio, standard, or release QA for a presentation project."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from pptx_production import P_NS, slide_audio_target, timeline_rows
from production_common import (
    canonical_hash,
    chapter_groups,
    current_input_fingerprints,
    file_hash,
    load_object,
    load_project_config,
    load_state,
    load_voice_profile,
    normalize_director_pages,
    project_paths,
    require_approvals,
    source_fingerprint,
    visual_fingerprint,
    write_object,
)
from validate_project import validate as validate_full_project


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def directory_hashes(directory: Path, patterns: tuple[str, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    if not directory.is_dir():
        return result
    for pattern in patterns:
        for path in sorted(directory.glob(pattern)):
            if path.is_file():
                result[str(path.relative_to(directory))] = file_hash(path)
    return result


def cache_fingerprint(
    project: Path,
    level: str,
    state: dict[str, Any],
) -> str:
    paths = project_paths(project)
    config = load_project_config(project)
    manifest = (
        load_object(paths["manifest"])
        if paths["manifest"].is_file()
        else {"slides": []}
    )
    static_payload = {
        "source": source_fingerprint(project, config),
        "visual": visual_fingerprint(
            project,
            config,
            manifest,
            include_timing=False,
        ),
        "template": (
            file_hash(paths["template_working"])
            if paths["template_working"].is_file()
            else None
        ),
        "pptx": (
            file_hash(paths["static_pptx"])
            if paths["static_pptx"].is_file()
            else None
        ),
        "qa_tools": {
            path.name: file_hash(path)
            for path in (
                Path(__file__),
                Path(__file__).with_name("validate_project.py"),
                Path(__file__).with_name("production_common.py"),
            )
        },
    }
    if level == "static":
        return canonical_hash(static_payload)
    audio_payload = {
        "director": file_hash(paths["director"]) if paths["director"].is_file() else None,
        "voice_profile": (
            file_hash(paths["voice_profile"])
            if paths["voice_profile"].is_file()
            else None
        ),
        "manifest": file_hash(paths["manifest"]) if paths["manifest"].is_file() else None,
        "timeline": (
            file_hash(paths["audio_timeline"])
            if paths["audio_timeline"].is_file()
            else None
        ),
        "audio": directory_hashes(
            paths["audio_dir"],
            ("*.mp3", "*.sha256", "*.bookmarks.json"),
        ),
        "scripts": directory_hashes(paths["scripts_dir"], ("*.ssml",)),
        "qa_tools": {
            path.name: file_hash(path)
            for path in (
                Path(__file__),
                Path(__file__).with_name("validate_project.py"),
                Path(__file__).with_name("pptx_production.py"),
                Path(__file__).with_name("production_common.py"),
            )
        },
    }
    if level == "audio":
        return canonical_hash(audio_payload)
    standard_payload = {
        "audio": audio_payload,
        "pptx": (
            file_hash(paths["narrated_pptx"])
            if paths["narrated_pptx"].is_file()
            else None
        ),
    }
    if level == "standard":
        return canonical_hash(standard_payload)
    release_payload = {
        "standard": standard_payload,
        "inputs": current_input_fingerprints(project),
        "video": file_hash(paths["video"]) if paths["video"].is_file() else None,
        "powerpoint": state.get("powerpoint"),
    }
    return canonical_hash(release_payload)


def static_qa(
    project: Path,
    errors: list[str],
    warnings: list[str],
) -> tuple[str, dict[str, Any]]:
    paths = project_paths(project)
    config = load_project_config(project)
    full_errors, full_warnings = validate_full_project(
        project,
        stage="static_pptx",
    )
    errors.extend(full_errors)
    warnings.extend(full_warnings)
    template = paths["template_working"]
    if not template.is_file():
        errors.append(f"Working template not found: {template}")
    elif not zipfile.is_zipfile(template):
        errors.append(f"Working template is not a valid PPTX package: {template}")

    manifest = load_object(paths["manifest"])
    expected_pages = [
        row.get("page")
        for row in manifest.get("slides", [])
        if isinstance(row, dict)
    ]
    pptx = paths["static_pptx"]
    pptx_report: dict[str, Any] | None = None
    if not pptx.is_file():
        errors.append(f"Static PPTX not found: {pptx}")
    else:
        try:
            with zipfile.ZipFile(pptx) as archive:
                bad_member = archive.testzip()
                if bad_member is not None:
                    errors.append(f"PPTX ZIP member is corrupt: {bad_member}")
                slide_names = {
                    name
                    for name in archive.namelist()
                    if name.startswith("ppt/slides/slide")
                    and name.endswith(".xml")
                    and "/_rels/" not in name
                }
                if len(slide_names) != len(expected_pages):
                    errors.append(
                        f"Static PPTX slide count {len(slide_names)} "
                        f"!= manifest pages {len(expected_pages)}"
                    )
                svg_members = [
                    name
                    for name in archive.namelist()
                    if name.startswith("ppt/media/")
                    and name.lower().endswith(".svg")
                ]
                if len(svg_members) < len(expected_pages):
                    errors.append(
                        "Static PPTX does not contain one embedded SVG per page"
                    )
                external_media: list[str] = []
                for name in archive.namelist():
                    if not name.endswith(".rels"):
                        continue
                    root = ET.fromstring(archive.read(name))
                    for relationship in root:
                        rel_type = relationship.get("Type", "")
                        if (
                            relationship.get("TargetMode") == "External"
                            and rel_type.rsplit("/", 1)[-1]
                            in {"audio", "image", "media"}
                        ):
                            external_media.append(
                                f"{name}:{relationship.get('Target')}"
                            )
                if external_media:
                    errors.append(
                        "Static PPTX contains external media relationships: "
                        + ", ".join(external_media)
                    )
                pptx_report = {
                    "file": str(pptx.relative_to(project)),
                    "sha256": file_hash(pptx),
                    "slides": len(slide_names),
                    "embedded_svg": len(svg_members),
                }
        except (ET.ParseError, zipfile.BadZipFile) as exc:
            errors.append(f"Invalid static PPTX package: {exc}")

    fingerprint = canonical_hash(
        {
            "source": source_fingerprint(project, config),
            "visual": visual_fingerprint(
                project,
                config,
                manifest,
                include_timing=False,
            ),
            "template": (
                file_hash(template) if template.is_file() else None
            ),
            "pptx": file_hash(pptx) if pptx.is_file() else None,
            "qa_script": file_hash(Path(__file__)),
        }
    )
    return fingerprint, {
        "project": {
            "errors": full_errors,
            "warnings": full_warnings,
        },
        "template": (
            {
                "file": str(template.relative_to(project)),
                "sha256": file_hash(template),
            }
            if template.is_file()
            else None
        ),
        "pptx": pptx_report,
    }


def audio_qa(
    project: Path,
    errors: list[str],
    warnings: list[str],
) -> tuple[str, dict[str, Any]]:
    paths = project_paths(project)
    director = load_object(paths["director"])
    manifest = load_object(paths["manifest"])
    voice = load_voice_profile(paths["voice_profile"])
    expected_pages = [
        int(row["page"])
        for row in manifest.get("slides", [])
        if isinstance(row, dict)
    ]
    pages = normalize_director_pages(director, expected_pages)
    groups = chapter_groups(pages)
    manifest_voice = manifest.get("voice")
    if (
        not isinstance(manifest_voice, dict)
        or manifest_voice.get("profile_sha256") != canonical_hash(voice)
    ):
        errors.append(
            "Manifest voice is stale; rerun synthesize or manifest merge"
        )
    slide_by_page = {
        int(slide["page"]): slide
        for slide in manifest.get("slides", [])
        if isinstance(slide, dict)
        and isinstance(slide.get("page"), int)
        and not isinstance(slide.get("page"), bool)
    }
    for page in pages:
        merged = slide_by_page.get(page["page"], {}).get("narration")
        expected = {key: page[key] for key in ("chapter", "role", "direction", "segments")}
        if not isinstance(merged, dict) or any(
            merged.get(key) != value for key, value in expected.items()
        ):
            errors.append(
                f"Manifest page {page['page']} narration is stale"
            )
        elif merged.get("text") != "".join(
            segment["text"] for segment in page["segments"]
        ):
            errors.append(
                f"Manifest page {page['page']} narration text is stale"
            )
    timeline = load_object(paths["audio_timeline"])
    rows = timeline_rows(timeline)
    if [row["page"] for row in rows] != expected_pages:
        errors.append("Audio timeline page set differs from the manifest")
    expected_chapters = {
        page["page"]: page["chapter"] for page in pages
    }
    for row in rows:
        if row.get("chapter") != expected_chapters.get(row["page"]):
            errors.append(
                f"Audio timeline page {row['page']} chapter is stale"
            )

    try:
        from mutagen.mp3 import MP3
    except ImportError as exc:
        raise RuntimeError("Missing mutagen; run bootstrap first") from exc

    expected_names = {f"{page:02d}.mp3" for page in expected_pages}
    actual_names = {
        path.name
        for path in paths["audio_dir"].glob("*.mp3")
        if path.stem.isdigit()
    }
    if actual_names != expected_names:
        errors.append(
            f"Audio file set differs: expected={sorted(expected_names)}, "
            f"actual={sorted(actual_names)}"
        )

    page_results: list[dict[str, Any]] = []
    for row in rows:
        page = int(row["page"])
        audio_file = (paths["audio_timeline"].parent / row["audio_file"]).resolve()
        if not audio_file.is_file():
            errors.append(f"Page {page} audio not found: {audio_file}")
            continue
        if audio_file.stat().st_size < 512:
            errors.append(f"Page {page} audio is unexpectedly small")
            continue
        try:
            actual_duration = float(MP3(audio_file).info.length)
        except Exception as exc:
            errors.append(f"Page {page} MP3 cannot be parsed: {exc}")
            continue
        recorded_duration = row.get("audio_duration_seconds")
        if (
            isinstance(recorded_duration, bool)
            or not isinstance(recorded_duration, (int, float))
            or recorded_duration <= 0
        ):
            errors.append(f"Page {page} timeline duration is invalid")
        elif abs(actual_duration - float(recorded_duration)) > 0.05:
            errors.append(f"Page {page} real duration differs from timeline")
        expected_advance = (
            round(actual_duration * 1000)
            + int(timeline.get("advance_safety_ms", 150))
        )
        if abs(int(row["advance_ms"]) - expected_advance) > 50:
            errors.append(f"Page {page} advance time differs from real MP3")
        page_results.append(
            {
                "page": page,
                "file": str(audio_file.relative_to(project)),
                "sha256": file_hash(audio_file),
                "duration_seconds": round(actual_duration, 3),
            }
        )

    chapter_results: list[dict[str, Any]] = []
    for group in groups:
        page_numbers = [page["page"] for page in group["pages"]]
        metadata_path = paths["audio_dir"] / f"{group['id']}.bookmarks.json"
        if len(page_numbers) > 1:
            if not metadata_path.is_file():
                errors.append(
                    f"Chapter {group['id']} spans pages {page_numbers} but has "
                    "no bookmark metadata"
                )
                continue
            metadata = load_object(metadata_path)
            recorded_pages = [
                row.get("page")
                for row in metadata.get("pages", [])
                if isinstance(row, dict)
            ]
            if recorded_pages != page_numbers:
                errors.append(
                    f"Chapter {group['id']} bookmark pages differ: {recorded_pages}"
                )
        chapter_results.append(
            {
                "id": group["id"],
                "pages": page_numbers,
                "bookmark_metadata": (
                    str(metadata_path.relative_to(project))
                    if metadata_path.is_file()
                    else None
                ),
            }
        )

    text = "\n".join(
        segment["text"]
        for page in pages
        for segment in page["segments"]
    )
    applicable_terms = [
        term for term in voice["pronunciations"] if term in text
    ]
    if applicable_terms:
        warnings.append(
            "Pronunciation rules were rendered but human audition remains "
            f"required for: {', '.join(applicable_terms)}"
        )
    else:
        warnings.append(
            "Automatic audio QA passed; human pronunciation audition was not "
            "performed by this command"
        )

    fingerprint = canonical_hash(
        {
            "director": pages,
            "voice": voice,
            "timeline": timeline,
            "audio": {row["file"]: row["sha256"] for row in page_results},
            "qa_script": file_hash(Path(__file__)),
        }
    )
    return fingerprint, {
        "pages": page_results,
        "chapters": chapter_results,
        "pronunciation_terms": applicable_terms,
        "human_pronunciation": "not-confirmed",
    }


def transition_advance(payload: bytes) -> int | None:
    try:
        from lxml import etree
    except ImportError as exc:
        raise RuntimeError("Missing lxml; run bootstrap first") from exc
    root = etree.fromstring(payload)
    transition = root.find(f"{{{P_NS}}}transition")
    if transition is None:
        return None
    value = transition.get("advTm")
    return int(value) if value and value.isdigit() else None


def standard_qa(
    project: Path,
    errors: list[str],
    warnings: list[str],
) -> tuple[str, dict[str, Any]]:
    audio_fingerprint, audio_report = audio_qa(project, errors, warnings)
    paths = project_paths(project)
    pptx = paths["narrated_pptx"]
    if not pptx.is_file():
        errors.append(f"Narrated PPTX not found: {pptx}")
        return canonical_hash({"audio": audio_fingerprint, "pptx": None}), {
            "audio": audio_report,
            "pptx": None,
        }
    timeline = load_object(paths["audio_timeline"])
    rows = timeline_rows(timeline)
    pptx_rows: list[dict[str, Any]] = []
    try:
        with zipfile.ZipFile(pptx) as archive:
            bad_member = archive.testzip()
            if bad_member is not None:
                errors.append(f"PPTX ZIP member is corrupt: {bad_member}")
            slide_names = {
                name
                for name in archive.namelist()
                if name.startswith("ppt/slides/slide")
                and name.endswith(".xml")
                and "/_rels/" not in name
            }
            if len(slide_names) != len(rows):
                errors.append(
                    f"PPTX slide count {len(slide_names)} != audio pages {len(rows)}"
                )
            media_targets: set[str] = set()
            for row in rows:
                page = int(row["page"])
                try:
                    target = slide_audio_target(archive, page)
                except ValueError as exc:
                    errors.append(str(exc))
                    continue
                if target in media_targets:
                    errors.append(f"PPTX media target is shared: {target}")
                media_targets.add(target)
                source_audio = (
                    paths["audio_timeline"].parent / row["audio_file"]
                ).resolve()
                try:
                    embedded = archive.read(target)
                except KeyError:
                    errors.append(f"Embedded audio is missing: {target}")
                    continue
                if source_audio.is_file() and embedded != source_audio.read_bytes():
                    errors.append(
                        f"Slide {page} embedded audio differs from timeline file"
                    )
                slide_name = f"ppt/slides/slide{page}.xml"
                slide_xml = archive.read(slide_name)
                advance = transition_advance(slide_xml)
                if advance != row["advance_ms"]:
                    errors.append(
                        f"Slide {page} PPTX advance {advance} != "
                        f"timeline {row['advance_ms']}"
                    )
                if b"playFrom" not in slide_xml:
                    errors.append(
                        f"Slide {page} has no automatic media playFrom command"
                    )
                pptx_rows.append(
                    {
                        "page": page,
                        "media_target": target,
                        "advance_ms": advance,
                    }
                )
            presentation_xml = archive.read("ppt/presentation.xml")
            for attribute in (b'useTimings="1"', b'showNarration="1"', b'showAnimation="1"'):
                if attribute not in presentation_xml:
                    errors.append(
                        "ppt/presentation.xml is missing "
                        + attribute.decode("ascii")
                    )
    except zipfile.BadZipFile as exc:
        errors.append(f"Invalid PPTX ZIP: {exc}")

    fingerprint = canonical_hash(
        {
            "audio": audio_fingerprint,
            "pptx": file_hash(pptx),
            "qa_script": file_hash(Path(__file__)),
        }
    )
    return fingerprint, {
        "audio": audio_report,
        "pptx": {
            "file": str(pptx.relative_to(project)),
            "sha256": file_hash(pptx),
            "slides": pptx_rows,
        },
    }


def probe_video(video: Path) -> dict[str, Any]:
    report: dict[str, Any] = {
        "file": str(video),
        "sha256": file_hash(video),
        "bytes": video.stat().st_size,
    }
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        report["ffprobe"] = "unavailable"
        return report
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(video),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        payload = json.loads(result.stdout)
        duration = payload.get("format", {}).get("duration")
        if duration is not None:
            report["duration_seconds"] = float(duration)
    return report


def release_qa(
    project: Path,
    state: dict[str, Any],
    errors: list[str],
    warnings: list[str],
) -> tuple[str, dict[str, Any]]:
    standard_fingerprint, standard_report = standard_qa(
        project,
        errors,
        warnings,
    )
    full_errors, full_warnings = validate_full_project(
        project,
        stage="video",
    )
    errors.extend(f"Full project: {message}" for message in full_errors)
    errors.extend(f"Full project warning: {message}" for message in full_warnings)
    paths = project_paths(project)
    video = paths["video"]
    video_report: dict[str, Any] | None = None
    if not video.is_file() or video.stat().st_size <= 0:
        errors.append(f"Exported video not found or empty: {video}")
    else:
        video_report = probe_video(video)
        timeline = load_object(paths["audio_timeline"])
        duration = video_report.get("duration_seconds")
        estimated = timeline.get("estimated_deck_seconds")
        if isinstance(duration, (int, float)) and isinstance(
            estimated,
            (int, float),
        ):
            tolerance = max(2.0, float(estimated) * 0.05)
            if abs(float(duration) - float(estimated)) > tolerance:
                errors.append(
                    f"MP4 duration {duration:.3f}s differs from estimated "
                    f"{estimated:.3f}s"
                )

    powerpoint = state.get("powerpoint", {})
    opened = powerpoint.get("opened") if isinstance(powerpoint, dict) else None
    exported = (
        powerpoint.get("video_exported")
        if isinstance(powerpoint, dict)
        else None
    )
    watched = (
        powerpoint.get("human_watch")
        if isinstance(powerpoint, dict)
        else None
    )
    pptx_sha = (
        file_hash(paths["narrated_pptx"])
        if paths["narrated_pptx"].is_file()
        else None
    )
    video_sha = file_hash(video) if video.is_file() else None
    if not isinstance(opened, dict) or opened.get("pptx_sha256") != pptx_sha:
        errors.append("Current PPTX has no matching PowerPoint-open evidence")
    if not isinstance(exported, dict) or exported.get("video_sha256") != video_sha:
        errors.append("Current MP4 has no matching PowerPoint-export evidence")
    if not isinstance(watched, dict) or watched.get("video_sha256") != video_sha:
        errors.append(
            "Current MP4 has no human full-watch confirmation; rerun release "
            "QA with --human-confirmed only after actually watching it"
        )

    inputs = current_input_fingerprints(project)
    fingerprint = canonical_hash(
        {
            "standard": standard_fingerprint,
            "inputs": inputs,
            "video": video_sha,
            "powerpoint": powerpoint,
            "qa_script": file_hash(Path(__file__)),
        }
    )
    return fingerprint, {
        "standard": standard_report,
        "full_project": {
            "errors": full_errors,
            "warnings": full_warnings,
        },
        "video": video_report,
        "powerpoint": powerpoint,
        "inputs": inputs,
    }


def qa_command(args: argparse.Namespace) -> int:
    project = args.project.expanduser().resolve()
    config = load_project_config(project)
    deliverable = config["deliverable"]
    if args.level in {"audio", "standard"} and deliverable not in {
        "narrated_pptx",
        "video",
    }:
        raise RuntimeError(
            f"qa={args.level} requires narrated_pptx or video deliverable"
        )
    if args.level == "release" and deliverable != "video":
        raise RuntimeError("qa=release requires deliverable=video")
    approval_requirements = {
        "static": ("content", "visual"),
        "audio": ("content", "narration"),
        "standard": ("content", "visual", "narration"),
        "release": ("content", "visual", "narration"),
    }
    require_approvals(project, approval_requirements[args.level])
    paths = project_paths(project)
    state = load_state(paths["build_state"])
    if args.human_confirmed and args.level != "release":
        raise ValueError("--human-confirmed is only valid with --level release")
    if args.confirmed_by and not args.human_confirmed:
        raise ValueError("--confirmed-by requires --human-confirmed")
    if args.human_confirmed:
        video = paths["video"]
        if not video.is_file():
            raise FileNotFoundError(video)
        state["powerpoint"]["human_watch"] = {
            "status": "passed",
            "video_sha256": file_hash(video),
            "confirmed_at": now_iso(),
            "confirmed_by": args.confirmed_by or "user",
            "evidence": "explicit-full-watch-confirmation",
        }
        write_object(paths["build_state"], state)

    fingerprint = cache_fingerprint(project, args.level, state)
    cached = state["qa"].get(args.level)
    if (
        not args.force
        and isinstance(cached, dict)
        and cached.get("status") == "passed"
        and cached.get("fingerprint") == fingerprint
    ):
        print(f"SKIP qa={args.level}: inputs and tools unchanged")
        return 0

    errors: list[str] = []
    warnings: list[str] = []
    if args.level == "static":
        _, report = static_qa(project, errors, warnings)
    elif args.level == "audio":
        _, report = audio_qa(project, errors, warnings)
    elif args.level == "standard":
        _, report = standard_qa(project, errors, warnings)
    else:
        _, report = release_qa(
            project,
            state,
            errors,
            warnings,
        )

    for warning in warnings:
        print(f"WARN {warning}")
    for error in errors:
        print(f"ERROR {error}")
    qa_report = {
        "schema_version": 1,
        "level": args.level,
        "status": "failed" if errors else "passed",
        "fingerprint": fingerprint,
        "checked_at": now_iso(),
        "errors": errors,
        "warnings": warnings,
        "evidence": report,
    }
    report_path = project / "video" / f"qa_{args.level}.json"
    write_object(report_path, qa_report)
    state = load_state(paths["build_state"])
    state["qa"][args.level] = {
        "status": qa_report["status"],
        "fingerprint": fingerprint,
        "checked_at": qa_report["checked_at"],
        "report": str(report_path.relative_to(project)),
    }
    if not errors and args.level == "release":
        state["inputs"] = report["inputs"]
    write_object(paths["build_state"], state)
    if errors:
        return 1
    print(f"OK  qa={args.level}: {report_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument(
        "--level",
        choices=("static", "audio", "standard", "release"),
        required=True,
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--human-confirmed",
        action="store_true",
        help="Assert that a person watched the current MP4 in full",
    )
    parser.add_argument("--confirmed-by")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    return qa_command(build_parser().parse_args(argv))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        FileNotFoundError,
        OSError,
        ValueError,
        RuntimeError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        raise SystemExit(1)
