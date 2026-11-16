#!/usr/bin/env python3
"""Install Thunar-only GTK core-pointer launchers; preview by default. Does not close live windows."""
import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

from xfce_input import query, save


WRAPPER = '/usr/local/bin/tablet-thunar-core'


def launcher_files(root, home):
    source = next((root / 'usr/share/applications' / n for n in ('thunar.desktop', 'org.xfce.Thunar.desktop') if (root / 'usr/share/applications' / n).is_file()), None)
    if source is None:
        raise ValueError('Install guest dependency: apt-get install thunar')
    target = home / '.local/share/applications' / source.name
    text = (target if target.exists() else source).read_text(encoding='utf-8')
    section = text.split('\n[', 1)[0]
    if not re.search(r'(?m)^Exec=(?:/usr/bin/)?[Tt]hunar(?:\s|$)|^Exec=' + re.escape(WRAPPER) + r'(?:\s|$)', section):
        raise ValueError('Custom Thunar launcher: review its Exec before replacing it')
    section = re.sub(r'(?m)^Exec=(?:/usr/bin/)?[Tt]hunar(?=\s|$)', 'Exec=' + WRAPPER, section)
    section = re.sub(r'(?m)^DBusActivatable=.*$', 'DBusActivatable=false', section)
    if not re.search(r'(?m)^DBusActivatable=', section):
        section += '\nDBusActivatable=false\n'
    text = section + ('\n[' + text.split('\n[', 1)[1] if '\n[' in text else '')
    helper = '[Desktop Entry]\nType=X-XFCE-Helper\nName=Thunar\nX-XFCE-Category=FileManager\nX-XFCE-Commands=' + WRAPPER + ';\nX-XFCE-CommandsWithParameter=' + WRAPPER + ' "%s";\n'
    rc = home / '.config/xfce4/helpers.rc'
    old = rc.read_text(encoding='utf-8') if rc.exists() else ''
    selected = re.search(r'(?m)^FileManager=(.*)$', old)
    if selected and selected.group(1) not in ('Thunar', 'thunar', 'custom-ThunarCore'):
        raise ValueError('Another file manager is selected; review before changing its helper')
    new = re.sub(r'(?m)^FileManager=.*$', 'FileManager=custom-ThunarCore', old) if selected else old.rstrip() + '\nFileManager=custom-ThunarCore\n'
    return {target: text, home / '.local/share/xfce4/helpers/custom-ThunarCore.desktop': helper, rc: new}


def array(prop):
    lines = subprocess.check_output(['xfconf-query', '-c', 'xfce4-session', '-p', prop], text=True,
                                    env=dict(os.environ, LC_ALL='C'), timeout=10).strip().splitlines()
    return [line for line in lines[1:] if line] if lines and lines[0].startswith('Value is an array') else lines


def set_array(prop, values):
    args = ['-c', 'xfce4-session', '-p', prop, '--force-array']
    for text in values:
        args += ['-t', 'string', '-s', text]
    query(*args)
    if array(prop) != values:
        raise RuntimeError('Session command readback differs')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def apply(args):
    home = Path.home()
    wrapper = args.wrapper or Path(__file__).resolve().parents[1] / 'assets/desktop/guest/tablet-thunar-core'
    files = launcher_files(Path('/'), home)
    files[Path(WRAPPER)] = wrapper.read_text(encoding='utf-8')
    changes = []
    for prop in query('-c', 'xfce4-session', '-l').splitlines():
        if '/Failsafe/' in prop and prop.endswith('_Command'):
            old = array(prop)
            if old and Path(old[0]).name.lower() == 'thunar':
                changes.append({'property': prop, 'before': old, 'after': [WRAPPER, *old[1:]]})
    state = {'schema': 1, 'home': str(home), 'status': 'planned', 'files': [], 'session': changes}
    for path, text in files.items():
        if path.is_symlink():
            raise ValueError('Review launcher symlink before replacing it')
        state['files'].append({'path': str(path), 'before': base64.b64encode(path.read_bytes()).decode() if path.exists() else None,
                               'mode': stat.S_IMODE(path.stat().st_mode) if path.exists() else None,
                               'after': hashlib.sha256(text.encode()).hexdigest()})
    if not args.apply:
        return state
    if args.state.exists():
        raise ValueError('State exists; preserve the previous backup')
    state['status'] = 'preparing'
    save(args.state, state)
    written, attempted = [], []
    try:
        for item, (path, text) in zip(state['files'], files.items()):
            current = base64.b64encode(path.read_bytes()).decode() if path.exists() else None
            if current != item['before']:
                raise ValueError('Launcher changed during preparation')
            path.parent.mkdir(parents=True, exist_ok=True)
            written.append(item)
            path.write_text(text, encoding='utf-8')
            path.chmod(0o755 if str(path) == WRAPPER else 0o644)
        for change in changes:
            attempted.append(change)
            set_array(change['property'], change['after'])
    except Exception:
        state['status'] = 'rolled-back'
        for change in reversed(attempted):
            current = array(change['property'])
            if current == change['after']:
                set_array(change['property'], change['before'])
            elif current != change['before']:
                state['status'] = 'partial'
        for item in reversed(written):
            path = Path(item['path'])
            if not path.is_file() or sha(path) != item['after']:
                state['status'] = 'partial';continue
            if item['before'] is None:
                path.unlink()
            else:
                path.write_bytes(base64.b64decode(item['before']));path.chmod(item['mode'])
        save(args.state, state)
        raise
    state['status'] = 'passed'
    save(args.state, state)
    return state


def restore(args):
    state = json.loads(args.state.read_text(encoding='utf-8'))
    if state.get('schema') != 1 or state.get('home') != str(Path.home()):
        raise ValueError('State belongs to another home or schema')
    if state.get('status') == 'restored':
        for item in state['files']:
            path = Path(item['path'])
            current = base64.b64encode(path.read_bytes()).decode() if path.exists() else None
            if path.is_symlink() or current != item['before']:
                raise ValueError('Launcher changed after restore; review before continuing')
        for change in state['session']:
            if array(change['property']) != change['before']:
                raise ValueError('Session command changed after restore')
        return {'status': 'restored' if args.apply else 'planned', 'live_process_restart_required': True}
    for item in state['files']:
        path = Path(item['path'])
        if path.is_symlink() or not path.is_file() or sha(path) != item['after']:
            raise ValueError('Launcher changed after apply; review before restoring')
    for change in state['session']:
        if array(change['property']) != change['after']:
            raise ValueError('Session command changed after apply; review before restoring')
    if args.apply:
        for item in state['files']:
            path = Path(item['path'])
            if item['before'] is None:
                path.unlink()
            else:
                path.write_bytes(base64.b64decode(item['before']));path.chmod(item['mode'])
        for change in state['session']:
            set_array(change['property'], change['before'])
        state['status'] = 'restored';save(args.state, state)
    return {'status': 'restored' if args.apply else 'planned', 'live_process_restart_required': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('apply', 'restore'))
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--wrapper', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        if not shutil.which('xfconf-query'):
            raise RuntimeError('Install guest dependency: apt-get install xfconf')
        result = apply(args) if args.action == 'apply' else restore(args)
        print(json.dumps({'status': result['status'], 'live_process_restart_required': True, 'state': str(args.state),
                          'files': [item['path'] for item in result.get('files', [])], 'session': result.get('session', [])}))
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(json.dumps({'status': 'failed', 'error': str(error)}));return 1


if __name__ == '__main__':
    raise SystemExit(main())
