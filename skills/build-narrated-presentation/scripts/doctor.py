#!/usr/bin/env python3
"""Check Python dependencies and report the PowerPoint validation boundary."""

from __future__ import annotations

import importlib.util
import platform


MODULES = {
    "azure.cognitiveservices.speech": "azure-cognitiveservices-speech",
    "fitz": "PyMuPDF",
    "lxml": "lxml",
    "mutagen": "mutagen",
    "PIL": "Pillow",
    "pptx": "python-pptx",
    "dotenv": "python-dotenv",
    "weasyprint": "WeasyPrint",
}


def main() -> int:
    missing: list[str] = []
    for module, package in MODULES.items():
        try:
            available = importlib.util.find_spec(module) is not None
        except (ModuleNotFoundError, ValueError):
            available = False
        if not available:
            missing.append(package)
            print(f"ERROR missing Python dependency: {package}")
        else:
            print(f"OK  Python dependency: {package}")
    print(f"INFO platform: {platform.system()} {platform.machine()}")
    if platform.system() == "Windows":
        print("INFO Validate the final PPTX in the installed desktop PowerPoint.")
    else:
        print(
            "INFO Final playback and MP4 export still require Windows desktop "
            "PowerPoint."
        )
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
