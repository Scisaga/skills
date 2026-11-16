#!/usr/bin/env python3
"""Plan/install the optional desktop. Native SSH bootstrap remains independent."""
from __future__ import annotations

import argparse
import datetime
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

from desktop_profile import ASSETS, guest_root, load_profile, profile_digest
from jsonc_settings import merge as merge_code_settings
from desktop_gpu_bundle import install_bundle, installed_driver_ready, DRIVER_ROOT
from desktop_video_bundle import install_video, VLC_ROOT
from managed_context import migrate_legacy_ssh_rule, replace_block


def run(args, *, script=None, check=True, timeout=None):
    p = subprocess.run([str(x) for x in args], input=script, stdin=None if script is not None else subprocess.DEVNULL, text=True, encoding="utf-8",
                       errors="replace", capture_output=True, timeout=timeout)
    if check and p.returncode:
        raise RuntimeError(f"Command failed: {args[0]} (exit {p.returncode})\n{(p.stderr or p.stdout)[-1600:]}")
    return p


def require_termux() -> tuple[Path, Path]:
    prefix = Path(os.environ.get("PREFIX", "/data/data/com.termux/files/usr"))
    if sys.platform not in ("linux", "android") or not str(prefix).endswith("/com.termux/files/usr") or not Path("/system/bin/getprop").exists():
        raise RuntimeError("This native installer/service diagnostic requires native Termux; inspect Xfce menus and settings in the current Xfce UI or terminal")
    return prefix, Path.home()


class Writer:
    def __init__(self, home: Path, prefix: Path, root: Path):
        self.prefix = prefix
        self.allowed = [p.resolve() for p in (home, prefix, root)]
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        self.backup = home / ".local/state/tablet-desktop/backups" / stamp
        self.changed = []

    def put(self, path: Path, content: str | bytes, mode=0o644):
        resolved = path.resolve()
        if not any(resolved.is_relative_to(base) for base in self.allowed):
            raise ValueError(f"Write escapes intended desktop directories: {path}")
        data = content.replace("\r\n", "\n").encode("utf-8") if isinstance(content, str) else content
        if path.exists() and path.read_bytes() == data:
            path.chmod(mode)
            return
        if path.exists():
            destination = self.backup / str(path).lstrip("/:").replace(":", "_")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            destination.chmod(0o600)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".termux-new")
        tmp.write_bytes(data)
        tmp.chmod(mode)
        tmp.replace(path)
        if path.read_bytes() != data:
            raise RuntimeError(f"Write readback failed; inspect the retained backup: {path}")
        self.changed.append(str(path))


def property_(parent, name, kind, value=None):
    node = parent.find(f"property[@name='{name}']")
    if node is None:
        node = ET.SubElement(parent, "property", name=name)
    node.set("type", kind)
    if isinstance(value, (list, tuple)):
        node[:] = []
        for item in value:
            ET.SubElement(node, "value", type="int" if isinstance(item, int) else "string", value=str(item))
    elif value is not None:
        node.set("value", str(value).lower() if isinstance(value, bool) else str(value))
    return node


def channel(root: Path, user: str, name: str):
    path = root / f"home/{user}/.config/xfce4/xfconf/xfce-perchannel-xml/{name}.xml"
    tree = ET.parse(path) if path.exists() else ET.ElementTree(ET.Element("channel", name=name, version="1.0"))
    return path, tree


def desktop_entry(name, command, icon, categories="Utility;", extra=""):
    return (f"[Desktop Entry]\nVersion=1.0\nType=Application\nName={name}\nExec={command}\n"
            f"Icon={icon}\nTerminal=false\nStartupNotify=false\nCategories={categories}\n{extra}")


def configure_xfce_pointer(root, user, enabled, writer):
    path, tree = channel(root, user, "xfce4-session")
    original = ET.tostring(tree.getroot())
    defaults = root / "etc/xdg/xfce4/xfconf/xfce-perchannel-xml/xfce4-session.xml"
    base = ET.parse(defaults).getroot() if defaults.exists() else tree.getroot()
    candidates = {}
    for source in (base, tree.getroot()):
        node = source.find("property[@name='sessions']/property[@name='Failsafe']")
        if node is not None:
            for command in node.findall("property"):
                if command.get('name', '').endswith('_Command'):
                    # Xfconf persists inherited default nodes as type=empty.
                    if command.get('type') == 'empty' and not command.findall('value'):
                        continue
                    candidates[command.get('name')] = [v.get('value') for v in command.findall('value')]
    roles = {'xfce4-panel': 'panel', 'xfdesktop': 'desktop'}
    found = set()
    for name, command in candidates.items():
        if not command or not isinstance(command[0], str):
            continue
        if command[0] == '/usr/local/bin/tablet-thunar-core':
            executable = None
            replacement = command if enabled else ['Thunar', *command[1:]]
        elif Path(command[0]).name.lower() == 'thunar':
            if not enabled:
                continue
            executable = None
            replacement = ['/usr/local/bin/tablet-thunar-core', *command[1:]]
        elif command[0] == '/usr/local/bin/tablet-xfce-pointer' and len(command) >= 2:
            role = command[1]
            executable = next((name for name, value in roles.items() if value == role), None)
            if not executable:
                continue
            replacement = command if enabled else [executable, *command[2:]]
        elif command[0] in roles or command[0] in ('/usr/bin/xfce4-panel', '/usr/bin/xfdesktop'):
            executable = Path(command[0]).name
            if not enabled:
                continue
            replacement = ['/usr/local/bin/tablet-xfce-pointer', roles[executable], *command[1:]]
        else:
            continue
        if executable is not None:
            found.add(executable)
        sessions = property_(tree.getroot(), 'sessions', 'empty')
        failsafe = property_(sessions, 'Failsafe', 'empty')
        property_(failsafe, name, 'array', replacement)
    if enabled and found != set(roles):
        raise RuntimeError('Custom Xfce startup entries are missing panel/desktop; review the session before enabling touch_long_press')
    if ET.tostring(tree.getroot()) != original:
        writer.put(path, ET.tostring(tree.getroot(), encoding='unicode') + '\n')


