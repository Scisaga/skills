#!/usr/bin/env python3
"""Check only the dependencies required by the selected production stage."""

from __future__ import annotations

import argparse
import importlib.util
import os
import platform
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

from browser_render import browser_page
from html_fonts import catalog_files, check_font
from qwen_tts_client import QwenTTSClient, QwenTTSError, load_tts_environment

STATIC_MODULES = {
    "playwright": "playwright",
    "fontTools": "fonttools[woff]",
    "brotli": "brotli",
    "tinycss2": "tinycss2",
}
AUDIO_MODULES = {
    "lameenc": "lameenc",
    "mutagen": "mutagen",
    "dotenv": "python-dotenv",
}
STAGES = ("static", "audio", "narrated", "video", "all")
AUDIO_STAGES = {"audio", "narrated", "all"}


def required_modules(stage: str, provider: str = "auto") -> dict[str, str]:
    required = {} if stage == "audio" else dict(STATIC_MODULES)
    if stage in AUDIO_STAGES:
        required.update(AUDIO_MODULES)
        if provider == "azure-speech":
            required["azure.cognitiveservices.speech"] = "azure-cognitiveservices-speech"
    return required


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
    if stage in AUDIO_STAGES and provider == "auto" and not module_available("azure.cognitiveservices.speech"):
        print("INFO Azure fallback needs: python -m pip install azure-cognitiveservices-speech")
    print(f"INFO stage: {stage}")
    print(f"INFO platform: {platform.system()} {platform.machine()}")
    if stage != "audio" and not missing:
        try:
            for asset in catalog_files().values():
                check_font(asset)
            with browser_page() as page:
                page.set_content("<p>slides</p>")
            print("OK  Chromium and bundled font sources")
        except (OSError, RuntimeError, ValueError) as exc:
            print(f"ERROR {exc}")
            print("Chromium system libraries: python -m playwright install --with-deps chromium")
            missing.append("Chromium or font sources")
    if stage in {"narrated", "video", "all"}:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            missing.append("ffmpeg")
        else:
            result = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True)
            encoders = result.stdout.split()
            expected = {"libmp3lame"} if stage == "narrated" else {"libx264", "aac"}
            if stage == "all":
                expected.add("libmp3lame")
            missing.extend(sorted(expected - set(encoders)))
        if stage in {"video", "all"} and not shutil.which("ffprobe"):
            missing.append("ffprobe")
        for tool in missing:
            if tool in {"ffmpeg", "ffprobe", "libx264", "libmp3lame", "aac"}:
                print(f"ERROR missing {tool}; run install_ffmpeg.sh or install_ffmpeg.ps1")
    return missing


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        choices=STAGES,
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
            f"bootstrap --stage {args.stage}."
        )
        return 1
    if args.stage in AUDIO_STAGES:
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
