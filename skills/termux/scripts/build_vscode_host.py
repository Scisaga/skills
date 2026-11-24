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
import sys
import tempfile
import zipfile

from build_desktop_manager import SKILL, SOURCE, TOOLS, download

UPSTREAM = "https://github.com/termux/termux-x11.git"
COMMIT = "c5d09202be5fe403cbd631712f567f64b3cce72e"
APK_SHA256 = "77c1791d6dccb4853a0b9e5e5fd85dc27872968fefe9122a8c6e45abd342f618"
PACKAGE = "com.scisaga.tabletvscode"
ASSETS = SKILL / "assets/desktop/standalone-code/android"
INPUT_PATCH = ASSETS / "vscode-unicode-input.patch"
NDK_VERSION = "29.0.14206865"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args, **options):
    return subprocess.run([str(arg) for arg in args], check=True, **options)


def checkout(source):
    run(["git", "init", "-q", source])
    run(["git", "-C", source, "fetch", "--depth=1", UPSTREAM, COMMIT])
    run(["git", "-C", source, "checkout", "-q", "--detach", COMMIT])


def private_paths(*paths):
    repository = SKILL.parent.parent
    protected = repository if (repository / "plugin.json").is_file() else SKILL
    if any(path.is_relative_to(protected) for path in paths):
        raise ValueError("Keep build artifacts, signing keys and caches outside the skill repository")


def native_manifest(library):
    return {"upstream_commit": COMMIT, "patch_sha256": digest(INPUT_PATCH), "library_sha256": digest(library)}


