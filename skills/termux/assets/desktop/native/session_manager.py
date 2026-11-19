"""Private native-Termux desktop lifecycle manager; no network listener."""
import json
import os
import signal
import socket
import subprocess
import threading
import time
import uuid
from pathlib import Path
from gpu_resource import GpuResource
from browser_resource import NativeBrowser, native_members
from office_resource import NativeOffice
from video_resource import VideoResource

from desktop_config import PREFIX, HOME, STATE, GUEST, CONTAINER, USER, DISPLAY, DISPLAY_NUMBER, CONFIG
UID = getattr(os, 'getuid', lambda: 0)()
TICKS = os.sysconf('SC_CLK_TCK') if hasattr(os, 'sysconf') else 100


def atomic_json(path, value):
    tmp = path.with_name(path.name + '.new')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    tmp.chmod(0o600)
    tmp.replace(path)


def read_process(pid):
    try:
        p = Path('/proc') / str(pid)
        if p.stat().st_uid != UID:
            return None
        stat = (p / 'stat').read_text(encoding="utf-8")
        f = stat[stat.rfind(')') + 2:].split()
        if f[0] == 'Z':
            return None
        cmd = (p / 'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace').strip()
        if not cmd:
            return None
        status = dict(line.split(':', 1) for line in (p / 'status').read_text(encoding="utf-8").splitlines() if ':' in line)
        exe = cmd.split(' ', 1)[0]
        kind = 'guest'
        if exe == '/usr/share/code/code' and '--type=zygote' in cmd:
            kind = 'code-zygote'
        elif exe == '/usr/bin/dbus-daemon':
            kind = 'dbus-daemon'
        elif exe.split('/')[-1] == 'xfce4-session':
            kind = 'xfce-session'
        elif exe == str(PREFIX / 'bin/proot'):
            kind = 'proot'
        elif cmd.startswith('termux-x11 com.termux.x11 ' + DISPLAY + ' '):
            kind = 'x11'
        return {'pid': int(pid), 'start': int(f[19]), 'cpu': int(f[11]) + int(f[12]),
                'ppid': int(f[1]), 'tracer': int(status.get('TracerPid', '0').strip()),
                'kind': kind, 'exe': exe, 'uid': UID}
    except (OSError, ValueError, IndexError):
        return None


def snapshot():
    result = {}
    for p in Path('/proc').iterdir():
        if p.name.isdigit():
            r = read_process(int(p.name))
            if r:
                result[r['pid']] = r
    return result


def same_identity(record, current):
    return bool(record and current and record['pid'] == current['pid']
                and record['start'] == current['start'] and record['exe'] == current['exe']
                and record['uid'] == current['uid'] == UID)


def may_reap(record, current, root_alive, core_alive, high_samples):
    """A high CPU count alone must never authorize terminating an application."""
    return bool(same_identity(record, current) and not root_alive and not core_alive
                and current['tracer'] == 0 and high_samples >= 2
                and record.get('kind') in ('code-zygote', 'dbus-daemon')
                and record.get('root') and record.get('session'))


def run(args, timeout=10, **kwargs):
    return subprocess.run([str(x) for x in args], stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=timeout, **kwargs)


