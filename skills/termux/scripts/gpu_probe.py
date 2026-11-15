#!/usr/bin/env python3
"""Measure an explicitly isolated Chromium instance over a temporary SSH tunnel."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import socket
import subprocess
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from device_transport import Device, atomic_json
from desktop_verify import gpu_summary

WORKLOAD = Path(__file__).resolve().parents[1] / 'assets/desktop/probes/gpu-benchmark.js'


def owned_profile(arguments, expected):
    profiles = []
    for index, value in enumerate(arguments):
        if value.startswith('--user-data-dir='):
            profiles.append(value.split('=', 1)[1].rstrip('/'))
        elif value == '--user-data-dir' and index + 1 < len(arguments):
            profiles.append(arguments[index + 1].rstrip('/'))
    return profiles == [expected.rstrip('/')]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connection', type=Path, required=True)
    parser.add_argument('--remote-port', type=int, required=True)
    parser.add_argument('--expected-profile', required=True, help='Fresh isolated remote profile below tablet-desktop/probes/')
    parser.add_argument('--owned-probe', action='store_true', help='Required: this endpoint is an owned disposable probe, never the daily browser')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--trials', type=int, default=3)
    parser.add_argument('--width', type=int, default=1600)
    parser.add_argument('--height', type=int, default=940)
    parser.add_argument('--dpr', type=float, default=2)
    parser.add_argument('--label', default='candidate')
    args = parser.parse_args(argv)
    if not args.owned_probe or args.expected_profile.rsplit('/', 1)[-1] in ('.', '..') or not re.fullmatch(r'/(?:data/(?:data|user/0)/com\.termux/files/home|home/[a-z][a-z0-9_-]*)/\.local/state/tablet-desktop/probes/[A-Za-z0-9_.-]+', args.expected_profile):
        parser.error('Use --owned-probe and a fresh private tablet-desktop/probes/<name> profile; daily profiles are refused')
    if not 1024 <= args.remote_port <= 65535 or not 1 <= args.trials <= 10 or not 320 <= args.width <= 7680 or not 240 <= args.height <= 4320 or not .5 <= args.dpr <= 4:
        parser.error('Invalid debug port, trial count, viewport or scale')
    try:
        import websocket
    except ImportError:
        parser.error('Missing websocket-client. Install: python -m pip install websocket-client==1.9.2')
    # Only this diagnostic process changes its proxy environment. Loopback never uses a VPN HTTP proxy.
    for name in list(os.environ):
        if name.lower() in ('http_proxy', 'https_proxy', 'all_proxy'):
            os.environ.pop(name)
    os.environ['NO_PROXY'] = os.environ['no_proxy'] = '127.0.0.1,localhost,::1'
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    result = {'status': 'pending', 'label': args.label, 'samples': [], 'cleanup': 'pending'}
    tunnel = browser = page = None
    validated = False
    try:
        device = Device.read(args.connection)
        code = WORKLOAD.read_text(encoding='utf-8')
        workload_digest = hashlib.sha256(code.encode()).hexdigest()
        summary = {'connection_sha256': device.digest, 'expected_profile': args.expected_profile,
                   'remote_port': args.remote_port, 'trials': args.trials, 'viewport': [args.width, args.height],
                   'dpr': args.dpr, 'workload_sha256': workload_digest}
        result.update(input_summary=summary, input_sha256=hashlib.sha256(json.dumps(summary, sort_keys=True).encode()).hexdigest())
        with socket.socket() as port:
            port.bind(('127.0.0.1', 0))
            local = port.getsockname()[1]
        options = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if os.name == 'nt':
            options['creationflags'] = subprocess.CREATE_NO_WINDOW
        tunnel = subprocess.Popen(device.ssh_args() + ['-o', 'ExitOnForwardFailure=yes', '-N', '-L',
                                  f'127.0.0.1:{local}:127.0.0.1:{args.remote_port}', device.config['ssh_target']], **options)

        def get(path):
            return json.load(opener.open(f'http://127.0.0.1:{local}' + path, timeout=2))

        class CDP:
            def __init__(self, url):
                parts = urlsplit(url)
                url = urlunsplit((parts.scheme, '127.0.0.1:' + str(local), parts.path, parts.query, parts.fragment))
                self.socket = websocket.create_connection(url, origin='http://localhost:' + str(args.remote_port), timeout=30,
                                                          http_no_proxy=['127.0.0.1', 'localhost'])
                self.serial = 0

            def call(self, method, params=None):
                self.serial += 1
                self.socket.send(json.dumps({'id': self.serial, 'method': method, 'params': params or {}}))
                while True:
                    value = json.loads(self.socket.recv())
                    if value.get('id') == self.serial:
                        if 'error' in value:
                            raise RuntimeError(str(value['error']))
                        return value.get('result', {})

            def close(self):
                self.socket.close()

        deadline = time.monotonic() + 12
        while True:
            try:
                version = get('/json/version')
                break
            except (OSError, ValueError):
                if tunnel.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError('Owned debug endpoint did not become reachable through SSH')
                time.sleep(.2)
        browser = CDP(version['webSocketDebuggerUrl'])
        arguments = browser.call('Browser.getBrowserCommandLine').get('arguments', [])
        if not owned_profile(arguments, args.expected_profile):
            raise RuntimeError('Profile identity mismatch: no page was modified and the unknown browser will not be closed')
        validated = True
        target = browser.call('Target.createTarget', {'url': 'about:blank'})['targetId']
        pages = get('/json/list')
        entry = next(x for x in pages if x.get('id') == target)
        page = CDP(entry['webSocketDebuggerUrl'])
        bounds = browser.call('Browser.getWindowForTarget', {'targetId': target})
        browser.call('Browser.setWindowBounds', {'windowId': bounds['windowId'], 'bounds': {'windowState': 'maximized'}})
        page.call('Emulation.setDeviceMetricsOverride', {'width': args.width, 'height': args.height, 'deviceScaleFactor': args.dpr, 'mobile': False})
        page.call('Runtime.evaluate', {'expression': "document.open();document.write('<title>Tablet GPU check</title><body></body>');document.close();"})
        for trial in range(args.trials):
            page.call('Page.bringToFront')
            value = page.call('Runtime.evaluate', {'expression': code, 'awaitPromise': True, 'returnByValue': True})
            if value.get('exceptionDetails'):
                raise RuntimeError('WebGL probe JavaScript failed: ' + str(value['exceptionDetails'])[:500])
            sample = value['result']['value']
            sample['workload_sha256'] = workload_digest
            result['samples'].append(sample)
            atomic_json(args.output, result)
            print(json.dumps({'trial': trial + 1, 'callback_rate': sample.get('fps'), 'renderer': sample.get('renderer')}), flush=True)
        if args.trials >= 3:
            result['summary'] = gpu_summary(result)
            result['status'] = 'passed'
        else:
            result['status'] = 'collected'
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, StopIteration, subprocess.SubprocessError, websocket.WebSocketException) as error:
        result.update(status='failed', error=str(error))
    finally:
        if page:
            with contextlib.suppress(OSError, websocket.WebSocketException):
                page.close()
        if validated and browser:
            try:
                browser.call('Browser.close')
                result['cleanup'] = 'normal close requested for the verified owned browser'
            except (OSError, ValueError, websocket.WebSocketException):
                result['cleanup'] = 'owned browser connection closed; verify endpoint termination'
            confirmed = False
            deadline = time.monotonic() + 5
            while tunnel.poll() is None and time.monotonic() < deadline:
                try:
                    get('/json/version')
                except (OSError, ValueError):
                    confirmed = tunnel.poll() is None
                    break
                time.sleep(.1)
            if confirmed:
                result['cleanup'] = 'verified owned browser endpoint stopped; temporary SSH tunnel removed'
            else:
                result.update(status='failed', error='Owned browser shutdown could not be verified; inspect the probe before completion')
        if browser:
            with contextlib.suppress(OSError, websocket.WebSocketException):
                browser.close()
        if tunnel:
            tunnel.terminate()
            try:
                tunnel.wait(timeout=5)
            except subprocess.TimeoutExpired:
                tunnel.kill(); tunnel.wait(timeout=5)
            if tunnel.stderr:
                tunnel.stderr.close()
        atomic_json(args.output, result)
    print(json.dumps({k: v for k, v in result.items() if k != 'samples'}, ensure_ascii=False))
    return 1 if result['status'] == 'failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
