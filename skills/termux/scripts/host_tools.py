#!/usr/bin/env python3
"""Install local Android platform-tools and/or Temurin JDK; no admin rights or .env needed."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import tarfile
import urllib.request
import zipfile
from pathlib import Path


def download(url, destination: Path, sha256=None):
    if not url.startswith("https://"):
        raise ValueError("Tool downloads must use HTTPS")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and sha256 and hashlib.sha256(destination.read_bytes()).hexdigest() == sha256:
        return destination
    temporary = destination.with_name(destination.name + ".part")
    try:
        with urllib.request.urlopen(url, timeout=60) as response, temporary.open("wb") as out:
            shutil.copyfileobj(response, out)
        if sha256 and hashlib.sha256(temporary.read_bytes()).hexdigest() != sha256:
            raise ValueError(f"SHA256 mismatch: {destination.name}")
        temporary.replace(destination)
    finally:
        if temporary.exists(): temporary.unlink()
    return destination


def extract(archive: Path, target: Path):
    """Validate paths before extracting downloaded SDK/JDK archives."""
    target = target.resolve()
    target.mkdir(parents=True, exist_ok=True)
    def checked(name):
        if not (target / name).resolve().is_relative_to(target):
            raise ValueError("Archive contains a path outside its destination")
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as z:
            for item in z.infolist():
                checked(item.filename)
                if (item.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("Unexpected symlink in ZIP")
            z.extractall(target)
    else:
        with tarfile.open(archive) as t:
            for item in t.getmembers():
                checked(item.name)
                if item.issym(): checked(str(Path(item.name).parent / item.linkname))
                if item.islnk(): checked(item.linkname)
                if item.isdev() or item.isfifo(): raise ValueError("Unexpected special file in tool archive")
            t.extractall(target, filter="data") if hasattr(tarfile, "data_filter") else t.extractall(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", action="store_true")
    parser.add_argument("--jdk", action="store_true")
    parser.add_argument("--directory", type=Path, default=Path.home() / ".cache/scisaga/termux/host-tools")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    system = {"Windows": "windows", "Linux": "linux", "Darwin": "mac"}.get(platform.system())
    if not system: parser.error("Supported hosts: Windows, Linux, macOS")
    if not args.adb and not args.jdk: parser.error("Select --adb and/or --jdk")
    if not args.apply:
        print(json.dumps({"directory": str(args.directory), "adb": args.adb, "jdk": args.jdk, "changes_host": False, "next": "Add --apply to download and extract into this user-owned directory."}))
        return
    root = args.directory.resolve()
    if args.adb:
        archive = download(f"https://dl.google.com/android/repository/platform-tools-latest-{system if system != 'mac' else 'darwin'}.zip", root / "platform-tools.zip")
        extract(archive, root)
        executable = root / "platform-tools" / ("adb.exe" if system == "windows" else "adb")
        if os.name != "nt": executable.chmod(0o755)
        print("ADB:", executable)
    if args.jdk:
        arch = "aarch64" if platform.machine().lower() in ("aarch64", "arm64") else "x64"
        api_os = "mac" if system == "mac" else system
        request = f"https://api.adoptium.net/v3/assets/latest/21/hotspot?architecture={arch}&image_type=jdk&os={api_os}&vendor=eclipse"
        with urllib.request.urlopen(request, timeout=45) as response: releases = json.load(response)
        if not releases: raise RuntimeError("Temurin did not return a JDK for this platform")
        package = releases[0]["binary"]["package"]
        archive = download(package["link"], root / package["name"], package["checksum"])
        extract(archive, root / "jdk")
        candidates = list((root / "jdk").rglob("javac.exe" if os.name == "nt" else "javac"))
        if not candidates: raise RuntimeError("JDK archive contains no javac")
        print("JDK home:", candidates[0].parent.parent)


if __name__ == "__main__":
    try: main()
    except (OSError, ValueError, RuntimeError) as error: raise SystemExit(str(error))
