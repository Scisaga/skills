#!/usr/bin/env python3
"""Check only the dependencies required by the selected production stage."""

from __future__ import annotations

import argparse
import importlib.util
import platform
import shutil
from typing import Sequence


STATIC_MODULES = {
    "fitz": "PyMuPDF",
    "lxml": "lxml",
    "PIL": "Pillow",
    "pptx": "python-pptx",
    "weasyprint": "WeasyPrint",
}
AUDIO_MODULES = {
    "azure.cognitiveservices.speech": "azure-cognitiveservices-speech",
    "lameenc": "lameenc",
    "mutagen": "mutagen",
    "dotenv": "python-dotenv",
}


def required_modules(stage: str) -> dict[str, str]:
    if stage == "static":
        return dict(STATIC_MODULES)
    if stage == "audio":
        return dict(AUDIO_MODULES)
    return {**STATIC_MODULES, **AUDIO_MODULES}


def module_available(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ModuleNotFoundError, ValueError):
        return False


def check_stage(stage: str) -> list[str]:
    missing: list[str] = []
    for module, package in required_modules(stage).items():
        if module_available(module):
            print(f"OK  Python dependency: {package}")
        else:
            missing.append(package)
            print(f"ERROR missing Python dependency: {package}")

    print(f"INFO stage: {stage}")
    print(f"INFO platform: {platform.system()} {platform.machine()}")
    if stage == "video":
        powershell = (
            shutil.which("powershell.exe")
            or shutil.which("powershell")
            or shutil.which("pwsh")
        )
        if powershell:
            print(f"OK  PowerShell: {powershell}")
        else:
            missing.append("PowerShell")
            print(
                "ERROR PowerShell is required for Windows PowerPoint automation."
            )
        ffprobe = shutil.which("ffprobe")
        if ffprobe:
            print(f"OK  ffprobe: {ffprobe}")
        else:
            missing.append("ffprobe")
            print("ERROR ffprobe is required for video QA.")
        print(
            "INFO Final video export still requires installed Windows desktop "
            "PowerPoint."
        )
    return missing


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        choices=("static", "audio", "video"),
        default="static",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    missing = check_stage(args.stage)
    if missing:
        print(
            "Install dependencies with "
            "skills/build-narrated-presentation/scripts/bootstrap.sh "
            "or bootstrap.ps1."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
