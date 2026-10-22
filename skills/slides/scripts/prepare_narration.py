#!/usr/bin/env python3
"""Create a complete narration director from a prepared page script."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Sequence

from build_manifest import build_manifest, render_review
from page_script_contract import (
    audit_page_script,
    narration_paragraphs,
    parse_page_script,
)
from narration_performance import (
    PERFORMANCE_CONTRACT,
    derive_page_performance,
)
from production_common import (
    load_object,
    load_project_config,
    load_voice_profile,
    project_paths,
    require_approvals,
    write_object,
)


def prepare(
    project: Path,
    *,
    force: bool,
    chapter_max_seconds: int = 240,
    performance_plan: Path | None = None,
) -> int:
    project = project.expanduser().resolve()
    config = load_project_config(project)
    if config["deliverable"] not in {
        "narration_audio",
        "narrated_pptx",
        "video",
    }:
        raise RuntimeError(
            "prepare-narration requires narration_audio, narrated_pptx, or video"
        )
    require_approvals(project, ("content",))
    paths = project_paths(project, config)
    audit = audit_page_script(paths["page_script"])
    if audit["status"] != "pass":
        raise RuntimeError("Page script contract: " + "; ".join(audit["errors"]))
    existing = load_object(paths["director"])
    if existing.get("pages") and not force:
        raise RuntimeError(
            "narration_director.json already contains pages; use --force only "
            "after confirming it may be regenerated"
        )
    if not 30 <= chapter_max_seconds <= 600:
        raise ValueError("--chapter-max-seconds must be 30-600")
    source_pages = parse_page_script(paths["page_script"])
    plan_by_page: dict[int, dict[str, object]] = {}
    if performance_plan is not None:
        plan_path = performance_plan.expanduser().resolve()
        plan = load_object(plan_path)
        if plan.get("schema_version") != 1:
            raise ValueError("Performance plan schema_version must be 1")
        raw_plan_pages = plan.get("pages")
        if not isinstance(raw_plan_pages, list):
            raise ValueError("Performance plan pages must be an array")
        for raw_plan_page in raw_plan_pages:
            if not isinstance(raw_plan_page, dict):
                raise ValueError("Performance plan pages must be objects")
            page = raw_plan_page.get("page")
            if isinstance(page, bool) or not isinstance(page, int) or page <= 0:
                raise ValueError(f"Invalid performance plan page {page!r}")
            if page in plan_by_page:
                raise ValueError(f"Duplicate performance plan page {page}")
            if "text" in raw_plan_page:
                raise ValueError(
                    f"Performance plan page {page} must not contain narration text"
                )
            plan_by_page[page] = raw_plan_page
        expected_plan_pages = [row["page"] for row in source_pages]
        if sorted(plan_by_page) != expected_plan_pages:
            raise ValueError(
                "Performance plan pages must exactly match page-script pages: "
                f"expected={expected_plan_pages}, got={sorted(plan_by_page)}"
            )
    director_pages = []
    chapter_index = 1
    chapter_seconds = 0
    for row in source_pages:
        paragraphs = narration_paragraphs(row["body"])
        estimated_seconds = row["target_seconds"] or max(
            20, (row["body_characters"] + 3) // 4
        )
        if chapter_seconds and (
            chapter_seconds + estimated_seconds > chapter_max_seconds
        ):
            chapter_index += 1
            chapter_seconds = 0
        chapter = f"chapter-{chapter_index:02d}"
        chapter_seconds += estimated_seconds
        performance = derive_page_performance(
            page=row["page"],
            total_pages=len(source_pages),
            title=row["title"],
            body=row["body"],
            paragraphs=paragraphs,
        )
        override = plan_by_page.get(row["page"])
        if override is not None:
            unknown_page_keys = set(override) - {
                "page",
                "intent",
                "direction",
                "rationale",
                "segments",
            }
            if unknown_page_keys:
                raise ValueError(
                    f"Performance plan page {row['page']} has unsupported keys "
                    f"{sorted(unknown_page_keys)}"
                )
            for key in ("intent", "direction", "rationale"):
                if key in override:
                    performance[key] = override[key]
            raw_cues = override.get("segments")
            if not isinstance(raw_cues, list) or len(raw_cues) != len(paragraphs):
                raise ValueError(
                    f"Performance plan page {row['page']} must contain "
                    f"{len(paragraphs)} segment cue objects"
                )
            for index, cue in enumerate(raw_cues):
                if not isinstance(cue, dict):
                    raise ValueError(
                        f"Performance plan page {row['page']} segment "
                        f"{index + 1} must be an object"
                    )
                if "text" in cue:
                    raise ValueError(
                        f"Performance plan page {row['page']} segment "
                        f"{index + 1} must not contain text"
                    )
                unknown = set(cue) - {"rate", "pitch", "pause_after_ms"}
                if unknown:
                    raise ValueError(
                        f"Performance plan page {row['page']} segment "
                        f"{index + 1} has unsupported keys {sorted(unknown)}"
                    )
                performance["segments"][index].update(cue)
        director_pages.append(
            {
                "page": row["page"],
                "chapter": chapter,
                "role": re.sub(r"\s*·\s*\d+\s*秒(?:钟)?\s*$", "", row["title"]),
                "target_seconds": row["target_seconds"],
                **performance,
            }
        )
    director = {
        "schema_version": 2,
        "policy": {
            "visual_sync": "independent",
            "audio_start_ms": 0,
            "paragraph_per_slide": 1,
            "animation_window_ms": 1000,
            "chapter_max_seconds": chapter_max_seconds,
            "performance_contract": PERFORMANCE_CONTRACT,
        },
        "pages": director_pages,
    }
    voice = load_voice_profile(paths["voice_profile"])
    visual = (
        None
        if config["deliverable"] == "narration_audio"
        else load_object(paths["manifest"])
    )
    manifest = build_manifest(visual, director, voice)
    write_object(paths["director"], director)
    write_object(paths["manifest"], manifest)
    review = project / "video" / "narration_review.md"
    review.write_text(render_review(manifest), encoding="utf-8")
    print(f"OK  prepared narration pages={len(director_pages)}: {paths['director']}")
    if performance_plan is not None:
        print(f"OK  applied performance plan: {performance_plan.expanduser().resolve()}")
    print(f"OK  narration review: {review}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--chapter-max-seconds", type=int, default=240)
    parser.add_argument(
        "--performance-plan",
        type=Path,
        help="Optional text-free per-page rate/pitch/pause override plan",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return prepare(
        args.project,
        force=args.force,
        chapter_max_seconds=args.chapter_max_seconds,
        performance_plan=args.performance_plan,
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        raise SystemExit(1)