class Manager:
    def __init__(self):
        STATE.mkdir(parents=True, exist_ok=True)
        self.path = STATE / 'manager.json'
        try:
            boot = Path('/proc/sys/kernel/random/boot_id').read_text(encoding="utf-8").strip()
        except OSError:
            boot = run(['/system/bin/getprop', 'ro.runtime.firstboot']).stdout.strip()
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
            if self.data.get('boot') != boot:
                self.data = {}
        except (OSError, ValueError):
            self.data = {}
        if not self.data:
            self.data = {'boot': boot, 'session': uuid.uuid4().hex, 'phase': 'stopped',
                         'roots': [], 'processes': {}, 'core': None, 'x11': None,
                         'desired': False, 'pulse_owned': False}
        self.main_child = None
        self.helpers = []
        self.previous = {}
        self.high = {}
        self.last_notice = {}
        self.next_sample = 0
        self.next_battery = 0
        self.battery_busy = False
        self.cleanup_at = None
        self.gpu = GpuResource(self, PREFIX, HOME, STATE, read_process, same_identity, guest=GUEST)
        self.browser = NativeBrowser(self, CONFIG, PREFIX, HOME, GUEST, STATE, read_process)
        self.office = NativeOffice(self, CONFIG, PREFIX, HOME, GUEST, read_process)
        self.video = VideoResource(self, PREFIX, read_process, same_identity)
        self.adopt_existing()
        self.sample()

    def event(self, text, **details):
        item = {'time': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'event': text, **details}
        path = STATE / 'manager-events.jsonl'
        if path.exists() and path.stat().st_size > 131072:
            path.replace(STATE / 'manager-events.previous.jsonl')
        with path.open('a') as f:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')
        path.chmod(0o600)

    def save(self):
        atomic_json(self.path, self.data)

    def root_valid(self, root, processes=None):
        return same_identity(root, (processes or {}).get(root['pid']) if processes is not None
                             else read_process(root['pid']))

    def core_alive(self):
        return same_identity(self.data.get('core'), read_process((self.data.get('core') or {}).get('pid', 0)))

    def adopt_existing(self):
        processes = snapshot()
        # Adopt the existing configured desktop sessions, not short SSH inspection shells.
        roots = {r['pid']: r for r in self.data['roots'] if self.root_valid(r, processes)}
        for path in (PREFIX / 'var/lib/proot-distro/sessions').glob('*.json'):
            try:
                entry = json.loads(path.read_text(encoding="utf-8"))
                command = ' '.join(entry.get('command', []))
                recognized = ('/usr/local/bin/tablet-desktop-session' in command or
                              any(x in command for x in ('/tmp/chromium-tablet.log', '/tmp/xfwm4-hidpi.log',
                                  '/tmp/libreoffice-hidpi.log', '/tmp/default-browser-hidpi.log',
                                  '/tmp/xfdesktop-touch.log')))
                p = processes.get(int(entry['pid']))
                if entry.get('container') == CONTAINER and recognized and p and p['kind'] == 'proot':
                    roots[p['pid']] = p
            except (OSError, ValueError, KeyError):
                continue
        cores = [p for p in processes.values() if p['kind'] == 'xfce-session' and p['tracer'] in roots]
        if not cores:
            return
        core = cores[0]
        if not same_identity(self.data.get('core'), core):
            if self.data['phase'] not in ('starting', 'closing', 'stopping'):
                self.data['session'] = uuid.uuid4().hex
            self.data['core'] = core
            self.data['phase'] = 'running'
            self.data['desired'] = True
        self.data['roots'] = list(roots.values())
        for p in processes.values():
            if p['kind'] == 'x11':
                self.data['x11'] = p
        self.save()

    def register(self, processes):
        roots = {r['pid']: r for r in self.data['roots'] if self.root_valid(r, processes)}
        native = native_members(roots, processes)
        for p in processes.values():
            root = p['tracer'] if p['tracer'] in roots else native.get(p['pid'])
            if root is not None:
                r = dict(p, root=root, session=self.data['session'])
                self.data['processes'][str(p['pid'])] = r

    def sample(self):
        now = time.monotonic()
        processes = snapshot()
        self.register(processes)
        core_alive = self.core_alive()
        roots = {r['pid']: r for r in self.data['roots']}
        for key, r in list(self.data['processes'].items()):
            p = processes.get(int(key))
            if not same_identity(r, p):
                self.data['processes'].pop(key, None)
                self.previous.pop(key, None)
                self.high.pop(key, None)
                continue
            old = self.previous.get(key)
            self.previous[key] = (now, p['cpu'])
            if not old or now - old[0] < 20:
                continue
            cpu = max(0, (p['cpu'] - old[1]) / TICKS / (now - old[0]) * 100)
            self.high[key] = self.high.get(key, 0) + 1 if cpu >= 80 else 0
            root = roots.get(r['root'])
            alive = bool(root and self.root_valid(root, processes))
            if key not in self.data.get('pending_reap', {}) and may_reap(r, p, alive, core_alive, self.high[key]):
                # Recheck creation time immediately before signalling; never target a recycled PID.
                if same_identity(r, read_process(p['pid'])):
                    os.kill(p['pid'], signal.SIGTERM)
                    self.event('orphan-helper-term', pid=p['pid'], kind=r['kind'], cpu=round(cpu, 1))
                    self.data.setdefault('pending_reap', {})[key] = dict(r, deadline=time.time() + 10)
            elif self.high[key] >= 2 and now - self.last_notice.get(key, -3600) >= 1800:
                self.event('sustained-cpu-observed', pid=p['pid'], kind=r['kind'], cpu=round(cpu, 1),
                           active_session=core_alive)
                self.last_notice[key] = now
        for key, r in list(self.data.get('pending_reap', {}).items()):
            if time.time() >= r['deadline']:
                p = read_process(r['pid'])
                root = roots.get(r['root'])
                if may_reap(r, p, bool(root and self.root_valid(root)), self.core_alive(), 2):
                    os.kill(r['pid'], signal.SIGKILL)
                    self.event('orphan-helper-kill', pid=r['pid'], kind=r['kind'])
                self.data['pending_reap'].pop(key, None)
        self.data['last_check'] = time.time()
        self.next_sample = now + (10 if self.data.get('pending_reap') else 60)
        self.save()

    def battery(self):
        if self.battery_busy:
            return
        self.battery_busy = True
        self.next_battery = time.monotonic() + 60
        def worker():
            try:
                p = run([PREFIX / 'bin/termux-battery-status'], timeout=6)
                d = json.loads(p.stdout)
                if p.returncode or not isinstance(d.get('percentage'), (int, float)):
                    raise ValueError('Battery query unavailable')
                # Retain only fields needed by the panel.
                value = {k: d.get(k) for k in ('percentage', 'status', 'plugged', 'temperature')}
                atomic_json(STATE / 'battery.json', dict(value, updated=time.time()))
            except (OSError, ValueError, subprocess.SubprocessError):
                pass  # Existing data ages visibly; a failure never blocks touch or desktop control.
            finally:
                self.battery_busy = False
        threading.Thread(target=worker, daemon=True).start()

    def reap_children(self):
        self.helpers = [p for p in self.helpers if p.poll() is None]
        if self.main_child:
            self.main_child.poll()

    def tick(self):
        self.reap_children()
        now = time.monotonic()
        core = self.core_alive()
        if self.data['phase'] in ('closing', 'stopping') and not core:
            self.cleanup(force=False)
        elif self.data['phase'] == 'starting':
            processes = snapshot()
            roots = {r['pid'] for r in self.data['roots'] if self.root_valid(r, processes)}
            for p in processes.values():
                if p['kind'] == 'xfce-session' and p['tracer'] in roots:
                    self.data['core'] = p
                    self.data['phase'] = 'running'
                    self.register(processes)
                    self.save()
                    self.event('desktop-running', core=p['pid'])
                    break
            if now > self.data.get('start_deadline', now + 1) and self.data['phase'] == 'starting':
                self.data['phase'] = 'degraded'
                self.event('desktop-start-timeout')
                self.save()
        elif self.data['phase'] == 'running' and not core:
            self.data['phase'] = 'degraded'
            self.event('desktop-session-ended-unexpectedly')
            self.save()
        if now >= self.next_sample:
            self.sample()
        if self.data['phase'] in ('starting', 'running', 'closing') and now >= self.next_battery:
            self.battery()

    def delay(self):
        if self.data['phase'] in ('starting', 'closing', 'stopping'):
            return 1
        return max(.1, min(60, self.next_sample - time.monotonic()))

    def status(self):
        return {'ok': True, 'phase': self.data['phase'], 'session': self.data['session'],
                'core_alive': self.core_alive(), 'registered_processes': len(self.data['processes']),
                'last_check': self.data.get('last_check'), 'guard_interval_seconds': 60,
                'video_decoder_alive': self.video.alive(), **self.gpu.status()}

    def x11_ready(self):
        try:
            with socket.socket(socket.AF_UNIX) as s:
                s.settimeout(.5)
                s.connect(str(PREFIX / ('tmp/.X11-unix/X' + DISPLAY_NUMBER)))
            return True
        except OSError:
            return False

    def spawn(self, args, log_name):
        path = STATE / log_name
        if path.exists() and path.stat().st_size > 2097152:
            path.replace(path.with_name(path.name + '.previous'))
        with path.open('ab', buffering=0) as out:
            return subprocess.Popen([str(x) for x in args], stdin=subprocess.DEVNULL, stdout=out,
                                    stderr=subprocess.STDOUT, start_new_session=True, close_fds=True)

    def start(self):
        if self.core_alive() or self.data['phase'] == 'starting':
            try:
                self.gpu.ensure()
            except (OSError, RuntimeError) as error:
                return {'ok': False, 'error': str(error)}
            return self.status()
        # A partial desktop may still hold documents. Do not replace it silently.
        if any(same_identity(r, read_process(r['pid'])) for r in self.data['processes'].values()):
            return {'ok': False, 'error': '\u53d1\u73b0\u5c1a\u672a\u7ed3\u675f\u7684\u4f1a\u8bdd\uff0c\u8bf7\u5728\u684c\u9762\u7ba1\u7406\u4e2d\u67e5\u770b\u3002'}
        self.data.update(session=uuid.uuid4().hex, phase='starting', roots=[], processes={}, core=None,
                         desired=True, start_deadline=time.monotonic() + 40, pending_reap={})
        self.previous.clear()
        self.high.clear()
        self.last_notice.clear()
        # Existing SSH wake-lock ownership is retained; the desktop does not release it.
        try:
            self.gpu.ensure()
            p = run([PREFIX / 'bin/pulseaudio', '--check'], timeout=3)
            if p.returncode:
                run([PREFIX / 'bin/pulseaudio', '--start', '--exit-idle-time=-1'])
                self.data['pulse_owned'] = True
            modules = run([PREFIX / 'bin/pactl', 'list', 'short', 'modules']).stdout
            if 'module-native-protocol-tcp' not in modules:
                run([PREFIX / 'bin/pactl', 'load-module', 'module-native-protocol-tcp',
                     'listen=127.0.0.1', 'port=4713', 'auth-cookie=' + str(HOME / '.config/pulse/cookie')])
            if not self.x11_ready():
                command = [PREFIX / 'bin/termux-x11', DISPLAY, '-nolisten', 'tcp']
                if not CONFIG.get('x11_mitshm', True):
                    command += ['-extension', 'MIT-SHM']
                if CONFIG.get('x11_glamor', False):
                    command += ['-glamor']
                p = self.spawn(command, 'x11.log')
                self.helpers.append(p)
                for _ in range(30):
                    if self.x11_ready():
                        break
                    time.sleep(.2)
            if not self.x11_ready():
                raise RuntimeError('X11 display did not become ready')
            self.data['x11'] = next((p for p in snapshot().values() if p['kind'] == 'x11'), None)
            p = self.spawn([PREFIX / 'bin/proot-distro', 'login', CONTAINER, '--user', USER,
                            '--shared-tmp', '--', '/usr/local/bin/tablet-desktop-session'], 'session.log')
            self.main_child = p
            for _ in range(20):
                root = read_process(p.pid)
                if root and root['kind'] == 'proot':
                    self.data['roots'] = [root]
                    break
                time.sleep(.1)
            self.next_sample = 0
            self.save()
            self.event('desktop-start-requested', pid=p.pid)
        except Exception as e:
            self.data['phase'] = 'degraded'
            self.save()
            return {'ok': False, 'error': str(e)}
        return self.status()

    def launch_stop(self):
        if not self.core_alive():
            return {'ok': False, 'error': '\u684c\u9762\u4f1a\u8bdd\u672a\u8fd0\u884c\uff0c\u53ef\u5728\u7ba1\u7406\u5165\u53e3\u67e5\u770b\u72b6\u6001\u3002'}
        p = self.spawn([PREFIX / 'bin/proot-distro', 'login', CONTAINER, '--user', USER,
                        '--shared-tmp', '--', '/bin/bash', '-c',
                        '. ' + __import__('shlex').quote(str(STATE / 'session.env')) + '; '
                        'exec /usr/local/bin/tablet-desktop-end'], 'end-desktop.log')
        self.helpers.append(p)
        return self.status()

    def cleanup(self, force):
        if not force and self.core_alive():
            raise RuntimeError('Desktop is still running; normal cleanup is deferred')
        self.data['phase'] = 'stopping'
        self.data['desired'] = False
        processes = snapshot()
        self.register(processes)
        records = list(self.data['processes'].values())
        roots = list(self.data['roots'])
        # Guest processes receive TERM while their PRoot tracer is still alive.
        for r in records:
            if same_identity(r, read_process(r['pid'])):
                try:
                    os.kill(r['pid'], signal.SIGTERM)
                except ProcessLookupError:
                    pass
        time.sleep(1)
        for r in records:
            if same_identity(r, read_process(r['pid'])):
                try:
                    os.kill(r['pid'], signal.SIGKILL)
                except ProcessLookupError:
                    pass
        for r in roots:
            if same_identity(r, read_process(r['pid'])):
                try:
                    os.kill(r['pid'], signal.SIGTERM)
                except ProcessLookupError:
                    pass
        time.sleep(.3)
        for r in roots:
            if same_identity(r, read_process(r['pid'])):
                try:
                    os.kill(r['pid'], signal.SIGKILL)
                except ProcessLookupError:
                    pass
        x11 = self.data.get('x11')
        if x11 and same_identity(x11, read_process(x11['pid'])):
            try:
                os.kill(x11['pid'], signal.SIGTERM)
            except ProcessLookupError:
                pass
        if not force:
            try:
                run([PREFIX / 'bin/am', 'broadcast', '-a', 'com.termux.x11.ACTION_STOP',
                     '-p', 'com.termux.x11'], timeout=4)
            except (OSError, subprocess.SubprocessError):
                pass
        self.gpu.stop()
        self.video.stop()
        if self.data.get('pulse_owned'):
            # Do not stop audio if another native application still uses it.
            clients = run([PREFIX / 'bin/pactl', 'list', 'short', 'clients']).stdout.splitlines()
            if len(clients) <= 1:
                run([PREFIX / 'bin/pulseaudio', '--kill'])
        self.data.update(phase='stopped', core=None, roots=[], processes={}, x11=None, pulse_owned=False, pending_reap={})
        self.previous.clear()
        self.high.clear()
        self.last_notice.clear()
        self.save()
        self.event('desktop-stopped', forced=force)
        return self.status()

    def handle(self, action, request):
        if action == 'browser.open':
            return self.browser.open(request)
        if action == 'office.open':
            return self.office.open(request)
        if action == 'video.ensure':
            if CONFIG.get('media_backend') != 'termux-va' or request.get('session') != self.data['session'] or not self.core_alive() or self.data['phase'] != 'running':
                raise RuntimeError('Open hardware video from the current running desktop session')
            self.video.ensure()
            return self.status()
        if action == 'desktop.status':
            return self.status()
        if action == 'desktop.start':
            return self.start()
        if action == 'desktop.launch-stop':
            return self.launch_stop()
        if action == 'desktop.ready':
            self.adopt_existing()
            self.sample()
            self.battery()
            return self.status()
        if action == 'desktop.events':
            p = STATE / 'manager-events.jsonl'
            return {'ok': True, 'events': p.read_text(encoding="utf-8").splitlines()[-20:] if p.exists() else []}
        if action not in ('desktop.begin-stop', 'desktop.cancel-stop', 'desktop.logout-ready', 'desktop.force-stop'):
            return {'ok': False, 'error': 'Unsupported action'}
        if request.get('session') != self.data['session']:
            return {'ok': False, 'error': 'Desktop session changed; reopen the control'}
        if action == 'desktop.begin-stop':
            if self.data['phase'] == 'closing':
                return {'ok': False, 'error': '\u7ed3\u675f\u6d41\u7a0b\u5df2\u5728\u8fdb\u884c\u3002'}
            self.data['phase'] = 'closing'
            self.sample()
            self.event('normal-stop-begun')
        elif action == 'desktop.cancel-stop':
            self.data['phase'] = 'running' if self.core_alive() else 'degraded'
            self.event('normal-stop-cancelled')
        elif action == 'desktop.logout-ready':
            self.data['phase'] = 'stopping'
            self.event('applications-closed-awaiting-logout')
        else:
            return self.cleanup(force=True)
        self.save()
        return self.status()