def active_container_roots(prefix: Path, root: Path, container: str):
    """Read-only maintenance guard, including desktops not yet using our controller."""
    live = set()
    for record in (prefix / "var/lib/proot-distro/sessions").glob("*.json"):
        try:
            entry = json.loads(record.read_text(encoding="utf-8"))
            pid = int(entry["pid"])
            if entry.get("container") == container and Path(f"/proc/{pid}").exists(): live.add(pid)
        except (OSError, ValueError, KeyError): pass
    proc = Path("/proc")
    if proc.is_dir():
        for directory in proc.glob("[0-9]*"):
            try:
                if directory.stat().st_uid != os.getuid(): continue
                command = (directory / "cmdline").read_bytes().split(b'\0')
                if not command or not command[0].endswith(b'/proot'): continue
                cwd = (directory / "cwd").resolve()
                root_bytes = str(root).encode()
                if cwd == root.resolve() or any(arg in (root_bytes, b'--rootfs=' + root_bytes) for arg in command): live.add(int(directory.name))
            except (OSError, ValueError): pass
    return sorted(live)


def configure_guest(root: Path, native_home: Path, p: dict, writer: Writer):
    user = p["user"]
    home = root / "home" / user
    native = str(native_home)
    configure_xfce_pointer(root, user, p['touch_long_press'], writer)
    for src in (ASSETS / "guest").iterdir():
        if src.name == "install-packages.sh" or not src.is_file():
            continue
        data = src.read_text(encoding="utf-8").replace("/data/data/com.termux/files/home", native)
        data = data.replace("/home/developer", f"/home/{user}").replace("runtime-developer", "runtime-" + user)
        data = data.replace("DISPLAY=:1", "DISPLAY=" + p["display"])
        data = data.replace("LANG=en_US.UTF-8 TZ=Asia/Shanghai", f"LANG={p['language']} TZ={p['timezone']}")
        if not p["software_rendering"]:
            data = data.replace("export GDK_GL=disable LIBGL_ALWAYS_INDIRECT=1 NO_AT_BRIDGE=1", "export NO_AT_BRIDGE=1")
        if src.name == 'tablet-thunar-core' and not p['touch_long_press']:
            data = data.replace('export GDK_CORE_DEVICE_EVENTS=1', 'unset GDK_CORE_DEVICE_EVENTS')
        if src.name == "tablet-desktop-session":
            if "chromium" not in p["applications"]:
                data = data.replace("export BROWSER=/usr/local/bin/chromium-tablet\n", "")
            data = data.replace("export LANG=", f"export GDK_SCALE={p['scale']} GDK_DPI_SCALE=1\nexport LANG=", 1)
        location = "usr/local/share/tablet-desktop/" + src.name if src.suffix == ".c" else ("usr/local/lib/tablet-desktop/ipc.py" if src.name == "ipc.py" else "usr/local/bin/" + src.name)
        writer.put(root / location, data, 0o644 if src.name == "ipc.py" or src.suffix == ".c" else 0o755)
    if p['touch_long_press'] and any((root / 'usr/share/applications' / n).is_file() for n in ('thunar.desktop', 'org.xfce.Thunar.desktop')):
        from thunar_core import launcher_files
        for path, text in launcher_files(root, home).items():
            writer.put(path, text)
    software = "unset GDK_CORE_DEVICE_EVENTS\n" + ("export GDK_GL=disable LIBGL_ALWAYS_INDIRECT=1 NO_AT_BRIDGE=1\n" if p["software_rendering"] else "")
    hardware = p["gpu_backend"] in ("virgl-android", "freedreno-kgsl")
    gpu = " --disable-gpu" if p["software_rendering"] and not hardware else ""
    runner = "/usr/local/bin/tablet-gpu-run " if hardware else ""
    code_angle = " --use-gl=angle --use-angle=gles" if p.get("code_angle_backend") == "gles" else ""
    qt_scale = f"export QT_AUTO_SCREEN_SCALE_FACTOR=0 QT_SCALE_FACTOR={p['scale']}\n"
    wrappers = {
        "code": ("code-tablet", f'exec {runner}/usr/bin/code --no-sandbox{gpu} --disable-dev-shm-usage --ozone-platform=x11{code_angle} "$@"'),
        "chromium": ("chromium-tablet", f'exec {runner}/usr/bin/chromium --no-sandbox{gpu} --disable-dev-shm-usage --ozone-platform=x11 --force-device-scale-factor={p["scale"]} --no-first-run --no-default-browser-check "$@"'),
        "office": ("libreoffice-tablet", 'export SAL_USE_VCLPLUGIN=gtk3\nexec /usr/bin/libreoffice "$@"'),
        "vlc": ("vlc-tablet", qt_scale + ('exec /usr/bin/vlc --avcodec-hw=none --vout=xcb_x11 "$@"' if p["software_rendering"] else 'exec /usr/bin/vlc "$@"')),
    }
    if p["browser_backend"] == "termux-zink":
        guest_browser = wrappers["chromium"][1]
        writer.put(root / "usr/local/bin/chromium-tablet-guest", "#!/bin/sh\n" + software + guest_browser + "\n", 0o755)
        wrappers["chromium"] = ("chromium-tablet", 'exec /usr/local/bin/tablet-native-browser "$@"')
        writer.put(home / ".local/share/applications/chromium-tablet-guest.desktop",
                   desktop_entry("Chromium（兼容版）", "/usr/local/bin/chromium-tablet-guest %U", "chromium", "Network;WebBrowser;"), 0o755)
    if p["office_backend"] == "native-gtk3":
        writer.put(root / "usr/local/bin/libreoffice-tablet-guest", "#!/bin/sh\n" + software + wrappers["office"][1] + "\n", 0o755)
        wrappers["office"] = ("libreoffice-tablet", 'exec /usr/local/bin/tablet-native-office "$@"')
    if p["media_backend"] == "termux-va":
        writer.put(root / "usr/local/bin/vlc-tablet-guest", "#!/bin/sh\n" + software + wrappers["vlc"][1] + "\n", 0o755)
        wrappers["vlc"] = ("vlc-tablet", qt_scale + 'exec /usr/local/bin/tablet-video-run "$@"')
    for app in p["applications"]:
        name, body = wrappers[app]
        writer.put(root / "usr/local/bin" / name, "#!/bin/sh\n" + software + body + "\n", 0o755)
        if hardware and app in ("code", "chromium") and not (app == "chromium" and p["browser_backend"] == "termux-zink"):
            fallback = body.replace(runner, "", 1).replace(" --no-sandbox", " --no-sandbox --disable-gpu", 1)
            if app == "code" and code_angle:
                fallback = fallback.replace(code_angle, "", 1)
            writer.put(root / "usr/local/bin" / (name + "-software"), "#!/bin/sh\nexport GDK_GL=disable LIBGL_ALWAYS_INDIRECT=1 NO_AT_BRIDGE=1\n" + fallback + "\n", 0o755)
    entries = [
        ("EndDesktop", "结束桌面", "/usr/local/bin/tablet-desktop-end", "xfsm-logout", "System;X-XFCE;X-Xfce-Toplevel;"),
        ("TouchMode", "触控模式⇄", "/usr/local/bin/tablet-touch-toggle", "input-touchpad", "Settings;"),
    ]
    app_entries = {
        "code": [("VSCode", "VS Code", "/usr/local/bin/code-tablet %F", "visual-studio-code", "Development;IDE;")],
        "chromium": [("Chromium", "Chromium", "/usr/local/bin/chromium-tablet %U", "chromium", "Network;WebBrowser;")],
        "office": [("Writer", "Writer", "/usr/local/bin/libreoffice-tablet --writer %U", "libreoffice-writer", "Office;WordProcessor;"),
                   ("Calc", "Calc", "/usr/local/bin/libreoffice-tablet --calc %U", "libreoffice-calc", "Office;Spreadsheet;"),
                   ("Impress", "Impress", "/usr/local/bin/libreoffice-tablet --impress %U", "libreoffice-impress", "Office;Presentation;")],
        "vlc": [("VLC", "VLC", "/usr/local/bin/vlc-tablet %U", "vlc", "AudioVideo;Player;")],
    }
    for app in p["applications"]:
        entries.extend(app_entries[app])
    text_by_key = {}
    names = {"EndDesktop": "tablet-desktop-end", "TouchMode": "tablet-touch-toggle", "Chromium": "chromium-tablet"}
    for key, label, command, icon, categories in entries:
        extra = "X-Tablet-Touch-Control=true\n" if key == "TouchMode" else ""
        if key == "Chromium": extra += "MimeType=text/html;x-scheme-handler/http;x-scheme-handler/https;\n"
        if key == "VSCode": extra += "StartupWMClass=Code\n"
        text = desktop_entry(label, command, icon, categories, extra)
        text_by_key[key] = text
        writer.put(home / "Desktop" / (key + ".desktop"), text, 0o755)
        # The standard logout desktop ID is the sole menu entry; keep this alias for compatibility.
        menu_text = text + "NoDisplay=true\n" if key == "EndDesktop" else text
        writer.put(home / ".local/share/applications" / (names.get(key, "tablet-" + key.lower()) + ".desktop"), menu_text, 0o755)
    writer.put(home / ".local/share/applications/xfce4-session-logout.desktop", text_by_key["EndDesktop"], 0o755)
    # Shadow distro desktop IDs too, so MIME/Open With requests use the same wrappers.
    import re
    redirects = []
    if "code" in p["applications"]:
        redirects.append(("code.desktop", "/usr/local/bin/code-tablet %F", False))
    if "office" in p["applications"] and p["office_backend"] == "native-gtk3":
        redirects += [("libreoffice-" + mode + ".desktop", "/usr/local/bin/libreoffice-tablet --" + mode + " %U", True)
                      for mode in ("writer", "calc", "impress")]
    if "vlc" in p["applications"] and p["media_backend"] == "termux-va":
        redirects.append(("vlc.desktop", "/usr/local/bin/vlc-tablet %U", True))
    for name, command, native_bridge in redirects:
        system = root / "usr/share/applications" / name
        if not system.is_file():
            continue
        text = re.sub(r"(?m)^Exec=.*$", lambda _: "Exec=" + command, system.read_text(encoding="utf-8"), count=1)
        text = re.sub(r"(?m)^TryExec=.*\n?", "", text)
        writer.put(home / ".local/share/applications" / name, text, 0o644)
        if native_bridge:
            native_command = '/usr/local/bin/tablet-session-open-vlc %U' if name == 'vlc.desktop' else command
            bridge = str(writer.prefix / "bin/proot-distro") + " login " + p["container"] + " --user " + user + " --shared-tmp -- " + native_command
            writer.put(native_home / ".local/share/applications" / name,
                       re.sub(r"(?m)^Exec=.*$", lambda _: "Exec=" + bridge, text, count=1), 0o644)
    for src in (ASSETS / "icons").glob("*.svg"):
        writer.put(home / ".local/share/icons" / src.name, src.read_bytes())
    for src in (ASSETS / "theme/xfwm4").iterdir():
        if src.is_file(): writer.put(home / ".themes/Tablet-Touch/xfwm4" / src.name, src.read_bytes())
    for filename in ("COPYING", "NOTICE"):
        writer.put(home / ".themes/Tablet-Touch" / filename, (ASSETS / "theme" / filename).read_bytes())
    auto = home / ".config/autostart"
    writer.put(auto / "tablet-controller.desktop", desktop_entry("Desktop session registration", "/usr/local/bin/tablet-session-ready", "computer", extra="OnlyShowIn=XFCE;\nNoDisplay=true\n"))
    writer.put(auto / "tablet-touch-state.desktop", desktop_entry("Touch state", "/usr/local/bin/tablet-touch-toggle status --quiet", "input-touchpad", extra="OnlyShowIn=XFCE;\nNoDisplay=true\n"))
    writer.put(auto / "tablet-panel-edge.desktop", desktop_entry("Tablet dock edge", "/usr/local/bin/tablet-panel-edge", "xfce4-panel", extra="OnlyShowIn=XFCE;\nNoDisplay=true\nHidden=" + str(not (p["dock_autohide"] and p["dock_hide_indicator"] and not p['window_compositing'])).lower() + "\n"))
    writer.put(auto / "tablet-touch-longpress.desktop", desktop_entry("Tablet touch secondary click",
               f"/usr/local/bin/tablet-touch-longpress --hold-ms {p['touch_long_press_ms']} --move-px {p['touch_long_press_move_px']}",
               "input-touchscreen", extra="OnlyShowIn=XFCE;\nNoDisplay=true\nHidden=" + str(not p['touch_long_press']).lower() + "\n"))
    if p["code_autostart"] and "code" in p["applications"]:
        writer.put(auto / "tablet-code.desktop", desktop_entry("VS Code", f"/usr/local/bin/code-tablet /home/{user}/workspaces", "visual-studio-code"))
    elif (auto / "tablet-code.desktop").exists():
        writer.put(auto / "tablet-code.desktop", "[Desktop Entry]\nType=Application\nName=VS Code\nHidden=true\n")
    old_auto = auto / "vscode.desktop"
    if old_auto.exists() and "/usr/local/bin/code-tablet" in old_auto.read_text(encoding="utf-8"):
        writer.put(old_auto, "[Desktop Entry]\nType=Application\nName=VS Code (legacy)\nHidden=true\n")
    if "code" in p["applications"]:
        path = home / ".config/Code/User/settings.json"
        settings = path.read_text(encoding="utf-8") if path.exists() else "{}\n"
        updates = {"editor.fontFamily": p["monospace_font"] + ", monospace", "editor.fontSize": p["editor_font_size"],
                         "editor.scrollbar.verticalScrollbarSize": p["scrollbar_size"], "editor.scrollbar.horizontalScrollbarSize": p["scrollbar_size"],
                         "editor.minimap.maxColumn": 80, "window.titleBarStyle": "custom", "window.zoomLevel": 0,
                         "workbench.reduceMotion": "on",
                         "terminal.integrated.defaultProfile.linux": "bash"}
        writer.put(path, merge_code_settings(settings, updates), 0o600)
    for name, values in {
        "xsettings": {"Net": {"ThemeName": ("string", p["theme"]), "IconThemeName": ("string", p["icons"])},
                      "Gtk": {"FontName": ("string", f"{p['font']} {p['font_size']}"), "MonospaceFontName": ("string", f"{p['monospace_font']} {p['font_size']}"),
                              "CursorThemeSize": ("int", p["cursor_size"]), "CursorThemeName": ("string", p["cursor_theme"])},
                      "Gdk": {"WindowScalingFactor": ("int", p["scale"])},
                      "Xft": {"DPI": ("int", p["dpi"]), "Antialias": ("int", 1), "HintStyle": ("string", "hintslight")}},
        "xfwm4": {"general": {"theme": ("string", p["titlebar_theme"]), "title_font": ("string", f"{p['font']} Bold {p['font_size']}"),
                              "use_compositing": ("bool", p['window_compositing']), "vblank_mode": ("string", p['window_vblank_mode']),
                              "show_frame_shadow": ("bool", p['window_shadows']), "show_dock_shadow": ("bool", p['window_shadows']),
                              "button_layout": ("string", "O|HMC")}},
        "xfce4-desktop": {"desktop-icons": {"icon-size": ("uint", 52)}},
    }.items():
        path, tree = channel(root, user, name)
        for group, props in values.items():
            parent = property_(tree.getroot(), group, "empty")
            for key, (kind, value) in props.items(): property_(parent, key, kind, value)
        writer.put(path, ET.tostring(tree.getroot(), encoding="unicode"))
    panel_path, tree = channel(root, user, "xfce4-panel")
    top = tree.getroot()
    property_(top, "configver", "int", 2)
    panels = property_(top, "panels", "array", [1, 2])
    property_(panels, "dark-mode", "bool", True)
    plugins = property_(top, "plugins", "empty")
    top_ids = [1, 2, 3, 4, 5, 6, 7, 25, 23, 8, 9, 24]
    for n, size, length, pos, ids in [(1, 40, 100, "p=6;x=0;y=0", top_ids), (2, 52, 1, "p=10;x=0;y=0", [])]:
        pan = property_(panels, f"panel-{n}", "empty")
        for key, kind, value in [("size", "uint", size), ("icon-size", "uint", 28 if n == 1 else 40), ("length", "uint", length),
                                 ("position", "string", pos), ("position-locked", "bool", True), ("output-name", "string", p["dock_output"])]:
            property_(pan, key, kind, value)
        if n == 1: property_(pan, "plugin-ids", "array", ids)
        else:
            property_(pan, "autohide-behavior", "uint", 2 if p["dock_autohide"] else 0)
            property_(pan, "popdown-speed", "uint", 0)
    for i, kind in [(1, "applicationsmenu"), (2, "tasklist"), (3, "separator"), (4, "pager"), (5, "separator"), (6, "systray"), (7, "separator"), (8, "clock"), (9, "separator"), (11, "showdesktop"), (12, "separator"), (17, "separator"), (18, "directorymenu"), (23, "genmon")]:
        node = property_(plugins, f"plugin-{i}", "string", kind)
        if i == 3: property_(node, "expand", "bool", True)
        if kind == "separator": property_(node, "style", "uint", 0)
        if i == 18: property_(node, "base-directory", "string", f"/home/{user}")
    launchers = [(22, "TouchMode", "tablet-touch.desktop"), (24, "EndDesktop", "tablet-end.desktop"), (25, "TouchMode", "tablet-touch.desktop")]
    app_ids = {"Chromium": 13, "VSCode": 16, "Writer": 19, "Calc": 20, "Impress": 21, "VLC": 15}
    dock_ids = [11, 12]
    for key, n in app_ids.items():
        if key in text_by_key:
            launchers.append((n, key, "tablet-" + key.lower() + ".desktop")); dock_ids.append(n)
    dock_ids.extend([22, 17, 18])
    property_(panels.find("property[@name='panel-2']"), "plugin-ids", "array", dock_ids)
    for n, key, filename in launchers:
        node = property_(plugins, f"plugin-{n}", "string", "launcher")
        property_(node, "items", "array", [filename])
        writer.put(home / f".config/xfce4/panel/launcher-{n}" / filename, text_by_key[key], 0o755)
    writer.put(panel_path, ET.tostring(top, encoding="unicode"))
    writer.put(home / ".config/xfce4/panel/genmon-23.rc", f"Command=/usr/local/bin/tablet-desktop-battery\nUseLabel=0\nUpdatePeriod=60000\nFont={p['font']} {p['font_size']}\n", 0o600)
    css = home / ".config/gtk-3.0/gtk.css"
    old = css.read_text(encoding="utf-8") if css.exists() else ""
    for block in ("tablet touch", "tablet hidden dock"):
        begin, end = f"/* BEGIN {block} */", f"/* END {block} */"
        if begin in old and end in old: old = old[:old.index(begin)] + old[old.index(end) + len(end):]
    contents = (old.strip("\r\n") + "\n\n") if old.strip("\r\n") else ""
    contents += "/* BEGIN tablet touch */\nmenu > menuitem { min-height: 28px; padding: 7px 12px; }\n.xfce4-panel button { min-width: 36px; padding-left: 5px; padding-right: 5px; }\n/* END tablet touch */\n"
    if p["dock_hide_indicator"]:
        contents += "\n/* BEGIN tablet hidden dock */\n.xfce4-panel#XfcePanelWindowHidden.panel-2-hidden { background: transparent; border: none; box-shadow: none; }\n/* END tablet hidden dock */\n"
    writer.put(css, contents)
    if "chromium" in p["applications"]:
        helper = "[Desktop Entry]\nVersion=1.0\nType=X-XFCE-Helper\nName=Chromium\nIcon=chromium\nX-XFCE-Category=WebBrowser\nX-XFCE-Commands=/usr/local/bin/chromium-tablet\nX-XFCE-CommandsWithParameter=/usr/local/bin/chromium-tablet \"%s\"\n"
        writer.put(home / ".local/share/xfce4/helpers/custom-WebBrowser.desktop", helper)
        helpers = home / ".config/xfce4/helpers.rc"
        old_helpers = helpers.read_text(encoding="utf-8") if helpers.exists() else ""
        import re
        old_helpers = re.sub(r"(?m)^WebBrowser=.*$", "WebBrowser=custom-WebBrowser", old_helpers) if re.search(r"(?m)^WebBrowser=", old_helpers) else old_helpers.rstrip() + "\nWebBrowser=custom-WebBrowser\n"
        writer.put(helpers, old_helpers)
        mime = home / ".config/mimeapps.list"
        import configparser
        cfg = configparser.ConfigParser(interpolation=None); cfg.optionxform = str
        if mime.exists(): cfg.read(mime)
        if not cfg.has_section("Default Applications"): cfg.add_section("Default Applications")
        for key in ("text/html", "x-scheme-handler/http", "x-scheme-handler/https"):
            cfg["Default Applications"][key] = "chromium-tablet.desktop"
        import io
        buffer = io.StringIO(); cfg.write(buffer); writer.put(mime, buffer.getvalue())


