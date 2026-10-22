#!/usr/bin/env python3
"""Check only the dependencies required by the selected production stage."""

from __future__ import annotations

import argparse
import importlib.util
import os
import platform
import shutil
from collections.abc import Sequence
from pathlib import Path

from qwen_tts_client import QwenTTSClient, QwenTTSError, load_tts_environment

STATIC_MODULES = {
    "fitz": "PyMuPDF",
    "lxml": "lxml",
    "PIL": "Pillow",
    "pptx": "python-pptx",
    "weasyprint": "WeasyPrint",
}
AUDIO_MODULES = {
    "lameenc": "lameenc",
    "mutagen": "mutagen",
    "dotenv": "python-dotenv",
}


def required_modules(stage: str, provider: str = "auto") -> dict[str, str]:
    if stage == "static":
        return dict(STATIC_MODULES)
    audio = dict(AUDIO_MODULES)
    if provider == "azure-speech":
        audio["azure.cognitiveservices.speech"] = "azure-cognitiveservices-speech"
    if stage == "audio":
        return audio
    return {**STATIC_MODULES, **audio}


def module_available(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ModuleNotFoundError, ValueError):
        return False


def check_stage(stage: str, provider: str = "auto") -> list[str]:
    missing: list[str] = []
    for module, package in required_modules(stage, provider).items():
        if module_available(module):
            print(f"OK  Python dependency: {package}")
        else:
            missing.append(package)
            print(f"ERROR missing Python dependency: {package}")
    if stage != "static" and provider == "auto" and not module_available("azure.cognitiveservices.speech"):
        print(
            "INFO Azure fallback needs: python -m pip install azure-cognitiveservices-speech"
        )

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
            print("ERROR PowerShell is required for Windows PowerPoint automation.")
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            print(f"OK  optional Office 2019 color-range helper: {ffmpeg}")
        else:
            print(
                "INFO ffmpeg is only required when the Office 2019 color-range "
                "compatibility fix is selected."
            )
        print(
            "INFO Final video export still requires installed Windows desktop "
            "PowerPoint; no post-export video inspection is required."
        )
    return missing


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        choices=("static", "audio", "video"),
        default="static",
    )
    parser.add_argument(
        "--provider",
        choices=("auto", "qwen3-tts-openai", "azure-speech"),
        default="auto",
    )
    parser.add_argument(
        "--check-service",
        action="store_true",
        help="Check Qwen readiness and list the number of ready voices",
    )
    parser.add_argument("--env-file", type=Path, help="TTS 环境文件，优先于当前目录及技能目录 .env")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    missing = check_stage(args.stage, args.provider)
    if missing:
        print(
            "Install dependencies with "
            "skills/slides/scripts/bootstrap.sh "
            "or bootstrap.ps1."
        )
        return 1
    if args.stage != "static":
        load_tts_environment(args.env_file)
        if args.check_service and args.provider != "azure-speech":
            try:
                client = QwenTTSClient()
                if client.request("/ready").get("inference_ready") is not True:
                    raise QwenTTSError("Qwen is not ready")
                voices = client.request("/v1/voices").get("voices", [])
                ready = sum(v.get("conditioning_state") == "ready" for v in voices)
                print(f"OK  Qwen ready: {client.base_url}; {ready} ready voices")
            except QwenTTSError as exc:
                print(f"WARN {exc}")
                if (
                    args.provider != "auto"
                    or not os.getenv("AZURE_SPEECH_KEY")
                    or not module_available("azure.cognitiveservices.speech")
                ):
                    return 1
                print(
                    "INFO Azure fallback credentials and SDK are available; synthesis is not requested by doctor"
                )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR {exc}")
        raise SystemExit(1)
