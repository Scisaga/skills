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
    page_script_source: Path,
    template_source: Path | None,
    visual_style: str,
    visual_theme: str,
    force: bool,
    source_metadata: dict[str, Any],
    review_source: Path | None,
    gate_report: dict[str, Any] | None,
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

    shutil.copy2(page_script_source, output / "page-script.md")

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
        inputs_dir = output / "inputs"
        inputs_dir.mkdir(parents=True, exist_ok=True)
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
        recorded_gate["review"] = "input-review.json"
        (output / "input-gate.json").write_text(
            json.dumps(recorded_gate, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (output / "input-gate.md").write_text(
            render_markdown(recorded_gate),
            encoding="utf-8",
        )

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
    project["source"] = source_metadata
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
    for relative in (
        "video/layers",
        "video/audio",
        "video/scripts",
        "inputs",
        "deliverables",
    ):
        (output / relative).mkdir(parents=True, exist_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument(
        "--deliverable",
        choices=(
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
        required=True,
        help="SHA-bound semantic review JSON for --input-document",
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
    source = {
        "mode": "document",
        "document": gate["document"],
        "document_sha256": gate["document_sha256"],
        "profile": gate["profile"],
        "review": "input-review.json",
        "gate_report": "input-gate.json",
        "quality_gate": "passed",
    }
    review_source = args.input_review.expanduser().resolve()
    page_script_source = args.input_document.expanduser().resolve()
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
        page_script_source=page_script_source,
        template_source=template_source,
        visual_style=args.visual_style,
        visual_theme=args.visual_theme,
        force=args.force,
        source_metadata=source,
        review_source=review_source,
        gate_report=gate_report,
    )
    print(f"OK  {output}: narrated-presentation project initialized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
