#!/usr/bin/env python3
"""Refresh input-gate evidence without rebuilding unchanged presentation material."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Sequence

from production_common import (
    approval_status,
    content_acceptance_fingerprint,
    file_hash,
    load_project_config,
    project_paths,
    resolve_path,
    write_object,
)
from validate_input_document import (
    PROFILES,
    gate_document,
    inspect_document,
    render_markdown,
)


def refresh(
    project: Path,
    review_source: Path | None = None,
    input_profile: str = "auto",
) -> int:
    project = project.expanduser().resolve()
    config = load_project_config(project)
    paths = project_paths(project, config)
    source = config["source"]
    document_value = source.get("document")
    if not isinstance(document_value, str) or not document_value:
        raise ValueError("project.json source.document is required")
    document = resolve_path(project, document_value)
    if not document.is_file():
        raise FileNotFoundError(document)
    if file_hash(document) != source.get("document_sha256"):
        raise RuntimeError(
            "inputs/source.md changed; gate refresh is only allowed for the "
            "same bound source bytes"
        )
    recorded_profile = source.get("profile")
    if not isinstance(recorded_profile, str) or not recorded_profile:
        raise ValueError("project.json source.profile is required")
    try:
        before_acceptance = content_acceptance_fingerprint(project, config)
    except (OSError, ValueError):
        before_acceptance = None

    preflight = inspect_document(document, input_profile)
    profile = preflight["profile"]

    semantic_required = profile != "page-narration"
    review: Path | None = None
    if semantic_required:
        if review_source is not None:
            review = review_source.expanduser().resolve()
        else:
            configured_review = source.get("review")
            if isinstance(configured_review, str) and configured_review:
                review = resolve_path(project, configured_review)
        if review is None or not review.is_file():
            raise RuntimeError(
                "This source profile requires a current --input-review; run "
                "prepare-input-review for inputs/source.md first"
            )
    review_for_gate = review
    if not semantic_required and review_source is not None:
        review_for_gate = review_source.expanduser().resolve()
    report = gate_document(document, profile, review_for_gate)
    if not report["passed"]:
        blockers = [
            row for row in report["findings"] if row["severity"] == "blocking"
        ]
        print("BLOCKED refreshed input gate did not pass")
        for row in blockers:
            print(f"ERROR {row['code']}: {row['message']}")
        return 1

    target_review = project / "input-review.json"
    if review is not None:
        if review != target_review.resolve():
            shutil.copy2(review, target_review)
        recorded_review: str | None = "input-review.json"
    else:
        recorded_review = None

    recorded_report = dict(report)
    recorded_report["document"] = "inputs/source.md"
    recorded_report["review"] = recorded_review
    gate_path = project / "input-gate.json"
    write_object(gate_path, recorded_report)
    (project / "input-gate.md").write_text(
        render_markdown(recorded_report),
        encoding="utf-8",
    )

    source["gate_report"] = "input-gate.json"
    source["gate_report_sha256"] = file_hash(gate_path)
    source["review"] = recorded_review
    source["review_sha256"] = (
        file_hash(target_review) if recorded_review is not None else None
    )
    source["profile"] = report["profile"]
    write_object(paths["project"], config)
    refreshed_config = load_project_config(project)
    try:
        after_acceptance = content_acceptance_fingerprint(
            project,
            refreshed_config,
        )
    except (OSError, ValueError):
        after_acceptance = None
    try:
        content_current, content_message = approval_status(project, "content")
    except (OSError, ValueError) as exc:
        content_current = False
        content_message = f"content approval status cannot be read: {exc}"
    evidence_changed = (
        before_acceptance is None
        or after_acceptance is None
        or before_acceptance != after_acceptance
    )
    if content_current:
        approval_message = "content approval remains current"
    else:
        approval_message = content_message
    profile_message = (
        f"; profile corrected {recorded_profile} -> {report['profile']}"
        if recorded_profile != report["profile"]
        else ""
    )
    action = "input gate refreshed" if evidence_changed else "input gate unchanged"
    print(
        f"OK  {action}"
        f"; evidence_changed={str(evidence_changed).lower()}"
        f"; {approval_message}{profile_message}; unchanged visual and "
        "narration material remains reusable"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--input-review", type=Path)
    parser.add_argument(
        "--input-profile",
        choices=PROFILES,
        default="auto",
        help="Re-detect by default; override only when source identity is explicit",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return refresh(args.project, args.input_review, args.input_profile)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        raise SystemExit(1)