def context(home: Path, root: Path, p: dict, writer: Writer):
    begin, end = "<!-- BEGIN termux desktop -->", "<!-- END termux desktop -->"
    block = f"""{begin}
## Managed Termux desktop
- Guest: {p['container']}, user {p['user']}; X11 {p['display']}; native adaptive resolution.
- Execution location: use the current Xfce UI or its terminal for menus, Thunar, desktop settings and guest applications. Use native Termux only for native services; use the existing ADB/system UI for Android settings. ADB shell restrictions are not a reason to leave a working Xfce terminal.
- Connection: keep the user's confirmed device and transport. A USB/ADB task does not require an additional LAN SSH connection, host-key registration or network change. Follow the user's correction of environment/transport immediately; independent SSH checks apply only to tasks requiring that delivery.
- Start/return: native `desktop start` or Android Linux-desktop entry. `start-code` is a compatibility alias. The native runit service `tablet-touch` owns the session; the launch terminal may close.
- Normal end: Xfce EndDesktop shortcut/menu/top button; ordinary application save dialogs remain interactive. Android desktop manager offers the same action and an explicitly confirmed force-stop scoped to the current session ID. SSH remains available.
- Screen-off does not intentionally log out Xfce. Android background termination remains possible; report actual sleep/reboot tests separately.
- Optional Android manager boot recovery runs only the fixed native `tablet-boot-services` after first unlock when enabled. It restores existing runit services without opening the graphical desktop or enabling SSH; keep official Termux:Boot installed and verify actual ROM autostart permission persistence.
- Touch toggle: desktop, application menu, bottom dock and top panel synchronize. Main action switches direct touch/trackpad. Simulated touch remains available in X11 preferences, CLI `tablet-touch-toggle touch`, and launchers that support Desktop Actions. Startup preserves the selected mode. Dock auto-hide={p['dock_autohide']}, hidden indicator={p['dock_hide_indicator']}, output={p['dock_output']}. The panel-edge helper is enabled only without whole-desktop compositing; release its existing manual redirect before enabling a full compositor.
- Window theme={p['titlebar_theme']}; Xfwm compositing={p['window_compositing']}, vblank={p['window_vblank_mode']}, shadows={p['window_shadows']}. Verify visible output, drag redraws and application performance separately; XPresent or a GL library name is not proof of accelerated composition.
- Direct-touch secondary click={p['touch_long_press']}: hold {p['touch_long_press_ms']}ms then release in Xfdesktop/Thunar; movement beyond {p['touch_long_press_move_px']} physical pixels or multiple contacts cancels. Other applications retain their native touch handling. The helper observes only raw touch events, uses an X selection for a single instance, and exits with its X11 session.
- GTK core pointer active={p['touch_long_press']}: desktop/panel use tablet-xfce-pointer; Thunar uses tablet-thunar-core so its Exo icon view receives button multiclicks. Code/Chromium/Office/VLC launchers clear GDK_CORE_DEVICE_EVENTS. No preloaded input library is used. The long-press observer never synthesizes ordinary left clicks.
- X11 MIT-SHM enabled={p['x11_mitshm']}. When disabled for a proven PRoot/shared-memory failure, only this X11 extension is disabled; DRI3/Present and GPU application drivers remain separately configured and must be retested.
- Battery comes from native Termux:API with a 60-second cache; stale data is marked unavailable.
- Hardware video policy: {p['media_hardware_policy']}. With h264-baseline, only verified local Baseline/8-bit/1080p30 files use hardware decode; other inputs use software decode with GPU presentation. Reopen VLC to select a different path; do not describe the compatibility path as hardware decoding.
- Native private socket `~/.local/state/tablet-desktop/touch-control.sock` is same-UID only (0600); no desktop control TCP port. Audio uses authenticated localhost PulseAudio.
- Controller registry checks UID, PID, creation ticks, executable, session, tracer and desktop state. Only recorded detached helper cases can be automatically reaped; active applications and compilers are not stopped for high CPU alone.
- Profile `~/.config/tablet-desktop/config.json`; logs/backups `~/.local/state/tablet-desktop/`. Companion APK signing keys stay on the host.
- Real Android identity remains Termux, even when guest `id` says root. Android per-app VPN must include Termux; verify VPN state, explicit proxy and DNS independently.
- Applications: {', '.join(p['applications']) or 'none'}; GTK scale {p['scale']}, logical DPI {p['dpi']}. GTK compatibility={p['software_rendering']}; GPU backend={p['gpu_backend']}; browser={p['browser_backend']}, office={p['office_backend']}, media={p['media_backend']}. VirGL owns a multi-client service/socket; freedreno-kgsl uses an isolated pinned /opt driver without that service. Optional native Chromium and LibreOffice use fixed same-UID controller actions and registered process roots; normal shutdown waits for their save prompts. Native office has a separately copied profile; original guest profiles remain. Optional Termux:VA starts on demand, checks real decoder output and joins desktop resource cleanup. Confirm real rendering/decoding separately; these paths do not imply full native performance.
- Cursor: {p['cursor_theme']} / {p['cursor_size']}; preserve a nonempty GTK/Xcursor theme and make it available to native applications. Normally reopen Electron after changing its cached cursor-size environment. ROM keyboard automatic workbench entry is independent of manual workbench mode: disable only the verified automatic-entry preference, then test both real typing and manual entry.
- Android related home icons may be grouped in a `{p['android_folder']}` folder through the actual launcher UI; keep both native launcher entries available in All Apps. Do not edit the launcher database.
{end}"""
    for path in (home / "AGENTS.md", root / f"home/{p['user']}/AGENTS.md"):
        old = path.read_text(encoding="utf-8") if path.exists() else ""
        old = migrate_legacy_ssh_rule(old)
        legacy_begin, legacy_end = "<!-- BEGIN tablet-desktop setup -->", "<!-- END tablet-desktop setup -->"
        if legacy_begin in old or legacy_end in old:
            if old.count(legacy_begin) != 1 or old.count(legacy_end) != 1 or old.index(legacy_begin) > old.index(legacy_end) or begin in old:
                raise ValueError(f"Conflicting/incomplete legacy desktop context: {path}")
            old = old.replace(legacy_begin, begin, 1).replace(legacy_end, end, 1)
        writer.put(path, replace_block(old, block, 'termux desktop', append=True), 0o600)


