"""Keep an independent VS Code PRoot session's children tied to its launcher."""

import ctypes
import os
from pathlib import Path
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


def run(command):
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) != 0:
        print(f"VSCode session: cannot adopt children: {os.strerror(ctypes.get_errno())}", file=sys.stderr)
        os.execvp(command[0], command)

    with subprocess.Popen(command) as process:
        def relay(signum, _frame):
            process.send_signal(signum)

        for signum in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
            signal.signal(signum, relay)
        result = process.wait()
        reap_after_exit()
    return result if result >= 0 else 128 - result


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
