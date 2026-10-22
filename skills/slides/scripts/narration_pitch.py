#!/usr/bin/env python3
"""Shared stable-speaker pitch contract for narration production."""

from __future__ import annotations

import re
from typing import Any


PITCH_MIN_ST = -0.1
PITCH_MAX_ST = 0.1
PITCH_EPSILON = 1e-6
PITCH_RE = re.compile(r"^[+-]\d+(?:\.\d+)?st$")
PITCH_CONTRACT = "stable-speaker-v1"


def parse_pitch(value: object, *, field: str) -> float:
    if not isinstance(value, str) or not PITCH_RE.fullmatch(value):
        raise ValueError(f"{field} must use the +0st form")
    return float(value[:-2])


def format_pitch(value: float) -> str:
    if abs(value) <= PITCH_EPSILON:
        return "+0st"
    rendered = f"{value:+.6f}".rstrip("0").rstrip(".")
    return rendered + "st"


def pitch_in_default_range(value: float) -> bool:
    return (
        value >= PITCH_MIN_ST - PITCH_EPSILON
        and value <= PITCH_MAX_ST + PITCH_EPSILON
    )


def validate_pitch_component(value: object, *, field: str) -> str:
    parsed = parse_pitch(value, field=field)
    if not pitch_in_default_range(parsed):
        raise ValueError(
            f"{field} must be within {format_pitch(PITCH_MIN_ST)} to "
            f"{format_pitch(PITCH_MAX_ST)}"
        )
    return str(value)


def combine_pitch(global_pitch: str, local_pitch: str | None) -> str:
    global_value = parse_pitch(global_pitch, field="Global narration pitch")
    local_display = local_pitch if local_pitch is not None else "+0st"
    local_value = parse_pitch(local_display, field="Local narration pitch")
    final_value = global_value + local_value
    final_display = format_pitch(final_value)
    if final_value < PITCH_MIN_ST - PITCH_EPSILON:
        raise ValueError(
            "Combined narration pitch is below "
            f"{format_pitch(PITCH_MIN_ST)}: {global_pitch} + "
            f"{local_display} = {final_display}"
        )
    if final_value > PITCH_MAX_ST + PITCH_EPSILON:
        raise ValueError(
            "Combined narration pitch is above "
            f"{format_pitch(PITCH_MAX_ST)}: {global_pitch} + "
            f"{local_display} = {final_display}"
        )
    return final_display


def narration_pitch_audit(
    pages: list[dict[str, Any]],
    voice_profile: dict[str, Any],
) -> dict[str, Any]:
    global_pitch = voice_profile["pitch"]
    global_value = parse_pitch(global_pitch, field="Global narration pitch")
    rows: list[dict[str, Any]] = []
    out_of_range: list[dict[str, Any]] = []
    final_values: list[float] = []
    for page in pages:
        for index, segment in enumerate(page["segments"], 1):
            local_pitch = segment.get("pitch", "+0st")
            local_value = parse_pitch(
                local_pitch,
                field=f"Page {page['page']} segment {index} local pitch",
            )
            final_value = global_value + local_value
            final_values.append(final_value)
            row = {
                "page": page["page"],
                "segment": index,
                "global_pitch": global_pitch,
                "local_pitch": local_pitch,
                "final_pitch": format_pitch(final_value),
                "within_range": pitch_in_default_range(final_value),
            }
            rows.append(row)
            if not row["within_range"]:
                out_of_range.append(dict(row))
    minimum = min(final_values) if final_values else 0.0
    maximum = max(final_values) if final_values else 0.0
    return {
        "schema_version": 1,
        "contract": PITCH_CONTRACT,
        "allowed_min_pitch": format_pitch(PITCH_MIN_ST),
        "allowed_max_pitch": format_pitch(PITCH_MAX_ST),
        "min_final_pitch": format_pitch(minimum),
        "max_final_pitch": format_pitch(maximum),
        "status": "pass" if not out_of_range else "blocked",
        "segments": rows,
        "out_of_range": out_of_range,
    }


def require_narration_pitch(
    pages: list[dict[str, Any]],
    voice_profile: dict[str, Any],
) -> dict[str, Any]:
    audit = narration_pitch_audit(pages, voice_profile)
    if audit["out_of_range"]:
        details = "; ".join(
            f"page {row['page']} segment {row['segment']}: "
            f"{row['global_pitch']} + {row['local_pitch']} = "
            f"{row['final_pitch']}"
            for row in audit["out_of_range"]
        )
        raise ValueError(
            "Combined narration pitch must stay within "
            f"{audit['allowed_min_pitch']} to {audit['allowed_max_pitch']}; "
            + details
        )
    return audit
