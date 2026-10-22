#!/usr/bin/env python3
"""Derive and audit executable narration-performance cues."""

from __future__ import annotations

import re
from typing import Any

from contract_versions import NARRATION_PERFORMANCE_CONTRACT_VERSION
from narration_pitch import format_pitch, pitch_in_default_range


PERFORMANCE_CONTRACT = (
    f"rhetorical-v{NARRATION_PERFORMANCE_CONTRACT_VERSION}"
)
INTENTS = {
    "opening",
    "context",
    "explanation",
    "comparison",
    "evidence",
    "case-study",
    "catalog",
    "conclusion",
    "closing",
}

_INTENT_LABELS = {
    "opening": "正式开场",
    "context": "背景铺陈",
    "explanation": "机制解释",
    "comparison": "客观对比",
    "evidence": "证据陈述",
    "case-study": "案例叙事",
    "catalog": "分类巡览",
    "conclusion": "判断收束",
    "closing": "结束致意",
}

_PROFILES = {
    "opening": {
        "rate": -2,
        "pitch": 0.0,
        "pause": 180,
        "direction": "温暖克制地正式开场；首段稍慢建立注意，中段清楚展开结构，末段收稳并引向主题。",
        "rationale": "开场需要先建立信任，再交代路线；因此首尾降速，并用较长段间停顿稳定说话人身份。",
    },
    "context": {
        "rate": -1,
        "pitch": 0.0,
        "pause": 170,
        "direction": "平稳铺陈背景；因果与转折前留出短停，最后落在本页为何重要以及下一步问题。",
        "rationale": "背景页的信息价值来自因果关系；保持中性语气，并用停顿区分条件、矛盾和结论。",
    },
    "explanation": {
        "rate": -1,
        "pitch": 0.0,
        "pause": 150,
        "direction": "采用教学式讲解；定义和关键因果稍慢，过程说明保持连贯，结论句降低重心。",
        "rationale": "机制页需要兼顾可懂与准确；中段略提速保持连贯，首尾放慢以突出定义和结论。",
    },
    "comparison": {
        "rate": -2,
        "pitch": 0.0,
        "pause": 190,
        "direction": "保持客观克制；对比项使用对称节奏，转折前短停，不制造高低优劣，结论句加重。",
        "rationale": "比较页容易被听成站队；使用对称语速和停顿，让边界与选择依据成为重心。",
    },
    "evidence": {
        "rate": -4,
        "pitch": 0.0,
        "pause": 200,
        "direction": "以审慎可信的证据语气讲述；数据和口径刻意放慢，限制条件与最终判断进一步收稳。",
        "rationale": "数字、标准和事实边界需要更高可辨识度；降低局部语速并延长停顿，避免机械播报。",
    },
    "case-study": {
        "rate": -2,
        "pitch": 0.0,
        "pause": 180,
        "direction": "采用工程案例叙事；先交代对象，再逐步增强问题张力，难点、结果与启示分开落点。",
        "rationale": "案例页需要形成对象—难点—解决—结果的推进；中段保持流动，关键判断和结尾收慢。",
    },
    "catalog": {
        "rate": 4,
        "pitch": 0.1,
        "pause": 140,
        "direction": "清晰分组而不逐项报表；同类内容适度提速，类别切换留停顿，末段归纳共同价值。",
        "rationale": "分类或清单页容易单调；用轻微提速维持流动，并在类别边界与归纳句处降速。",
    },
    "conclusion": {
        "rate": -4,
        "pitch": -0.1,
        "pause": 220,
        "direction": "降低速度并增强确定性；先收束判断，再给出边界或行动方向，结尾留出思考空间。",
        "rationale": "判断页承担观点落地；整体降速并拉开停顿，只用极轻微音高回落辅助收束。",
    },
    "closing": {
        "rate": -5,
        "pitch": -0.1,
        "pause": 240,
        "direction": "庄重而真诚地结束；回扣主旨，核心判断慢、稳、低，最后完整落地并自然致谢。",
        "rationale": "结束页需要形成价值峰值并明确收尾；逐段减速、拉开停顿，只作极轻微音高回落。",
    },
}

_PLACEHOLDER_DIRECTIONS = {
    "natural",
    "自然清晰保留原稿信息不逐项机械念画面",
}


def _compact(value: str) -> str:
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).lower()


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(pattern.lower() in lowered for pattern in patterns)


