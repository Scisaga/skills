#!/usr/bin/env python3
"""Generate a compact entrance timeline independent from narration sentences."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence


SUPPORTED_EFFECTS = {
    "fade",
    "wipe_left",
    "wipe_right",
    "wipe_up",
    "wipe_down",
}


def build_timing(
    manifest: dict[str, Any],
    *,
    duration_ms: int,
    first_content_start_ms: int,
    start_step_ms: int,
    animation_window_ms: int,
    advance_safety_ms: int,
) -> dict[str, Any]:
    raw_slides = manifest.get("slides")
    if not isinstance(raw_slides, list) or not raw_slides:
        raise ValueError("Manifest must contain slides[]")

    slides: list[dict[str, Any]] = []
    for fallback_page, slide in enumerate(raw_slides, 1):
        if not isinstance(slide, dict):
            raise ValueError(f"slides[{fallback_page - 1}] must be an object")
        page = slide.get("page", fallback_page)
        beats = slide.get("beats")
        if not isinstance(beats, list) or not beats:
            raise ValueError(f"Page {page} must contain beats[]")
        if len(beats) > 6:
            raise ValueError(f"Page {page} has more than six animation groups")

        timed_beats: list[dict[str, Any]] = []
        for index, beat in enumerate(beats):
            if not isinstance(beat, dict):
                raise ValueError(f"Page {page} beat {index} must be an object")
            name = beat.get("id")
            effect = beat.get("effect")
            if not isinstance(name, str) or not name:
                raise ValueError(f"Page {page} beat {index} is missing id")
            if effect not in SUPPORTED_EFFECTS:
                raise ValueError(f"Page {page} {name} has unsupported effect {effect}")
            start_ms = (
                0
                if index == 0
                else first_content_start_ms + (index - 1) * start_step_ms
            )
            timed_beats.append(
                {
                    "id": name,
                    "effect": effect,
                    "start_ms": start_ms,
                    "duration_ms": duration_ms,
                }
            )

        final_end_ms = max(
            beat["start_ms"] + beat["duration_ms"] for beat in timed_beats
        )
        if not 500 <= final_end_ms <= animation_window_ms:
            raise ValueError(
                f"Page {page} animation ends at {final_end_ms}ms; "
                f"expected 500-{animation_window_ms}ms"
            )
        slides.append(
            {
                "page": page,
                "audio_start_ms": 0,
                "animation_window_ms": animation_window_ms,
                "animation_end_ms": final_end_ms,
                "advance_safety_ms": advance_safety_ms,
                "beats": timed_beats,
            }
        )

    return {
        "schema_version": 1,
        "strategy": "fast-parallel-entrance",
        "defaults": {
            "audio_start_ms": 0,
            "duration_ms": duration_ms,
            "first_content_start_ms": first_content_start_ms,
            "start_step_ms": start_step_ms,
            "animation_window_ms": animation_window_ms,
            "advance_safety_ms": advance_safety_ms,
        },
        "slides": slides,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--duration-ms", type=int, default=280)
    parser.add_argument("--first-content-start-ms", type=int, default=120)
    parser.add_argument("--start-step-ms", type=int, default=130)
    parser.add_argument("--animation-window-ms", type=int, default=1000)
    parser.add_argument("--advance-safety-ms", type=int, default=150)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check that the existing output matches generated timing",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    timing = build_timing(
        manifest,
        duration_ms=args.duration_ms,
        first_content_start_ms=args.first_content_start_ms,
        start_step_ms=args.start_step_ms,
        animation_window_ms=args.animation_window_ms,
        advance_safety_ms=args.advance_safety_ms,
    )
    rendered = json.dumps(timing, ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if not args.output.is_file():
            raise FileNotFoundError(args.output)
        if args.output.read_text(encoding="utf-8") != rendered:
            raise ValueError(f"{args.output} does not match the manifest")
        print(f"OK  {args.output}: timing matches")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(f"OK  {args.output}: {len(timing['slides'])} slides")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
