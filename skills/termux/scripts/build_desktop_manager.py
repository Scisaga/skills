#!/usr/bin/env python3
"""Build the two-entry Android manager from source with pinned, verified build tools."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import secrets
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from host_tools import download

SKILL = Path(__file__).resolve().parents[1]
SOURCE = SKILL / "assets/desktop/android"
GOOGLE = "https://dl.google.com/dl/android/maven2/"
MAVEN = "https://repo.maven.apache.org/maven2/"
TOOLS = {
    "android.jar": (MAVEN + "com/google/android/android/4.1.1.4/android-4.1.1.4.jar", "84072541cbb711eff89f7277100ff854929a446dba7ceb1b195c340e0b4fd3cb"),
    "json.jar": (MAVEN + "org/json/json/20180813/json-20180813.jar", "518080049ba83181914419d11a25d9bc9833a2d729b6a6e7469fa52851356da8"),
    "r8.jar": (GOOGLE + "com/android/tools/r8/9.4.17/r8-9.4.17.jar", "2100511344497f041644a4d63fb7be8a516ce9bace30b7d17ab27cc93a0e58d4"),
    "apksig.jar": (GOOGLE + "com/android/tools/build/apksig/9.3.2/apksig-9.3.2.jar", "562cd0a88890960d2ece48e116c61f12872222f1dcc306890799382bc019b201"),
}
AAPT = {"windows": "b1006ecec7e5936257e95e97f3eba7ef439d3e44178967cc048f86c9119fb231", "linux": "e772a3dae8354764f1b0793903218427f483982445207f2e4ffc8c2026755bd4", "osx": "1e35bc2ce18c3aae840be2a29659ce50d6043e907a44d98ee1cf375d044fa29c"}


def run(args):
    p = subprocess.run([str(x) for x in args], text=True, encoding="utf-8", errors="replace", capture_output=True)
    if p.returncode:
        raise RuntimeError(f"{Path(args[0]).name} failed (exit {p.returncode}): {(p.stderr or p.stdout)[-1800:]}")
    return p.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--cache-dir", type=Path, default=Path.home() / ".cache/scisaga/termux/android-build")
    parser.add_argument("--key-dir", type=Path, default=Path.home() / ".config/scisaga/termux/signing")
    parser.add_argument("--java-home", type=Path)
    args = parser.parse_args()
    host = {"Windows": "windows", "Linux": "linux", "Darwin": "osx"}.get(platform.system())
    if host not in AAPT: parser.error("Supported hosts: Windows, Linux, macOS")
    suffix = ".exe" if os.name == "nt" else ""
    java_home = args.java_home or (Path(os.environ["JAVA_HOME"]) if os.environ.get("JAVA_HOME") else None)
    javac = java_home / "bin" / ("javac" + suffix) if java_home else shutil.which("javac")
    if not javac or not Path(javac).is_file():
        parser.error("JDK missing. Run `python scripts/host_tools.py --jdk --apply`, then pass --java-home PATH")
    jdk = Path(javac).resolve().parent
    cache, keys = args.cache_dir.resolve(), args.key_dir.resolve()
    repository = SKILL.parent.parent
    if keys.is_relative_to(SKILL) or ((repository / "plugin.json").exists() and keys.is_relative_to(repository)):
        parser.error("Signing keys must stay outside the skill repository")
    if cache.is_relative_to(SKILL): parser.error("Build cache must stay outside the skill directory")
    if host == "linux" and platform.machine().lower() not in ("x86_64", "amd64"):
        parser.error("Pinned Linux AAPT2 requires an x86_64 build host; use an x86_64 Linux/Windows host or supported macOS host")
    cache.mkdir(parents=True, exist_ok=True); keys.mkdir(parents=True, exist_ok=True)
    tools = {name: download(url, cache / name, digest) for name, (url, digest) in TOOLS.items()}
    aapt_jar = download(GOOGLE + f"com/android/tools/build/aapt2/9.3.2-15703166/aapt2-9.3.2-15703166-{host}.jar", cache / f"aapt2-{host}.jar", AAPT[host])
    key, password_file = keys / "desktop-manager.p12", keys / "signing-password"
    if key.exists() != password_file.exists(): raise RuntimeError("Incomplete signing key state; preserve and inspect this key directory")
    if not key.exists():
        password_file.write_text(secrets.token_urlsafe(24), encoding="utf-8"); password_file.chmod(0o600)
        run([jdk / ("keytool" + suffix), "-J-Duser.language=en", "-genkeypair", "-noprompt", "-keystore", key, "-storetype", "PKCS12", "-storepass:file", password_file,
             "-keypass:file", password_file, "-alias", "desktop", "-keyalg", "RSA", "-keysize", "3072", "-validity", "3650", "-dname", "CN=Local Termux Desktop Manager"])
        key.chmod(0o600)
    output = (args.output or cache / "desktop-manager.apk").resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="manager-build-", dir=cache) as folder:
        build = Path(folder); classes = build / "classes"; classes.mkdir(); dex = build / "dex"; dex.mkdir()
        with zipfile.ZipFile(aapt_jar) as z: aapt = build / ("aapt2" + suffix); aapt.write_bytes(z.read("aapt2" + suffix)); aapt.chmod(0o700)
        cp = os.pathsep.join(str(tools[k]) for k in ("android.jar", "json.jar"))
        run([jdk / ("javac" + suffix), "-encoding", "UTF-8", "-source", "8", "-target", "8", "-Xlint:-options", "-cp", cp, "-d", classes, *sorted((SOURCE / "src").glob("*.java"))])
        run([jdk / ("java" + suffix), "-cp", tools["r8.jar"], "com.android.tools.r8.D8", "--min-api", "26", "--lib", tools["android.jar"], "--lib", tools["json.jar"], "--output", dex, *classes.rglob("*.class")])
        flats = []
        for icon in sorted((SOURCE / "res/drawable").glob("*.png")):
            run([aapt, "compile", icon, "-o", build]); flats.append(build / ("drawable_" + icon.name + ".flat"))
        unsigned = build / "unsigned.apk"
        run([aapt, "link", "-I", tools["android.jar"], "--manifest", SOURCE / "AndroidManifest.xml", "--min-sdk-version", "26", "--target-sdk-version", "35", "-o", unsigned, *flats])
        with zipfile.ZipFile(unsigned, "a", compression=zipfile.ZIP_DEFLATED) as z: z.write(dex / "classes.dex", "classes.dex")
        run([jdk / ("javac" + suffix), "-cp", tools["apksig.jar"], "-d", build, SOURCE / "tools/SignApk.java"])
        run([jdk / ("java" + suffix), "-cp", str(build) + os.pathsep + str(tools["apksig.jar"]), "SignApk", key, password_file, unsigned, output])
    print(json.dumps({"apk": str(output), "sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "launcher_entries": ["Linux desktop", "Desktop manager"], "key_directory": str(keys)}, ensure_ascii=False))


if __name__ == "__main__":
    try: main()
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc: raise SystemExit(str(exc))
