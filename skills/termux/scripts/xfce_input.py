#!/usr/bin/env python3
"""Apply reviewed Xfce shortcuts/click thresholds in the current guest session, or restore them."""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

def menu_paths():
    key = hashlib.sha256(os.environ.get('DISPLAY', '').encode()).hexdigest()[:12]
    base = Path.home() / '.local/state/tablet-desktop'
    return base / ('menu-key-' + key + '.lock'), base / ('menu-key-' + key + '.json')


def process_identity(pid):
    proc = Path('/proc') / str(pid)
    fields = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
    return {'pid': pid, 'start_ticks': fields[19], 'session': fields[3], 'uid': proc.stat().st_uid}


def menu_service():
    import fcntl
    binary = str(Path.home() / '.local/lib/tablet-desktop/menu-key')
    if not Path(binary).is_file():
        raise RuntimeError('Menu observer is not installed; apply --windows-shortcuts in the Xfce terminal')
    lock, record = menu_paths()
    lock.parent.mkdir(parents=True, exist_ok=True)
    stream = lock.open('a')
    try:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return {'status': 'skipped', 'reason': 'menu key already running for this display'}
    os.set_inheritable(stream.fileno(), True)
    argv = [binary, str(Path.home() / '.local/bin/tablet-window-action')]
    identity = dict(process_identity(os.getpid()), argv=argv, display=os.environ['DISPLAY'])
    save(record, identity)
    # Exec a blocking XInput observer, with no resident Python interpreter or input logs.
    with open(os.devnull, 'wb') as quiet:
        os.dup2(quiet.fileno(), 1)
        os.dup2(quiet.fileno(), 2)
    os.execv(binary, argv)


def stop_menu(identity):
    if identity is None:
        return
    pid = identity['pid']
    try:
        current = process_identity(pid)
    except FileNotFoundError:
        return
    if any(current[k] != identity[k] for k in current):
        raise ValueError('Menu-key PID identity changed; inspect before stopping')
    argv = (Path('/proc') / str(pid) / 'cmdline').read_bytes().rstrip(b'\0').decode().split('\0')
    if argv != identity['argv'] or str((Path('/proc') / str(pid) / 'exe').readlink()) != identity['argv'][0]:
        raise ValueError('Menu-key command changed; inspect before stopping')
    os.kill(pid, signal.SIGTERM)
    until = time.monotonic() + 1
    while (Path('/proc') / str(pid)).exists() and time.monotonic() < until:
        time.sleep(.02)


def menu_restore_identity(state):
    """Autostart can create a new PID after apply; use this display's verified record."""
    _, record = menu_paths()
    if not record.exists():
        return state.get('menu_process')
    identity = json.loads(record.read_text(encoding='utf-8'))
    expected = [str(Path.home() / '.local/lib/tablet-desktop/menu-key'),
                str(Path.home() / '.local/bin/tablet-window-action')]
    if identity.get('display') != os.environ.get('DISPLAY') or identity.get('argv') != expected:
        raise ValueError('Menu-key record belongs to another display or command; inspect before restoring')
    return identity