def native_packages(p: dict):
    packages = ["proot-distro", "termux-x11-nightly", "pulseaudio", "termux-services", "termux-api", "libexpat", "libc++"]
    if p["gpu_backend"] == "virgl-android":
        packages.append("virglrenderer-android")
    if p["browser_backend"] == "termux-zink" and "chromium" in p["applications"]:
        packages += ["chromium", "mesa", "mesa-vulkan-icd-freedreno"]
    if p["office_backend"] == "native-gtk3" and "office" in p["applications"]:
        packages.append("libreoffice")
    return packages


def install(p: dict, args):
    prefix, home = require_termux()
    if not args.apply:
        raise RuntimeError("Installation requires --apply after reviewing `desktop-plan`; no changes made")
    root = guest_root(prefix, p["container"])
    config = home / ".config/tablet-desktop/config.json"
    client = prefix / "bin/desktop"
    if client.exists():
        status = run([client, "status", "--json"], check=False, timeout=30)
        if status.returncode != 0:
            raise RuntimeError("Cannot establish the existing desktop state. Diagnose the controller before changing packages or runtime files")
        state = json.loads(status.stdout)
        if state.get("phase") != "stopped":
            raise RuntimeError("Desktop is active or partially running. Use its normal End Desktop action, handle save prompts, then retry installation; SSH stays available")
    if root.exists() and active_container_roots(prefix, root, p["container"]):
        raise RuntimeError("The selected container still has active PRoot sessions. Close them normally before changing its desktop files")
    existing_panel = root / f"home/{p['user']}/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml"
    if existing_panel.exists() and not config.exists() and not args.adopt_existing:
        raise RuntimeError("Existing Xfce layout is not registered by this installer; review it and use --adopt-existing to apply the selected profile with backups")
    run([prefix / "bin/pkg", "install", "-y", "x11-repo"])
    run([prefix / "bin/pkg", "install", "-y", *native_packages(p)])
    if not root.exists():
        help_result = run([prefix / "bin/proot-distro", "install", "--help"])
        help_text = help_result.stdout + help_result.stderr
        if "--name" not in help_text:
            raise RuntimeError("This fresh-install path needs OCI-capable proot-distro (5.x). Update it with `pkg upgrade proot-distro`; existing legacy rootfs layouts remain readable")
        run([prefix / "bin/proot-distro", "install", "--name", p["container"], p["image"]])
        root = guest_root(prefix, p["container"])
    release = (root / "etc/os-release").read_text(encoding="utf-8")
    if "ID=debian" not in release or not any(x in release for x in ('VERSION_ID="13"', 'VERSION_ID=13')):
        raise RuntimeError("Existing container is not Debian 13; preserve it and select a different container name")
    run([prefix / "bin/proot-distro", "login", p["container"], "--shared-tmp", "--", "/bin/bash", "-s", "--", p["user"],
         ",".join(p["applications"]), p["language"], p["code_version"], "1" if p["touch_long_press"] else "0"], script=(ASSETS / "guest/install-packages.sh").read_text(encoding="utf-8"))
    writer = Writer(home, prefix, root)
    if p["gpu_backend"] == "freedreno-kgsl":
        install_bundle(root, prefix / "var/cache/tablet-desktop")
    if p["media_backend"] == "termux-va" and "vlc" in p["applications"]:
        install_video(root, prefix / "var/cache/tablet-desktop", prefix)
    writer.put(config, json.dumps(p, ensure_ascii=False, indent=2) + "\n", 0o600)
    writer.put(home / ".config/tablet-desktop/gpu.json", json.dumps({"backend": p["gpu_backend"], "driver_root": DRIVER_ROOT}) + "\n", 0o600)
    for src in (ASSETS / "native").iterdir():
        if not src.is_file():
            continue
        dest = prefix / "bin" / src.name if src.name in ("desktop", "start-code", "tablet-boot-services") else home / ".local/lib/tablet-desktop" / src.name
        writer.put(dest, src.read_bytes(), 0o755 if dest.parent == prefix / "bin" else 0o600)
    configure_guest(root, home, p, writer)
    if p["touch_long_press"]:
        with tempfile.TemporaryDirectory(prefix="tablet-touch-build-", dir=root / "tmp") as build:
            binary = Path(build) / "tablet-touch-longpress"
            guest_binary = "/" + binary.relative_to(root).as_posix()
            run([prefix / "bin/proot-distro", "login", p["container"], "--", "/usr/bin/gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                 "/usr/local/share/tablet-desktop/tablet-touch-longpress.c", "-o", guest_binary, "-lXi", "-lXtst", "-lX11", "-lm"])
            writer.put(root / "usr/local/bin/tablet-touch-longpress", binary.read_bytes(), 0o755)
    cookie = home / ".config/pulse/cookie"
    if not cookie.exists(): writer.put(cookie, os.urandom(256), 0o600)
    cookie.chmod(0o600)
    service = prefix / "var/service/tablet-touch"
    writer.put(service / "run", f"#!{prefix}/bin/sh\nexport PREFIX={shlex.quote(str(prefix))}\nexport HOME={shlex.quote(str(home))}\nexport PATH=\"$PREFIX/bin:/system/bin:$PATH\"\nexec python -u {shlex.quote(str(home / '.local/lib/tablet-desktop/touch-control.py'))} 2>&1\n", 0o700)
    writer.put(service / "log/run", f"#!{prefix}/bin/sh\nexec {prefix}/bin/svlogd -tt {home}/.local/state/tablet-desktop/service-log\n", 0o700)
    (home / ".local/state/tablet-desktop/service-log").mkdir(parents=True, exist_ok=True)
    (home / ".local/state/tablet-desktop/service-log").chmod(0o700)
    if p["hardware_keyboard"]:
        import re
        properties = home / ".termux/termux.properties"
        text = properties.read_text(encoding="utf-8") if properties.exists() else ""
        for key, value in {"extra-keys": "[]", "hide-soft-keyboard-on-startup": "true"}.items():
            pattern = r"(?m)^\s*" + re.escape(key) + r"\s*=.*$"
            line = key + " = " + value
            text = re.sub(pattern, line, text) if re.search(pattern, text) else text.rstrip() + "\n" + line + "\n"
        writer.put(properties, text, 0o600)
        run([prefix / "bin/termux-reload-settings"])
    context(home, root, p, writer)
    run([prefix / "bin/proot-distro", "login", p["container"], "--", "/usr/bin/chown", "-R", f"{p['user']}:{p['user']}", f"/home/{p['user']}"])
    preference = prefix / "bin/termux-x11-preference"
    preferences = ["displayResolutionMode:native", "displayScale:" + str(p["scale"] * 100), "fullscreen:true"]
    if p["hardware_keyboard"]: preferences += ["showAdditionalKbd:false"]
    if p["touch_mode"] != "preserve": preferences += ["touchMode:" + {"touch": "2", "direct": "3", "trackpad": "1"}[p["touch_mode"]]]
    result = run([preference, *preferences], check=False, timeout=20)
    if result.returncode: print("WARN: Open Termux:X11 once, then apply native resolution/input preferences through its settings.")
    (service / "down").unlink(missing_ok=True)
    run([prefix / "bin/bash", "-c", '''set -eu
export SVDIR="$PREFIX/var/service"
. "$PREFIX/etc/profile.d/start-services.sh"
'''])
    ready = [prefix / "bin/python", home / ".local/lib/tablet-desktop/service_ready.py", "--timeout", "20"]
    run(ready, timeout=25)
    run([prefix / "bin/sv", "-w", "10", "restart", service], timeout=15)
    run([*ready, "--controller"], timeout=25)
    print(json.dumps({"ok": True, "profile_sha256": profile_digest(p), "backup": str(writer.backup), "changed_files": len(writer.changed),
                      "next": "Install/open the X11 APK if needed; build/deploy the optional Android manager; then `desktop start`. Android APKs are separate from native pkg packages."}, ensure_ascii=False))


def doctor(p: dict):
    prefix, home = require_termux()
    root = guest_root(prefix, p["container"])
    checks = {"native_x11_cli": (prefix / "bin/termux-x11").is_file(), "guest_rootfs": root.is_dir(),
              "desktop_client": (prefix / "bin/desktop").is_file(), "pulse_cookie_private": (home / ".config/pulse/cookie").is_file() and (home / ".config/pulse/cookie").stat().st_mode & 0o077 == 0}
    for package in ("com.termux.x11", "com.termux.api", "com.scisaga.tabletdesktop"):
        result = run(["/system/bin/pm", "path", package], check=False, timeout=5)
        checks[package] = bool(result.returncode == 0 and "package:" in result.stdout)
    if p["gpu_backend"] == "virgl-android":
        checks["native_gpu_server"] = (prefix / "bin/virgl_test_server_android").is_file()
    if p["browser_backend"] == "termux-zink":
        checks["native_browser"] = (prefix / "lib/chromium/chrome").is_file()
        checks["native_browser_icd"] = (prefix / "share/vulkan/icd.d" / p["native_browser_icd"]).is_file()
    if p["gpu_backend"] == "freedreno-kgsl":
        try:
            selected = json.loads((home / '.config/tablet-desktop/gpu.json').read_text())
        except (OSError, ValueError):
            selected = {}
        checks["direct_gpu_driver"] = installed_driver_ready(root, selected)
    if p["office_backend"] == "native-gtk3" and "office" in p["applications"]:
        checks["native_office"] = (prefix / 'lib/libreoffice/program/oosplash').is_file()
    if p["media_backend"] == "termux-va" and "vlc" in p["applications"]:
        checks["video_bundle"] = (root / VLC_ROOT.lstrip('/') / 'usr/bin/vlc').is_file() and (prefix / 'bin/termux-va').is_file()
    if p['touch_long_press']:
        checks['touch_longpress_binary'] = (root / 'usr/local/bin/tablet-touch-longpress').is_file()
        checks['xfce_pointer_wrapper'] = (root / 'usr/local/bin/tablet-xfce-pointer').is_file()
    state = None
    import socket
    try:
        with socket.socket(socket.AF_UNIX) as connection:
            connection.settimeout(3)
            connection.connect(str(home / ".local/state/tablet-desktop/touch-control.sock"))
            connection.sendall(b'{"action":"desktop.status"}\n')
            state = json.loads(connection.makefile().readline(65536))
    except (OSError, ValueError): pass
    window_runtime = {'status': 'skipped', 'reason': 'Desktop is not running; diagnosis does not start it'}
    if state and state.get('phase') == 'running' and state.get('core_alive'):
        from window_probe import native_run, options
        try:
            window_runtime = native_run(options())
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            window_runtime = {'status': 'failed', 'error': str(error)}
        checks['window_runtime'] = window_runtime.get('status') == 'passed'
    print(json.dumps({"checks": checks, "desktop": state, "window_runtime": window_runtime, "profile_sha256": profile_digest(p),
                      "note": "API/manager APKs are optional; running status is not proof of sleep/reboot survival or browser connectivity."}, ensure_ascii=False, indent=2))
    required = ["native_x11_cli", "guest_rootfs", "desktop_client", "com.termux.x11"]
    if p["gpu_backend"] == "virgl-android": required.append("native_gpu_server")
    if p["browser_backend"] == "termux-zink": required += ["native_browser", "native_browser_icd"]
    if p["gpu_backend"] == "freedreno-kgsl": required.append("direct_gpu_driver")
    if "native_office" in checks: required.append("native_office")
    if "video_bundle" in checks: required.append("video_bundle")
    if p['touch_long_press']:
        required += ['touch_longpress_binary', 'xfce_pointer_wrapper']
    if 'window_runtime' in checks:
        required.append('window_runtime')
    return 0 if all(checks[x] for x in required) else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["plan", "install", "doctor", "update-context", "repair-panel"])
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--apps", help="code,chromium,office,vlc or none")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--adopt-existing", action="store_true")
    args = parser.parse_args(argv)
    p = None
    try:
        installed = Path.home() / ".config/tablet-desktop/config.json"
        profile_path = args.profile or (installed if installed.exists() else None)
        p = load_profile(profile_path, args.apps)
        if args.command == "plan":
            print(json.dumps({"profile": p, "profile_sha256": profile_digest(p), "native_packages": ["x11-repo", *native_packages(p)],
                              "android_apks": ["Termux:X11", "Termux:API (battery, optional)", "Desktop Manager (optional)"],
                              "android_folder": p["android_folder"], "changes_device": False}, ensure_ascii=False, indent=2))
        elif args.command == "install": install(p, args)
        elif args.command == "doctor": return doctor(p)
        elif args.command == "update-context":
            prefix, home = require_termux(); root = guest_root(prefix, p["container"])
            context(home, root, p, Writer(home, prefix, root))
        else:
            prefix, home = require_termux()
            script = '. ' + shlex.quote(str(home / '.local/state/tablet-desktop/session.env')) + '; export GDK_GL=disable LIBGL_ALWAYS_INDIRECT=1 NO_AT_BRIDGE=1; xfconf-query -c xfce4-panel -p /panels/panel-2/output-name --create -t string -s ' + shlex.quote(p['dock_output']) + '; exec xfce4-panel --restart'
            run([prefix / "bin/proot-distro", "login", p["container"], "--user", p["user"], "--shared-tmp", "--", "/bin/bash", "-c", script], timeout=15)
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        digest = profile_digest(p) if p else "unavailable"
        print(f"ERROR: {exc}; input_profile_sha256={digest}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
