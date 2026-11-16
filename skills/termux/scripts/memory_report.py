#!/usr/bin/env python3
"""Bounded, read-only Android/Termux PSS snapshots; never reclaim or signal processes."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shlex
import statistics
import sys
import time
from pathlib import Path


def kib_fields(text):
    return {m[1]: int(m[2]) for m in re.finditer(r'^([\w_()]+):\s+(\d+) kB$', text, re.M)}


def classify(first, executable, comm):
    if '/code/' in first or comm == 'copilot-runtime':
        return 'code'
    if Path(first).name == 'codex':
        return 'codex'
    if 'chromium' in executable:
        return 'chromium'
    if 'com.termux.x11' in first or comm == 'termux-x11':
        return 'x11'
    if comm.startswith(('xfce', 'xfwm', 'xfdesktop', 'xfsettings', 'Thunar', 'tablet-panel', 'tablet-touch-lo', 'wrapper-2.0')):
        return 'xfce'
    return 'termux_other'


def identity(proc):
    fields = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
    status = (proc / 'status').read_text()
    return dict(pid=int(proc.name), uid=proc.stat().st_uid, start_ticks=int(fields[19]),
                exe=os.readlink(proc / 'exe'), ppid=int(fields[1]), sid=int(fields[3]),
                tracer=int(re.search(r'^TracerPid:\s*(\d+)', status, re.M)[1]))


def collect_native():
    """Runs once in native Termux; command arguments and environment secrets are omitted."""
    started = time.time()
    mem_before = kib_fields(Path('/proc/meminfo').read_text())
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    manager_path = Path.home() / '.local/state/tablet-desktop/manager.json'
    manager = json.loads(manager_path.read_text()) if manager_path.exists() else {}
    registry = manager.get('processes', {})
    processes, errors = [], []
    # Exclude this sampler's entire SSH ancestry from application aggregates.
    excluded, parent = set(), os.getpid()
    while parent > 1 and parent not in excluded:
        excluded.add(parent)
        try:
            parent = identity(Path('/proc') / str(parent))['ppid']
        except OSError:
            break
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) in excluded:
            continue
        try:
            if proc.stat().st_uid != os.getuid():
                continue
            if (proc / 'stat').read_text().rsplit(')', 1)[1].split()[0] == 'Z':
                continue  # Zombies have no address space and no resident/swap footprint.
            before = identity(proc)
            args = [os.fsdecode(v) for v in (proc / 'cmdline').read_bytes().split(b'\0') if v]
            if len(args) == 1 and ' ' in args[0]:
                args = shlex.split(args[0])
            comm = (proc / 'comm').read_text().strip()
            group = classify(args[0] if args else '', before['exe'], comm)
            if 'com.termux.x11' in args:
                group = 'x11'
            memory = kib_fields((proc / 'smaps_rollup').read_text())
            if not all(k in memory for k in ('Pss', 'SwapPss')):
                raise ValueError('smaps_rollup lacks Pss/SwapPss')
            gpu = bool(re.search(r'/dev/(?:kgsl|dri/)', (proc / 'maps').read_text()))
            if identity(proc) != before:
                errors.append(dict(pid=int(proc.name), error='identity_changed'))
                continue
            record = registry.get(proc.name, {})
            registered = (record.get('start') == before['start_ticks'] and record.get('uid') == before['uid']
                          and record.get('session') == manager.get('session') and record.get('tracer') == before['tracer'])
            processes.append(dict(**before, comm=comm, group=group, memory_kib=memory,
                                  gpu_context=gpu, registered_current_session=registered,
                                  flags=[v for v in args if v.startswith(('--type=', '--use-angle=', '--use-gl='))]))
        except (OSError, ValueError, IndexError) as error:
            # /proc is live: disappearing and inaccessible processes are explicit coverage gaps.
            try:
                if (proc.stat().st_uid == os.getuid()
                        and (proc / 'stat').read_text().rsplit(')', 1)[1].split()[0] != 'Z'):
                    errors.append(dict(pid=int(proc.name), error=type(error).__name__))
            except OSError:
                pass
    by_pid = {r['pid']: r for r in processes}
    for row in processes:
        if row['group'] != 'termux_other':
            continue
        seen, parent = set(), row['ppid']
        while parent in by_pid and parent not in seen:
            seen.add(parent)
            ancestor = by_pid[parent]
            if ancestor['group'] in ('code', 'codex', 'chromium'):
                row['group'] = ancestor['group']
                break
            parent = ancestor['ppid']
    return dict(started_at=started, ended_at=time.time(), boot_id=boot,
                session=manager.get('session'), phase=manager.get('phase'),
                core=manager.get('core'), mem_before_kib=mem_before,
                mem_after_kib=kib_fields(Path('/proc/meminfo').read_text()),
                processes=processes, coverage_errors=errors)


def parse_android(text, *, total_includes_swap):
    """Android 16 Debug.getTotalPss includes swap; older/OEM formats require an explicit choice."""
    if 'DUMP TIMEOUT' in text:
        raise ValueError('Android meminfo timed out; do not compare a partial dump')
    rows = []
    blocks = re.split(r'\*\* MEMINFO in pid (\d+) \[([^\]]+)\] \*\*', text)
    for index in range(1, len(blocks), 3):
        pid, name, body = int(blocks[index]), blocks[index + 1], blocks[index + 2]
        match = re.search(r'TOTAL PSS:\s*(\d+).*?TOTAL SWAP PSS:\s*(\d+)', body)
        if not match:
            raise ValueError(f'PID {pid} lacks TOTAL PSS / TOTAL SWAP PSS')
        total, swap = map(int, match.groups())
        resident = total - swap if total_includes_swap else total
        if resident < 0:
            raise ValueError('Negative resident PSS; check Android TOTAL PSS semantics')
        mtrack = sum(int(m[1]) for m in re.finditer(r'^\s*(?:EGL|GL|Other) mtrack\s+(\d+)', body, re.M))
        graphics = re.search(r'^\s*Graphics:\s*(\d+)', body, re.M)
        rows.append(dict(pid=pid, name=name, resident_total_kib=resident, swap_pss_kib=swap,
                         logical_total_kib=resident + swap, graphics_mtrack_kib=mtrack,
                         graphics_summary_kib=int(graphics[1]) if graphics else None,
                         mapped_pss_kib=resident - mtrack))
    if not rows:
        raise ValueError('No per-process Android meminfo records')
    return rows


def parse_zram(text):
    match = re.search(r'ZRAM:\s*([\d,]+)K physical used for ([\d,]+)K in swap\s*\(([\d,]+)K total swap\)', text)
    if not match:
        raise ValueError('ZRAM physical usage unavailable; do not substitute logical SwapPss')
    physical, logical, capacity = (int(v.replace(',', '')) for v in match.groups())
    return dict(source='dumpsys_meminfo_zram_physical_used', mem_used_total_kib=physical,
                swap_used_kib=logical, swap_capacity_kib=capacity)


def parse_app_packages(text):
    result = {}
    blocks = re.split(r'^\s*\*APP\* UID (\d+) ProcessRecord\{[^\n]*? (\d+):([^/\n]+)/[^\n]*\}', text, flags=re.M)
    for index in range(1, len(blocks), 4):
        uid, pid, name, body = int(blocks[index]), int(blocks[index + 1]), blocks[index + 2], blocks[index + 3]
        packages = re.search(r'^\s*packageList=\{([^}]+)\}', body, re.M)
        if packages:
            result[pid] = dict(uid=uid, name=name, packages=[p.strip() for p in packages[1].split(',')])
    return result


def app_group(row, package_map):
    owner = package_map.get(row['pid'], {})
    packages = owner.get('packages', []) if owner.get('name') == row['name'] else []
    if len(packages) == 1:
        return 'android:' + packages[0]
    matches = [p for p in packages if row['name'] == p or row['name'].startswith((p + ':', p + '.'))]
    if matches:
        return 'android:' + max(matches, key=len)
    # Shared-UID/package attribution can be ambiguous; retain that fact instead of double counting.
    return 'android:shared:' + '|'.join(sorted(packages)) if packages else 'android:' + row['name'].split(':')[0]


def merge_sample(native, android_rows, native_details, package_map=None):
    details = {r['pid']: r for r in native_details}
    processes = []
    for proc in native['processes']:
        row = dict(proc)
        mapped, swap = (proc['memory_kib'][k] for k in ('Pss', 'SwapPss'))
        detail = details.get(proc['pid'])
        mtrack = detail['graphics_mtrack_kib'] if detail else (None if proc['gpu_context'] else 0)
        row.update(mapped_pss_kib=mapped, swap_pss_kib=swap, graphics_mtrack_kib=mtrack,
                   resident_total_kib=mapped + mtrack if mtrack is not None else None,
                   logical_total_kib=mapped + mtrack + swap if mtrack is not None else None)
        processes.append(row)
    # Java Android processes and native children can overlap on some builds: count each PID once.
    own_pids = {r['pid'] for r in processes}
    groups = {}
    for row in processes + [dict(r, group=app_group(r, package_map or {})) for r in android_rows if r['pid'] not in own_pids]:
        group = groups.setdefault(row['group'], dict(process_count=0, mapped_pss_kib=0, swap_pss_kib=0,
                                                    graphics_mtrack_kib=0, resident_total_kib=0,
                                                    logical_total_kib=0, missing_graphics_pids=[]))
        group['process_count'] += 1
        for key in ('mapped_pss_kib', 'swap_pss_kib', 'graphics_mtrack_kib', 'resident_total_kib', 'logical_total_kib'):
            if row[key] is None:
                group[key] = None
            elif group[key] is not None:
                group[key] += row[key]
        if row['graphics_mtrack_kib'] is None:
            group['missing_graphics_pids'].append(row['pid'])
    return dict(native=native, android_processes=android_rows, processes=processes, groups=groups)


def remote_native(device):
    source = base64.b64encode(Path(__file__).read_bytes()).decode()
    script = "python - <<'TERMUX_MEMORY'\nimport base64\nns={'__name__':'memory_payload'}\nexec(compile(base64.b64decode(" + repr(source) + "),'memory_report.py','exec'),ns)\nimport json\nprint(json.dumps(ns['collect_native']()))\nTERMUX_MEMORY\n"
    return json.loads(device.ssh_script(script, timeout=40))


def snapshot(args):
    from device_transport import Device, atomic_json
    device = Device.read(args.connection)
    samples = []
    for index in range(args.samples):
        if index:
            time.sleep(args.interval)
        native = remote_native(device)
        android_rows, native_details, zram, package_map = [], [], None, {}
        retries = []
        if args.android:
            for attempt in range(3):
                raw = device.shell('dumpsys', '-t', '40', 'meminfo', '--local', '-a', '-S', timeout=48)
                try:
                    android_rows = parse_android(raw, total_includes_swap=args.android_total == 'includes-swap')
                    break
                except ValueError as error:
                    if 'lacks TOTAL' not in str(error) or attempt == 2:
                        raise
                    # A cached Android process can exit between enumeration and reading.
                    retries.append(str(error))
            zram = parse_zram(raw)
            package_map = parse_app_packages(device.shell('dumpsys', 'activity', 'processes', timeout=25))
            pids = [r['pid'] for r in native['processes'] if r['gpu_context']]
            if pids:
                # Native-only PID dumps omit the usual Android process header.
                raw = device.shell_script('\n'.join(
                    f"printf '\\n** MEMINFO in pid {pid} [native:{pid}] **\\n'\ndumpsys meminfo --local {pid}"
                    for pid in pids), timeout=45)
                native_details = parse_android(raw, total_includes_swap=args.android_total == 'includes-swap')
            after = remote_native(device)
            before_ids = {r['pid']: (r['uid'], r['start_ticks'], r['exe']) for r in native['processes'] if r['gpu_context']}
            after_ids = {r['pid']: (r['uid'], r['start_ticks'], r['exe']) for r in after['processes']}
            if native['boot_id'] != after['boot_id'] or native['session'] != after['session']:
                raise ValueError('Device boot or desktop session changed during collection')
            if any(after_ids.get(pid) != ident for pid, ident in before_ids.items()):
                raise ValueError('GPU process identity changed during memtrack collection; retry snapshot')
        sample = merge_sample(native, android_rows, native_details, package_map)
        sample['zram'] = zram
        sample['android_package_map'] = package_map
        sample['collection_retries'] = retries
        samples.append(sample)
    summary = dict(mem_available_kib=statistics.median(s['native']['mem_before_kib']['MemAvailable'] for s in samples),
                   zram_mem_used_total_kib=statistics.median(s['zram']['mem_used_total_kib'] for s in samples) if args.android else None,
                   groups={})
    for key in sorted(set().union(*(s['groups'] for s in samples))):
        values = [s['groups'].get(key) for s in samples]
        summary['groups'][key] = {field: (statistics.median(v[field] for v in values)
                                         if all(v is not None and v[field] is not None for v in values) else None)
                                  for field in ('process_count', 'mapped_pss_kib', 'graphics_mtrack_kib', 'resident_total_kib', 'swap_pss_kib', 'logical_total_kib')}
    inputs = dict(connection_sha256=device.digest, workload=args.workload, samples=args.samples,
                  interval=args.interval, android=args.android, android_total=args.android_total)
    complete = (all(not g['missing_graphics_pids'] for s in samples for g in s['groups'].values())
                and all(not s['native']['coverage_errors'] for s in samples))
    result = dict(schema=1, status='passed' if complete else 'pending', input_summary=inputs,
                  input_sha256=hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest(),
                  samples=samples, summary=summary)
    atomic_json(args.state, result)
    print(json.dumps(dict(status=result['status'], samples=len(samples),
                          mem_available_kib=summary['mem_available_kib'],
                          zram_mem_used_total_kib=summary['zram_mem_used_total_kib'],
                          group_count=len(summary['groups'])), ensure_ascii=False))
    return 0 if complete else 3


def compare(before, after):
    if (not isinstance(before, dict) or not isinstance(after, dict)
            or before.get('status') != 'passed' or after.get('status') != 'passed'):
        raise ValueError('Cannot compare incomplete snapshots')
    if not all(isinstance(r.get('input_summary'), dict) for r in (before, after)):
        raise ValueError('Snapshot input summary is missing')
    for key in ('connection_sha256', 'workload', 'android', 'android_total', 'samples', 'interval'):
        if key not in before['input_summary'] or key not in after['input_summary']:
            raise ValueError(f'Snapshot input is missing: {key}')
        if before['input_summary'][key] != after['input_summary'][key]:
            raise ValueError(f'Comparison input changed: {key}')
    all_samples = before['samples'] + after['samples']
    if len({(s['native']['boot_id'], s['native']['session']) for s in all_samples}) != 1:
        raise ValueError('Comparison crossed a boot or desktop session')
    def work_roots(sample):
        return sorted((p['group'], p['pid'], p['start_ticks'], p['exe']) for p in sample['processes']
                      if p['group'] in ('code', 'chromium', 'codex') and not any(f.startswith('--type=') for f in p['flags'])
                      and p['ppid'] not in {q['pid'] for q in sample['processes'] if q['group'] == p['group']})
    roots = [work_roots(s) for s in all_samples]
    if not roots[0] or any(r != roots[0] for r in roots[1:]):
        raise ValueError('Application roots changed; establish a new matched baseline')
    result = dict(status='passed', workload=before['input_summary']['workload'],
                  mem_available_delta_kib=after['summary']['mem_available_kib'] - before['summary']['mem_available_kib'],
                  zram_physical_delta_kib=None, groups={})
    result['appeared_groups'] = sorted(after['summary']['groups'].keys() - before['summary']['groups'].keys())
    result['disappeared_groups'] = sorted(before['summary']['groups'].keys() - after['summary']['groups'].keys())
    if before['summary']['zram_mem_used_total_kib'] is not None:
        result['zram_physical_delta_kib'] = after['summary']['zram_mem_used_total_kib'] - before['summary']['zram_mem_used_total_kib']
    for key in before['summary']['groups'].keys() & after['summary']['groups'].keys():
        old, new = before['summary']['groups'][key], after['summary']['groups'][key]
        result['groups'][key] = {field: new[field] - old[field] if old[field] is not None and new[field] is not None else None for field in old}
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    collect = commands.add_parser('snapshot', help='read via LAN SSH; --android additionally uses ADB')
    collect.add_argument('--connection', type=Path, required=True)
    collect.add_argument('--state', type=Path, required=True)
    collect.add_argument('--workload', required=True, help='describe tabs, foreground application and idle interval')
    collect.add_argument('--samples', type=int, choices=range(1, 6), default=3)
    collect.add_argument('--interval', type=float, default=3)
    collect.add_argument('--android', action='store_true')
    collect.add_argument('--android-total', choices=('includes-swap', 'resident'), default='includes-swap',
                         help='Android 16 includes SwapPss in TOTAL PSS; verify other platform versions')
    diff = commands.add_parser('compare', help='offline comparison; rejects mismatched workloads or application roots')
    diff.add_argument('--before', type=Path, required=True)
    diff.add_argument('--after', type=Path, required=True)
    diff.add_argument('--state', type=Path, required=True)
    args = parser.parse_args(argv)
    sources = [args.connection] if args.command == 'snapshot' else [args.before, args.after]
    if args.state.resolve() in {p.resolve() for p in sources}:
        parser.error('--state must not overwrite an input or connection file')
    try:
        if args.command == 'snapshot':
            if not 0 <= args.interval <= 30:
                parser.error('--interval must be 0..30 seconds')
            return snapshot(args)
        from device_transport import atomic_json
        result = compare(json.loads(args.before.read_text(encoding='utf-8')), json.loads(args.after.read_text(encoding='utf-8')))
        atomic_json(args.state, result)
        print(json.dumps({k: v for k, v in result.items() if k != 'groups'}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
        from device_transport import atomic_json
        inputs = {k: v for k, v in vars(args).items() if not isinstance(v, Path)}
        inputs['source_sha256'] = {}
        for key, value in vars(args).items():
            if isinstance(value, Path) and key != 'state':
                try:
                    inputs['source_sha256'][key] = hashlib.sha256(value.read_bytes()).hexdigest()
                except OSError:
                    inputs['source_sha256'][key] = None
        result = dict(schema=1, status='failed', input_summary=inputs,
                      input_sha256=hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest(),
                      error=dict(type=type(error).__name__, message=str(error)))
        atomic_json(args.state, result)
        print(f'{type(error).__name__}: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
