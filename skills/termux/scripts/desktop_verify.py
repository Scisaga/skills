#!/usr/bin/env python3
"""Resumable boot evidence, effective-policy gates, real screen-off and GPU reports."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import time
from pathlib import Path

from device_transport import Device, atomic_json

PROBE = r'''set -eu
python - <<'PY'
import hashlib,json,os,subprocess,time
from pathlib import Path
home=Path.home(); prefix=Path(os.environ['PREFIX'])
desktop=json.loads(subprocess.run([str(prefix/'bin/desktop'),'status','--json'],capture_output=True,text=True,check=True,timeout=12).stdout)
state=home/'.local/state/tablet-desktop'; battery={}
try: battery=json.loads((state/'battery.json').read_text())
except (OSError,ValueError): pass
helper={}
try: helper=json.loads((state/'boot-services.json').read_text())
except (OSError,ValueError): pass
config=home/'.config/tablet-desktop/config.json'
print(json.dumps({'uid':os.getuid(),'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
 'desktop':desktop,'boot_helper':helper,'profile_sha256':hashlib.sha256(config.read_bytes()).hexdigest(),
 'battery_age_seconds':time.time()-battery.get('updated',0),'battery_status':battery.get('status')}))
PY
'''


def integer(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def policy_values(stored, activity, monitor_global, monitor_property, sync, min_cap=None, monitor='any'):
    match = re.search(r'\bmax_phantom_processes=(\d+)', activity)
    effective = int(match.group(1)) if match else None
    saved = integer(stored)
    errors = []
    if effective is None:
        errors.append('effective phantom-process cap unavailable')
    if saved is not None and effective is not None and saved != effective:
        errors.append('stored cap differs from the live ActivityManager cap')
    if min_cap is not None and (effective is None or effective < min_cap):
        errors.append(f'effective cap is below required {min_cap}')
    flags = [x.strip().lower() for x in (monitor_global, monitor_property) if x.strip().lower() in ('true', 'false', '1', '0')]
    declarations = {x in ('true', '1') for x in flags}
    state = 'unknown' if not declarations else 'conflict' if len(declarations) > 1 else ('enabled' if True in declarations else 'disabled')
    if monitor != 'any' and state != monitor:
        errors.append('monitoring state does not match the requested state')
    return {'status': 'failed' if errors else 'passed', 'stored_cap': saved, 'effective_cap': effective,
            'monitor': state, 'monitor_global': monitor_global, 'monitor_property': monitor_property,
            'config_sync_mode': sync, 'errors': errors}


def check_policy(device, min_cap=None, monitor='any'):
    return policy_values(device.shell('device_config', 'get', 'activity_manager', 'max_phantom_processes'),
                         device.shell('dumpsys', 'activity', 'settings'),
                         device.shell('settings', 'get', 'global', 'settings_enable_monitor_phantom_procs'),
                         device.shell('getprop', 'persist.sys.fflag.override.settings_enable_monitor_phantom_procs'),
                         device.shell('device_config', 'get_sync_disabled_for_tests'), min_cap, monitor)


def native_probe(device):
    value = json.loads(device.ssh_script(PROBE, timeout=30))
    if not value.get('desktop', {}).get('ok'):
        raise ValueError('Desktop controller did not return a valid status')
    return value


def boot_result(before, current_boot, credential, probe, no_manual_start):
    if not before or not current_boot or current_boot == before:
        return {'status': 'failed', 'error': 'No new kernel boot; do not count manual service restarts as reboot proof'}
    if credential != 'true':
        return {'status': 'pending', 'reason': 'awaiting first local PIN/pattern unlock', 'boot_id': current_boot}
    if not no_manual_start:
        return {'status': 'failed', 'error': 'Boot check needs confirmation that no relevant app was manually opened'}
    if probe['boot_id'] != current_boot:
        return {'status': 'failed', 'error': 'ADB and native boot identities disagree'}
    if probe['desktop']['phase'] != 'stopped' or probe['desktop'].get('registered_processes') != 0:
        return {'status': 'failed', 'error': 'Expected idle controller before the first graphical desktop start'}
    helper = probe.get('boot_helper', {})
    return {'status': 'passed', 'boot_id': current_boot, 'automatic_fresh_lan_ssh': True,
            'idle_controller': True, 'this_boot_helper_record': helper.get('boot_id') == current_boot}


def power_state(device, uid):
    text = device.shell('dumpsys', 'power')
    match = re.search(r'\bmWakefulness=(\w+)', text)
    locks = [x.strip() for x in text.splitlines() if 'PARTIAL_WAKE_LOCK' in x and
             'termux:service-wakelock' in x and re.search(r'\buid=' + str(uid) + r'\b', x)]
    return {'wakefulness': match.group(1) if match else 'unknown',
            'partial_wake_lock_active': bool(locks) and not any('DISABLED' in x for x in locks)}


def freeze_events(device, uid):
    try:
        text = device.shell('dumpsys', 'greezer')
    except RuntimeError:
        return []
    return [x.strip() for x in text.splitlines() if re.search(r'\bFZ\s+uid\s*=\s*' + str(uid) + r'\b', x)]


def validate_sleep_sample(baseline, probe, power, freezes, before_freezes, policy, require_battery):
    errors = []
    if probe['boot_id'] != baseline['boot_id'] or probe['profile_sha256'] != baseline['profile_sha256']:
        errors.append('boot or profile changed during the test')
    state = probe['desktop']
    if state.get('session') != baseline['desktop'].get('session') or state.get('phase') != 'running' or not state.get('core_alive'):
        errors.append('desktop stopped or session changed')
    if power['wakefulness'] != 'Asleep' or not power['partial_wake_lock_active']:
        errors.append('screen is not physically asleep or the Termux wake lock is inactive')
    if set(freezes) - set(before_freezes):
        errors.append('new vendor freeze event')
    if policy['status'] != 'passed':
        errors.extend(policy['errors'])
    if require_battery and not 0 <= probe.get('battery_age_seconds', float('inf')) < 180:
        errors.append('battery cache unavailable or stale')
    return errors


def gpu_summary(record, min_fps=None):
    samples = record.get('samples', [])
    if len(samples) < 3:
        raise ValueError('GPU acceptance needs at least three valid measured samples')
    workloads = set()
    rates = []
    for sample in samples:
        renderer = sample.get('renderer', '')
        if not isinstance(renderer, str):
            raise ValueError('Missing renderer name')
        renderer = renderer.lower()
        if not renderer or any(x in renderer for x in ('llvmpipe', 'softpipe', 'swiftshader', 'software rasterizer')):
            raise ValueError('Missing hardware renderer or software rendering detected')
        pixel = sample.get('pixel', [])
        if sample.get('error') != 0 or sample.get('contextLost') is not False or sample.get('visibility') != 'visible':
            raise ValueError('WebGL error, lost context or hidden page invalidates a sample')
        if len(pixel) != 4 or any(type(v) is not int for v in pixel) or pixel[3] != 255 or any(abs(v - expected) > 3 for v, expected in zip(pixel[:3], [128, 128, 217])):
            raise ValueError('Actual shader drawing/pixel readback was not verified')
        if any(not isinstance(sample.get(k), (int, float)) or not math.isfinite(sample[k]) for k in ('warmup_seconds', 'seconds', 'frames')) or sample['warmup_seconds'] < 4 or sample['seconds'] < 10 or type(sample['frames']) is not int or sample['frames'] <= 0:
            raise ValueError('Need four seconds warmup and at least ten measured seconds')
        for key in ('canvas', 'viewport'):
            if not isinstance(sample.get(key), list) or len(sample[key]) != 2 or any(type(v) is not int or v <= 0 for v in sample[key]):
                raise ValueError('Invalid canvas or viewport dimensions')
        if not isinstance(sample.get('dpr'), (int, float)) or not math.isfinite(sample['dpr']) or sample['dpr'] <= 0:
            raise ValueError('Invalid device scale factor')
        digest = sample.get('workload_sha256', '')
        if not re.fullmatch(r'[a-f0-9]{64}', digest):
            raise ValueError('Missing benchmark workload hash')
        workload = (tuple(sample['canvas']), tuple(sample['viewport']), sample['dpr'], digest)
        workloads.add(workload)
        rate = sample['frames'] / sample['seconds']
        reported = sample.get('fps', rate)
        if not isinstance(reported, (int, float)) or not math.isfinite(reported) or abs(rate - reported) > max(.1, rate * .02):
            raise ValueError('Reported frame rate disagrees with measured frames/time')
        rates.append(rate)
    if len(workloads) != 1:
        raise ValueError('Canvas, viewport, scale or workload changed between samples')
    median = statistics.median(rates)
    if min_fps is not None and median < min_fps:
        raise ValueError(f'Median animation callback rate {median:.2f} is below required {min_fps}')
    return {'median_callback_rate': median, 'samples': rates, 'workload': list(workloads.pop()),
            'measurement': 'requestAnimationFrame callbacks; not SurfaceFlinger presented frames'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['policy', 'boot-baseline', 'boot-check', 'sleep', 'gpu-report', 'window-report', 'final-check'])
    parser.add_argument('--connection', type=Path)
    parser.add_argument('--state', type=Path, required=True, help='Private checkpoint/result JSON outside the repository')
    parser.add_argument('--min-cap', type=int)
    parser.add_argument('--monitor', choices=['any', 'enabled', 'disabled'], default='any')
    parser.add_argument('--no-manual-app-start', action='store_true')
    parser.add_argument('--require-boot-helper', action='store_true')
    parser.add_argument('--boot-wait', type=int, default=60, help='Bounded wait for automatic native services after first unlock')
    parser.add_argument('--require-battery', action='store_true')
    parser.add_argument('--duration', type=int, default=360)
    parser.add_argument('--interval', type=int, default=45)
    parser.add_argument('--apply', action='store_true', help='Allow entering real screen-off for the sleep test')
    parser.add_argument('--wake-at-end', action='store_true', help='Wake to the existing secure lockscreen without unlocking')
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--min-fps', type=float)
    parser.add_argument('--min-speedup', type=float)
    args = parser.parse_args(argv)
    if args.min_cap is not None and args.min_cap < 1:
        parser.error('--min-cap must be positive')
    if not 0 <= args.boot_wait <= 180:
        parser.error('--boot-wait must be 0..180 seconds')
    for metric in (args.min_fps, args.min_speedup):
        if metric is not None and (not math.isfinite(metric) or metric <= 0):
            parser.error('GPU thresholds must be finite positive numbers')
    summary = {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items() if k != 'connection'}
    result = {'command': args.command, 'status': 'pending', 'input_summary': summary}
    device = None
    try:
        if args.command != 'gpu-report':
            if not args.connection:
                parser.error('--connection is required for live checks')
            device = Device.read(args.connection)
            summary['connection_sha256'] = device.digest
        for label, path in (('candidate', args.candidate), ('baseline', args.baseline)):
            if path:
                summary[label + '_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        result['input_sha256'] = hashlib.sha256(json.dumps(summary, sort_keys=True).encode()).hexdigest()
        if args.command == 'gpu-report':
            if not args.candidate:
                parser.error('--candidate is required')
            candidate = gpu_summary(json.loads(args.candidate.read_text(encoding='utf-8')), args.min_fps)
            result['candidate'] = candidate
            if args.baseline:
                baseline = gpu_summary(json.loads(args.baseline.read_text(encoding='utf-8')))
                if baseline['workload'] != candidate['workload']:
                    raise ValueError('Baseline and candidate workloads differ')
                ratio = candidate['median_callback_rate'] / baseline['median_callback_rate']
                if args.min_speedup is not None and ratio < args.min_speedup:
                    raise ValueError(f'Speedup {ratio:.2f} is below required {args.min_speedup}')
                result.update(baseline=baseline, median_speedup=ratio)
            elif args.min_speedup is not None:
                raise ValueError('--min-speedup requires --baseline')
        elif args.command == 'window-report':
            from window_probe import probe_device
            result.update(probe_device(device))
        elif args.command == 'policy':
            result.update(check_policy(device, args.min_cap, args.monitor))
        elif args.command == 'boot-baseline':
            result['boot_id_before'] = device.shell('cat', '/proc/sys/kernel/random/boot_id')
            result['policy'] = check_policy(device, args.min_cap, args.monitor)
            if result['policy']['status'] != 'passed':
                raise ValueError('Pre-reboot policy check failed; correct it before asking for another unlock')
            result['connection_sha256'] = device.digest
        elif args.command == 'boot-check':
            previous = json.loads(args.state.read_text(encoding='utf-8'))
            if previous.get('connection_sha256') != device.digest:
                raise ValueError('Connection differs from the saved boot baseline')
            before = previous.get('boot_id_before')
            current = device.shell('cat', '/proc/sys/kernel/random/boot_id')
            credential = device.shell('getprop', 'sys.user.0.ce_available')
            result.update(boot_id_before=before, connection_sha256=device.digest)
            probe = {}
            if current and current != before and credential == 'true' and args.no_manual_app_start:
                deadline = time.monotonic() + args.boot_wait
                while True:
                    try:
                        probe = native_probe(device)
                        break
                    except (RuntimeError, ValueError) as error:
                        if time.monotonic() >= deadline:
                            raise RuntimeError('Automatic services not ready within the wait window; retry boot-check after diagnosis without opening apps or rebooting again') from error
                        print(json.dumps({'status': 'pending', 'reason': 'waiting for automatic native service readiness'}), flush=True)
                        time.sleep(min(2, max(0, deadline - time.monotonic())))
            result.update(boot_result(before, current, credential, probe, args.no_manual_app_start))
            if result['status'] == 'passed':
                result['policy'] = check_policy(device, args.min_cap, args.monitor)
                if result['policy']['status'] != 'passed':
                    raise ValueError('Post-reboot effective policy failed; do not start the desktop')
                if args.require_boot_helper and not result['this_boot_helper_record']:
                    raise ValueError('Boot helper completion record does not match this boot')
        elif args.command == 'sleep':
            if not 360 <= args.duration <= 43200 or not 1 <= args.interval <= 60:
                raise ValueError('Sleep acceptance duration must be 360..43200 seconds; sample interval 1..60')
            if not args.apply:
                result.update(status='skipped', reason='Preview only: --apply enters physical screen-off; battery endurance is a separate test')
            else:
                baseline = native_probe(device)
                if baseline['desktop'].get('phase') != 'running' or not baseline['desktop'].get('core_alive'):
                    raise ValueError('Start the desktop normally before the screen-off test')
                uid = baseline['uid']; before_freezes = freeze_events(device, uid)
                result.update(baseline=baseline, samples=[], power_condition='Read battery_status; charging does not establish battery endurance')
                device.shell('input', 'keyevent', '223')
                started = time.monotonic()
                targets = list(range(0, args.duration + 1, args.interval))
                if targets[-1] != args.duration:
                    targets.append(args.duration)
                try:
                    time.sleep(1)
                    for target in targets:
                        delay = target - (time.monotonic() - started)
                        if delay > 0:
                            time.sleep(delay)
                        # First open a fresh host-to-device SSH connection; no outbound priming probe.
                        probe = native_probe(device)
                        power = power_state(device, uid)
                        freezes = freeze_events(device, uid)
                        policy = check_policy(device, args.min_cap, args.monitor)
                        errors = validate_sleep_sample(baseline, probe, power, freezes, before_freezes, policy, args.require_battery)
                        sample = {'elapsed_seconds': round(time.monotonic() - started, 2), 'probe': probe,
                                  'power': power, 'new_freezes': len(set(freezes) - set(before_freezes)), 'policy': policy, 'errors': errors}
                        result['samples'].append(sample)
                        atomic_json(args.state, result)
                        print(json.dumps({'elapsed_seconds': sample['elapsed_seconds'], 'status': 'failed' if errors else 'passed'}), flush=True)
                        if errors:
                            raise ValueError('; '.join(errors))
                finally:
                    if args.wake_at_end:
                        device.shell('input', 'keyevent', '224')
        else:
            # Never issue an ADB command here: that would restart a stopped adb server.
            result['native'] = native_probe(device)
            if result['native']['desktop'].get('phase') != 'running' or not result['native']['desktop'].get('core_alive'):
                raise ValueError('Final independent LAN connection did not find a live desktop')
            result['adb_free_check'] = 'fresh SSH only; operator must stop/disconnect ADB before invoking this command'
        if result['status'] == 'pending' and args.command != 'boot-check':
            result['status'] = 'passed'
        atomic_json(args.state, result)
        printable = {k: v for k, v in result.items() if k not in ('samples', 'baseline')} if args.command == 'sleep' else result
        print(json.dumps(printable, ensure_ascii=False))
        return 0 if result['status'] == 'passed' else (3 if result['status'] == 'pending' else 4 if result['status'] == 'skipped' else 1)
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
        result.update(status='failed', error=str(error))
        atomic_json(args.state, result)
        print(json.dumps(result, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
