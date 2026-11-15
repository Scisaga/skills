import json
import socket

SOCKET = '/data/data/com.termux/files/home/.local/state/tablet-desktop/touch-control.sock'


def request(action, session=None, **fields):
    data = {'action': action, **fields}
    if session:
        data['session'] = session
    with socket.socket(socket.AF_UNIX) as s:
        s.settimeout(25)
        s.connect(SOCKET)
        s.sendall((json.dumps(data) + '\n').encode())
        result = json.loads(s.makefile().readline(65536))
    if not result.get('ok'):
        raise RuntimeError(result.get('error', 'Desktop control failed'))
    return result
