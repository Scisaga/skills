#!/usr/bin/env python3
"""Publish the normal VS Code window's X11 title to its Android task."""
import argparse
import codecs
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time


APP_TITLE = "Visual Studio Code"
PACKAGE = "com.scisaga.tabletvscode"


def label(text):
    # ZUI adds the app's name before the task label.
    title = text.removesuffix(" - " + APP_TITLE)
    title = re.sub(r"[\x00-\x1f\x7f]", " ", title).strip() or APP_TITLE
    return title.encode("utf-16-le")[:320].decode("utf-16-le", errors="ignore")


def parse_title(line):
    match = re.fullmatch(r'_NET_WM_NAME = "(.*)"', line.rstrip("\r\n"))
    if match is None:
        return None
    raw = codecs.escape_decode(match[1].encode("utf-8"))[0]
    return label(raw.decode("utf-8", errors="replace"))


def xprop(env, *args):
    return subprocess.run(["xprop", "-notype", *args], env=env, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                          text=True, encoding="utf-8", errors="replace", timeout=5)


def find_editor(env):
    clients = xprop(env, "-root", "_NET_CLIENT_LIST")
    if clients.returncode:
        raise ConnectionError("X11 display closed")
    for window in re.findall(r"0x[0-9a-fA-F]+", clients.stdout):
        props = xprop(env, "-id", window, "WM_CLASS", "_NET_WM_WINDOW_TYPE", "_NET_WM_NAME").stdout
        if '"com.microsoft.vscode"' not in props.lower() or "_NET_WM_WINDOW_TYPE_NORMAL" not in props:
            continue
        for line in props.splitlines():
            title = parse_title(line)
            if title is not None:
                return window, title
    return None, None


def initial_title(env, state, workspace, fresh):
    _, title = find_editor(env)
    if title:
        return title
    if workspace:
        return label(Path(workspace).name.removesuffix(".code-workspace"))
    saved = state / "window-title"
    if not fresh and saved.is_file():
        return label(saved.read_text(encoding="utf-8").strip())
    return APP_TITLE


def publish(tag, title):
    am = Path(os.environ["PREFIX"]) / "bin/am"
    subprocess.run([str(am), "broadcast", "--user", "0", "-a", PACKAGE + ".WINDOW_TITLE",
                    "-p", PACKAGE, "--es", "document_tag", tag, "--es", "title", title,
                    "--ez", "editor_title", "true"], stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL, check=True, timeout=8)


def watch(env, tag, state):
    import fcntl

    with (state / "window-title.lock").open("a") as lease:
        try:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        previous = None
        while True:
            try:
                window, _ = find_editor(env)
            except ConnectionError:
                return
            if window is None:
                time.sleep(0.25)
                continue
            with subprocess.Popen(["xprop", "-notype", "-spy", "-id", window, "_NET_WM_NAME"],
                                  env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                                  errors="replace") as changes:
                try:
                    for line in changes.stdout:
                        title = parse_title(line)
                        if title is None or title == previous:
                            continue
                        staged = state / ".window-title"
                        staged.write_text(title + "\n", encoding="utf-8")
                        staged.replace(state / "window-title")
                        previous = title
                        try:
                            publish(tag, title)
                        except (OSError, subprocess.SubprocessError) as error:
                            print(f"VS Code window title: {error}", file=sys.stderr)
                finally:
                    if changes.poll() is None:
                        changes.terminate()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("initial", "watch"))
    parser.add_argument("display")
    parser.add_argument("tag")
    parser.add_argument("state", type=Path)
    parser.add_argument("--workspace")
    parser.add_argument("--fresh", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r":[0-9]{1,2}", args.display) or not re.fullmatch(r"vscode-[0-9]{1,2}", args.tag):
        parser.error("Expected a local X11 display and a VS Code window tag")
    env = dict(os.environ, DISPLAY=args.display, LC_ALL="C.UTF-8")
    if args.action == "initial":
        print(initial_title(env, args.state, args.workspace, args.fresh))
        return
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    watch(env, args.tag, args.state)


if __name__ == "__main__":
    try:
        main()
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        raise SystemExit(f"VS Code window title: {error}") from error
