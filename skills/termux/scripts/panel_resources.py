#!/usr/bin/env python3
"""A small Xfce genmon widget: sampled own-UID CPU and real system MemAvailable."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from html import escape
from pathlib import Path


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        stream.write((json.dumps(data, ensure_ascii=False) + '\n').encode('utf-8'))
        temporary = Path(stream.name)
    temporary.chmod(0o600)
    os.replace(temporary, path)


def memory_values(text):
    values = {k: int(v) for k, v in re.findall(r'^(MemTotal|MemAvailable):\s+(\d+)\s+kB$', text, re.M)}
    total, available = values['MemTotal'], values['MemAvailable']
    if total <= 0 or not 0 <= available <= total:
        raise ValueError('Invalid system memory counters')
    return {'total_kib': total, 'available_kib': available, 'used_kib': total - available,
            'percent': (total - available) * 100 / total}


def uid_counters(proc=Path('/proc')):
    # /proc/self ownership is the real Android UID even when PRoot translates getuid().
    uid = (proc / 'self').stat().st_uid
    values = {}
    for item in proc.iterdir():
        if not item.name.isdigit():
            continue
        try:
            if item.stat().st_uid != uid:
                continue
            fields = (item / 'stat').read_text().rsplit(')', 1)[1].split()
            values[item.name + ':' + fields[19]] = int(fields[11]) + int(fields[12])
        except (OSError, ValueError, IndexError):
            continue
    return uid, values


def cpu_percent(previous, current, elapsed, ticks, cores):
    if not previous or elapsed <= 0 or elapsed > 30 or ticks <= 0 or cores <= 0:
        return None
    shared = previous.keys() & current.keys()
    if not shared:
        return None
    delta = sum(max(0, current[key] - previous[key]) for key in shared)
    return min(100.0, delta * 100 / (elapsed * ticks * cores))


def sample(cache):
    memory = memory_values(Path('/proc/meminfo').read_text())
    uid, counters = uid_counters()
    now = time.monotonic()
    try:
        boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    except OSError:
        boot = None
    cores = os.cpu_count() or 1
    percent = None
    try:
        previous = json.loads(cache.read_text())
        if previous['uid'] == uid and previous['boot'] == boot and isinstance(previous.get('counters'), dict):
            percent = cpu_percent(previous['counters'], counters, now - previous['time'], os.sysconf('SC_CLK_TCK'), cores)
    except (OSError, ValueError, KeyError, TypeError):
        pass
    save(cache, {'schema': 1, 'uid': uid, 'boot': boot, 'time': now, 'counters': counters})
    return dict(memory, cpu_percent=percent, cores=cores, sampled_processes=len(counters))


def render(data):
    cpu = '—' if data['cpu_percent'] is None else str(round(data['cpu_percent'])) + '%'
    label = '桌面CPU ' + cpu + '\n内存 ' + str(round(data['percent'])) + '%'
    tool = ('CPU：采样时可读取的 Termux UID 进程，包含 Xfce、Code、native Chromium；不含其他 Android 应用。\n'
            + f"{data['cores']} 核平均 0–100%，每 2 秒采样；短于采样周期的进程可能漏计。\n"
            + f"内存：Android 整机 {data['used_kib'] / 1048576:.2f} / {data['total_kib'] / 1048576:.2f} GiB\n"
            + f"可用 {data['available_kib'] / 1048576:.2f} GiB；已用 = MemTotal − MemAvailable。")
    return '<txt><span size="small">' + escape(label) + '</span></txt><tool>' + escape(tool) + '</tool>'


def query(*args, check=True):
    result = subprocess.run(['xfconf-query', '-c', 'xfce4-panel', *args], capture_output=True, text=True, timeout=10)
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or 'xfconf-query failed')
    return result.stdout.strip()


def panel_ids(panel):
    return [int(v) for v in query('-p', f'/panels/panel-{panel}/plugin-ids').splitlines() if v.strip().isdigit()]


def put_ids(panel, values):
    args = ['-p', f'/panels/panel-{panel}/plugin-ids', '--force-array']
    for value in values:
        args += ['-t', 'int', '-s', str(value)]
    query(*args)
    if panel_ids(panel) != values:
        raise RuntimeError('Panel plugin order readback differs')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def genmon_running(plugin):
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            argv = (proc / 'cmdline').read_bytes().rstrip(b'\0').decode().split('\0')
            if len(argv) >= 3 and Path(argv[1]).name == 'libgenmon.so' and argv[2] == str(plugin):
                return True
        except (OSError, UnicodeError):
            continue
    return False


def reload_panel(plugin, expected):
    # Direct Xfconf array edits are persisted but do not instantiate/remove live plugins.
    result = subprocess.run(['xfce4-panel', '--restart'], capture_output=True, text=True, timeout=12)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or 'Panel refresh failed')
    until = time.monotonic() + 6
    while time.monotonic() < until:
        if genmon_running(plugin) == expected:
            return
        time.sleep(.2)
    raise RuntimeError('Genmon runtime differs from configuration; inspect the retained state')


def install(args):
    if not shutil.which('xfconf-query'):
        raise RuntimeError('Install guest dependency: apt-get install xfconf xfce4-genmon-plugin')
    properties = query('-l').splitlines()
    genmons = [p for p in properties if re.fullmatch(r'/plugins/plugin-\d+', p) and query('-p', p) == 'genmon']
    if not genmons:
        raise RuntimeError('No installed genmon instance found; install xfce4-genmon-plugin first')
    ids = panel_ids(args.panel)
    if not ids:
        raise ValueError('Review the selected panel plugin array')
    home = Path.home()
    used = {int(m.group(1)) for p in properties if (m := re.match(r'/plugins/plugin-(\d+)', p))}
    used |= {int(m.group(1)) for p in (home / '.config/xfce4/panel').glob('genmon-*.rc') if (m := re.fullmatch(r'genmon-(\d+)\.rc', p.name))}
    plugin = next(n for n in range(100, 10000) if n not in used)
    after = ids.copy()
    after.insert(after.index(23) if 23 in after else len(after), plugin)
    helper = home / '.local/bin/tablet-resource-widget'
    if helper.exists() or helper.is_symlink():
        raise ValueError('Resource helper already exists; restore its reviewed state first')
    rc = home / f'.config/xfce4/panel/genmon-{plugin}.rc'
    payload = Path(__file__).read_bytes()
    contents = ('Command=' + shlex.quote(str(helper)) + '\nUseLabel=0\nUpdatePeriod=2000\n').encode()
    state = {'schema': 1, 'status': 'planned', 'home': str(home), 'panel': args.panel, 'plugin': plugin,
             'before_ids': ids, 'after_ids': after, 'helper_sha256': hashlib.sha256(payload).hexdigest(),
             'rc_sha256': hashlib.sha256(contents).hexdigest()}
    if not args.apply:
        return state
    if args.state.exists():
        raise ValueError('State already exists; do not overwrite a previous installation')
    state['status'] = 'preparing'
    save(args.state, state)
    helper.parent.mkdir(parents=True, exist_ok=True)
    helper.write_bytes(payload)
    helper.chmod(0o755)
    rc.parent.mkdir(parents=True, exist_ok=True)
    rc.write_bytes(contents)
    query('-p', f'/plugins/plugin-{plugin}', '-n', '-t', 'string', '-s', 'genmon')
    if panel_ids(args.panel) != ids:
        raise ValueError('Panel changed during preparation; backup retained')
    put_ids(args.panel, after)
    reload_panel(plugin, True)
    state['rc_sha256'] = sha(rc)
    state['status'] = 'passed'
    save(args.state, state)
    return state


def restore(args):
    state = json.loads(args.state.read_text())
    if state.get('schema') != 1 or state['home'] != str(Path.home()):
        raise ValueError('State belongs to another home or schema')
    plugin, panel = state['plugin'], state['panel']
    helper = Path.home() / '.local/bin/tablet-resource-widget'
    rc = Path.home() / f'.config/xfce4/panel/genmon-{plugin}.rc'
    for path, expected in [(helper, state['helper_sha256']), (rc, state['rc_sha256'])]:
        if path.is_symlink() or (path.exists() and sha(path) != expected):
            raise ValueError('Widget file changed after install; review before restoring')
    current = panel_ids(panel)
    if plugin in current and query('-p', f'/plugins/plugin-{plugin}') != 'genmon':
        raise ValueError('Panel plugin identity changed after install')
    if not args.apply:
        return {'status': 'planned', 'remove_plugin': plugin, 'preserve_other_plugins': True}
    if plugin in current:
        put_ids(panel, [n for n in current if n != plugin])
    if plugin in current or genmon_running(plugin):
        reload_panel(plugin, False)
        query('-p', f'/plugins/plugin-{plugin}', '-r', '-R')
    helper.unlink(missing_ok=True)
    rc.unlink(missing_ok=True)
    state['status'] = 'restored'
    save(args.state, state)
    return {'status': 'restored', 'plugin': plugin}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('sample', 'install', 'restore'), nargs='?', default='sample')
    parser.add_argument('--panel', type=int, default=1)
    parser.add_argument('--state', type=Path)
    parser.add_argument('--cache', type=Path, default=Path.home() / '.cache/tablet-desktop/resource-widget.json')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        if args.action == 'sample':
            print(render(sample(args.cache)))
        else:
            if args.state is None:
                raise ValueError('--state is required for install/restore')
            print(json.dumps(install(args) if args.action == 'install' else restore(args), ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        if args.action == 'sample':
            print('<txt>桌面CPU —\n内存 —</txt><tool>' + escape(str(error)) + '</tool>')
        else:
            print(json.dumps({'status': 'failed', 'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
