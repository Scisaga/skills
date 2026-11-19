#!/usr/bin/env python3
"""Install the optional Android VS Code shortcut and configure its isolated profile."""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from textwrap import indent

from desktop_profile import ASSETS, guest_root, load_profile, profile_digest
from desktop_setup import Writer, require_termux, run
from jsonc_settings import merge as merge_settings, parse as parse_settings
from keyring_setup import CODE_GUARD


OFFICE_ID = "cweijan.vscode-office"
OFFICE_VERSION = "4.2.3"
OFFICE_TYPES = frozenset("docx dotx xls xlsx xlsm ods pptx pptm".split())
# Default editor claims in the reviewed release, used before first installation.
OFFICE_EXTRAS = frozenset(
    "md markdown csv tsv pdf epub ttf woff woff2 otf svg icns psd xmind tiff tif heif heic "
    "jar zip 7z rar tar.gz tgz tar apk vsix crx class".split()
)
PDF_ID = "mathematic.vscode-pdf"
CHROME_ENTRY = "tablet-android-chrome-preview.desktop"
PROFILE_DIR = ".local/share/tablet-vscode"
EDITOR_SETTING = "workbench.editorAssociations"


def scoped_path(path, base):
    if path.is_symlink() or not path.resolve().is_relative_to(base.resolve()):
        raise ValueError(f"Path leaves the isolated profile: {path}")
    if path.with_name(path.name + ".termux-new").is_symlink():
        raise ValueError(f"Unsafe staging path for {path}")
    return path


def replace_config_if_current(path, expected, replacement, mode):
    """Update the config only while it still contains the expected bytes."""
    if not path.is_file() or path.is_symlink() or path.read_bytes() != expected:
        return False
    if replacement is None:
        path.unlink()
        return True
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temp = Path(stream.name)
        stream.write(replacement)
    try:
        temp.chmod(mode)
        if path.is_symlink() or path.read_bytes() != expected:
            return False
        os.replace(temp, path)
        return True
    finally:
        temp.unlink(missing_ok=True)


def code_arguments(profile):
    args = ["/usr/share/code/code", "--no-sandbox", "--disable-dev-shm-usage", "--ozone-platform=x11"]
    if profile["gpu_backend"] != "freedreno-kgsl":
        return args + ["--disable-gpu"]
    if profile["code_angle_backend"] == "gles":
        args += ["--use-gl=angle", "--use-angle=gles"]
    return ["/usr/local/bin/tablet-gpu-run", *args]


def render_launcher(prefix, profile, display):
    if not re.fullmatch(r":[0-9]{1,2}", display) or int(display[1:]) == int(profile["display"][1:]):
        raise ValueError("Use a separate numeric X11 display, such as :2")
    values = {
        "PREFIX": str(prefix),
        "PREFIX_SHELL": shlex.quote(str(prefix)),
        "CONTAINER": shlex.quote(profile["container"]),
        "USER": shlex.quote(profile["user"]),
        "DISPLAY": ":" + str(int(display[1:])),
        "SCALE": str(profile["scale"]),
        "X11_ARGS": "" if profile["x11_mitshm"] else "-extension MIT-SHM",
        "CODE_ARGS": shlex.join(code_arguments(profile)),
        "CODE_GUARD": indent(CODE_GUARD.rstrip("\n"), "    "),
    }
    template = (ASSETS / "standalone-code/launch.sh").read_text(encoding="utf-8")
    return re.sub(r"@([A-Z][A-Z0-9_]+)@", lambda m: values[m[1]], template)


