"""Native desktop Chromium: fixed launcher, validated targets and owned process roots."""
import time
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit


def normalize_targets(values, prefix, home, guest):
    if not isinstance(values, list) or len(values) > 8:
        raise ValueError('Browser targets must be a list of at most eight URLs or files')
    if any(not isinstance(v, str) or not v or any(ord(c) < 32 for c in v) for v in values):
        raise ValueError('Invalid browser target')
    if sum(len(v) for v in values) > 3000:
        raise ValueError('Browser targets exceed the local request size')
    result = []
    for value in values:
        parsed = urlsplit(value)
        if parsed.scheme in ('http', 'https'):
            if not parsed.netloc:
                raise ValueError('Web URL is missing its host')
            result.append(value)
            continue
        if parsed.scheme in ('chrome', 'about'):
            result.append(value)
            continue
        if parsed.scheme == 'file':
            if parsed.netloc not in ('', 'localhost'):
                raise ValueError('Remote file URLs are unsupported')
            path = PurePosixPath(unquote(parsed.path))
        elif not parsed.scheme and value.startswith('/'):
            path = PurePosixPath(value)
        else:
            raise ValueError('Use an http, https, file, chrome or about URL, or an absolute file path')
        if not path.is_absolute():
            raise ValueError('File path must be absolute')
        if path.is_relative_to(prefix) or path.is_relative_to(home) or str(path).startswith('/storage/'):
            native = Path(str(path))
        elif str(path).startswith('/tmp/'):
            native = prefix / 'tmp' / path.relative_to('/tmp')
        else:
            native = guest / str(path).lstrip('/')
        target = native.resolve().as_uri()
        if parsed.scheme == 'file':
            target += ('?' + parsed.query) if parsed.query else ''
            target += ('#' + parsed.fragment) if parsed.fragment else ''
        result.append(target)
    return result


def native_members(roots, processes):
    """Follow only live, recorded native application roots."""
    members = {pid: pid for pid, r in roots.items() if r.get('kind') in ('native-browser', 'native-office')}
    changed = True
    while changed:
        changed = False
        for pid, p in processes.items():
            if pid not in members and p['ppid'] in members and p['tracer'] == 0:
                members[pid] = members[p['ppid']]
                changed = True
    return members


class NativeBrowser:
    def __init__(self, owner, config, prefix, home, guest, state, read_process):
        self.owner, self.config = owner, config
        self.prefix, self.home, self.guest, self.state = prefix, home, guest, state
        self.read_process = read_process

    def open(self, request):
        if self.config.get('browser_backend', 'guest') != 'termux-zink':
            raise RuntimeError('Native browser is not selected in the desktop profile')
        if request.get('session') != self.owner.data['session']:
            raise RuntimeError('Desktop session changed; retry from the current desktop')
        if not self.owner.core_alive() or self.owner.data['phase'] != 'running':
            raise RuntimeError('Start the desktop before opening its native browser')
        targets = normalize_targets(request.get('urls', []), self.prefix, self.home, self.guest)
        executable = self.prefix / 'lib/chromium/chrome'
        icd = self.prefix / 'share/vulkan/icd.d' / self.config['native_browser_icd']
        if not executable.is_file() or not icd.is_file():
            raise RuntimeError('Native browser dependencies missing: pkg install chromium mesa mesa-vulkan-icd-freedreno')
        self.owner.data['roots'] = [r for r in self.owner.data['roots']
                                    if r.get('kind') != 'native-browser' or self.owner.root_valid(r)]
        existing = any(r.get('kind') == 'native-browser' and self.owner.root_valid(r)
                       for r in self.owner.data['roots'])
        if existing and not targets:
            root = next(r for r in self.owner.data['roots'] if r.get('kind') == 'native-browser')
            return dict(self.owner.status(), native_browser_pid=root['pid'], display=self.config['display'])
        profile = self.home / '.config/chromium-native'
        if not existing and (profile / 'SingletonLock').is_symlink():
            try:
                pid = int((profile / 'SingletonLock').readlink().name.rsplit('-', 1)[-1])
                if self.read_process(pid):
                    raise RuntimeError('Native browser profile is already used by an unregistered process')
            except ValueError:
                raise RuntimeError('Unknown native browser profile lock; inspect before opening')
        child = self.owner.spawn([self.prefix / 'bin/python', self.home / '.local/lib/tablet-desktop/browser_exec.py',
                                  *targets], 'native-browser.log')
        self.owner.helpers.append(child)
        if not existing:
            for _ in range(30):
                current = self.read_process(child.pid)
                if current and current['exe'] == str(executable) and current['tracer'] == 0:
                    self.owner.data['roots'].append(dict(current, kind='native-browser',
                                                        session=self.owner.data['session']))
                    self.owner.sample()
                    break
                if child.poll() is not None:
                    raise RuntimeError('Native browser exited during launch; inspect native-browser.log')
                time.sleep(.1)
            else:
                raise RuntimeError('Native browser launch was not registered; inspect desktop records')
        self.owner.event('native-browser-opened', targets=len(targets), reused=existing)
        return self.owner.status()