def classify_intent(
    *,
    page: int,
    total_pages: int,
    title: str,
    body: str,
) -> str:
    """Choose a conservative rhetorical role from page position and content."""
    combined = f"{title}\n{body}"
    if page == 1:
        return "opening"
    if page == total_pages:
        return "closing"
    if _contains_any(
        title,
        ("总结", "结论", "结束", "前景", "展望", "理性认识", "takeaway", "outlook"),
    ):
        return "conclusion"
    if _contains_any(
        title,
        ("对比", "比较", "边界", "差异", "区别", "异同", " vs ", " versus "),
    ):
        return "comparison"
    if _contains_any(
        title,
        ("案例", "典型产品", "典型应用", "工程应用", "case", "example"),
    ):
        return "case-study"
    numeric_density = len(re.findall(r"\d", combined))
    if numeric_density >= 8 or _contains_any(
        title,
        ("数据", "性能", "成果", "指标", "验证", "evidence", "result", "metric"),
    ):
        return "evidence"
    if _contains_any(
        title,
        ("分类", "产品", "材料", "能力", "布局", "路线", "catalog", "portfolio"),
    ):
        return "catalog"
    if _contains_any(
        title,
        ("背景", "需求", "产业", "为什么", "context", "background", "problem"),
    ):
        return "context"
    return "explanation"


def _format_rate(value: int) -> str:
    return f"{max(-15, min(10, value)):+d}%"


def _format_pitch(value: float) -> str:
    if not pitch_in_default_range(value):
        raise ValueError("Default narration pitch must stay within ±0.1st")
    return format_pitch(value)


def derive_page_performance(
    *,
    page: int,
    total_pages: int,
    title: str,
    body: str,
    paragraphs: list[str],
) -> dict[str, Any]:
    """Compile a page role into reviewable and executable prosody cues."""
    intent = classify_intent(
        page=page,
        total_pages=total_pages,
        title=title,
        body=body,
    )
    profile = _PROFILES[intent]
    base_rate = int(profile["rate"])
    base_pitch = float(profile["pitch"])
    base_pause = int(profile["pause"])
    segment_count = len(paragraphs)
    segments: list[dict[str, Any]] = []
    for index, paragraph in enumerate(paragraphs):
        if segment_count == 1:
            rate = base_rate - 2
        elif index == 0:
            rate = base_rate - 1
        elif index == segment_count - 1:
            rate = base_rate - 2
        else:
            rate = base_rate + (1 if index % 2 else 0)
        pause = 0
        if index < segment_count - 1:
            pause = min(
                300,
                base_pause + (20 if index in {0, segment_count - 2} else 0),
            )
        segments.append(
            {
                "text": paragraph,
                "rate": _format_rate(rate),
                "pitch": _format_pitch(base_pitch),
                "pause_after_ms": pause,
            }
        )
    role = re.sub(r"\s*·\s*\d+\s*秒(?:钟)?\s*$", "", title).strip()
    return {
        "intent": intent,
        "direction": f"围绕“{role}”：{profile['direction']}",
        "rationale": f"{_INTENT_LABELS[intent]}。{profile['rationale']}",
        "segments": segments,
    }


def _rate_value(value: object) -> int | None:
    if not isinstance(value, str) or not re.fullmatch(r"[+-]\d+%", value):
        return None
    return int(value[:-1])


def _rate_bucket(value: object) -> str:
    parsed = _rate_value(value)
    if parsed is None:
        return "invalid"
    if parsed <= -6:
        return "very-slow"
    if parsed <= -4:
        return "slow"
    if parsed >= 7:
        return "very-fast"
    if parsed >= 4:
        return "fast"
    return "neutral"


def _pause_bucket(value: object, *, final: bool) -> str:
    if final:
        return "end"
    if isinstance(value, bool) or not isinstance(value, int):
        return "invalid"
    if value <= 80:
        return "short"
    if value >= 140:
        return "long"
    return "neutral"


