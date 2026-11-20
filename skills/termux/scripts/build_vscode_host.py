#!/usr/bin/env python3
"""Build the separately signed Android host for standalone VS Code windows."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import zipfile

from build_desktop_manager import SKILL, SOURCE, TOOLS, download

UPSTREAM = "https://github.com/termux/termux-x11.git"
COMMIT = "c5d09202be5fe403cbd631712f567f64b3cce72e"
APK_SHA256 = "77c1791d6dccb4853a0b9e5e5fd85dc27872968fefe9122a8c6e45abd342f618"
PACKAGE = "com.scisaga.tabletvscode"
ASSETS = SKILL / "assets/desktop/standalone-code/android"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args, **options):
    return subprocess.run([str(arg) for arg in args], check=True, **options)


def signing_key(jdk, keys, certificate):
    keys.mkdir(mode=0o700, parents=True, exist_ok=True)
    key, password = keys / "vscode-host.p12", keys / "signing-password"
    if key.exists() != password.exists():
        raise ValueError("The signing directory has an incomplete key pair")
    if not key.exists():
        with password.open("x", encoding="ascii") as stream:
            stream.write(secrets.token_urlsafe(32))
        password.chmod(0o600)
        try:
            run([jdk / "keytool", "-genkeypair", "-noprompt", "-keystore", key, "-storetype", "PKCS12",
                 "-storepass:file", password, "-keypass:file", password, "-alias", "desktop",
                 "-keyalg", "RSA", "-keysize", "3072", "-validity", "3650", "-dname", "CN=Local VS Code Android Host"])
        except (OSError, subprocess.SubprocessError):
            if not key.exists():
                password.unlink()
            raise
        key.chmod(0o600)
    run([jdk / "keytool", "-exportcert", "-keystore", key, "-storepass:file", password,
         "-alias", "desktop", "-file", certificate], stdout=subprocess.DEVNULL)
    return key, password


def build(args):
    sdk = args.android_sdk.resolve()
    if not (sdk / "platforms/android-34/android.jar").is_file() or not (sdk / "build-tools/36.0.0").is_dir():
        raise ValueError("Install Android SDK packages with sdkmanager 'platforms;android-34' 'build-tools;36.0.0'")
    java_home = args.java_home or (Path(os.environ["JAVA_HOME"]) if "JAVA_HOME" in os.environ else None)
    javac = java_home / "bin" / ("javac.exe" if os.name == "nt" else "javac") if java_home else shutil.which("javac")
    if not javac or not Path(javac).is_file():
        raise ValueError("Install JDK 21 with host_tools.py --jdk --apply and pass --java-home")
    jdk = Path(javac).resolve().parent
    if not shutil.which("git"):
        raise ValueError("Install Git using winget install Git.Git, apt install git, or xcode-select --install")
    if digest(args.upstream_apk) != APK_SHA256:
        raise ValueError("Upstream APK does not match the reviewed Termux:X11 release")
    icon = args.code_icon.read_bytes()
    if not icon.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Use the code.png from the installed Linux VS Code")

    output, keys, cache = args.output.resolve(), args.key_dir.resolve(), args.cache_dir.resolve()
    repository = SKILL.parent.parent
    protected = repository if (repository / "plugin.json").is_file() else SKILL
    if any(path.is_relative_to(protected) for path in (output, keys, cache)):
        raise ValueError("Keep build artifacts, signing keys and caches outside the skill repository")
    cache.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    apksig_url, apksig_hash = TOOLS["apksig.jar"]
    apksig = download(apksig_url, cache / "apksig.jar", apksig_hash)
    with tempfile.TemporaryDirectory(prefix="vscode-host-", dir=cache) as work:
        work = Path(work)
        source = work / "x11"
        run(["git", "init", "-q", source])
        run(["git", "-C", source, "fetch", "--depth=1", UPSTREAM, COMMIT])
        run(["git", "-C", source, "checkout", "-q", "--detach", COMMIT])
        run(["git", "-C", source, "apply", ASSETS / "vscode-host.patch"])
        certificate = source / "vscode-signing-cert.der"
        key, password = signing_key(jdk, keys, certificate)
        with zipfile.ZipFile(args.upstream_apk) as original:
            library = source / "vscode-jni/arm64-v8a/libXlorie.so"
            library.parent.mkdir(parents=True)
            library.write_bytes(original.read("lib/arm64-v8a/libXlorie.so"))
        main = source / "lorie/src/main"
        shutil.copy2(ASSETS / "CodeLauncher.java", main / "java/com/termux/x11/CodeLauncher.java")
        for values in ("values", "values-zh-rCN", "xml"):
            target = main / "res" / values
            target.mkdir(exist_ok=True)
            shutil.copy2(ASSETS / values / "vscode.xml", target / "vscode.xml")
        drawable = main / "res/drawable-nodpi"
        drawable.mkdir(exist_ok=True)
        (drawable / "vscode_icon.png").write_bytes(icon)

        env = dict(os.environ, ANDROID_HOME=str(sdk), ANDROID_SDK_ROOT=str(sdk), JAVA_HOME=str(jdk.parent))
        run([jdk / "java", "-classpath", source / "gradle/wrapper/gradle-wrapper.jar",
             "org.gradle.wrapper.GradleWrapperMain", "--no-daemon", ":lorie-app:assembleStandaloneRelease",
             ":shell-loader:assembleRelease"], cwd=source, env=env)
        unsigned = source / "lorie-app/build/outputs/apk/standalone/release/termux-x11-universal-release.apk"
        signed = work / "vscode-host.apk"
        run([jdk / "javac", "-cp", apksig, "-d", work, SOURCE / "tools/SignApk.java"])
        run([jdk / "java", "-cp", str(work) + os.pathsep + str(apksig), "SignApk", key, password, unsigned, signed])
        with zipfile.ZipFile(source / "shell-loader/build/outputs/apk/release/shell-loader.apk") as loader:
            with zipfile.ZipFile(work / "vscode-loader.apk", "w", compression=zipfile.ZIP_DEFLATED) as bundle:
                bundle.writestr("classes.dex", loader.read("classes.dex"))
        names = ("vscode-host.apk", "vscode-loader.apk")
        result = {"package": PACKAGE, "upstream_commit": COMMIT,
                  "signer_sha256": digest(certificate), "files": {name: digest(work / name) for name in names}}
        for name in names:
            shutil.copy2(work / name, output / name)
        (output / "manifest.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--android-sdk", type=Path, required=True)
    parser.add_argument("--java-home", type=Path)
    parser.add_argument("--upstream-apk", type=Path, required=True)
    parser.add_argument("--code-icon", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, default=Path.home() / ".cache/scisaga/termux/vscode-build")
    parser.add_argument("--key-dir", type=Path, default=Path.home() / ".config/scisaga/termux/vscode-signing")
    args = parser.parse_args()
    try:
        print(json.dumps(build(args), indent=2))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
