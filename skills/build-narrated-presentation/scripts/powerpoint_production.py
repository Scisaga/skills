#!/usr/bin/env python3
"""Run Windows PowerPoint export adapters and record distinct evidence."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Sequence

from production_common import (
    deliverable_pptx,
    file_hash,
    load_project_config,
    load_state,
    project_paths,
    require_approvals,
    write_object,
)


SCRIPT_DIR = Path(__file__).resolve().parent

OFFICE_2019_POWERPOINT_PRODUCTS = (
    "powerpoint2019",
    "proplus2019",
    "standard2019",
    "professional2019",
    "homebusiness2019",
    "homestudent2019",
    "personal2019",
)
NEWER_POWERPOINT_PRODUCTS = (
    "powerpoint2021",
    "powerpoint2024",
    "proplus2021",
    "proplus2024",
    "standard2021",
    "standard2024",
    "professional2021",
    "professional2024",
    "homebusiness2021",
    "homebusiness2024",
    "homestudent2021",
    "personal2021",
    "o365proplus",
    "o365business",
)


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


def office_product_release_ids(report: dict[str, object]) -> list[str]:
    value = report.get("office_product_release_ids")
    if isinstance(value, str):
        return [item for item in re.split(r"[,;\s]+", value) if item]
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def office_build_number(report: dict[str, object]) -> int | None:
    for key in ("powerpoint_build", "office_click_to_run_version"):
        value = report.get(key)
        if value is None:
            continue
        numbers = [int(item) for item in re.findall(r"\d+", str(value))]
        if len(numbers) >= 3 and numbers[0:2] == [16, 0]:
            return numbers[2]
        for number in numbers:
            if number >= 1000:
                return number
    return None


def classify_powerpoint_generation(
    report: dict[str, object],
) -> tuple[str, str]:
    product_ids = [item.lower() for item in office_product_release_ids(report)]
    has_2019 = any(
        product.startswith(prefix)
        for product in product_ids
        for prefix in OFFICE_2019_POWERPOINT_PRODUCTS
    )
    has_newer = any(
        product.startswith(prefix)
        for product in product_ids
        for prefix in NEWER_POWERPOINT_PRODUCTS
    )
    if has_2019 and not has_newer:
        return "office-2019", "Office ProductReleaseIds identifies a 2019 PowerPoint suite"
    if has_newer and not has_2019:
        return "newer-office", "Office ProductReleaseIds identifies Office 2021/2024/Microsoft 365"
    if has_2019 and has_newer:
        return "unknown", "conflicting PowerPoint-capable Office ProductReleaseIds"

    build = office_build_number(report)
    if build is not None and 10000 <= build < 14000:
        return "office-2019", f"PowerPoint build {build} is in the Office 2019 volume range"
    if build is not None and build >= 14000:
        return (
            "unknown",
            f"PowerPoint build {build} is shared by retail Office generations",
        )
    return "unknown", "PowerPoint generation could not be identified reliably"


def find_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg
    raise RuntimeError(
        "Office 2019 color-range compatibility requires ffmpeg. Run "
        "scripts/install_ffmpeg.ps1 on Windows or scripts/install_ffmpeg.sh "
        "on Linux/WSL, then rerun export-video."
    )


def reencode_office2019_color_range(video: Path) -> dict[str, object]:
    ffmpeg = find_ffmpeg()
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{video.stem}.color-fixed-",
        suffix=".mp4",
        dir=video.parent,
    )
    os.close(file_descriptor)
    temporary = Path(temporary_name)
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(video),
        "-map",
        "0",
        "-c",
        "copy",
        "-c:v",
        "libx264",
        "-preset",
        "slow",
        "-crf",
        "16",
        "-pix_fmt",
        "yuv420p",
        "-vf",
        "scale=in_range=pc:out_range=tv",
        "-color_range",
        "tv",
        "-color_primaries",
        "bt709",
        "-color_trc",
        "bt709",
        "-colorspace",
        "bt709",
        "-movflags",
        "+faststart",
        str(temporary),
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or f"exit code {result.returncode}"
            raise RuntimeError(f"ffmpeg Office 2019 color-range re-encode failed: {message}")
        if not temporary.is_file() or temporary.stat().st_size <= 0:
            raise RuntimeError("ffmpeg Office 2019 color-range re-encode created an empty MP4")
        os.replace(temporary, video)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {
        "method": "h264-reencode-full-to-limited",
        "input_range": "pc",
        "output_range": "tv",
        "video_codec": "libx264",
        "preset": "slow",
        "crf": 16,
        "pixel_format": "yuv420p",
        "color_primaries": "bt709",
        "transfer_characteristics": "bt709",
        "matrix_coefficients": "bt709",
        "audio_reencoded": False,
        "reencoded": True,
        "ffmpeg": ffmpeg,
    }


def apply_color_range_compatibility(
    video: Path,
    report: dict[str, object],
    mode: str,
) -> dict[str, object]:
    generation, reason = classify_powerpoint_generation(report)
    should_apply = mode == "on" or (mode == "auto" and generation == "office-2019")
    compatibility: dict[str, object] = {
        "mode": mode,
        "powerpoint_generation": generation,
        "decision_reason": reason,
        "action": "applied" if should_apply else "skipped",
    }
    if should_apply:
        compatibility["input_sha256"] = file_hash(video)
        compatibility.update(reencode_office2019_color_range(video))
        compatibility["output_sha256"] = file_hash(video)
    elif mode == "auto" and generation == "unknown":
        compatibility["warning"] = (
            "Office generation is ambiguous; pass --color-range-fix on for a "
            "known Office 2019 installation or off for a known unaffected version"
        )
    return compatibility


def export_video_command(args: argparse.Namespace) -> int:
    project = args.project.expanduser().resolve()
    config = load_project_config(project)
    if config["deliverable"] != "video":
        raise RuntimeError("Video export requires deliverable=video")
    require_approvals(project, ("content", "visual", "narration"))
    paths = project_paths(project)
    state = load_state(paths["build_state"])
    from qa_presentation import cache_fingerprint, current_cached_report

    current_standard = cache_fingerprint(project, "standard", state)
    if current_cached_report(
        project,
        "standard",
        state,
        current_standard,
    ) is None:
        raise RuntimeError(
            "Current standard QA has not passed; run qa --level standard "
            "before exporting video"
        )
    input_pptx = (
        args.input_pptx.expanduser().resolve()
        if args.input_pptx
        else paths["narrated_pptx"]
    )
    if input_pptx != paths["narrated_pptx"].resolve():
        raise ValueError(
            "--input-pptx must be the configured narrated PPTX that passed "
            "standard QA"
        )
    output_mp4 = (
        args.output_mp4.expanduser().resolve()
        if args.output_mp4
        else paths["video"]
    )
    if output_mp4 != paths["video"].resolve():
        raise ValueError(
            "--output-mp4 must be the configured project video output so "
            "the export evidence records the delivered file"
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
    compatibility = apply_color_range_compatibility(
        output_mp4,
        report,
        getattr(args, "color_range_fix", "auto"),
    )
    report["powerpoint_output_bytes"] = report.get("output_bytes")
    report["output_bytes"] = output_mp4.stat().st_size
    report["color_range_compatibility"] = compatibility
    write_object(report_path, report)
    output_sha = file_hash(output_mp4)
    state["artifacts"]["video"] = output_sha
    state["powerpoint"]["opened"] = {
        "status": "passed",
        "pptx_sha256": file_hash(input_pptx),
        "powerpoint_version": report.get("powerpoint_version"),
        "powerpoint_build": report.get("powerpoint_build"),
        "evidence": "presentation-opened-for-create-video",
    }
    state["powerpoint"]["video_exported"] = {
        "status": "passed",
        "video_sha256": output_sha,
        "pptx_sha256": file_hash(input_pptx),
        "powerpoint_version": report.get("powerpoint_version"),
        "powerpoint_build": report.get("powerpoint_build"),
        "color_range_compatibility": compatibility,
        "report": str(report_path.relative_to(project)),
        "report_sha256": file_hash(report_path),
    }
    state["powerpoint"]["human_watch"] = None
    write_object(paths["build_state"], state)
    print(
        f"OK  {output_mp4}: PowerPoint export completed; "
        f"color_range_fix={compatibility['action']} "
        f"({compatibility['powerpoint_generation']}); "
        "no post-export video inspection requested"
    )
    if compatibility.get("warning"):
        print(f"WARN {compatibility['warning']}")
    return 0


def export_pages_command(args: argparse.Namespace) -> int:
    project = args.project.expanduser().resolve()
    load_project_config(project)
    input_pptx = (
        args.input_pptx.expanduser().resolve()
        if args.input_pptx
        else deliverable_pptx(project)
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
    video.add_argument(
        "--color-range-fix",
        choices=("auto", "on", "off"),
        default="auto",
        help="Re-encode Office 2019 video pixels with correct color-range mapping",
    )
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
