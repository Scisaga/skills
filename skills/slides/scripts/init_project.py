#!/usr/bin/env python3
"""Create a narrated-presentation project from the bundled generic template."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any, Sequence

from validate_input_document import PROFILES, gate_document, render_markdown
from page_script_contract import audit_page_script


SKILL_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_ROOT = SKILL_ROOT / "assets" / "project-template"
TEXT_SUFFIXES = {".json", ".md", ".svg", ".txt"}


def safe_filename(value: str) -> str:
    cleaned = re.sub(r"[\x00-\x1f]", "_", value)
    cleaned = re.sub(r'[<>:"/\\|?*]+', "_", cleaned).strip(" ._")
    return cleaned or "presentation"


def copy_template(
    output: Path,
    *,
    project_name: str,
    deliverable: str,
    source_document: Path,
    page_script_source: Path,
    template_source: Path | None,
    visual_style: str,
    visual_theme: str,
    force: bool,
    source_metadata: dict[str, Any],
    review_source: Path | None,
    gate_report: dict[str, Any] | None,
    page_script_audit: dict[str, Any],
    rewrite_authorized: bool = False,
) -> None:
    if not TEMPLATE_ROOT.is_dir():
        raise FileNotFoundError(f"Template not found: {TEMPLATE_ROOT}")
    if template_source is not None:
        if not template_source.is_file():
            raise FileNotFoundError(template_source)
        if template_source.suffix.lower() != ".pptx":
            raise ValueError("--template-source must be a .pptx file")
        if not zipfile.is_zipfile(template_source):
            raise ValueError(
                f"--template-source is not a valid PPTX package: {template_source}"
            )
    if output.exists() and not output.is_dir():
        raise NotADirectoryError(output)
    if output.exists() and any(output.iterdir()) and not force:
        raise FileExistsError(
            f"{output} is not empty; use --force to overwrite template files"
        )
    output.mkdir(parents=True, exist_ok=True)

    project_file_stem = safe_filename(project_name)
    deck_file = f"{project_file_stem}_动画.pptx"
    replacements = {
        "{{PROJECT_NAME}}": json.dumps(
            project_name,
            ensure_ascii=False,
        )[1:-1],
        "{{PROJECT_FILE_STEM}}": project_file_stem,
        "{{DECK_FILE}}": json.dumps(
            deck_file,
            ensure_ascii=False,
        )[1:-1],
    }
    for source in TEMPLATE_ROOT.rglob("*"):
        relative = source.relative_to(TEMPLATE_ROOT)
        if deliverable == "narration_audio" and (
            relative.parts[0] == "assets"
            or relative == Path("video/svg_layer_plan.json")
        ):
            continue
        target = output / relative
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not force:
            raise FileExistsError(target)
        if source.suffix.lower() in TEXT_SUFFIXES:
            text = source.read_text(encoding="utf-8")
            for token, replacement in replacements.items():
                text = text.replace(token, replacement)
            target.write_text(text, encoding="utf-8")
        else:
            shutil.copy2(source, target)

    inputs_dir = output / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    preserved_source = inputs_dir / "source.md"
    shutil.copy2(source_document, preserved_source)
    shutil.copy2(page_script_source, output / "page-script.md")
    binding_mode = (
        "identity"
        if source_metadata.get("profile") == "page-narration"
        and isinstance(page_script_audit.get("fidelity"), dict)
        and page_script_audit["fidelity"].get("exact_byte_copy")
        else "adapted"
    )
    recorded_binding = json.loads(json.dumps(page_script_audit))
    recorded_binding["page_script"] = "page-script.md"
    recorded_binding["page_script_origin_document"] = str(page_script_source)
    recorded_binding["source_document"] = "inputs/source.md"
    recorded_binding["source_document_sha256"] = source_metadata[
        "document_sha256"
    ]
    recorded_binding["source_profile"] = source_metadata["profile"]
    recorded_binding["binding_mode"] = binding_mode
    recorded_binding["rewrite_authorized"] = bool(
        rewrite_authorized
        and source_metadata.get("profile") == "page-narration"
        and binding_mode == "adapted"
    )
    recorded_binding["rewrite_authorized_page_script_sha256"] = (
        page_script_audit["page_script_sha256"]
        if recorded_binding["rewrite_authorized"]
        else None
    )
    if isinstance(recorded_binding.get("fidelity"), dict):
        recorded_binding["fidelity"]["source"] = "inputs/source.md"
    (inputs_dir / "page-script-binding.json").write_text(
        json.dumps(recorded_binding, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    template_metadata: dict[str, Any] = {
        "mode": "generated",
        "source": None,
        "working": "template.pptx",
        "safe_area": {
            "x": 120,
            "y": 150,
            "width": 1360,
            "height": 620,
        },
    }
    if template_source is not None:
        preserved = inputs_dir / "template-source.pptx"
        working = output / "template.pptx"
        shutil.copy2(template_source, preserved)
        shutil.copy2(template_source, working)
        template_metadata.update(
            {
                "mode": "provided",
                "source": "inputs/template-source.pptx",
            }
        )

    if review_source is not None:
        review_target = output / "input-review.json"
        if review_target.exists() and not force:
            raise FileExistsError(review_target)
        shutil.copy2(review_source, review_target)
    if gate_report is not None:
        recorded_gate = dict(gate_report)
        recorded_gate["document"] = "inputs/source.md"
        recorded_gate["review"] = (
            "input-review.json" if review_source is not None else None
        )
        (output / "input-gate.json").write_text(
            json.dumps(recorded_gate, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (output / "input-gate.md").write_text(
            render_markdown(recorded_gate),
            encoding="utf-8",
        )

    if deliverable != "narration_audio":
        source_svg = output / "assets" / "00_cover.svg"
        layer_plan = output / "video" / "svg_layer_plan.json"
        digest = hashlib.sha256(source_svg.read_bytes()).hexdigest()
        text = layer_plan.read_text(encoding="utf-8")
        layer_plan.write_text(
            text.replace("{{SOURCE_SHA256}}", digest),
            encoding="utf-8",
        )
    project_path = output / "project.json"
    project = json.loads(project_path.read_text(encoding="utf-8"))
    project["deliverable"] = deliverable
    recorded_source = dict(source_metadata)
    recorded_source["origin_document"] = str(source_document)
    recorded_source["document"] = "inputs/source.md"
    recorded_source["page_script_sha256_at_init"] = page_script_audit[
        "page_script_sha256"
    ]
    gate_path = output / "input-gate.json"
    recorded_source["gate_report_sha256"] = (
        hashlib.sha256(gate_path.read_bytes()).hexdigest()
        if gate_path.is_file()
        else None
    )
    review_path = output / "input-review.json"
    recorded_source["review_sha256"] = (
        hashlib.sha256(review_path.read_bytes()).hexdigest()
        if review_path.is_file()
        else None
    )
    project["source"] = recorded_source
    project["content"] = {
        "page_script": "page-script.md",
        "binding_mode": binding_mode,
        "binding_audit": "inputs/page-script-binding.json",
        "page_script_origin_document": str(page_script_source),
        "page_count_at_init": page_script_audit["page_count"],
    }
    project["template"] = template_metadata
    project["visual"] = {
        "style_preset": visual_style,
        "theme": visual_theme,
        "density": "presentation",
    }
    project_path.write_text(
        json.dumps(project, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    directories = [
        "video/audio",
        "video/scripts",
        "inputs",
        "deliverables",
    ]
    if deliverable != "narration_audio":
        directories.append("video/layers")
    for relative in directories:
        (output / relative).mkdir(parents=True, exist_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument(
        "--deliverable",
        choices=(
            "narration_audio",
            "static_pptx",
            "animated_pptx",
            "narrated_pptx",
            "video",
        ),
        required=True,
        help="Highest deliverable level this project is allowed to produce",
    )
    parser.add_argument(
        "--input-document",
        type=Path,
        required=True,
        help="Markdown source that must pass the complete input quality gate",
    )
    parser.add_argument(
        "--input-review",
        type=Path,
        help="SHA-bound semantic review JSON; optional for page-narration inputs",
    )
    parser.add_argument(
        "--page-script-source",
        type=Path,
        help=(
            "Explicit prepared page script. Required for plan inputs; "
            "page-narration inputs default to an identity copy."
        ),
    )
    parser.add_argument(
        "--allow-substantial-rewrite",
        action="store_true",
        help="Authorize a non-identity adaptation of a page-narration source",
    )
    parser.add_argument(
        "--input-profile",
        choices=PROFILES,
        default="auto",
    )
    parser.add_argument(
        "--template-source",
        type=Path,
        help="Optional user PPTX copied into inputs/ and adapted as template.pptx",
    )
    parser.add_argument(
        "--visual-style",
        choices=("project-default", "technical-infographic"),
        default="project-default",
        help="Visual preset recorded in project.json",
    )
    parser.add_argument(
        "--visual-theme",
        choices=("light", "dark"),
        default="light",
        help="Preferred theme for the selected visual preset",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite template-owned files without deleting other files",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    output = args.output.expanduser().resolve()
    gate = gate_document(
        args.input_document,
        args.input_profile,
        args.input_review,
    )
    if not gate["passed"]:
        print("BLOCKED input document did not pass the quality gate")
        for row in gate["findings"]:
            if row["severity"] == "blocking":
                location = f" [{row['location']}]" if row["location"] else ""
                print(
                    f"ERROR {row['code']}{location}: {row['message']} "
                    f"返工要求：{row['required_change']}"
                )
        return 1
    if args.allow_substantial_rewrite and gate["profile"] != "page-narration":
        parser.error(
            "--allow-substantial-rewrite applies only when adapting an already "
            "prepared page-narration source"
        )
    source_document = args.input_document.expanduser().resolve()
    if args.page_script_source is not None:
        page_script_source = args.page_script_source.expanduser().resolve()
    elif gate["profile"] == "page-narration":
        page_script_source = source_document
    else:
        parser.error(
            "--page-script-source is required for narrative-plan, "
            "execution-plan, and presentation-source inputs"
        )
    if not page_script_source.is_file():
        raise FileNotFoundError(page_script_source)
    page_script_audit = audit_page_script(
        page_script_source,
        source=source_document,
        allow_substantial_rewrite=args.allow_substantial_rewrite,
        enforce_source_fidelity=gate["profile"] == "page-narration",
    )
    if page_script_audit["status"] != "pass":
        print("BLOCKED prepared page script did not pass its contract")
        for message in page_script_audit["errors"]:
            print(f"ERROR {message}")
        return 1
    effective_review = gate.get("review")
    source = {
        "mode": "document",
        "document": gate["document"],
        "document_sha256": gate["document_sha256"],
        "profile": gate["profile"],
        "review": "input-review.json" if effective_review else None,
        "gate_report": "input-gate.json",
    }
    review_source = Path(effective_review) if effective_review else None
    template_source = (
        args.template_source.expanduser().resolve()
        if args.template_source
        else None
    )
    gate_report = gate
    copy_template(
        output,
        project_name=args.name,
        deliverable=args.deliverable,
        source_document=source_document,
        page_script_source=page_script_source,
        template_source=template_source,
        visual_style=args.visual_style,
        visual_theme=args.visual_theme,
        force=args.force,
        source_metadata=source,
        review_source=review_source,
        gate_report=gate_report,
        page_script_audit=page_script_audit,
        rewrite_authorized=args.allow_substantial_rewrite,
    )
    print(f"OK  {output}: narrated-presentation project initialized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
