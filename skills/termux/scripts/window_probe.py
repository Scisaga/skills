#!/usr/bin/env python3
"""Read-only X11 audit, or an explicit reversible dock-helper redraw comparison."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import re
import select
import shlex
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

EXIT_CODES = {'passed': 0, 'failed': 1, 'pending': 3, 'skipped': 4}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def options(mode='inspect', *, trials=3, steps=120, step_ms=20, apply=False):
    if mode not in ('inspect', 'compare') or type(apply) is not bool:
        raise ValueError('Invalid window probe mode')
    if any(type(v) is not int for v in (trials, steps, step_ms)):
        raise ValueError('Trial and trajectory options must be integers')
    if not (1 <= trials <= 5 and 30 <= steps <= 300 and 10 <= step_ms <= 50):
        raise ValueError('Use 1..5 trials, 30..300 steps, and 10..50 step milliseconds')
    if 3 * trials * (steps * step_ms / 1000 + .4) > 36:
        raise ValueError('Comparison exceeds the bounded run time; reduce trials or steps')
    return dict(mode=mode, trials=trials, steps=steps, step_ms=step_ms, apply=apply)


def process_identity(pid):
    p = Path('/proc') / str(int(pid))
    fields = (p / 'stat').read_text().rsplit(')', 1)[1].split()
    status = (p / 'status').read_text()
    return {'pid': int(pid), 'uid': p.stat().st_uid, 'start_ticks': int(fields[19]),
            'executable': os.readlink(p / 'exe'),
            'tracer': int(re.search(r'^TracerPid:\s*(\d+)', status, re.M).group(1)),
            'cmd': [os.fsdecode(x) for x in (p / 'cmdline').read_bytes().split(bytes([0])) if x]}


def process_birth(start_ticks):
    return time.time() - time.clock_gettime(time.CLOCK_BOOTTIME) + start_ticks / os.sysconf('SC_CLK_TCK')


def verified_helper(process, wm_process, *, uid, state_mtime):
    if not process or not wm_process:
        return False
    born = process_birth(process['start_ticks'])
    return (process['uid'] == uid and process['cmd'] == ['/usr/bin/python3', '/usr/local/bin/tablet-panel-edge']
            and process['tracer'] > 0 and process['tracer'] == wm_process['tracer'] and state_mtime + 1 >= born)


def require_same_identity(before, current):
    if before != current:
        raise ValueError('Helper identity changed; refuse to signal the current PID')


def diagnosis(snapshot):
    helper, compositor = snapshot['helper'], snapshot['compositor']
    if helper.get('selection_owner') and not helper.get('verified'):
        return 'unverified_helper_state'
    if compositor['selection_owner'] and helper.get('verified') and helper.get('redirected_frames'):
        return 'possible_redirect_conflict'
    if compositor['configured'] != bool(compositor['selection_owner']):
        return 'compositor_state_mismatch'
    return 'composited' if compositor['selection_owner'] else 'non_composited'


def run_with_recovery(action, restore, cleanup):
    """A failed restore must never skip owned-window cleanup or hide the first error."""
    errors = []
    try:
        action()
    except BaseException as error:
        errors.append(f'probe: {type(error).__name__}: {error}')
    finally:
        try:
            restore()
        except BaseException as error:
            errors.append(f'restore: {type(error).__name__}: {error}')
        finally:
            try:
                cleanup()
            except BaseException as error:
                errors.append(f'cleanup: {type(error).__name__}: {error}')
    return errors


class WindowAudit:
    def __init__(self):
        try:
            from Xlib import X, Xatom, display
        except ImportError as error:
            raise RuntimeError('Missing python-xlib. Guest root: apt-get install -y python3-xlib') from error
        try:
            from gi.repository import Gio, GLib
        except ImportError as error:
            raise RuntimeError('Missing Gio Python bindings. Guest root: apt-get install -y python3-gi gir1.2-glib-2.0') from error
        self.Gio, self.GLib = Gio, GLib
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.X, self.A = X, Xatom
        self.d = display.Display()
        self.root = self.d.screen().root
        self.screen = self.d.get_default_screen()
        self.state_file = Path(os.environ['XDG_RUNTIME_DIR']) / 'tablet-panel-edge.json'

    def call(self, destination, path, interface, method, signature, values):
        result = self.bus.call_sync(destination, path, interface, method,
            self.GLib.Variant(signature, values), None, self.Gio.DBusCallFlags.NONE, 3000, None)
        return result.unpack()

    def close(self):
        try:
            self.bus.close_sync(None)
        finally:
            try:
                self.d.close()
            except BaseException:
                self.d.display.socket.close()  # Our diagnostic connection only; do not leave owned windows behind.
                raise

    def property(self, w, name, kind):
        value = w.get_full_property(self.d.intern_atom(name), kind)
        return list(value.value) if value and value.format == 32 else []

    def owner(self, name):
        window = self.d.get_selection_owner(self.d.intern_atom(name))
        return hex(window.id) if window else None

    def workarea(self):
        g = self.root.get_geometry()
        desktop = self.property(self.root, '_NET_CURRENT_DESKTOP', self.A.CARDINAL)
        areas = self.property(self.root, '_NET_WORKAREA', self.A.CARDINAL)
        at = (desktop[0] if desktop else 0) * 4
        work = areas[at:at + 4] if len(areas) >= at + 4 else [0, 0, g.width, g.height]
        x, y, w, h = map(int, work)
        if not (w > 0 and h > 0 and x >= 0 and y >= 0 and x + w <= g.width and y + h <= g.height):
            raise ValueError('Current work area must fit the root window')
        return [x, y, w, h]

    def snapshot(self):
        wm_ids = self.property(self.root, '_NET_SUPPORTING_WM_CHECK', self.A.WINDOW)
        if not wm_ids:
            raise ValueError('No active EWMH window manager')
        wm = self.d.create_resource_object('window', int(wm_ids[0]))
        wm_pid = self.property(wm, '_NET_WM_PID', self.A.CARDINAL)
        wm_process = process_identity(wm_pid[0]) if wm_pid else None
        if not wm_process or Path(wm_process['cmd'][0]).name != 'xfwm4':
            raise ValueError('This diagnostic is for the active Xfwm session')
        configured = self.call('org.xfce.Xfconf', '/org/xfce/Xfconf', 'org.xfce.Xfconf',
                               'GetProperty', '(ss)', ('xfwm4', '/general/use_compositing'))[0]
        if type(configured) is not bool:
            raise ValueError('Cannot read actual Xfwm compositing setting')
        helper = {'selection_owner': self.owner('_SCISAGA_TABLET_PANEL_EDGE'), 'verified': False,
                  'redirected_frames': [], 'handles': []}
        try:
            raw = json.loads(self.state_file.read_text(encoding='utf-8'))
            process = process_identity(raw['pid'])
            helper.update(process=process, redirected_frames=raw['redirected_frames'], handles=raw['handles'])
            helper['verified'] = bool(helper['selection_owner']) and verified_helper(
                process, wm_process, uid=os.getuid(), state_mtime=self.state_file.stat().st_mtime)
        except (OSError, ValueError, KeyError, TypeError) as error:
            helper['state_error'] = str(error)
        g = self.root.get_geometry()
        for item in helper['handles']:
            try:
                client = self.d.create_resource_object('window', int(item['client']))
                frame = self.d.create_resource_object('window', int(item['frame']))
                size = frame.get_geometry()
                item['actual_geometry'] = [size.x, size.y, size.width, size.height]
                if client.get_wm_class() != ('xfce4-panel', 'Xfce4-panel') or not 1 <= size.height <= 16:
                    helper['verified'] = False
                item['at_bottom'] = size.y + size.height == g.height
            except Exception as error:
                item['geometry_error'] = str(error)
                helper['verified'] = False
        source = Path('/usr/local/bin/tablet-panel-edge')
        return {'screen': [g.width, g.height], 'workarea': self.workarea(),
                'wm': {'xid': hex(wm.id), 'process': wm_process}, 'guest_uid': os.getuid(),
                'compositor': {'configured': configured,
                               'selection_owner': self.owner('_NET_WM_CM_S' + str(self.screen))},
                'helper': helper, 'helper_source_sha256': sha(source.read_bytes()) if source.exists() else None}

    def launch_helper(self, wm_process):
        self.call('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus',
                  'StartServiceByName', '(su)', ('org.xfce.FileManager', 0))
        pid = self.call('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus',
                        'GetConnectionUnixProcessID', '(s)', ('org.xfce.FileManager',))[0]
        if process_identity(pid)['tracer'] != wm_process['tracer']:
            raise ValueError('File-manager launch service is outside the managed desktop tracer cohort')
        self.call('org.xfce.FileManager', '/org/xfce/FileManager', 'org.xfce.FileManager', 'Execute',
                  '(ssasss)', (str(Path.home()), 'file:///usr/local/bin/tablet-panel-edge', [], os.environ['DISPLAY'], ''))

    def wait_helper(self, running):
        end = time.monotonic() + 3
        while time.monotonic() < end:
            owner = self.owner('_SCISAGA_TABLET_PANEL_EDGE')
            if running and owner and self.state_file.exists():
                snap = self.snapshot()
                if snap['helper']['verified'] and snap['helper']['redirected_frames']:
                    return snap
            if not running and not owner and not self.state_file.exists():
                return None
            time.sleep(.05)
        raise RuntimeError('Expected dock-helper state was not reached; inspect recovery checkpoint')


def compare(audit, request, before, checkpoint):
    from Xlib import Xutil, display
    from Xlib.protocol import event
    X = audit.X
    if diagnosis(before) != 'non_composited' or not before['helper']['verified']:
        raise ValueError('Compare requires a verified helper and no active/configured whole-desktop compositor')
    if not before['helper']['redirected_frames']:
        raise ValueError('No verified manual dock redirect to compare')
    wm_identity = before['wm']['process']
    original = before['helper']['process']
    state = {'trials': [], 'recovery': {'needed': False, 'restored': False},
             'original_helper': original, 'original_wm': wm_identity,
             'probe_process': process_identity(os.getpid()), 'stage': 'preflight'}
    windows, counters, gcs = [], {}, []
    drawing = None
    area = before['workarea']
    x, y, w, h = area
    if w < 640 or h < 480:
        raise ValueError('Comparison needs a work area of at least 640x480; inspection remains available')
    geometries = [(x + w // 20, y + h // 20, w * 4 // 5, h * 3 // 5),
                  (x + w // 8, y + h // 6, w * 2 // 5, h * 3 // 10)]
    start_x, start_y = geometries[1][:2]
    workload = {'workarea': area, 'windows': geometries, 'steps': request['steps'],
                'step_ms': request['step_ms'], 'travel': [w // 5, h // 8], 'pattern': 'sin-squared-stripes-v1'}
    state['workload'] = workload
    state['workload_sha256'] = sha(json.dumps(workload, sort_keys=True).encode())
    deadline = time.monotonic() + 43

    def save():
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        temp = checkpoint.with_suffix('.new')
        temp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        temp.chmod(0o600)
        temp.replace(checkpoint)

    def pump(seconds):
        end = time.monotonic() + seconds
        while True:
            if time.monotonic() > deadline:
                raise TimeoutError('Bounded window-probe duration exceeded')
            while drawing.pending_events():
                e = drawing.next_event()
                row = counters.get(getattr(getattr(e, 'window', None), 'id', None))
                if row is None:
                    continue
                if e.type in (X.DestroyNotify, X.ClientMessage):
                    raise InterruptedError('A probe window was closed')
                if e.type == X.Expose:
                    row['expose_events'] += 1
                    if e.count == 0:
                        row['draws'] += 1
                        for i in range(32):
                            e.window.fill_rectangle(row['gc'][i % 2], 0, i * row['height'] // 32,
                                                    row['width'], max(1, row['height'] // 32 + 1))
                        drawing.flush()
                if e.type == X.ConfigureNotify:
                    row.update(width=e.width, height=e.height)
                    if e.send_event:
                        row['positions'].append([e.x, e.y])
            remaining = end - time.monotonic()
            if remaining <= 0:
                return
            select.select([drawing.fileno()], [], [], remaining)

    def move(px, py):
        audit.root.send_event(event.ClientMessage(window=windows[1],
            client_type=audit.d.intern_atom('_NET_MOVERESIZE_WINDOW'),
            data=(32, [1 | (1 << 8) | (1 << 9) | (2 << 12), px, py, 0, 0])),
            event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
        audit.d.flush()

    def trials(label):
        for _ in range(request['trials']):
            state['stage'] = label + ':snapshot'
            save()
            if audit.workarea() != area or process_identity(wm_identity['pid']) != wm_identity:
                raise ValueError('Work area or desktop changed during comparison')
            if audit.owner('_NET_WM_CM_S' + str(audit.screen)):
                raise ValueError('Compositing changed during comparison')
            expected_owner = (None if label == 'stopped' else before['helper']['selection_owner']
                              if label == 'running' else state['recovery']['helper']['selection_owner'])
            if audit.owner('_SCISAGA_TABLET_PANEL_EDGE') != expected_owner:
                raise ValueError('Dock-helper state changed during comparison')
            if any(audit.d.create_resource_object('window', win.id).get_attributes().map_state != X.IsViewable
                   for win in windows):
                raise ValueError('Probe window is hidden; comparison is invalid')
            move(start_x, start_y)
            pump(.2)
            previous = {k: (v['draws'], v['expose_events']) for k, v in counters.items()}
            position_start = len(counters[windows[1].id]['positions'])
            started = time.monotonic()
            for i in range(request['steps']):
                t = math.sin(math.pi * (i + 1) / request['steps']) ** 2
                move(start_x + round(t * w / 5), start_y + round(t * h / 8))
                pump(max(0, started + (i + 1) * request['step_ms'] / 1000 - time.monotonic()))
            pump(.1)
            positions = counters[windows[1].id]['positions'][position_start:]
            if len({tuple(p) for p in positions}) < 5:
                raise ValueError('Requested trajectory was not applied by the WM')
            state['trials'].append({'helper': label, 'elapsed_seconds': round(time.monotonic() - started, 4),
                'observed_client_positions': positions,
                'windows': [{'role': row['role'], 'draws': row['draws'] - previous[ident][0],
                             'expose_events': row['expose_events'] - previous[ident][1]}
                            for ident, row in counters.items()]})
            save()

    def action():
        nonlocal drawing
        save()
        audit.launch_helper(wm_identity)  # Duplicate exits via the existing singleton selection.
        require_same_identity(original, process_identity(original['pid']))
        # Keep synchronous inspection replies off the event/drawing connection.
        drawing = display.Display()
        for role, (px, py, width, height), colors in zip(('base', 'front'), geometries,
                                                       ((0x34485e, 0x9bb3c4), (0x105c87, 0xc1e4f5))):
            win = drawing.screen().root.create_window(px, py, width, height, 0, drawing.screen().root_depth,
                X.InputOutput, X.CopyFromParent, background_pixel=colors[0],
                event_mask=X.ExposureMask | X.StructureNotifyMask)
            windows.append(win)
            win.set_wm_name('Window redraw check ' + role)
            win.set_wm_class('tablet-window-probe', 'TabletWindowProbe')
            win.set_wm_protocols([audit.d.intern_atom('WM_DELETE_WINDOW')])
            win.set_wm_normal_hints(flags=Xutil.USPosition, x=px, y=py)
            win.change_property(audit.d.intern_atom('_NET_WM_PID'), audit.A.CARDINAL, 32, [os.getpid()])
            gc = [win.create_gc(foreground=color) for color in colors]
            gcs.extend(gc)
            counters[win.id] = dict(role=role, draws=0, expose_events=0, width=width, height=height, gc=gc, positions=[])
            win.map()
        drawing.flush()
        pump(.5)
        state['actual_initial_frames'] = []
        for win in windows:
            g = audit.d.create_resource_object('window', win.id).query_tree().parent.get_geometry()
            if not (x <= g.x and y <= g.y and g.x + g.width <= x + w and g.y + g.height <= y + h):
                raise ValueError('Probe geometry does not fit the current work area')
            state['actual_initial_frames'].append([g.x, g.y, g.width, g.height])
        trials('running')
        require_same_identity(original, process_identity(original['pid']))
        state['recovery']['needed'] = True
        state['stage'] = 'pause:signal'
        save()  # Write recovery evidence before the reversible SIGTERM.
        os.kill(original['pid'], signal.SIGTERM)
        state['stage'] = 'pause:wait'
        save()
        audit.wait_helper(False)
        trials('stopped')
        restore()
        trials('restored')

    def restore():
        if not state['recovery']['needed'] or state['recovery']['restored']:
            return
        require_same_identity(wm_identity, process_identity(wm_identity['pid']))
        if audit.owner('_NET_WM_CM_S' + str(audit.screen)):
            raise ValueError('A compositor appeared; preserve checkpoint instead of restarting the redirector')
        state['stage'] = 'restore:launch'
        save()
        audit.launch_helper(wm_identity)
        state['stage'] = 'restore:wait'
        save()
        after = audit.wait_helper(True)
        if not all(item['at_bottom'] for item in after['helper']['handles']):
            raise ValueError('Restored dock trigger is not at the current bottom edge')
        state['recovery'].update(restored=True, helper=after['helper'])
        save()

    def cleanup():
        state['stage'] = 'cleanup'
        save()
        errors = []
        for win in windows:
            try:
                win.destroy()
            except Exception as error:
                errors.append(str(error))
        for gc in gcs:
            gc.free()
        if drawing is not None:
            try:
                drawing.close()
            except BaseException:
                drawing.display.socket.close()
                raise
        time.sleep(.05)
        state['owned_windows_cleanup_attempted'] = True
        remaining = []
        from Xlib import error as xerror
        for win in windows:
            try:
                audit.d.create_resource_object('window', win.id).get_attributes()
                remaining.append(hex(win.id))
            except xerror.BadWindow:
                pass
        state['owned_windows_remaining'] = remaining
        if remaining:
            errors.append('Owned probe windows remain')
        if errors:
            raise RuntimeError('; '.join(errors))

    state['errors'] = run_with_recovery(action, restore, cleanup)
    state['status'] = 'failed' if state['errors'] else 'passed'
    state['measurement'] = 'Expose events and completed redraws; not FPS, GPU utilization, or physical touch acceptance'
    save()
    return state


def guest_run(request):
    request = dict(request)
    validated = options(**{k: request[k] for k in ('mode', 'trials', 'steps', 'step_ms', 'apply')})
    if validated['mode'] == 'compare' and not validated['apply']:
        return {'status': 'skipped', 'reason': 'Comparison requires --apply'}
    os.environ.update(request['session_env'], GDK_GL='disable', LIBGL_ALWAYS_INDIRECT='1', NO_AT_BRIDGE='1')
    audit = None
    old_handlers = {}
    try:
        def interrupted(signum, _):
            raise InterruptedError(f'Window probe interrupted by signal {signum}')
        old_handlers[signal.SIGALRM] = signal.signal(signal.SIGALRM, interrupted)
        signal.alarm(50)
        audit = WindowAudit()
        before = audit.snapshot()
        finding = diagnosis(before)
        result = {'status': 'failed' if finding in ('possible_redirect_conflict', 'unverified_helper_state',
                   'compositor_state_mismatch') else 'passed', 'diagnosis': finding, 'before': before}
        if request['mode'] == 'compare':
            for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
                old_handlers[sig] = signal.signal(sig, interrupted)
            result['comparison'] = compare(audit, request, before, Path(request['checkpoint']))
            result['status'] = result['comparison']['status']
            result['after'] = audit.snapshot()
            if (diagnosis(result['after']) != 'non_composited'
                    or result['after']['wm']['process'] != before['wm']['process']):
                result.update(status='failed', error='Desktop/compositor changed during comparison')
        return result
    finally:
        try:
            if audit is not None:
                signal.alarm(5)
                audit.close()
        finally:
            signal.alarm(0)
            for sig, handler in old_handlers.items():
                signal.signal(sig, handler)


def interrupt_owned_probe(checkpoint: Path):
    """Native UID and the unique request must match before interrupting a timed-out diagnostic."""
    state = json.loads(checkpoint.read_text(encoding='utf-8'))
    saved = state['probe_process']
    current = process_identity(saved['pid'])
    if current['uid'] != os.getuid():
        raise ValueError('Diagnostic UID changed; refuse interruption')
    for key in ('pid', 'start_ticks', 'executable', 'tracer', 'cmd'):
        if current[key] != saved[key]:
            raise ValueError('Diagnostic identity changed; refuse interruption')
    cmd = current['cmd']
    if '--guest-request' not in cmd:
        raise ValueError('Unknown diagnostic command')
    payload = json.loads(base64.b64decode(cmd[cmd.index('--guest-request') + 1], validate=True))
    if payload.get('checkpoint') != str(checkpoint) or payload.get('mode') != 'compare':
        raise ValueError('Diagnostic request differs from checkpoint')
    if current['pid'] in (state['original_helper']['pid'], state['original_wm']['pid']):
        raise ValueError('Refuse interruption of a desktop component')
    os.kill(current['pid'], signal.SIGTERM)


def native_run(request):
    request = options(**request)
    home = Path.home()
    prefix = Path(os.environ.get('PREFIX', '/data/data/com.termux/files/usr'))
    if not Path('/system/bin/getprop').exists() or not str(prefix).endswith('/com.termux/files/usr'):
        raise ValueError('Native probe must run inside Termux')
    profile = home / '.config/tablet-desktop/config.json'
    data = profile.read_bytes()
    config = json.loads(data)
    container, user = config.get('container', 'desktop'), config.get('user', 'developer')
    if any(not isinstance(v, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', v)
           for v in (container, user)):
        raise ValueError('Invalid installed container or user')
    executable = prefix / 'bin/proot-distro'
    if not executable.is_file():
        raise RuntimeError('Missing proot-distro. Native Termux: pkg install proot-distro')
    env_file = home / '.local/state/tablet-desktop/session.env'
    env = {}
    for line in env_file.read_text(encoding='utf-8').splitlines():
        fields = shlex.split(line)
        if len(fields) != 2 or fields[0] != 'export' or '=' not in fields[1]:
            raise ValueError('Unrecognized session environment; no shell code will be executed')
        key, value = fields[1].split('=', 1)
        if key not in ('DISPLAY', 'DBUS_SESSION_BUS_ADDRESS', 'XDG_RUNTIME_DIR', 'SESSION_MANAGER'):
            raise ValueError('Unexpected session environment key')
        env[key] = value
    if not all(env.get(k) for k in ('DISPLAY', 'DBUS_SESSION_BUS_ADDRESS', 'XDG_RUNTIME_DIR')):
        raise ValueError('Desktop session environment is incomplete')
    desktop = json.loads(subprocess.check_output([prefix / 'bin/desktop', 'status', '--json'], text=True, timeout=12))
    if desktop.get('phase') != 'running' or not desktop.get('core_alive'):
        raise ValueError('Start the desktop normally before window diagnosis')
    source = globals().get('_SOURCE') or Path(__file__).read_text(encoding='utf-8')
    guest_request = dict(request, session_env=env)
    if request['mode'] == 'compare':
        guest_request['checkpoint'] = str(home / '.local/state/tablet-desktop/probes' /
                                          ('window-' + uuid.uuid4().hex) / 'recovery.json')
    encoded = base64.b64encode(json.dumps(guest_request).encode()).decode()
    child = subprocess.Popen([str(executable), 'login', container, '--user', user, '--shared-tmp', '--',
                              '/usr/bin/python3', '-', '--guest-request', encoded],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    timed_out = False
    try:
        stdout, stderr = child.communicate(source.encode('utf-8'), timeout=55)
    except subprocess.TimeoutExpired:
        timed_out = True
        checkpoint = guest_request.get('checkpoint')
        try:
            if checkpoint:
                interrupt_owned_probe(Path(checkpoint))
            else:
                child.terminate()  # This Popen is only the read-only diagnostic PRoot.
            stdout, stderr = child.communicate(timeout=8)
        except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired) as error:
            for stream in (child.stdin, child.stdout, child.stderr):
                if stream:
                    stream.close()
            return {'status': 'failed', 'error': 'Native I/O deadline; recovery requires inspection: ' + str(error),
                    'recovery_checkpoint': checkpoint, 'profile_sha256': sha(data), 'session': desktop['session']}
    if not stdout:
        raise RuntimeError('Guest probe failed: ' + stderr.decode('utf-8', errors='replace')[-1200:])
    result = json.loads(stdout.decode('utf-8'))
    if timed_out:
        result.update(status='failed', error='Native I/O deadline reached; inspect saved recovery result')
    result['native_uid'] = os.getuid()
    result['profile_sha256'] = sha(data)
    result['session'] = desktop['session']
    if 'checkpoint' in guest_request:
        result['recovery_checkpoint'] = guest_request['checkpoint']
    current = json.loads(subprocess.check_output([prefix / 'bin/desktop', 'status', '--json'], text=True, timeout=12))
    if profile.read_bytes() != data or current.get('session') != desktop['session'] or not current.get('core_alive'):
        result.update(status='failed', error='Profile or desktop changed during diagnosis; inspect recovery evidence')
    return result


def probe_device(device, request=None):
    request = options(**(request or {}))
    if request['mode'] == 'compare' and not request['apply']:
        return {'status': 'skipped', 'reason': 'Preview only: --apply creates owned windows and pauses/restores the dock helper'}
    source = Path(__file__).read_bytes()
    payload = base64.b64encode(json.dumps(request).encode()).decode()
    encoded_source = base64.b64encode(source).decode()
    bootstrap = ("python - <<'WINDOW_PROBE'\nimport base64,sys\n"
        f"source=base64.b64decode('{encoded_source}').decode('utf-8')\n"
        f"sys.argv=['window_probe.py','--native-request','{payload}']\n"
        "exec(compile(source,'window_probe.py','exec'),{'__name__':'__main__','__file__':'window_probe.py','_SOURCE':source})\nWINDOW_PROBE\n")
    result = json.loads(device.ssh_script(bootstrap, timeout=100))
    result['source_sha256'] = sha(source)
    result['input_summary'] = dict(request, connection_sha256=device.digest)
    result['input_sha256'] = sha(json.dumps(result['input_summary'], sort_keys=True).encode())
    return result


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ('--native-request', '--guest-request'):
        try:
            request = json.loads(base64.b64decode(argv[1], validate=True))
            result = native_run(request) if argv[0] == '--native-request' else guest_run(request)
        except Exception as error:
            result = {'status': 'failed', 'error': f'{type(error).__name__}: {error}'}
        print(json.dumps(result, ensure_ascii=False))
        return EXIT_CODES[result['status']]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['inspect', 'compare'], nargs='?', default='inspect')
    parser.add_argument('--connection', type=Path, required=True)
    parser.add_argument('--state', type=Path, required=True, help='Private output outside this skill')
    parser.add_argument('--apply', action='store_true', help='Allow temporary windows and verified helper pause/restore')
    parser.add_argument('--trials', type=int, default=3)
    parser.add_argument('--steps', type=int, default=120)
    parser.add_argument('--step-ms', type=int, default=20)
    args = parser.parse_args(argv)
    from device_transport import Device, atomic_json
    if args.state.resolve().is_relative_to(Path(__file__).resolve().parents[1]):
        parser.error('Keep device evidence outside the public skill directory')
    summary = {'mode': args.mode, 'trials': args.trials, 'steps': args.steps,
               'step_ms': args.step_ms, 'apply': args.apply}
    try:
        request = options(args.mode, trials=args.trials, steps=args.steps, step_ms=args.step_ms, apply=args.apply)
        device = Device.read(args.connection)
        summary['connection_sha256'] = device.digest
        result = probe_device(device, request)
        atomic_json(args.state, result)
        print(json.dumps(result, ensure_ascii=False))
        return EXIT_CODES[result['status']]
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        result = {'status': 'failed', 'error': str(error), 'input_summary': summary,
                  'input_sha256': sha(json.dumps(summary, sort_keys=True).encode()),
                  'source_sha256': sha(Path(__file__).read_bytes())}
        atomic_json(args.state, result)
        print(json.dumps(result, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
