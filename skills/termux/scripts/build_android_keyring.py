#!/usr/bin/env python3
"""Build the one-shot Android Keystore bridge; no APK or app update is needed."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

from build_desktop_manager import TOOLS, run
from host_tools import download

SKILL = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--cache-dir", type=Path, default=Path.home() / ".cache/scisaga/termux/android-build")
    parser.add_argument("--java-home", type=Path)
    args = parser.parse_args()
    suffix = ".exe" if os.name == "nt" else ""
    java_home = args.java_home or (Path(os.environ["JAVA_HOME"]) if os.environ.get("JAVA_HOME") else None)
    javac = java_home / "bin" / ("javac" + suffix) if java_home else shutil.which("javac")
    if not javac or not Path(javac).is_file():
        parser.error("JDK missing. Run `python scripts/host_tools.py --jdk --apply`, then pass --java-home PATH")
    jdk = Path(javac).resolve().parent
    cache = args.cache_dir.resolve()
    if cache.is_relative_to(SKILL):
        parser.error("Build cache must stay outside the skill directory")
    cache.mkdir(parents=True, exist_ok=True)
    deps = {name: download(TOOLS[name][0], cache / name, TOOLS[name][1]) for name in ("android.jar", "r8.jar")}
    output = (args.output or cache / "tablet-keyring.jar").resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="keyring-build-", dir=cache) as folder:
        build = Path(folder)
        classes, dex = build / "classes", build / "dex"
        classes.mkdir(); dex.mkdir()
        run([jdk / ("javac" + suffix), "-encoding", "UTF-8", "-source", "8", "-target", "8", "-Xlint:-options",
             "-d", classes, SKILL / "assets/desktop/android-keyring/TabletKeyring.java"])
        run([jdk / ("java" + suffix), "-cp", deps["r8.jar"], "com.android.tools.r8.D8", "--min-api", "35",
             "--lib", deps["android.jar"], "--output", dex, *classes.rglob("*.class")])
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(dex / "classes.dex", "classes.dex")
    print(json.dumps({"jar": str(output), "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as exc:
        raise SystemExit(str(exc))
