#!/usr/bin/env python3
"""Build a narration manifest, optionally merged with a visual manifest."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any, Sequence

from narration_pitch import require_narration_pitch
from production_common import (
    canonical_hash,
    chapter_groups,
    combine_pitch,
    combine_rate,
    load_voice_profile,
    normalize_director_pages,
    pronunciation_audit,
    voice_synthesis_projection,
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
    visual: dict[str, Any] | None,
    director: dict[str, Any],
    voice_profile: dict[str, Any],
) -> dict[str, Any]:
    slides = visual.get("slides") if isinstance(visual, dict) else None
    if isinstance(slides, list) and slides:
        expected_pages = [int(slide["page"]) for slide in slides]
        if expected_pages != list(range(1, len(expected_pages) + 1)):
            raise ValueError("Visual manifest pages must be contiguous from 1")
    else:
        expected_pages = [
            row["page"] for row in normalize_director_pages(director)
        ]
    rows = validate_director(director, expected_pages)
    normalized_pages = [rows[page] for page in expected_pages]
    pitch_audit = require_narration_pitch(normalized_pages, voice_profile)
    result = copy.deepcopy(visual) if isinstance(visual, dict) else {}
    if not isinstance(result.get("slides"), list) or not result["slides"]:
        result["slides"] = [{"page": page} for page in expected_pages]
    result["schema_version"] = 3
    result["voice"] = {
        "provider": voice_profile["provider"],
        "name": voice_profile["voice"],
        "style": voice_profile["style"],
        "rate": voice_profile["rate"],
        "pitch": voice_profile["pitch"],
        "profile_sha256": canonical_hash(
            voice_synthesis_projection(voice_profile)
        ),
    }
    result["narration_policy"] = copy.deepcopy(director["policy"])
    result["narration_policy"]["continuous_chapter_synthesis"] = True
    result["narration_pitch"] = pitch_audit
    for slide in result["slides"]:
        page = int(slide["page"])
        narration = copy.deepcopy(rows[page])
        narration.pop("page", None)
        narration["text"] = "".join(
            segment["text"] for segment in narration["segments"]
        )
        if narration.get("target_seconds") is not None:
            slide["target_seconds"] = narration["target_seconds"]
        slide["narration"] = narration
    result["pronunciation_review"] = pronunciation_audit(
        normalized_pages,
        voice_profile["pronunciations"],
    )
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
    voice = manifest["voice"]
    slides = manifest["slides"]
    pitch_audit = manifest["narration_pitch"]
    intents = sorted(
        {
            slide["narration"]["intent"]
            for slide in slides
            if isinstance(slide.get("narration"), dict)
        }
    )
    local_rates = sorted(
        {
            segment["rate"]
            for slide in slides
            for segment in slide["narration"]["segments"]
        }
    )
    local_pitches = sorted(
        {
            segment.get("pitch", "+0st")
            for slide in slides
            for segment in slide["narration"]["segments"]
        }
    )
    lines = [
        "# 旁白导演稿审阅版",
        "",
        "> 由旁白导演稿生成；语气说明必须编译为下表中的实际 SSML 参数。",
        "",
        "## 声音与编排摘要",
        "",
        f"- 音色：`{voice['name']}`",
        f"- 全局 style：`{voice['style'] or 'none'}`",
        f"- 全局语速 / 音高：`{voice['rate']}` / `{voice['pitch']}`",
        f"- 最终音高范围：`{pitch_audit['min_final_pitch']}` 至 "
        f"`{pitch_audit['max_final_pitch']}`（允许 "
        f"`{pitch_audit['allowed_min_pitch']}` 至 "
        f"`{pitch_audit['allowed_max_pitch']}`）",
        f"- 音高契约：`{pitch_audit['contract']}`",
        f"- 表现契约：`{manifest['narration_policy'].get('performance_contract')}`",
        f"- 页面 / 表达意图：{len(slides)} 页 / {', '.join(intents)}",
        f"- 局部语速：{', '.join(local_rates)}",
        f"- 局部音高：{', '.join(local_pitches)}",
        "",
    ]
    pronunciation_review = manifest.get("pronunciation_review", {})
    configured = pronunciation_review.get("configured", [])
    uncovered = pronunciation_review.get("uncovered", [])
    lines.extend(
        [
            "## 专业术语发音审阅",
            "",
            "> 技术代号只做候选发现，不根据字形自动猜读。材料成分牌号、字母前缀牌号和普通缩写必须结合专业语境分别确认；未覆盖项是审阅警告，不是输入门禁。",
            "",
        ]
    )
    if configured:
        lines.extend(
            [
                "### 已配置并命中正文",
                "",
                "| 原词 | 出现页 | 规则 | TTS 实际读法 |",
                "|---|---|---|---|",
            ]
        )
        for row in configured:
            term = str(row["term"]).replace("|", "\\|")
            spoken_as = str(row["spoken_as"]).replace("|", "\\|")
            pages_text = ", ".join(str(page) for page in row["pages"])
            lines.append(
                f"| `{term}` | {pages_text} | `{row['rule_type']}` | {spoken_as} |"
            )
        lines.append("")
    if uncovered:
        lines.extend(
            [
                "### 待确认的技术代号（非阻断）",
                "",
                "| 原词 | 出现页 | 状态 |",
                "|---|---|---|",
            ]
        )
        for row in uncovered:
            term = str(row["term"]).replace("|", "\\|")
            pages_text = ", ".join(str(page) for page in row["pages"])
            lines.append(f"| `{term}` | {pages_text} | 未配置读法 |")
        lines.append("")
    if not configured and not uncovered:
        lines.extend(["正文未发现需要单独审阅的拉丁技术代号。", ""])
    for slide in slides:
        narration = slide["narration"]
        target_seconds = narration.get("target_seconds")
        target_display = (
            f"{target_seconds} 秒" if target_seconds is not None else "未指定"
        )
        lines.extend(
            [
                f"## 第 {slide['page']} 页",
                "",
                f"**连续合成章节：** `{narration['chapter']}`",
                "",
                f"**讲述目的：** {narration['role']}",
                "",
                f"**表达意图：** `{narration['intent']}`",
                "",
                f"**语气编排：** {narration['direction']}",
                "",
                f"**编排依据与修正：** {narration['rationale']}",
                "",
                f"**目标时长：** {target_display}",
                "",
                "| 段 | 局部语速 | 全局音高 | 局部音高 | 最终语速 | 最终音高 | 段后停顿 | 正文 |",
                "|---:|---:|---:|---:|---:|---:|---:|---|",
            ]
        )
        for index, segment in enumerate(narration["segments"], 1):
            local_pitch = segment.get("pitch", "+0st")
            effective_rate = combine_rate(voice["rate"], segment["rate"])
            effective_pitch = combine_pitch(voice["pitch"], local_pitch)
            segment_text = segment["text"].replace("|", "\\|")
            lines.append(
                f"| {index} | `{segment['rate']}` | `{voice['pitch']}` | "
                f"`{local_pitch}` | `{effective_rate}` | `{effective_pitch}` | "
                f"{segment['pause_after_ms']}ms | {segment_text} |"
            )
        lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--visual", type=Path)
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
    visual = load_object(args.visual) if args.visual else None
    director = load_object(args.director)
    profile_path = args.voice_profile or args.director.with_name(
        "voice_profile.json"
    )
    voice_profile = load_voice_profile(profile_path)
    manifest = build_manifest(visual, director, voice_profile)
    review = render_review(manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.review.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.review.write_text(review, encoding="utf-8")
    print(f"OK  {args.output}: {len(manifest['slides'])} slides")
    print(f"OK  {args.review}: narration review")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
