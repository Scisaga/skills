"""Inspect standalone VS Code leases and selected native process identities."""
import os
import re
import stat
from pathlib import Path

from window_probe import process_identity


def lease_state(path):
    import fcntl

    try:
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                return "unreadable"
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return "held"
        return "released"
    except FileNotFoundError:
        return "missing"
    except OSError:
        return "unreadable"


def process_fields(proc):
    return (proc / "stat").read_text(errors="replace").rsplit(") ", 1)[1].split()


def selected_process(pid, uid):
    proc = Path("/proc") / str(pid)
    try:
        if proc.stat().st_uid != uid:
            return {"pid": pid, "status": "different-uid"}
        identity = process_identity(pid)
        fields = process_fields(proc)
        if identity["uid"] != uid or int(fields[19]) != identity["start_ticks"]:
            return {"pid": pid, "status": "identity-changed"}
        ppid = int(fields[1])
        cpu_ticks = int(fields[11]) + int(fields[12])
    except (OSError, ValueError, IndexError, AttributeError):
        return {"pid": pid, "status": "unavailable"}

    result = {key: identity[key] for key in ("pid", "uid", "start_ticks", "executable", "tracer")}
    command = Path(identity["cmd"][0].partition(" ")[0]).name if identity["cmd"] else None
    result.update(status="observed", state=fields[0], ppid=ppid, cpu_ticks=cpu_ticks, command=command)
    keys = {b"DISPLAY", b"TABLET_VSCODE_DOCK_TAG", b"VSCODE_STANDALONE_DATA"}
    try:
        for value in (proc / "environ").read_bytes().split(b"\0"):
            name, sep, field = value.partition(b"=")
            if sep and name in keys:
                result[name.decode()] = os.fsdecode(field)
    except OSError:
        result["environment"] = "unreadable"
    if command == "termux-x11" and result.get("TABLET_VSCODE_DOCK_TAG") is None:
        tag = re.search(r"(?:^| )-tag (vscode(?:-[0-9]{1,2})?)(?: |$)", " ".join(identity["cmd"]))
        if tag:
            result["launcher_tag"] = tag[1]
    if any(arg.endswith("/tablet-vscode/session.py") for arg in identity["cmd"]):
        result["editor_exit_guard"] = "--editor-pid-file" in identity["cmd"]
    try:
        if int(process_fields(proc)[19]) != identity["start_ticks"] or proc.stat().st_uid != uid:
            return {"pid": pid, "status": "identity-changed"}
    except (OSError, ValueError, IndexError):
        return {"pid": pid, "status": "unavailable"}
    return result


def session_status(directory, tag, uid):
    result = {"tag": tag, "lease": lease_state(directory / "session.lock")}
    marker = directory / "editor.pid"
    if marker.is_symlink() or (marker.exists() and not marker.is_file()):
        result["editor_marker"] = "unreadable"
        return result
    try:
        pid, start = map(int, marker.read_text(encoding="utf-8").split())
        if pid <= 1 or start <= 0:
            raise ValueError("invalid identity")
    except FileNotFoundError:
        result["editor_marker"] = "missing"
    except (OSError, ValueError):
        result["editor_marker"] = "unreadable"
    else:
        editor = selected_process(pid, uid)
        matches = None
        if editor["status"] == "observed":
            matches = editor["start_ticks"] == start and editor["state"] not in ("Z", "X")
        result.update(editor_pid=pid, editor_start_ticks=start, editor_process_status=editor["status"],
                      editor_identity_matches=matches)
    return result


def inspect_runtime(state, pids):
    if any(pid <= 1 for pid in pids):
        raise ValueError("Choose process IDs greater than 1")
    uid = os.getuid()
    try:
        boot = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
    except OSError:
        boot = None
    sessions = []
    if not state.is_symlink():
        if (state / "session.lock").exists():
            sessions.append(session_status(state, "vscode", uid))
        dock = state / "dock"
        if not dock.is_symlink():
            for directory in sorted(dock.glob("*")):
                if re.fullmatch(r"[0-9]{1,2}", directory.name) and directory.is_dir() and not directory.is_symlink():
                    sessions.append(session_status(directory, "vscode-" + directory.name, uid))
    return {"uid": uid, "boot_id": boot, "clock_ticks_per_second": os.sysconf("SC_CLK_TCK"), "sessions": sessions,
            "processes": [selected_process(pid, uid) for pid in dict.fromkeys(pids)]}