def shortcut(prefix, home, root, profile, writer, args):
    for executable, package in (
        ("bash", "bash"), ("flock", "util-linux"), ("am", "termux-am"),
        ("proot-distro", "proot-distro"), ("termux-x11", "termux-x11-nightly"), ("xprop", "xorg-xprop"),
    ):
        if not (prefix / "bin" / executable).is_file():
            hint = " Enable the X11 repository with pkg install x11-repo first." if executable in ("termux-x11", "xprop") else ""
            raise ValueError(f"Missing {executable}. Run pkg install {package}.{hint}")
    needed = ["/usr/bin/dbus-run-session", "/usr/bin/xfwm4", "/usr/bin/xprop", "/usr/share/code/code"]
    if profile["gpu_backend"] == "freedreno-kgsl":
        needed.append("/usr/local/bin/tablet-gpu-run")
    if any(not (root / name.lstrip("/")).is_file() for name in needed):
        raise ValueError("Guest Code or window components are missing. Review desktop-plan with --apps code and desktop-setup.md.")
    script = render_launcher(prefix, profile, args.display)
    icon = (root / "usr/share/code/resources/app/resources/linux/code.png").read_bytes()
    if not icon.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("The installed Code icon is invalid")
    shortcuts = scoped_path(home / ".shortcuts", home)
    entry = scoped_path(shortcuts / "tasks/VS Code", shortcuts)
    image = scoped_path(shortcuts / "icons/VS Code.png", shortcuts)
    if entry.is_file():
        old = entry.read_text(encoding="utf-8")
        if "# Managed by standalone_code.py" not in old and not all(
            value in old for value in ("vscode-standalone", "tag=vscode", "tablet-vscode")
        ):
            raise ValueError("The existing VS Code shortcut belongs to another launcher")
    if args.apply:
        import fcntl

        run([prefix / "bin/bash", "-n"], script=script, timeout=8)
        lock = scoped_path(home / ".local/state/tablet-desktop/vscode-standalone/session.lock", home)
        lock.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with lock.open("a") as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ValueError("Close the standalone Code window normally before updating its shortcut") from error
            for directory in (shortcuts, entry.parent, image.parent):
                directory.mkdir(mode=0o700, exist_ok=True)
            writer.put(image, icon, 0o600)
            writer.put(entry, script, 0o700)
    return {"shortcut": str(entry), "display": ":" + str(int(args.display[1:])),
            "graphics": "freedreno-kgsl" if profile["gpu_backend"] == "freedreno-kgsl" else "software"}


def extension_registry(base):
    state = base / "extensions/extensions.json"
    if not state.is_file():
        return {}
    return {record["identifier"]["id"].lower(): record for record in json.loads(state.read_text(encoding="utf-8"))}


def extension_manifest(base, record):
    location = record["relativeLocation"]
    if not isinstance(location, str) or not re.fullmatch(r"[a-zA-Z0-9_.-]+", location) or location in (".", ".."):
        raise ValueError("Invalid extension registry path")
    directory = base / "extensions" / location
    if directory.resolve().parent != (base / "extensions").resolve():
        raise ValueError("Extension registry path leaves the isolated profile")
    return json.loads((directory / "package.json").read_text(encoding="utf-8"))


def office_claims(package):
    if package is None:
        return OFFICE_TYPES, OFFICE_EXTRAS, {"cweijan.officeViewer", "cweijan.markdownViewer", "cweijan.archiveViewer",
                                           "cweijan.classViewer", "cweijan.imageViewer", "cweijan.htmlViewer", "cweijan.parquetViewer"}
    allowed, extra, editors = set(), set(), set()
    for editor in package["contributes"]["customEditors"]:
        view = editor["viewType"]
        editors.add(view)
        priority = editor.get("priority", "default")
        if priority == "option":
            continue
        if priority not in ("default", "builtin"):
            raise ValueError(f"Review the new Office Viewer priority for {view}")
        for selector in editor["selector"]:
            pattern = selector["filenamePattern"]
            match = re.fullmatch(r"(?:[\w-]+:/\*\*/)?\*\.([a-zA-Z0-9.]+)", pattern)
            if not match:
                raise ValueError(f"Review the new Office Viewer selector: {pattern}")
            suffix = match[1].lower()
            if view == "cweijan.officeViewer" and suffix in OFFICE_TYPES:
                allowed.add(suffix)
            else:
                extra.add(suffix)
    return allowed, extra, editors


def office_settings(source, package, pdf):
    current = parse_settings(source)[0].get(EDITOR_SETTING, {})
    if not isinstance(current, dict) or any(not isinstance(value, str) for value in current.values()):
        raise ValueError("VS Code editor associations must map patterns to editor IDs")
    allowed, extra, editors = office_claims(package)
    office = {"*." + suffix for suffix in allowed}
    updated = {key: value for key, value in current.items() if value not in editors or key in office}
    for key in sorted(office):
        updated.setdefault(key, "cweijan.officeViewer")
    pdf_view = "default"
    if pdf and any(editor["viewType"] == "pdf.view" for editor in pdf.get("contributes", {}).get("customEditors", [])):
        pdf_view = "pdf.view"
    for suffix in sorted(extra):
        updated.setdefault("*." + suffix, pdf_view if suffix == "pdf" else "default")
    return merge_settings(source, {EDITOR_SETTING: updated})


def guest_env(prefix, profile, base):
    return [prefix / "bin/proot-distro", "login", profile["container"], "--user", profile["user"], "--shared-tmp", "--",
            "/usr/bin/env", "-u", "ELECTRON_RUN_AS_NODE", "-u", "VSCODE_IPC_HOOK_CLI",
            "-u", "XDG_CURRENT_DESKTOP", "-u", "DESKTOP_SESSION", "-u", "BROWSER",
            f"XDG_CONFIG_HOME={base}/config", f"XDG_DATA_HOME={base}/data", f"XDG_CACHE_HOME={base}/cache"]


