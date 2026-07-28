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
    load_state,
    project_paths,
    write_object,
)


SCRIPT_DIR = Path(__file__).resolve().parent


def run_script(name: str, arguments: list[str]) -> None:
    command = [sys.executable, str(SCRIPT_DIR / name), *arguments]
    print("RUN " + " ".join(command[1:]), flush=True)
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"{name} failed with exit code {result.returncode}"
        )


def ensure_audio_scope(
    project: Path,
    *,
    allow_unverified_baseline: bool,
    record_unverified_baseline: bool = True,
) -> tuple[dict, dict[str, str]]:
    paths = project_paths(project)
    state = load_state(paths["build_state"])
    current = current_input_fingerprints(project)
    baseline = state.get("inputs")
    if not isinstance(baseline, dict):
        baseline = {}
    required = ("source", "narration", "visual")
    missing = [name for name in required if not baseline.get(name)]
    if missing and not allow_unverified_baseline:
        raise RuntimeError(
            "Audio-only rebuild needs a verified release baseline; missing "
            f"{missing}. Run release QA after a complete build, or explicitly "
            "use --allow-unverified-baseline for an existing trusted project."
        )
    for name in ("source", "visual"):
        recorded = baseline.get(name)
        if recorded and recorded != current[name]:
            raise RuntimeError(
                f"Audio-only rebuild blocked: {name} changed since the "
                "verified baseline"
            )
    narration = baseline.get("narration")
    if narration and narration != current["narration"]:
        raise RuntimeError(
            "Audio-only rebuild blocked: narration text, role, direction, or "
            "chapter mapping changed. Revalidate content consistency before "
            "rebuilding."
        )
    if missing:
        print(
            "WARN proceeding from an explicitly accepted unverified baseline; "
            "this does not count as release QA"
        )
        if record_unverified_baseline:
            state["inputs"].update(
                {
                    "source": current["source"],
                    "narration": current["narration"],
                    "visual": current["visual"],
                }
            )
            write_object(paths["build_state"], state)
    return state, current


def rebuild_audio(args: argparse.Namespace) -> int:
    project = args.project.expanduser().resolve()
    paths = project_paths(project)
    if (args.voice or args.rate or args.pitch) and args.pages:
        raise ValueError(
            "Global voice, rate, or pitch changes affect every chapter; "
            "omit --pages"
        )
    _, before = ensure_audio_scope(
        project,
        allow_unverified_baseline=args.allow_unverified_baseline,
        record_unverified_baseline=not args.dry_run,
    )

    synth_args = [
        "synthesize",
        "--project",
        str(project),
    ]
    if args.voice:
        synth_args.extend(["--voice", args.voice])
    if args.rate:
        synth_args.extend(["--rate", args.rate])
    if args.pitch:
        synth_args.extend(["--pitch", args.pitch])
    if args.pages:
        synth_args.extend(["--pages", args.pages])
    if args.force:
        synth_args.append("--force")
    if args.dry_run:
        synth_args.append("--dry-run")
    run_script("audio_production.py", synth_args)
    if args.dry_run:
        print(
            "PLAN audio timeline → audio QA → PPTX media/timing replacement "
            "→ standard QA → PowerPoint video export"
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
    run_script(
        "pptx_production.py",
        ["replace-audio", "--project", str(project)],
    )
    if args.qa in {"standard", "release"}:
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
    if not args.skip_export:
        run_script(
            "powerpoint_production.py",
            ["export-video", "--project", str(project)],
        )
    else:
        print("WARN PowerPoint video export was explicitly skipped")
    if args.qa == "release":
        if args.skip_export:
            raise RuntimeError("Release QA requires PowerPoint video export")
        print(
            "INFO release QA requires a later explicit human full-watch "
            "confirmation; running the check now will report that boundary"
        )
        run_script(
            "qa_presentation.py",
            ["--project", str(project), "--level", "release"],
        )

    state = load_state(paths["build_state"])
    after = current_input_fingerprints(project)
    if after["source"] != before["source"] or after["visual"] != before["visual"]:
        raise RuntimeError("Source or visual inputs changed during audio rebuild")
    state["inputs"].update(
        {
            "source": after["source"],
            "narration": after["narration"],
            "voice": after["voice"],
            "visual": after["visual"],
        }
    )
    write_object(paths["build_state"], state)
    print(
        f"OK  rebuild scope=audio qa={args.qa}; "
        f"video_exported={not args.skip_export}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--scope", choices=("audio",), required=True)
    parser.add_argument(
        "--qa",
        choices=("audio", "standard", "release"),
        default="standard",
    )
    parser.add_argument("--voice")
    parser.add_argument("--rate")
    parser.add_argument("--pitch")
    parser.add_argument("--pages")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-export", action="store_true")
    parser.add_argument("--allow-unverified-baseline", action="store_true")
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
