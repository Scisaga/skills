#!/usr/bin/env python3
"""Run Windows PowerPoint export adapters and record distinct evidence."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from production_common import (
    file_hash,
    load_state,
    project_paths,
    write_object,
)


SCRIPT_DIR = Path(__file__).resolve().parent


def find_powershell() -> str:
    candidates = ["powershell.exe", "powershell", "pwsh"]
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise RuntimeError(
        "PowerShell is unavailable; video and page export require Windows "
        "desktop PowerPoint"
    )


def native_path(path: Path) -> str:
    resolved = path.expanduser().resolve()
    if os.name == "nt":
        return str(resolved)
    wslpath = shutil.which("wslpath")
    if wslpath and str(resolved).startswith("/mnt/"):
        result = subprocess.run(
            [wslpath, "-w", str(resolved)],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    return str(resolved)


def run_powershell(script: Path, arguments: list[str]) -> None:
    command = [
        find_powershell(),
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        native_path(script),
        *arguments,
    ]
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"{script.name} failed with exit code {result.returncode}"
        )


def export_video_command(args: argparse.Namespace) -> int:
    project = args.project.expanduser().resolve()
    paths = project_paths(project)
    input_pptx = (
        args.input_pptx.expanduser().resolve()
        if args.input_pptx
        else paths["animated_pptx"]
    )
    output_mp4 = (
        args.output_mp4.expanduser().resolve()
        if args.output_mp4
        else paths["video"]
    )
    report_path = project / "video" / "powerpoint_export.json"
    run_powershell(
        SCRIPT_DIR / "export_video.ps1",
        [
            "-InputPptx",
            native_path(input_pptx),
            "-OutputMp4",
            native_path(output_mp4),
            "-ReportPath",
            native_path(report_path),
            "-TimeoutMinutes",
            str(args.timeout_minutes),
            "-VerticalResolution",
            str(args.vertical_resolution),
            "-FramesPerSecond",
            str(args.frames_per_second),
            "-Quality",
            str(args.quality),
        ],
    )
    if not output_mp4.is_file() or output_mp4.stat().st_size <= 0:
        raise RuntimeError(f"PowerPoint did not create {output_mp4}")
    with report_path.open(encoding="utf-8-sig") as handle:
        report = json.load(handle)
    output_sha = file_hash(output_mp4)
    state = load_state(paths["build_state"])
    state["artifacts"]["video"] = output_sha
    state["powerpoint"]["opened"] = {
        "status": "passed",
        "pptx_sha256": file_hash(input_pptx),
        "powerpoint_version": report.get("powerpoint_version"),
        "evidence": "presentation-opened-for-create-video",
    }
    state["powerpoint"]["video_exported"] = {
        "status": "passed",
        "video_sha256": output_sha,
        "powerpoint_version": report.get("powerpoint_version"),
        "report": str(report_path.relative_to(project)),
    }
    state["powerpoint"]["human_watch"] = None
    write_object(paths["build_state"], state)
    print(
        f"OK  {output_mp4}: PowerPoint export completed; "
        "human watch remains pending"
    )
    return 0


def export_pages_command(args: argparse.Namespace) -> int:
    project = args.project.expanduser().resolve()
    paths = project_paths(project)
    input_pptx = (
        args.input_pptx.expanduser().resolve()
        if args.input_pptx
        else paths["animated_pptx"]
    )
    output = args.output.expanduser().resolve()
    run_powershell(
        SCRIPT_DIR / "export_pages.ps1",
        [
            "-InputPptx",
            native_path(input_pptx),
            "-Pages",
            args.pages,
            "-Output",
            native_path(output),
            "-Format",
            args.format,
            "-Width",
            str(args.width),
            "-Height",
            str(args.height),
        ],
    )
    print(f"OK  exported pages {args.pages} to {output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    video = subparsers.add_parser("export-video")
    video.add_argument("--project", type=Path, required=True)
    video.add_argument("--input-pptx", type=Path)
    video.add_argument("--output-mp4", type=Path)
    video.add_argument("--timeout-minutes", type=int, default=90)
    video.add_argument("--vertical-resolution", type=int, default=1080)
    video.add_argument("--frames-per-second", type=int, default=30)
    video.add_argument("--quality", type=int, default=100)
    video.set_defaults(func=export_video_command)

    pages = subparsers.add_parser("export-pages")
    pages.add_argument("--project", type=Path, required=True)
    pages.add_argument("--input-pptx", type=Path)
    pages.add_argument("--pages", required=True)
    pages.add_argument("--format", choices=("pdf", "png", "jpg"), default="pdf")
    pages.add_argument("--output", type=Path, required=True)
    pages.add_argument("--width", type=int, default=1600)
    pages.add_argument("--height", type=int, default=900)
    pages.set_defaults(func=export_pages_command)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


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