def extensions(base, guest_base, guest, writer, args):
    requested = list(dict.fromkeys(value.lower() for value in args.ids))
    if any(not re.fullmatch(r"[\w-]+\.[\w-]+(?:@[0-9][\w.-]*)?", name, re.ASCII) for name in requested):
        raise ValueError("Use Marketplace IDs such as openai.chatgpt or an ID followed by @version")
    office = [name for name in requested if name.split("@")[0] == OFFICE_ID]
    if len(office) > 1 or (office and "@" in office[0] and office[0] != f"{OFFICE_ID}@{OFFICE_VERSION}"):
        raise ValueError(f"The reviewed Office Viewer install is {OFFICE_ID}@{OFFICE_VERSION}; use the unversioned ID to scope an existing installation")
    installed = extension_registry(base)
    if office and "@" in office[0] and OFFICE_ID in installed and installed[OFFICE_ID]["version"] != OFFICE_VERSION:
        raise ValueError(f"Use the unversioned {OFFICE_ID} to scope the installed release")
    plan = {"requested": requested, "installed": {name: record["version"] for name, record in installed.items()},
            "office_associations": "office files only" if office else None}
    if not args.apply or not requested:
        return plan
    code = guest + ["/usr/bin/code", "--no-sandbox", "--user-data-dir", f"{guest_base}/code",
                    "--extensions-dir", f"{guest_base}/extensions"]
    for name in requested:
        if name not in office:
            run(code + ["--install-extension", name], timeout=180)
    if office:
        installed = extension_registry(base)
        path = scoped_path(base / "code/User/settings.json", base)
        old = path.read_bytes() if path.is_file() else None
        mode = path.stat().st_mode & 0o777 if old is not None else 0o600
        source = old.decode("utf-8") if old is not None else "{}\n"
        pdf = extension_manifest(base, installed[PDF_ID]) if PDF_ID in installed else None
        package = extension_manifest(base, installed[OFFICE_ID]) if OFFICE_ID in installed else None
        # Set the association policy before the extension can start in a live editor.
        configured = office_settings(source, package, pdf).encode("utf-8")
        writer.put(path, configured, mode)
        if package is None:
            try:
                run(code + ["--install-extension", f"{OFFICE_ID}@{OFFICE_VERSION}"], timeout=180)
            except (RuntimeError, OSError, subprocess.SubprocessError):
                if OFFICE_ID not in extension_registry(base):
                    replace_config_if_current(path, configured, old, mode)
                raise
            record = extension_registry(base).get(OFFICE_ID)
            if not record:
                replace_config_if_current(path, configured, old, mode)
                raise ValueError("Office Viewer did not appear in the extension registry")
            if record["version"] != OFFICE_VERSION:
                raise ValueError("Office Viewer version did not match the reviewed association policy")
            package = extension_manifest(base, record)
            confirmed = office_settings(source, package, pdf).encode("utf-8")
            if confirmed != configured:
                if not replace_config_if_current(path, configured, confirmed, mode):
                    raise ValueError("Code settings changed during Office Viewer setup")
    installed = extension_registry(base)
    for name in requested:
        identifier, _, version = name.partition("@")
        if identifier not in installed or version and installed[identifier]["version"] != version:
            raise ValueError(f"Extension readback did not match {name}")
    plan["installed"] = {name: record["version"] for name, record in installed.items()}
    return plan


def update_http_default(source, desktop):
    source = source.replace("\r\n", "\n")
    line = f"x-scheme-handler/http={desktop};"
    section = re.compile(r"(?m)^[ \t]*\[Default Applications\][ \t]*$")
    header = section.search(source)
    if not header:
        return source.rstrip("\n") + ("\n\n" if source else "") + "[Default Applications]\n" + line + "\n"
    following = re.search(r"(?m)^[ \t]*\[", source[header.end():])
    end = header.end() + following.start() if following else len(source)
    body = source[header.end():end]
    key = re.compile(r"(?m)^[ \t]*x-scheme-handler/http[ \t]*=.*$")
    if len(key.findall(body)) > 1 or len(section.findall(source)) > 1:
        raise ValueError("Duplicate HTTP defaults require review")
    body = key.sub(line, body) if key.search(body) else "\n" + line + (body or "\n")
    return source[:header.end()] + body + source[end:]


