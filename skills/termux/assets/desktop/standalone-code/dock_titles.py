#!/usr/bin/env python3
"""Publish VS Code task titles and send normal X11 close requests."""
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


def editor_windows(env):
    clients = xprop(env, "-root", "_NET_CLIENT_LIST")
    if clients.returncode:
        raise ConnectionError("X11 display closed")
    for window in re.findall(r"0x[0-9a-fA-F]+", clients.stdout):
        props = xprop(env, "-id", window, "WM_CLASS", "_NET_WM_WINDOW_TYPE", "_NET_WM_NAME", "_NET_WM_PID").stdout
        if '"com.microsoft.vscode"' not in props.lower() or "_NET_WM_WINDOW_TYPE_NORMAL" not in props:
            continue
        yield window, props


def find_editor(env):
    for window, props in editor_windows(env):
        for line in props.splitlines():
            title = parse_title(line)
            if title is not None:
                return window, title
    return None, None


def editor_identity(state):
    from session import editor_start_time

    try:
        pid, started = map(int, (state / "editor.pid").read_text(encoding="ascii").split())
    except (OSError, ValueError):
        return None
    if pid > 1 and started > 0 and editor_start_time(pid) == started:
        return pid, started
    return None


def sibling_window_is_active(state):
    import fcntl

    for lease in state.parent.glob("*/session.lock"):
        if lease.parent == state or not re.fullmatch(r"[0-9]{1,2}", lease.parent.name):
            continue
        try:
            with lease.open("rb") as file:
                fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except FileNotFoundError:
            continue
        except OSError:
            return True
    return False


def close_editor(env, state, container, user, *, sole_session=False):
    token = env.get("TABLET_VSCODE_WINDOW_TOKEN", "")
    if not re.fullmatch(r"[0-9a-f]{32}", token):
        raise ValueError("Missing the current editor session token")

    def same_session():
        try:
            return (state / "editor-token").read_text(encoding="ascii").strip() == token
        except OSError:
            return False

    deadline = time.monotonic() + 20
    while same_session() and time.monotonic() < deadline:
        identity = editor_identity(state)
        if identity is not None:
            windows = [window for window, props in editor_windows(env)
                       if re.search(rf"^_NET_WM_PID = {identity[0]}$", props, re.M)]
            if windows:
                prefix = Path(env["PREFIX"])
                command = [str(prefix / "bin/proot-distro"), "login", container, "--user", user, "--shared-tmp", "--",
                           "/usr/bin/env", f"DISPLAY={env['DISPLAY']}", "/usr/bin/wmctrl", "-i", "-c"]
                for window in windows:
                    if not same_session() or editor_identity(state) != identity:
                        break
                    if sole_session and sibling_window_is_active(state):
                        print("Keeping the editor open because another standalone session is active", flush=True)
                        return
                    subprocess.run(command + [window], env=env, stdin=subprocess.DEVNULL, check=True, timeout=8)
                    print(f"Requested normal close on {env['DISPLAY']} for editor PID {identity[0]}", flush=True)
                return
        time.sleep(0.25)


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
    parser.add_argument("action", choices=("initial", "watch", "close"))
    parser.add_argument("display")
    parser.add_argument("tag")
    parser.add_argument("state", type=Path)
    parser.add_argument("--workspace")
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--container")
    parser.add_argument("--user")
    parser.add_argument("--sole-session", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r":[0-9]{1,2}", args.display) or not re.fullmatch(r"vscode-[0-9]{1,2}", args.tag):
        parser.error("Expected a local X11 display and a VS Code window tag")
    env = dict(os.environ, DISPLAY=args.display, LC_ALL="C.UTF-8")
    if args.action == "close":
        if not args.container or not args.user:
            parser.error("A close request requires the configured guest and user")
        close_editor(env, args.state, args.container, args.user, sole_session=args.sole_session)
        return
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
