#!/usr/bin/env python3
"""Incrementally rebuild only the affected narrated-presentation chain."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from production_common import (
    current_input_fingerprints,
    file_hash,
    load_project_config,
    project_paths,
)
from pptx_production import require_current_visual_baseline


SCRIPT_DIR = Path(__file__).resolve().parent


def run_script(name: str, arguments: list[str]) -> None:
    command = [sys.executable, str(SCRIPT_DIR / name), *arguments]
    print("RUN " + " ".join(command[1:]), flush=True)
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"{name} failed with exit code {result.returncode}"
        )


def rebuild_audio(args: argparse.Namespace) -> int:
    project = args.project.expanduser().resolve()
    config = load_project_config(project)
    deliverable = config["deliverable"]
    if deliverable not in {"narration_audio", "narrated_pptx", "video"}:
        raise RuntimeError(
            "Audio rebuild requires narration_audio, narrated_pptx, or video"
        )
    paths = project_paths(project)
    if (args.voice or args.rate or args.pitch) and args.pages:
        raise ValueError(
            "Global voice, rate, or pitch changes affect every chapter; "
            "omit --pages"
        )
    if args.voice or args.rate or args.pitch:
        before_voice = file_hash(paths["voice_profile"])
        configure_args = ["configure-voice", "--project", str(project)]
        if args.voice:
            configure_args.extend(["--voice", args.voice])
        if args.rate:
            configure_args.extend(["--rate", args.rate])
        if args.pitch:
            configure_args.extend(["--pitch", args.pitch])
        if args.dry_run:
            configure_args.append("--dry-run")
        run_script("audio_production.py", configure_args)
        if file_hash(paths["voice_profile"]) == before_voice:
            print("INFO voice profile unchanged; no production audio was requested")
        else:
            print(
                "INFO voice changed; approve narration before rebuilding; "
                "audition is recommended"
            )
        return 0

    if deliverable == "narration_audio" and args.qa != "audio":
        raise RuntimeError("narration_audio stops at --qa audio")
    if deliverable != "narration_audio" and not args.dry_run:
        require_current_visual_baseline(project, paths["animated_pptx"])

    before = (
        current_input_fingerprints(project)
        if deliverable != "narration_audio"
        else None
    )

    synth_args = [
        "synthesize",
        "--project",
        str(project),
    ]
    if args.pages:
        synth_args.extend(["--pages", args.pages])
    if args.force:
        synth_args.append("--force")
    if args.dry_run:
        synth_args.append("--dry-run")
    run_script("audio_production.py", synth_args)
    if args.dry_run:
        if deliverable == "narration_audio":
            print("PLAN audio timeline → audio QA → stop at per-page MP3")
        else:
            print(
                "PLAN audio timeline → audio QA → PPTX media/timing replacement "
                "→ standard QA → optional PowerPoint video export"
            )
        return 0

    run_script(
        "build_audio_timeline.py",
        [
            "--manifest",
            str(paths["manifest"]),
            "--audio-dir",
            str(paths["audio_dir"]),
            "--output",
            str(paths["audio_timeline"]),
        ],
    )
    run_script(
        "qa_presentation.py",
        [
            "--project",
            str(project),
            "--level",
            "audio",
            *(["--force"] if args.force else []),
        ],
    )
    if deliverable == "narration_audio":
        print("OK  rebuild scope=audio qa=audio; stopping at per-page MP3")
        return 0
    run_script(
        "pptx_production.py",
        ["replace-audio", "--project", str(project)],
    )
    if args.qa == "standard":
        run_script(
            "qa_presentation.py",
            [
                "--project",
                str(project),
                "--level",
                "standard",
                *(["--force"] if args.force else []),
            ],
        )
    if args.qa == "audio":
        assert before is not None
        after_audio = current_input_fingerprints(project)
        if (
            after_audio["source"] != before["source"]
            or after_audio["visual"] != before["visual"]
        ):
            raise RuntimeError("Source or visual inputs changed during audio rebuild")
        print(
            "OK  audio QA passed and narrated PPTX was rebuilt; "
            "stopping before video export because standard QA was not requested"
        )
        return 0
    if deliverable == "video" and not args.skip_export:
        run_script(
            "powerpoint_production.py",
            ["export-video", "--project", str(project)],
        )
    elif deliverable == "video":
        print("WARN PowerPoint video export was explicitly skipped")
    else:
        print("INFO deliverable=narrated_pptx; stopping before video export")
    if deliverable == "video" and not args.skip_export:
        print(
            "INFO video exported; stopping without post-export inspection"
        )

    assert before is not None
    after = current_input_fingerprints(project)
    if after["source"] != before["source"] or after["visual"] != before["visual"]:
        raise RuntimeError("Source or visual inputs changed during audio rebuild")
    print(
        f"OK  rebuild scope=audio qa={args.qa}; "
        f"video_exported={deliverable == 'video' and not args.skip_export}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--scope", choices=("audio",), required=True)
    parser.add_argument(
        "--qa",
        choices=("audio", "standard"),
        default="standard",
    )
    parser.add_argument("--voice")
    parser.add_argument("--rate")
    parser.add_argument("--pitch")
    parser.add_argument("--pages")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-export", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.scope == "audio":
        return rebuild_audio(args)
    raise ValueError(f"Unsupported scope: {args.scope}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        FileNotFoundError,
        OSError,
        ValueError,
        RuntimeError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        raise SystemExit(1)