def chrome(prefix, root, base, guest_base, guest, writer, args):
    if not (prefix / "bin/am").is_file():
        raise ValueError("Missing Android Intent launcher. Run pkg install termux-am in native Termux.")
    if any(not (root / "usr/bin" / exe).is_file() for exe in ("gio", "xdg-mime", "python3")):
        raise ValueError("Missing guest browser helpers. Run apt-get install libglib2.0-bin xdg-utils python3 in Debian.")

    def http_default():
        return run(guest + ["/usr/bin/xdg-mime", "query", "default", "x-scheme-handler/http"], timeout=8).stdout.strip()

    default = http_default()
    opener = scoped_path(base / "bin/open-android-chrome-preview", base)
    desktop = scoped_path(base / "data/applications" / CHROME_ENTRY, base)
    config = scoped_path(base / "config/mimeapps.list", base)
    entry = ("[Desktop Entry]\nType=Application\nName=Android Chrome Local Preview\n"
             f"Exec={guest_base}/bin/{opener.name} %u\nNoDisplay=true\nTerminal=false\n"
             "MimeType=x-scheme-handler/http;\nCategories=Network;WebBrowser;\n")
    if default == CHROME_ENTRY:
        if not (opener.is_file() and desktop.is_file() and desktop.read_text(encoding="utf-8") == entry and
                "com.android.chrome" in opener.read_text(encoding="utf-8") and os.access(opener, os.X_OK)):
            raise ValueError("The existing Android Chrome preview entry is incomplete")
        return {"http_handler": default, "already_configured": True}
    if not re.fullmatch(r"[a-zA-Z0-9_.-]+\.desktop", default):
        raise ValueError("Set the isolated profile's Linux HTTP handler before adding the local-only Chrome route")
    candidates = [f"{guest_base}/data/applications", "/usr/local/share/applications", "/usr/share/applications"]
    fallback = next((f"{where}/{default}" for where in candidates if (root / where.lstrip("/") / default).is_file()), None)
    if fallback is None:
        raise ValueError(f"Cannot resolve the existing Linux browser entry {default}")
    launcher = (ASSETS / "standalone-code/open-android-chrome-preview.py").read_text(encoding="utf-8")
    launcher = launcher.replace("@AM@", repr(str(prefix / "bin/am"))).replace("@FALLBACK@", repr(fallback))
    old = config.read_bytes() if config.is_file() else None
    mode = config.stat().st_mode & 0o777 if old is not None else 0o600
    source = old.decode("utf-8") if old is not None else ""
    preferred = update_http_default(source, CHROME_ENTRY)
    if args.apply:
        compile(launcher, str(opener), "exec")
        writer.put(opener, launcher, 0o700)
        writer.put(desktop, entry)
        writer.put(config, preferred, mode)
        try:
            if http_default() != CHROME_ENTRY:
                raise ValueError("The Android Chrome preview entry did not become the HTTP handler")
        except (ValueError, RuntimeError, OSError, subprocess.SubprocessError):
            replace_config_if_current(config, preferred.encode("utf-8"), old, mode)
            raise
    return {"http_handler": CHROME_ENTRY, "remote_http_handler": fallback}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    launch = sub.add_parser("launcher", help="create the Termux:Widget script for the independent window")
    launch.add_argument("--display", default=":2")
    plugins = sub.add_parser("extensions", help="install selected extensions in the isolated Code profile")
    plugins.add_argument("ids", nargs="*")
    browser = sub.add_parser("android-chrome", help="send loopback HTTP preview URLs to Android Chrome")
    for command in (launch, plugins, browser):
        command.add_argument("--apply", action="store_true", help="apply the previewed changes")
    args = parser.parse_args(argv)
    try:
        prefix, home = require_termux()
        profile = load_profile(home / ".config/tablet-desktop/config.json")
        root = guest_root(prefix, profile["container"])
        guest_base = f"/home/{profile['user']}/{PROFILE_DIR}"
        base = root / guest_base.lstrip("/")
        if not root.is_dir() or base.is_symlink() or not base.resolve().is_relative_to(root.resolve()):
            raise ValueError("The configured Debian rootfs or standalone profile path is unavailable")
        writer = Writer(home, prefix, root)
        if args.action == "launcher":
            result = shortcut(prefix, home, root, profile, writer, args)
        else:
            guest = guest_env(prefix, profile, guest_base)
            if args.action == "extensions":
                result = extensions(base, guest_base, guest, writer, args)
            else:
                result = chrome(prefix, root, base, guest_base, guest, writer, args)
        print(json.dumps({"applied": args.apply, "profile_sha256": profile_digest(profile), **result,
                          "changed": writer.changed, "backup": str(writer.backup) if writer.backup.exists() else None},
                         ensure_ascii=False))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
