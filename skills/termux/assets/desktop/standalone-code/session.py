"""Keep an independent VS Code PRoot session's children tied to its launcher."""

import ctypes
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time


PR_SET_CHILD_SUBREAPER = 36


def children():
    parent = str(os.getpid())
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            fields = (entry / "stat").read_text(errors="replace").rsplit(") ", 1)[1].split()
        except (OSError, IndexError):
            continue
        if len(fields) >= 2 and fields[1] == parent:
            yield int(entry.name)


def reap_after_exit():
    deadline = time.monotonic() + 2
    while True:
        try:
            while os.waitpid(-1, os.WNOHANG)[0]:
                pass
        except ChildProcessError:
            return

        # These are this subreaper's own adopted children. Their PIDs cannot
        # be recycled before we wait for them, even if they exit during the scan.
        for pid in children():
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if time.monotonic() >= deadline:
            print("VSCode session: child cleanup timed out.", file=sys.stderr)
            return
        time.sleep(0.025)


def editor_start_time(pid):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()
        return int(fields[19]) if fields[0] not in ("Z", "X") else None
    except (OSError, ValueError, IndexError):
        return None


def wait_for_editor_or_guest(process, editor_pid, started):
    descriptors = []
    try:
        descriptors.append(os.pidfd_open(process.pid))
        descriptors.append(os.pidfd_open(editor_pid))
        if editor_start_time(editor_pid) == started:
            events = select.poll()
            for descriptor in descriptors:
                events.register(descriptor, select.POLLIN)
            events.poll()
    except (AttributeError, OSError):
        # Some Termux builds lack pidfd support. Check process identity before each sleep.
        while process.poll() is None and editor_start_time(editor_pid) == started:
            time.sleep(0.5)
    finally:
        for descriptor in descriptors:
            os.close(descriptor)


def wait_for_guest(process, editor_file):
    if editor_file is None:
        return process.wait()
    while process.poll() is None:
        try:
            editor_pid, started = map(int, editor_file.read_text().split())
            if editor_pid <= 1 or started <= 0:
                raise ValueError("invalid editor identity")
        except FileNotFoundError:
            time.sleep(0.2)
            continue
        except (OSError, ValueError) as error:
            print(f"VSCode session: cannot read editor identity: {error}", file=sys.stderr)
            return process.wait()
        break
    else:
        return process.wait()

    wait_for_editor_or_guest(process, editor_pid, started)
    try:
        return process.wait(timeout=4)
    except subprocess.TimeoutExpired:
        print("VSCode session: editor exited and guest did not stop. Closing this guest.", file=sys.stderr)
        process.terminate()
    try:
        return process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        return process.wait()


def run(command, editor_file=None):
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) != 0:
        print(f"VSCode session: cannot adopt children: {os.strerror(ctypes.get_errno())}", file=sys.stderr)
        os.execvp(command[0], command)

    with subprocess.Popen(command) as process:
        def relay(signum, _frame):
            process.send_signal(signum)

        for signum in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
            signal.signal(signum, relay)
        result = wait_for_guest(process, editor_file)
        reap_after_exit()
    return result if result >= 0 else 128 - result


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "--editor-pid-file":
        sys.exit(run(sys.argv[3:], Path(sys.argv[2])))
    sys.exit(run(sys.argv[1:]))
