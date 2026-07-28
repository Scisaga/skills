#!/usr/bin/env python3
"""Build the slide-advance timeline from the real duration of per-slide MP3s."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Sequence

from mutagen.mp3 import MP3


def build_timeline(
    manifest: dict[str, Any],
    *,
    audio_dir: Path,
    output: Path,
) -> dict[str, Any]:
    slides = manifest.get("slides")
    if not isinstance(slides, list) or not slides:
        raise ValueError("Manifest must contain slides[]")
    defaults = manifest.get("animation_defaults", {})
    safety_ms = int(defaults.get("advance_safety_ms", 150))
    transition_ms = int(defaults.get("slide_transition_ms", 250))

    rows: list[dict[str, Any]] = []
    for fallback_page, slide in enumerate(slides, 1):
        if not isinstance(slide, dict):
            raise ValueError(f"slides[{fallback_page - 1}] must be an object")
        page = int(slide.get("page", fallback_page))
        audio_path = audio_dir / f"{page:02d}.mp3"
        if not audio_path.is_file():
            raise FileNotFoundError(audio_path)
        duration = round(float(MP3(audio_path).info.length), 3)
        rows.append(
            {
                "page": page,
                "audio_file": os.path.relpath(
                    audio_path.resolve(),
                    output.resolve().parent,
                ),
                "audio_duration_seconds": duration,
                "advance_ms": round(duration * 1000) + safety_ms,
                "target_seconds": float(slide.get("target_seconds", duration)),
            }
        )

    audio_total = round(
        sum(row["audio_duration_seconds"] for row in rows),
        3,
    )
    estimated_deck = round(
        audio_total
        + len(rows) * safety_ms / 1000
        + max(0, len(rows) - 1) * transition_ms / 1000,
        3,
    )
    return {
        "schema_version": 1,
        "profile": "continuous-independent-narration",
        "advance_safety_ms": safety_ms,
        "slide_transition_ms": transition_ms,
        "audio_total_seconds": audio_total,
        "estimated_deck_seconds": estimated_deck,
        "slides": rows,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--audio-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check that the existing output matches the real MP3 durations",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    timeline = build_timeline(
        manifest,
        audio_dir=args.audio_dir,
        output=args.output,
    )
    rendered = json.dumps(timeline, ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if not args.output.is_file():
            raise FileNotFoundError(args.output)
        if args.output.read_text(encoding="utf-8") != rendered:
            raise ValueError(f"{args.output} does not match the real MP3 durations")
        print(f"OK  {args.output}: audio timeline matches")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(
        f"OK  {args.output}: {len(timeline['slides'])} slides, "
        f"{timeline['estimated_deck_seconds']:.3f}s estimated deck"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
