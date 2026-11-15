#!/usr/bin/env python3
"""Inventory relevant launcher entries and plan Android home-folder grouping; read-only."""
import argparse
import json
import subprocess

PACKAGES = [("com.termux", "Termux"), ("com.termux.x11", "Termux:X11"),
            ("com.scisaga.tabletdesktop", "Linux desktop / Desktop manager"),
            ("com.termux.api", "Termux:API"), ("com.termux.boot", "Termux:Boot"), ("com.termux.widget", "Termux:Widget")]


def inventory(adb, serial):
    def shell(*args):
        p = subprocess.run([adb, "-s", serial, "shell", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
        if p.returncode: raise RuntimeError((p.stderr or p.stdout)[-500:])
        return p.stdout
    rows = []
    for package, label in PACKAGES:
        installed = "package:" + package in shell("pm", "list", "packages", package).splitlines()
        text = shell("cmd", "package", "query-activities", "--brief", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER", "-p", package) if installed else ""
        components = [x.strip() for x in text.splitlines() if x.strip().startswith(package + "/")]
        rows.append({"package": package, "label": label, "installed": installed, "launcher_entries": components})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--serial", required=True)
    parser.add_argument("--folder", default="Termux")
    args = parser.parse_args()
    print(json.dumps({"folder": args.folder, "inventory": inventory(args.adb, args.serial), "changes_device": False,
                      "workflow": ["Inspect the current launcher UI and existing folder/shortcuts", "Group actual installed home-screen entries through launcher drag/drop and rename the folder", "Keep Linux desktop and Desktop manager available in All Apps", "Verify new entries before removing a duplicate owned Widget shortcut", "Reopen the folder and test both start/return and management"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try: main()
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc: raise SystemExit(str(exc))