def audit_narration_performance(director: dict[str, Any]) -> dict[str, Any]:
    """Reject placeholder direction that never changes rendered SSML."""
    errors: list[str] = []
    warnings: list[str] = []
    policy = director.get("policy")
    if not isinstance(policy, dict) or policy.get(
        "performance_contract"
    ) != PERFORMANCE_CONTRACT:
        errors.append(
            "director.policy.performance_contract must be "
            f"{PERFORMANCE_CONTRACT}; rerun prepare-narration"
        )
    raw_pages = director.get("pages")
    if not isinstance(raw_pages, list) or not raw_pages:
        errors.append("director.pages must be a non-empty array")
        raw_pages = []

    directions: list[str] = []
    rationales: list[str] = []
    intents: list[str] = []
    signatures: list[tuple[tuple[str, str], ...]] = []
    cue_pages: list[int] = []
    page_evidence: list[dict[str, Any]] = []
    all_rates: set[str] = set()
    all_pitches: set[str] = set()
    all_pauses: set[int] = set()

    for fallback_page, raw_page in enumerate(raw_pages, 1):
        if not isinstance(raw_page, dict):
            errors.append(f"Director page {fallback_page} must be an object")
            continue
        page = raw_page.get("page", fallback_page)
        intent = raw_page.get("intent")
        direction = raw_page.get("direction")
        rationale = raw_page.get("rationale")
        if intent not in INTENTS:
            errors.append(f"Director page {page} has invalid intent {intent!r}")
        else:
            intents.append(intent)
        if not isinstance(direction, str) or len(direction.strip()) < 12:
            errors.append(f"Director page {page} needs a specific direction")
        else:
            compact_direction = _compact(direction)
            if compact_direction in _PLACEHOLDER_DIRECTIONS or any(
                placeholder in compact_direction
                for placeholder in _PLACEHOLDER_DIRECTIONS
                if len(placeholder) > 8
            ):
                errors.append(
                    f"Director page {page} still uses a placeholder direction"
                )
            directions.append(compact_direction)
        if not isinstance(rationale, str) or len(rationale.strip()) < 12:
            errors.append(
                f"Director page {page} needs a performance rationale"
            )
        else:
            rationales.append(_compact(rationale))

        raw_segments = raw_page.get("segments")
        if not isinstance(raw_segments, list) or not raw_segments:
            errors.append(f"Director page {page} has no performance segments")
            continue
        signature_rows: set[tuple[str, str]] = set()
        has_executable_cue = False
        for index, segment in enumerate(raw_segments):
            if not isinstance(segment, dict):
                continue
            rate = segment.get("rate", "+0%")
            pitch = segment.get("pitch", "+0st")
            pause = segment.get("pause_after_ms", 0)
            if isinstance(rate, str):
                all_rates.add(rate)
            if isinstance(pitch, str):
                all_pitches.add(pitch)
            if isinstance(pause, int) and not isinstance(pause, bool):
                all_pauses.add(pause)
            final = index == len(raw_segments) - 1
            signature_rows.add(
                (
                    _rate_bucket(rate),
                    _pause_bucket(pause, final=final),
                )
            )
            rate_value = _rate_value(rate)
            pause_is_cue = bool(
                not final
                and isinstance(pause, int)
                and not isinstance(pause, bool)
                and (pause <= 80 or pause >= 140)
            )
            if (
                isinstance(rate_value, int)
                and abs(rate_value) >= 2
                or pause_is_cue
            ):
                has_executable_cue = True
        if has_executable_cue:
            cue_pages.append(int(page))
        signature = tuple(sorted(signature_rows))
        signatures.append(signature)
        page_evidence.append(
            {
                "page": page,
                "intent": intent,
                "executable_cue": has_executable_cue,
                "performance_signature": [list(row) for row in signature],
            }
        )

    page_count = len(raw_pages)
    if page_count >= 4:
        if len(set(directions)) < 2:
            errors.append("All pages use the same narration direction")
        if len(set(intents)) < 2:
            errors.append("All pages use the same rhetorical intent")
        if len(set(signatures)) < 2:
            errors.append("All pages compile to the same prosody pattern")
        if len(set(rationales)) < 2:
            errors.append("All pages use the same performance rationale")
        required_profiles = 3 if page_count >= 8 else 2
        if len(set(signatures)) < required_profiles:
            errors.append(
                "Narration needs at least "
                f"{required_profiles} materially different audible profiles; "
                f"got {len(set(signatures))}"
            )
        required_cue_pages = max(2, (page_count + 4) // 5)
        if len(cue_pages) < required_cue_pages:
            errors.append(
                "Executable prosody cues must materially change at least "
                f"{required_cue_pages} pages; got {len(cue_pages)}"
            )
    if page_count and len(cue_pages) != page_count:
        warnings.append(
            f"Executable prosody cues cover {len(cue_pages)}/{page_count} pages"
        )

    return {
        "schema_version": 1,
        "contract_version": PERFORMANCE_CONTRACT,
        "status": "pass" if not errors else "blocked",
        "metrics": {
            "page_count": page_count,
            "pages_with_executable_cues": len(cue_pages),
            "unique_directions": len(set(directions)),
            "unique_rationales": len(set(rationales)),
            "unique_intents": len(set(intents)),
            "unique_performance_signatures": len(set(signatures)),
            "rate_values": sorted(all_rates),
            "pitch_values": sorted(all_pitches),
            "pause_values_ms": sorted(all_pauses),
        },
        "pages": page_evidence,
        "errors": errors,
        "warnings": warnings,
    }
