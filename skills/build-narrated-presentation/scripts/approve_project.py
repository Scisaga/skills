#!/usr/bin/env python3
"""Record SHA-bound content, visual, or narration approval."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from build_manifest import build_manifest, render_review
from production_common import (
    file_hash,
    load_object,
    load_project_config,
    load_voice_profile,
    parse_page_list,
    project_paths,
    record_approval,
    require_approvals,
)


def verify_source(project: Path) -> None:
    config = load_project_config(project)
    source = config["source"]
    if source.get("mode") != "document":
        raise ValueError("project.json source.mode must be document")
    document_value = source.get("document")
    if not isinstance(document_value, str) or not document_value:
        raise ValueError("project.json source.document is required")
    document = Path(document_value)
    if not document.is_absolute():
        document = project / document
    if not document.is_file():
        raise FileNotFoundError(document)
    if source.get("document_sha256") != file_hash(document):
        raise RuntimeError(
            "Input document changed after its quality gate; review it again "
            "before approving content"
        )
    gate_value = source.get("gate_report")
    if not isinstance(gate_value, str) or not gate_value:
        raise ValueError("project.json source.gate_report is required")
    gate_path = Path(gate_value)
    if not gate_path.is_absolute():
        gate_path = project / gate_path
    gate = load_object(gate_path)
    if (
        gate.get("passed") is not True
        or gate.get("document_sha256") != source["document_sha256"]
    ):
        raise RuntimeError("The recorded input quality gate is not current")


def verify_narration_review(project: Path) -> None:
    paths = project_paths(project)
    visual = load_object(paths["manifest"])
    director = load_object(paths["director"])
    voice = load_voice_profile(paths["voice_profile"])
    expected_manifest = build_manifest(visual, director, voice)
    if visual != expected_manifest:
        raise RuntimeError(
            "Narration fields in animation_manifest.json are stale; "
            "run manifest before approving narration"
        )
    review_path = project / "video" / "narration_review.md"
    if not review_path.is_file():
        raise FileNotFoundError(review_path)
    if review_path.read_text(encoding="utf-8") != render_review(
        expected_manifest
    ):
        raise RuntimeError(
            "narration_review.md is stale; run manifest before approval"
        )


def approve_command(args: argparse.Namespace) -> int:
    project = args.project.expanduser().resolve()
    verify_source(project)
    pages = parse_page_list(args.pages)
    if args.stage == "content":
        if pages:
            raise ValueError("--pages is only valid with --stage visual")
    elif args.stage == "visual":
        require_approvals(project, ("content",))
        if not pages:
            raise ValueError("--stage visual requires representative --pages")
    else:
        if pages:
            raise ValueError("--pages is only valid with --stage visual")
        require_approvals(project, ("content", "visual"))
        verify_narration_review(project)
    record = record_approval(
        project,
        args.stage,
        approved_by=args.approved_by,
        pages=pages,
    )
    print(
        f"OK  approved stage={args.stage} "
        f"fingerprint={record['fingerprint']} "
        f"by={record['approved_by']}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument(
        "--stage",
        choices=("content", "visual", "narration"),
        required=True,
    )
    parser.add_argument("--approved-by", required=True)
    parser.add_argument(
        "--pages",
        help="Representative pages for visual approval, for example 3,7,10",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    return approve_command(build_parser().parse_args(argv))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        raise SystemExit(1)
