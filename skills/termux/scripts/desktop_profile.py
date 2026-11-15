"""Validated, credential-free desktop profile; CLI/JSON configuration, no .env loading."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / "assets/desktop"
APPLICATIONS = {"code", "chromium", "office", "vlc"}


def validate_profile(value: dict) -> dict:
    if not isinstance(value, dict) or value.get("schema") != 1:
        raise ValueError("Desktop profile must be an object with schema=1")
    defaults = json.loads((ASSETS / "tablet.json").read_text(encoding="utf-8"))
    unknown = set(value) - set(defaults)
    if unknown:
        raise ValueError(f"Unknown desktop profile fields: {sorted(unknown)}")
    p = dict(defaults, **value)
    for key in ("container", "user"):
        if not isinstance(p[key], str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,30}", p[key]):
            raise ValueError(f"Invalid {key}; use a short lowercase Linux name")
    if not isinstance(p["display"], str) or not re.fullmatch(r":[0-9]{1,2}", p["display"]):
        raise ValueError("display must be :0 through :99")
    if not isinstance(p["image"], str) or not re.fullmatch(r"debian:13(?:@sha256:[a-f0-9]{64})?", p["image"]):
        raise ValueError("This installer supports debian:13, optionally pinned by sha256 digest")
    for key, lo, hi in (("scale", 1, 3), ("dpi", 72, 192), ("font_size", 8, 24),
                        ("editor_font_size", 8, 32), ("scrollbar_size", 4, 20), ("cursor_size", 16, 96),
                        ("touch_long_press_ms", 400, 3000), ("touch_long_press_move_px", 4, 80)):
        if type(p[key]) is not int or not lo <= p[key] <= hi:
            raise ValueError(f"{key} must be an integer between {lo} and {hi}")
    for key in ("software_rendering", "dock_autohide", "dock_hide_indicator", "code_autostart", "hardware_keyboard", "touch_long_press", "x11_mitshm", "window_compositing", "window_shadows"):
        if type(p[key]) is not bool:
            raise ValueError(f"{key} must be boolean")
    if p['window_vblank_mode'] not in ('auto', 'off', 'xpresent', 'glx'):
        raise ValueError('window_vblank_mode must be auto, off, xpresent or glx; verify the compositor on the device')
    if p["gpu_backend"] not in ("software", "virgl-android", "freedreno-kgsl"):
        raise ValueError("gpu_backend must be software, virgl-android or freedreno-kgsl; verify hardware on the device")
    if p["code_angle_backend"] not in ("default", "gles"):
        raise ValueError("code_angle_backend must be default or gles; verify editor interaction and actual GPU rendering")
    if p["code_angle_backend"] == "gles" and p["gpu_backend"] == "software":
        raise ValueError("code_angle_backend=gles requires an accelerated gpu_backend")
    if p["browser_backend"] not in ("guest", "termux-zink"):
        raise ValueError("browser_backend must be guest or termux-zink; verify the native GPU path first")
    if p["office_backend"] not in ("guest", "native-gtk3"):
        raise ValueError("office_backend must be guest or native-gtk3")
    if p["media_backend"] not in ("guest", "termux-va"):
        raise ValueError("media_backend must be guest or termux-va")
    if p["media_hardware_policy"] not in ("all", "h264-baseline"):
        raise ValueError("media_hardware_policy must be all or h264-baseline; use only device-verified decode profiles")
    if p["media_backend"] == "termux-va" and p["gpu_backend"] != "freedreno-kgsl":
        raise ValueError("termux-va requires the reviewed freedreno-kgsl driver bundle")
    if not isinstance(p["native_browser_icd"], str) or not re.fullmatch(r"[A-Za-z0-9_.-]+\.json", p["native_browser_icd"]):
        raise ValueError("native_browser_icd must be an installed Vulkan ICD filename, without a directory")
    if p["native_browser_present_mode"] not in ("default", "mailbox"):
        raise ValueError("native_browser_present_mode must be default or mailbox; verify presentation and performance on the device")
    if p["touch_mode"] not in ("preserve", "direct", "touch", "trackpad"):
        raise ValueError("touch_mode must be preserve, direct, touch or trackpad")
    if not isinstance(p["code_version"], str) or not re.fullmatch(r"stable|[0-9]+\.[0-9]+\.[0-9]+", p["code_version"]):
        raise ValueError("code_version must be stable or an explicit x.y.z release")
    if not isinstance(p["applications"], list) or any(not isinstance(x, str) or x not in APPLICATIONS for x in p["applications"]):
        raise ValueError(f"applications must be a list drawn from {sorted(APPLICATIONS)}")
    p["applications"] = list(dict.fromkeys(p["applications"]))
    for key in ("language", "timezone", "font", "monospace_font", "theme", "icons", "cursor_theme", "titlebar_theme", "dock_output", "android_folder"):
        v = p[key]
        if not isinstance(v, str) or not v.strip() or len(v) > 100 or any(ord(c) < 32 for c in v):
            raise ValueError(f"Invalid text field: {key}")
    if not re.fullmatch(r"[A-Za-z0-9_@.-]+", p["language"]) or not re.fullmatch(r"[A-Za-z0-9_+/-]+", p["timezone"]):
        raise ValueError("Invalid language or timezone")
    return p


def load_profile(path: Path | None = None, apps: str | None = None) -> dict:
    value = json.loads((path or ASSETS / "tablet.json").read_text(encoding="utf-8-sig"))
    if apps is not None:
        value["applications"] = [] if apps == "none" else apps.split(",")
    return validate_profile(value)


def profile_digest(profile: dict) -> str:
    return hashlib.sha256(json.dumps(profile, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def guest_root(prefix: Path, container: str) -> Path:
    base = prefix / "var/lib/proot-distro"
    current = base / "containers" / container / "rootfs"
    old = base / "installed-rootfs" / container
    return current if current.exists() or not old.exists() else old
