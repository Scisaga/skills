"""Same-UID local controller, retaining the original touch-toggle protocol."""
import json
import os
import re
import select
import signal
import socket
import struct
import subprocess
from pathlib import Path
from session_manager import Manager, PREFIX, STATE

os.umask(0o077)
STATE.mkdir(parents=True, exist_ok=True)
path = STATE / 'touch-control.sock'
command = str(PREFIX / 'bin/termux-x11-preference')


def pref(*args):
    p = subprocess.run([command, *args], stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, timeout=12)
    if p.returncode:
        raise RuntimeError((p.stderr or p.stdout)[-300:])
    return p.stdout


def touch(action):
    m = re.search(r'"touchMode"="([^"\n]+)"', pref('list'))
    if not m:
        raise RuntimeError('X11 input mode unavailable')
    label = m.group(1)
    labels = {'trackpad': 'Trackpad', 'touch': 'Simulated touchscreen', 'direct': 'Direct touch'}
    values = {'trackpad': '1', 'touch': '2', 'direct': '3'}
    mode = next((key for key, value in labels.items() if label == value), 'other')
    target = ('trackpad' if mode in ('touch', 'direct') else 'direct') if action == 'toggle' else action
    if action != 'status':
        pref('touchMode:' + values[target])
        mode = target
        label = labels[mode]
        print('input mode:', label, flush=True)
    return {'ok': True, 'mode': mode, 'label': label}


if path.exists():
    with socket.socket(socket.AF_UNIX) as check:
        check.settimeout(.5)
        try:
            check.connect(str(path))
        except OSError:
            path.unlink()
        else:
            raise SystemExit('Local desktop controller already running')

manager = Manager()
s = socket.socket(socket.AF_UNIX)
s.bind(str(path))
path.chmod(0o600)
s.listen(8)


def stop(*_):
    # Restarting the controller must not terminate the user's desktop.
    raise SystemExit(0)


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
try:
    while True:
        manager.tick()
        ready, _, _ = select.select([s], [], [], manager.delay())
        if not ready:
            continue
        c, _ = s.accept()
        with c:
            c.settimeout(3)
            try:
                pid, uid, _ = struct.unpack('3i', c.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                if uid != os.getuid():
                    raise RuntimeError('Peer not allowed')
                raw = c.makefile('rb').readline(4096).decode().strip()
                request = json.loads(raw) if raw.startswith('{') else {'action': raw}
                action = request.get('action')
                if action in ('toggle', 'status', 'touch', 'direct', 'trackpad'):
                    result = touch(action)
                else:
                    result = manager.handle(action, request)
            except Exception as e:
                result = {'ok': False, 'error': str(e)[:300]}
            try:
                c.sendall((json.dumps(result, ensure_ascii=False) + '\n').encode())
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                pass
finally:
    s.close()
    if path.exists():
        path.unlink()
