#!/usr/bin/env python3
"""Merge a visual animation manifest with the single-source narration director."""

from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path
from typing import Any, Sequence


RATE_RE = re.compile(r"^[+-]\d+%$")


def load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} root must be an object")
    return payload


def validate_director(
    director: dict[str, Any],
    expected_pages: list[int],
) -> dict[int, dict[str, Any]]:
    policy = director.get("policy")
    if not isinstance(policy, dict) or policy.get("visual_sync") != "independent":
        raise ValueError("director.policy.visual_sync must be independent")
    pages = director.get("pages")
    if not isinstance(pages, list):
        raise ValueError("director.pages must be an array")

    rows: dict[int, dict[str, Any]] = {}
    for row in pages:
        if not isinstance(row, dict):
            raise ValueError("director.pages[] must be objects")
        page = row.get("page")
        if isinstance(page, bool) or not isinstance(page, int) or page <= 0:
            raise ValueError(f"Invalid director page: {page!r}")
        if page in rows:
            raise ValueError(f"Duplicate director page: {page}")
        for field in ("role", "direction"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ValueError(f"Page {page} is missing {field}")
        segments = row.get("segments")
        if not isinstance(segments, list) or not segments:
            raise ValueError(f"Page {page} is missing narration segments")
        for index, segment in enumerate(segments, 1):
            if not isinstance(segment, dict):
                raise ValueError(f"Page {page} segment {index} must be an object")
            if not isinstance(segment.get("text"), str) or not segment["text"].strip():
                raise ValueError(f"Page {page} segment {index} is missing text")
            if not isinstance(segment.get("rate"), str) or not RATE_RE.fullmatch(
                segment["rate"]
            ):
                raise ValueError(f"Page {page} segment {index} has invalid rate")
            pause = segment.get("pause_after_ms")
            if (
                isinstance(pause, bool)
                or not isinstance(pause, int)
                or not 0 <= pause <= 300
            ):
                raise ValueError(f"Page {page} segment {index} has invalid pause")
        rows[page] = row

    if sorted(rows) != expected_pages:
        raise ValueError(
            f"Director pages must be {expected_pages}; got {sorted(rows)}"
        )
    return rows


def build_manifest(
    visual: dict[str, Any],
    director: dict[str, Any],
) -> dict[str, Any]:
    slides = visual.get("slides")
    if not isinstance(slides, list) or not slides:
        raise ValueError("Visual manifest must contain slides[]")
    expected_pages = [int(slide["page"]) for slide in slides]
    if expected_pages != list(range(1, len(expected_pages) + 1)):
        raise ValueError("Visual manifest pages must be contiguous from 1")
    rows = validate_director(director, expected_pages)

    result = copy.deepcopy(visual)
    result["schema_version"] = 2
    result["voice"] = {
        "provider": director["voice"]["provider"],
        "name": director["voice"]["name"],
        "style": director["voice"].get("style"),
        "rate": director["voice"]["default_rate"],
        "pitch": director["voice"]["pitch"],
    }
    result["narration_policy"] = copy.deepcopy(director["policy"])
    for slide in result["slides"]:
        page = int(slide["page"])
        narration = copy.deepcopy(rows[page])
        narration.pop("page", None)
        narration["text"] = "".join(
            segment["text"] for segment in narration["segments"]
        )
        slide["narration"] = narration
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
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    visual = load_object(args.visual)
    director = load_object(args.director)
    manifest = build_manifest(visual, director)
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
