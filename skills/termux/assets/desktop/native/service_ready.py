"""Bounded runit readiness checks shared by installation and boot recovery."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import stat
import subprocess
import time
from pathlib import Path


def controller_ready(path: Path, timeout: float) -> bool:
    try:
        info = path.stat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
            return False
        with socket.socket(socket.AF_UNIX) as connection:
            connection.settimeout(timeout)
            connection.connect(str(path))
            connection.sendall(b'{"action":"desktop.status"}\n')
            reply = connection.makefile('rb').readline(65536)
        value = json.loads(reply)
        return value.get('ok') is True and isinstance(value.get('phase'), str)
    except (OSError, ValueError, AttributeError):
        return False


def wait_ready(prefix: Path, home: Path, service='tablet-touch', timeout=20.0, require_controller=False):
    if not re.fullmatch(r'[a-zA-Z0-9_.-]+', service) or not 0 < timeout <= 300:
        raise ValueError('Invalid service or timeout (must be greater than 0 and at most 300 seconds)')
    summary = {'service': service, 'timeout_seconds': timeout, 'require_controller': require_controller}
    digest = hashlib.sha256(json.dumps(summary, sort_keys=True).encode()).hexdigest()
    started = time.monotonic()
    deadline = started + timeout
    env = dict(os.environ, SVDIR=str(prefix / 'var/service'))
    attempts = 0
    reason = 'supervisor-unavailable'
    while time.monotonic() < deadline:
        attempts += 1
        remaining = deadline - time.monotonic()
        try:
            result = subprocess.run([str(prefix / 'bin/sv'), '-w', '1', 'up', service],
                                    env=env, stdin=subprocess.DEVNULL, capture_output=True,
                                    timeout=max(.01, min(2, remaining)))
            if result.returncode == 0:
                reason = 'controller-unavailable'
                remaining = deadline - time.monotonic()
                if not require_controller or (remaining > 0 and controller_ready(
                        home / '.local/state/tablet-desktop/touch-control.sock', min(1, remaining))):
                    return dict(summary, ok=True, attempts=attempts,
                                elapsed_seconds=round(time.monotonic() - started, 3), input_sha256=digest)
        except FileNotFoundError:
            reason = 'sv-missing: install with pkg install termux-services'
            break
        except (OSError, subprocess.TimeoutExpired):
            pass
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(.25, remaining))
    return dict(summary, ok=False, attempts=attempts, error=reason,
                elapsed_seconds=round(time.monotonic() - started, 3), input_sha256=digest)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--service', default='tablet-touch')
    parser.add_argument('--timeout', type=float, default=20)
    parser.add_argument('--controller', action='store_true')
    args = parser.parse_args(argv)
    try:
        result = wait_ready(Path(os.environ.get('PREFIX', '/data/data/com.termux/files/usr')),
                            Path.home(), args.service, args.timeout, args.controller)
        print(json.dumps(result))
        return 0 if result['ok'] else 1
    except ValueError as error:
        parser.error(str(error))


if __name__ == '__main__':
    raise SystemExit(main())