def build_native(args):
    if not sys.platform.startswith("linux"):
        raise ValueError("Build the ARM64 native library on Linux or WSL")
    for tool in ("git", "cmake", "ninja", "bison", "m4", "patch"):
        if not shutil.which(tool):
            raise ValueError(f"Missing {tool}. On Debian or Ubuntu run: sudo apt install git cmake ninja-build bison m4 patch")
    ndk = args.android_ndk.resolve()
    toolchain = ndk / "build/cmake/android.toolchain.cmake"
    strip = next(ndk.glob("toolchains/llvm/prebuilt/linux-*/bin/llvm-strip"), None)
    if (not toolchain.is_file() or not strip
            or f"Pkg.Revision = {NDK_VERSION}" not in (ndk / "source.properties").read_text(encoding="ascii").splitlines()):
        raise ValueError(f"Install Android NDK {NDK_VERSION} with sdkmanager 'ndk;{NDK_VERSION}' and pass --android-ndk")

    output, cache = args.output.resolve(), args.cache_dir.resolve()
    private_paths(output, cache)
    cache.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vscode-native-", dir=cache) as work:
        work = Path(work)
        source, build_dir = work / "x11", work / "build"
        checkout(source)
        run(["git", "-C", source, "submodule", "update", "--init", "--recursive", "--jobs", "8", "--depth", "1"])
        run(["git", "-C", source, "apply", INPUT_PATCH])
        run(["cmake", "-S", source / "lorie/src/main/cpp", "-B", build_dir, "-G", "Ninja",
             f"-DCMAKE_TOOLCHAIN_FILE={toolchain}", "-DANDROID_ABI=arm64-v8a", "-DANDROID_PLATFORM=android-24"])
        run(["cmake", "--build", build_dir, "--target", "Xlorie", "--parallel", "8"])
        library = work / "libXlorie.so"
        run([strip, "--strip-unneeded", "-o", library, build_dir / library.name])
        result = native_manifest(library)
        shutil.copy2(library, output / library.name)
        (output / "native-manifest.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


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
    ime_bridge = args.ime_bridge or args.ime_test
    package = PACKAGE + ".imetest" if args.ime_test else PACKAGE
    if ime_bridge and not args.native_library:
        raise ValueError("The IME bridge requires the patched native library for key-event fallback")
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
    if args.native_library:
        native_result = native_manifest(args.native_library)
        manifest = args.native_library.with_name("native-manifest.json")
        if not manifest.is_file() or native_result != json.loads(manifest.read_text(encoding="utf-8")):
            raise ValueError("Use the native library and its manifest from the build-vscode-host native command")
    else:
        native_result = None
        if digest(args.upstream_apk) != APK_SHA256:
            raise ValueError("Upstream APK does not match the reviewed Termux:X11 release")
    icon = args.code_icon.read_bytes()
    if not icon.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Use the code.png from the installed Linux VS Code")

    output, keys, cache = args.output.resolve(), args.key_dir.resolve(), args.cache_dir.resolve()
    private_paths(output, keys, cache)
    cache.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    apksig_url, apksig_hash = TOOLS["apksig.jar"]
    apksig = download(apksig_url, cache / "apksig.jar", apksig_hash)
    with tempfile.TemporaryDirectory(prefix="vscode-host-", dir=cache) as work:
        work = Path(work)
        source = work / "x11"
        checkout(source)
        host_patch = work / "host.patch"
        host_patch.write_text((ASSETS / "vscode-host.patch").read_text(encoding="utf-8").replace(PACKAGE, package),
                              encoding="utf-8", newline="\n")
        run(["git", "-C", source, "apply", host_patch])
        run(["git", "-C", source, "apply", ASSETS / "vscode-task-close.patch"])
        certificate = source / "vscode-signing-cert.der"
        key, password = signing_key(jdk, keys, certificate)
        library = source / "vscode-jni/arm64-v8a/libXlorie.so"
        library.parent.mkdir(parents=True)
        if args.native_library:
            shutil.copy2(args.native_library, library)
            if digest(library) != native_result["library_sha256"]:
                raise ValueError("The native library changed while packaging the host")
        else:
            with zipfile.ZipFile(args.upstream_apk) as original:
                library.write_bytes(original.read("lib/arm64-v8a/libXlorie.so"))
        main = source / "lorie/src/main"
        java = main / "java/com/termux/x11"
        (java / "CodeLauncher.java").write_text(
            (ASSETS / "CodeLauncher.java").read_text(encoding="utf-8").replace(PACKAGE, package),
            encoding="utf-8")
        shutil.copy2(ASSETS / "EditorTaskClose.java", java)
        if ime_bridge:
            run(["git", "-C", source, "apply", ASSETS / "vscode-ime-bridge.patch"])
            shutil.copy2(ASSETS / "ImeTextBridge.java", java)
        # Append the methods after the base and optional IME transactions.
        aidl = main / "aidl/com/termux/x11/ICmdEntryInterface.aidl"
        body = aidl.read_text(encoding="utf-8").rstrip()
        if not body.endswith("}"):
            raise ValueError("Unexpected X11 Binder interface")
        aidl.write_text(body[:-1] + "    String editorSessionToken();\n"
                        "    boolean closeEditor(String sessionToken);\n"
                        "    void watchEditorHost(IBinder lifetime);\n}\n", encoding="utf-8")
        for values in ("values", "values-zh-rCN", "xml"):
            target = main / "res" / values
            target.mkdir(exist_ok=True)
            shutil.copy2(ASSETS / values / "vscode.xml", target / "vscode.xml")
            if args.ime_test and values != "xml":
                strings = target / "vscode.xml"
                strings.write_text(
                    strings.read_text(encoding="utf-8").replace(">VSCode</string>", ">VSCode IME Test</string>"),
                    encoding="utf-8")
        drawable = main / "res/drawable-nodpi"
        drawable.mkdir(exist_ok=True)
        (drawable / "vscode_icon.png").write_bytes(icon)

        env = dict(os.environ, ANDROID_HOME=str(sdk), ANDROID_SDK_ROOT=str(sdk), JAVA_HOME=str(jdk.parent))
        gradle = [jdk / "java", "-classpath", source / "gradle/wrapper/gradle-wrapper.jar",
                  "org.gradle.wrapper.GradleWrapperMain", "--no-daemon"]
        if native_result:
            gradle.append("-PvscodeImeFix")
        if ime_bridge:
            gradle.append("-PvscodeImeBridge")
        run(gradle + [":lorie-app:assembleStandaloneRelease", ":shell-loader:assembleRelease"], cwd=source, env=env)
        unsigned = source / "lorie-app/build/outputs/apk/standalone/release/termux-x11-universal-release.apk"
        signed = work / "vscode-host.apk"
        run([jdk / "javac", "-cp", apksig, "-d", work, SOURCE / "tools/SignApk.java"])
        run([jdk / "java", "-cp", str(work) + os.pathsep + str(apksig), "SignApk", key, password, unsigned, signed])
        with zipfile.ZipFile(source / "shell-loader/build/outputs/apk/release/shell-loader.apk") as loader:
            with zipfile.ZipFile(work / "vscode-loader.apk", "w", compression=zipfile.ZIP_DEFLATED) as bundle:
                bundle.writestr("classes.dex", loader.read("classes.dex"))
        names = ("vscode-host.apk", "vscode-loader.apk")
        result = {"package": package, "upstream_commit": COMMIT,
                  "signer_sha256": digest(certificate), "files": {name: digest(work / name) for name in names}}
        if native_result:
            result["native_input"] = native_result
        if ime_bridge:
            result["ime_bridge"] = True
        for name in names:
            shutil.copy2(work / name, output / name)
        (output / "manifest.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main():
    cache = Path.home() / ".cache/scisaga/termux/vscode-build"
    if sys.argv[1:2] == ["native"]:
        parser = argparse.ArgumentParser(description="Build the ARM64 Termux:X11 library with the VS Code input patch.")
        parser.add_argument("--android-ndk", type=Path, required=True)
        parser.add_argument("--output", type=Path, required=True)
        parser.add_argument("--cache-dir", type=Path, default=cache)
        args = parser.parse_args(sys.argv[2:])
        try:
            print(json.dumps(build_native(args), indent=2))
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            raise SystemExit(str(error)) from error
        return

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--android-sdk", type=Path, required=True)
    parser.add_argument("--java-home", type=Path)
    library = parser.add_mutually_exclusive_group(required=True)
    library.add_argument("--upstream-apk", type=Path)
    library.add_argument("--native-library", type=Path)
    ime = parser.add_mutually_exclusive_group()
    ime.add_argument("--ime-bridge", action="store_true", help="enable direct GTK text submission")
    ime.add_argument("--ime-test", action="store_true", help="build the IME bridge under a separate test package")
    parser.add_argument("--code-icon", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, default=cache)
    parser.add_argument("--key-dir", type=Path, default=Path.home() / ".config/scisaga/termux/vscode-signing")
    args = parser.parse_args()
    try:
        print(json.dumps(build(args), indent=2))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
