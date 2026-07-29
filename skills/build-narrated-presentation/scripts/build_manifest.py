#!/usr/bin/env python3
"""Merge a visual animation manifest with the single-source narration director."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any, Sequence

from production_common import (
    canonical_hash,
    chapter_groups,
    load_voice_profile,
    normalize_director_pages,
)



def load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} root must be an object")
    return payload


def validate_director(
    director: dict[str, Any],
    expected_pages: list[int],
) -> dict[int, dict[str, Any]]:
    return {
        row["page"]: row
        for row in normalize_director_pages(director, expected_pages)
    }


def build_manifest(
    visual: dict[str, Any],
    director: dict[str, Any],
    voice_profile: dict[str, Any],
) -> dict[str, Any]:
    slides = visual.get("slides")
    if not isinstance(slides, list) or not slides:
        raise ValueError("Visual manifest must contain slides[]")
    expected_pages = [int(slide["page"]) for slide in slides]
    if expected_pages != list(range(1, len(expected_pages) + 1)):
        raise ValueError("Visual manifest pages must be contiguous from 1")
    rows = validate_director(director, expected_pages)
    result = copy.deepcopy(visual)
    result["schema_version"] = 3
    result["voice"] = {
        "provider": voice_profile["provider"],
        "name": voice_profile["voice"],
        "style": voice_profile["style"],
        "rate": voice_profile["rate"],
        "pitch": voice_profile["pitch"],
        "profile_sha256": canonical_hash(voice_profile),
    }
    result["narration_policy"] = copy.deepcopy(director["policy"])
    result["narration_policy"]["continuous_chapter_synthesis"] = True
    for slide in result["slides"]:
        page = int(slide["page"])
        narration = copy.deepcopy(rows[page])
        narration.pop("page", None)
        narration["text"] = "".join(
            segment["text"] for segment in narration["segments"]
        )
        slide["narration"] = narration
    normalized_pages = [rows[page] for page in expected_pages]
    result["narration_chapters"] = [
        {
            "id": chapter["id"],
            "pages": [page["page"] for page in chapter["pages"]],
        }
        for chapter in chapter_groups(normalized_pages)
    ]
    result["slide_count"] = len(result["slides"])
    return result


def render_review(manifest: dict[str, Any]) -> str:
    lines = [
        "# 旁白导演稿审阅版",
        "",
        "> 由动画 manifest 生成；旁白与视觉动画独立。",
        "",
    ]
    for slide in manifest["slides"]:
        narration = slide["narration"]
        lines.extend(
            [
                f"## 第 {slide['page']} 页",
                "",
                f"**连续合成章节：** `{narration['chapter']}`",
                "",
                f"**讲述目的：** {narration['role']}",
                "",
                f"**语气：** {narration['direction']}",
                "",
                narration["text"],
                "",
                "**语速与停顿：** "
                + " → ".join(
                    f"{segment['rate']} / {segment['pause_after_ms']}ms"
                    for segment in narration["segments"]
                ),
                "",
            ]
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--visual", type=Path, required=True)
    parser.add_argument("--director", type=Path, required=True)
    parser.add_argument(
        "--voice-profile",
        type=Path,
        help="Defaults to voice_profile.json next to --director",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    visual = load_object(args.visual)
    director = load_object(args.director)
    profile_path = args.voice_profile or args.director.with_name(
        "voice_profile.json"
    )
    voice_profile = load_voice_profile(profile_path)
    manifest = build_manifest(visual, director, voice_profile)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.review.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.review.write_text(render_review(manifest), encoding="utf-8")
    print(f"OK  {args.output}: {len(manifest['slides'])} slides")
    print(f"OK  {args.review}: narration review")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
