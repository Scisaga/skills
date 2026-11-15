"""Fixed native LibreOffice launch; its process tree belongs to the desktop session."""
import time
from pathlib import Path
from urllib.parse import urlsplit
from browser_resource import normalize_targets


class NativeOffice:
    def __init__(self, owner, config, prefix, home, guest, read_process):
        self.owner, self.config = owner, config
        self.prefix, self.home, self.guest = prefix, home, guest
        self.read_process = read_process

    def open(self, request):
        if self.config.get('office_backend', 'guest') != 'native-gtk3':
            raise RuntimeError('Native office is not selected in the desktop profile')
        if request.get('session') != self.owner.data['session'] or not self.owner.core_alive() or self.owner.data['phase'] != 'running':
            raise RuntimeError('Open office from the current running desktop session')
        mode = request.get('mode', 'writer')
        if mode not in ('writer', 'calc', 'impress'):
            raise ValueError('Office mode must be writer, calc or impress')
        values = request.get('urls', [])
        if not isinstance(values, list) or any(not isinstance(v, str) or urlsplit(v).scheme in ('chrome', 'about') for v in values):
            raise ValueError('Unsupported office targets')
        targets = normalize_targets(values, self.prefix, self.home, self.guest)
        executable = self.prefix / 'lib/libreoffice/program/oosplash'
        if not executable.is_file():
            raise RuntimeError('Native office missing: pkg install libreoffice')
        self.owner.data['roots'] = [r for r in self.owner.data['roots'] if r.get('kind') != 'native-office' or self.owner.root_valid(r)]
        existing = any(r.get('kind') == 'native-office' for r in self.owner.data['roots'])
        profile = self.home / '.config/libreoffice-native'
        if not existing:
            for path in Path('/proc').glob('[0-9]*/cmdline'):
                try:
                    command = path.read_bytes().split(b'\0')
                    if command and command[0] in (str(executable).encode(), str(executable.with_name('soffice.bin')).encode()) and ('-env:UserInstallation=' + profile.as_uri()).encode() in command:
                        raise RuntimeError('Native office profile is used by an unregistered process')
                except OSError:
                    pass
        child = self.owner.spawn([self.prefix / 'bin/python', self.home / '.local/lib/tablet-desktop/office_exec.py', mode, *targets], 'native-office.log')
        self.owner.helpers.append(child)
        if not existing:
            for _ in range(40):
                current = self.read_process(child.pid)
                if current and current['exe'] == str(executable) and current['tracer'] == 0:
                    self.owner.data['roots'].append(dict(current, kind='native-office', session=self.owner.data['session']))
                    self.owner.sample()
                    break
                if child.poll() is not None:
                    raise RuntimeError('Native office exited during launch; inspect native-office.log')
                time.sleep(.1)
            else:
                raise RuntimeError('Native office launch was not registered')
        self.owner.event('native-office-opened', mode=mode, targets=len(targets), reused=existing)
        return self.owner.status()