def start_menu(helper):
    _, record = menu_paths()
    old_record = record.read_bytes() if record.exists() else None
    child = subprocess.Popen([sys.executable, str(helper), 'menu-service'], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    until = time.monotonic() + 3
    while time.monotonic() < until:
        if record.exists() and record.read_bytes() != old_record:
            identity = json.loads(record.read_text())
            if identity['pid'] == child.pid:
                argv = (Path('/proc') / str(child.pid) / 'cmdline').read_bytes().rstrip(b'\0').decode().split('\0')
                if argv == identity['argv']:
                    return identity
        if child.poll() is not None:
            if child.returncode == 0 and old_record is not None:
                return None
            raise RuntimeError('Menu-key helper failed to start; backup retained')
        time.sleep(.05)
    child.terminate()
    child.wait(timeout=5)
    raise RuntimeError('Menu-key startup timed out; backup retained')


def query(*args, check=True):
    p = subprocess.run(['xfconf-query', *args], text=True, capture_output=True, timeout=10)
    if check and p.returncode:
        raise RuntimeError(p.stderr.strip() or 'xfconf-query failed')
    return p.stdout.strip()


def value(channel, prop):
    names = query('-c', channel, '-l').splitlines()
    return query('-c', channel, '-p', prop) if prop in names else None


def put(change, target):
    channel, prop = change['channel'], change['property']
    current = value(channel, prop)
    if current == target:
        return
    if target is None:
        query('-c', channel, '-p', prop, '-r')
    elif current is None:
        query('-c', channel, '-p', prop, '-n', '-t', change['type'], '-s', target)
    else:
        query('-c', channel, '-p', prop, '-s', target)
    if value(channel, prop) != target:
        raise RuntimeError('Xfconf readback differs: ' + prop)


def plan(home, shortcuts=False, time_ms=None, distance=None):
    changes = []
    def add(channel, prop, kind, new):
        changes.append({'channel': channel, 'property': prop, 'type': kind, 'after': new})
    if time_ms is not None:
        if not 200 <= time_ms <= 2000:
            raise ValueError('Double-click time must be 200..2000 ms')
        add('xsettings', '/Net/DoubleClickTime', 'int', str(time_ms))
    if distance is not None:
        if not 4 <= distance <= 100:
            raise ValueError('Double-click distance must be 4..100 pixels')
        add('xsettings', '/Net/DoubleClickDistance', 'int', str(distance))
    if shortcuts:
        commands = {
            # A direct modifier grab in xfsettingsd prevents xfwm4 receiving its combinations.
            'Super_L': None, 'Super_R': None,
            '<Alt>F1': 'xfce4-popup-applicationsmenu',
            '<Super>e': 'thunar',
            '<Primary><Alt>t': 'exo-open --launch TerminalEmulator',
            '<Alt>F2': 'xfce4-appfinder --collapsed',
            '<Super>Up': shlex.quote(str(home / '.local/bin/tablet-window-action')) + ' up',
            '<Super>Down': shlex.quote(str(home / '.local/bin/tablet-window-action')) + ' down',
            '<Super>Left': shlex.quote(str(home / '.local/bin/tablet-window-action')) + ' left',
            '<Super>Right': shlex.quote(str(home / '.local/bin/tablet-window-action')) + ' right',
            '<Super>d': shlex.quote(str(home / '.local/bin/tablet-window-action')) + ' desktop',
        }
        windows = {
            '<Alt>F4': 'close_window_key',
            '<Alt>Tab': 'cycle_windows_key', '<Alt><Shift>Tab': 'cycle_reverse_windows_key',
        }
        # Exactly one provider owns each accelerator; remove only its conflicting custom entry.
        for keys, provider, other in ((commands, 'commands', 'xfwm4'), (windows, 'xfwm4', 'commands')):
            for key, command in keys.items():
                add('xfce4-keyboard-shortcuts', f'/{other}/custom/{key}', 'string', None)
                add('xfce4-keyboard-shortcuts', f'/{provider}/custom/{key}', 'string', command)
    if not changes:
        raise ValueError('Choose --windows-shortcuts and/or a double-click threshold')
    return changes


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    path.chmod(0o600)


def compile_menu(source):
    if importlib.util.find_spec('Xlib') is None:
        raise RuntimeError('Install guest action dependency: apt-get install python3-xlib')
    if not Path(source).is_file():
        raise ValueError('Supply --menu-source pointing to assets/desktop/guest/tablet-menu-key.c')
    if not shutil.which('gcc'):
        raise RuntimeError('Install guest build dependencies: gcc libx11-dev libxi-dev')
    with tempfile.TemporaryDirectory() as build:
        executable = Path(build) / 'menu-key'
        built = subprocess.run(['gcc', '-O2', '-Wall', '-Wextra', str(source), '-o', str(executable), '-lXi', '-lX11'], capture_output=True, text=True, timeout=30)
        if built.returncode:
            raise RuntimeError('Menu observer build failed; install gcc libx11-dev libxi-dev: ' + built.stderr[-1200:])
        return executable.read_bytes()


def apply_settings(args):
    home = Path.home()
    changes = plan(home, args.windows_shortcuts, args.double_click_time, args.double_click_distance)
    for item in changes:
        item['before'] = value(item['channel'], item['property'])
    changes = [item for item in changes if item['before'] != item['after']]
    state = {'schema': 1, 'home': str(home), 'status': 'planned', 'changes': changes}
    helper = home / '.local/bin/tablet-window-action'
    if args.windows_shortcuts:
        source = getattr(args, 'menu_source', None) or Path(__file__).resolve().parents[1] / 'assets/desktop/guest/tablet-menu-key.c'
        menu_payload = compile_menu(source)
        menu_binary = home / '.local/lib/tablet-desktop/menu-key'
        if menu_binary.is_symlink() or (menu_binary.exists() and not menu_binary.is_file()):
            raise ValueError('Menu observer must be a regular file')
        old_binary = menu_binary.read_bytes() if menu_binary.exists() else None
        state['menu_binary'] = {'before': base64.b64encode(old_binary).decode() if old_binary is not None else None,
                                'before_mode': menu_binary.stat().st_mode & 0o777 if old_binary is not None else None,
                                'after_sha256': hashlib.sha256(menu_payload).hexdigest()}
        if helper.is_symlink() or (helper.exists() and not helper.is_file()):
            raise ValueError('Window helper must be a regular file')
        payload = Path(__file__).read_bytes()
        old = helper.read_bytes() if helper.exists() else None
        state['helper'] = {'before': base64.b64encode(old).decode() if old is not None else None,
                           'before_mode': helper.stat().st_mode & 0o777 if old is not None else None,
                           'after_sha256': hashlib.sha256(payload).hexdigest()}
        autostart = home / '.config/autostart/tablet-menu-key.desktop'
        if autostart.is_symlink() or (autostart.exists() and not autostart.is_file()):
            raise ValueError('Menu autostart must be a regular file')
        entry = ('[Desktop Entry]\nType=Application\nName=Desktop menu key\nOnlyShowIn=XFCE;\n'
                 + 'Exec=' + json.dumps(str(helper)) + ' menu-service\nNoDisplay=true\n').encode()
        old_entry = autostart.read_bytes() if autostart.exists() else None
        state['menu_autostart'] = {'before': base64.b64encode(old_entry).decode() if old_entry is not None else None,
                                   'before_mode': autostart.stat().st_mode & 0o777 if old_entry is not None else None,
                                   'after_sha256': hashlib.sha256(entry).hexdigest()}
    if not args.apply:
        return state
    if args.state.exists():
        raise ValueError('State already exists; use a new path or restore the reviewed state')
    args.state.parent.mkdir(parents=True, exist_ok=True)
    with args.state.open('x', encoding='utf-8') as stream:
        stream.write('{}\n')
    state['status'] = 'applying'
    save(args.state, state)
    if args.windows_shortcuts:
        helper.parent.mkdir(parents=True, exist_ok=True)
        helper.write_bytes(payload)
        helper.chmod(0o755)
        menu_binary.parent.mkdir(parents=True, exist_ok=True)
        menu_binary.write_bytes(menu_payload)
        menu_binary.chmod(0o755)
        autostart.parent.mkdir(parents=True, exist_ok=True)
        autostart.write_bytes(entry)
        autostart.chmod(0o644)
    for item in changes:
        if value(item['channel'], item['property']) != item['before']:
            raise ValueError('Setting changed during preparation: ' + item['property'])
        put(item, item['after'])
    if args.windows_shortcuts:
        state['menu_process'] = start_menu(helper)
    state['status'] = 'passed'
    save(args.state, state)
    return state


def restore(args):
    state = json.loads(args.state.read_text(encoding='utf-8'))
    if state.get('schema') != 1 or state.get('home') != str(Path.home()):
        raise ValueError('State belongs to another schema/user home')
    for item in state['changes']:
        if value(item['channel'], item['property']) not in (item['before'], item['after']):
            raise ValueError('Setting changed after apply; inspect before restoring: ' + item['property'])
    helper = Path.home() / '.local/bin/tablet-window-action'
    if 'helper' in state:
        old = state['helper']['before']
        if helper.is_symlink() or (helper.exists() and not helper.is_file()) or (not helper.exists() and old is not None):
            raise ValueError('Installed helper is missing or no longer a regular file')
        allowed = {state['helper']['after_sha256']}
        if old is not None:
            allowed.add(hashlib.sha256(base64.b64decode(old)).hexdigest())
        if helper.exists() and hashlib.sha256(helper.read_bytes()).hexdigest() not in allowed:
            raise ValueError('Window helper changed after apply; inspect before restoring')
    autostart = Path.home() / '.config/autostart/tablet-menu-key.desktop'
    if 'menu_autostart' in state:
        old = state['menu_autostart']['before']
        allowed = {state['menu_autostart']['after_sha256']}
        if old is not None:
            allowed.add(hashlib.sha256(base64.b64decode(old)).hexdigest())
        if autostart.is_symlink() or (not autostart.exists() and old is not None) or (autostart.exists() and hashlib.sha256(autostart.read_bytes()).hexdigest() not in allowed):
            raise ValueError('Menu autostart changed after apply; inspect before restoring')
    menu_binary = Path.home() / '.local/lib/tablet-desktop/menu-key'
    if 'menu_binary' in state:
        old = state['menu_binary']['before']
        allowed = {state['menu_binary']['after_sha256']}
        if old is not None:
            allowed.add(hashlib.sha256(base64.b64decode(old)).hexdigest())
        if menu_binary.is_symlink() or (not menu_binary.exists() and old is not None) or (menu_binary.exists() and hashlib.sha256(menu_binary.read_bytes()).hexdigest() not in allowed):
            raise ValueError('Menu observer changed after apply; inspect before restoring')
    if not args.apply:
        return {'status': 'planned', 'changes': len(state['changes'])}
    stop_menu(menu_restore_identity(state) if 'menu_binary' in state else state.get('menu_process'))
    for item in reversed(state['changes']):
        put(item, item['before'])
    if 'helper' in state:
        old = state['helper']['before']
        if old is None:
            helper.unlink(missing_ok=True)
        else:
            helper.write_bytes(base64.b64decode(old))
            helper.chmod(state['helper']['before_mode'])
    if 'menu_autostart' in state:
        old = state['menu_autostart']['before']
        if old is None:
            autostart.unlink(missing_ok=True)
        else:
            autostart.write_bytes(base64.b64decode(old))
            autostart.chmod(state['menu_autostart']['before_mode'])
    if 'menu_binary' in state:
        old = state['menu_binary']['before']
        if old is None:
            menu_binary.unlink(missing_ok=True)
        else:
            menu_binary.write_bytes(base64.b64decode(old))
            menu_binary.chmod(state['menu_binary']['before_mode'])
    state['status'] = 'restored'
    save(args.state, state)
    return {'status': 'restored', 'changes': len(state['changes'])}


def window_decision(direction, maximized):
    return 'maximize' if direction == 'up' else 'restore' if maximized else 'minimize'


def window_action(direction):
    try:
        from Xlib import X, Xutil, display, protocol
    except ImportError as error:
        raise RuntimeError('Install guest dependency: sudo apt-get install python3-xlib') from error
    d = display.Display()
    try:
        root = d.screen().root
        mask = X.SubstructureRedirectMask | X.SubstructureNotifyMask
        def send(obj, kind, values):
            root.send_event(protocol.event.ClientMessage(window=obj, client_type=d.intern_atom(kind), data=(32, [int(v) & 0xffffffff for v in values])), event_mask=mask)
            d.sync()
        if direction == 'menu-toggle':
            visible = False
            for child in root.query_tree().children:
                try:
                    types = child.get_full_property(d.intern_atom('_NET_WM_WINDOW_TYPE'), X.AnyPropertyType)
                    if child.get_attributes().map_state == X.IsViewable and types is not None and any('MENU' in d.get_atom_name(int(a)) for a in types.value):
                        visible = True
                        break
                except Exception:
                    continue
            if visible:
                from Xlib import XK
                from Xlib.ext import xtest
                code = d.keysym_to_keycode(XK.string_to_keysym('Escape'))
                xtest.fake_input(d, X.KeyPress, code)
                xtest.fake_input(d, X.KeyRelease, code)
                d.sync()
            else:
                subprocess.run(['xfce4-popup-applicationsmenu'], check=True, timeout=5)
            return {'status': 'passed', 'action': 'close_menu' if visible else 'open_menu'}
        if direction == 'desktop':
            p = root.get_full_property(d.intern_atom('_NET_SHOWING_DESKTOP'), X.AnyPropertyType)
            target = 0 if p is not None and int(p.value[0]) else 1
            send(root, '_NET_SHOWING_DESKTOP', [target, 0, 0, 0, 0])
            return {'status': 'passed', 'action': 'show_desktop' if target else 'restore_desktop'}
        prop = root.get_full_property(d.intern_atom('_NET_ACTIVE_WINDOW'), X.AnyPropertyType)
        if prop is None or not int(prop.value[0]):
            return {'status': 'skipped', 'reason': 'no active window'}
        w = d.create_resource_object('window', int(prop.value[0]))
        kind = w.get_full_property(d.intern_atom('_NET_WM_WINDOW_TYPE'), X.AnyPropertyType)
        if kind is not None and any(d.get_atom_name(int(a)) in ('_NET_WM_WINDOW_TYPE_DESKTOP', '_NET_WM_WINDOW_TYPE_DOCK') for a in kind.value):
            return {'status': 'skipped', 'reason': 'desktop or panel'}
        a, b = d.intern_atom('_NET_WM_STATE_MAXIMIZED_VERT'), d.intern_atom('_NET_WM_STATE_MAXIMIZED_HORZ')
        states = w.get_full_property(d.intern_atom('_NET_WM_STATE'), X.AnyPropertyType)
        cached = w.get_full_property(d.intern_atom('_SCISAGA_TILE_RESTORE'), X.AnyPropertyType)
        maximized = states is not None and any(v in states.value for v in (a, b))
        action = window_decision(direction, maximized or cached is not None)
        def unmaximize():
            send(w, '_NET_WM_STATE', [0, a, b, 2, 0])
            until = time.monotonic() + .7
            while time.monotonic() < until:
                state = w.get_full_property(d.intern_atom('_NET_WM_STATE'), X.AnyPropertyType)
                if state is None or not any(v in state.value for v in (a, b)):
                    return
                time.sleep(.02)
            raise RuntimeError('Window manager did not restore the window')
        def resize(rect):
            send(w, '_NET_MOVERESIZE_WINDOW', [10 | 0xf00 | 0x2000, *rect])
        if direction in ('left', 'right'):
            if cached is None:
                g = w.get_geometry()
                pos = w.translate_coords(root, 0, 0)
                w.change_property(d.intern_atom('_SCISAGA_TILE_RESTORE'), d.intern_atom('CARDINAL'), 32, [int(v) & 0xffffffff for v in (-pos.x, -pos.y, g.width, g.height)])
            unmaximize()
            p = root.get_full_property(d.intern_atom('_NET_WORKAREA'), X.AnyPropertyType)
            desktop = root.get_full_property(d.intern_atom('_NET_CURRENT_DESKTOP'), X.AnyPropertyType)
            offset = int(desktop.value[0]) * 4 if desktop is not None else 0
            work = list(map(int, p.value[offset:offset + 4])) if p is not None else [0, 0, d.screen().width_in_pixels, d.screen().height_in_pixels]
            ext = w.get_full_property(d.intern_atom('_NET_FRAME_EXTENTS'), X.AnyPropertyType)
            left, right, top, bottom = map(int, ext.value) if ext is not None else (0, 0, 0, 0)
            half = work[2] // 2
            x = work[0] + (half if direction == 'right' else 0)
            width = work[2] - half if direction == 'right' else half
            resize([x + left, work[1] + top, max(1, width - left - right), max(1, work[3] - top - bottom)])
            return {'status': 'passed', 'action': direction, 'window': w.id}
        if action == 'minimize':
            event = protocol.event.ClientMessage(window=w, client_type=d.intern_atom('WM_CHANGE_STATE'), data=(32, [Xutil.IconicState, 0, 0, 0, 0]))
        else:
            event = protocol.event.ClientMessage(window=w, client_type=d.intern_atom('_NET_WM_STATE'), data=(32, [1 if action == 'maximize' else 0, a, b, 2, 0]))
        root.send_event(event, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
        d.sync()
        if action == 'restore' and cached is not None:
            unmaximize()
            resize(list(map(int, cached.value)))
            w.delete_property(d.intern_atom('_SCISAGA_TILE_RESTORE'))
            d.sync()
        return {'status': 'passed', 'action': action, 'window': w.id}
    finally:
        d.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('apply', 'restore', 'up', 'down', 'left', 'right', 'desktop', 'menu-toggle', 'menu-service'))
    parser.add_argument('--menu-source', type=Path)
    parser.add_argument('--windows-shortcuts', action='store_true')
    parser.add_argument('--double-click-time', type=int)
    parser.add_argument('--double-click-distance', type=int)
    parser.add_argument('--state', type=Path)
    parser.add_argument('--apply', action='store_true', help='Write settings; otherwise preview only')
    args = parser.parse_args(argv)
    try:
        if not os.environ.get('DISPLAY'):
            raise ValueError('Run in the current Xfce terminal with its DISPLAY/DBus environment')
        if args.action == 'menu-service':
            result = menu_service()
        elif args.action in ('up', 'down', 'left', 'right', 'desktop', 'menu-toggle'):
            result = window_action(args.action)
        else:
            if not shutil.which('xfconf-query'):
                raise RuntimeError('Install guest dependency: sudo apt-get install xfconf')
            if args.state is None:
                raise ValueError('--state is required for apply/restore')
            result = apply_settings(args) if args.action == 'apply' else restore(args)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(json.dumps({'status': 'failed', 'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
