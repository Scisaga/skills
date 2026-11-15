"""Owned native VirGL resource; no extra TCP listener or global process-name kills."""
import json
import os
import re
import signal
import socket
import stat
import subprocess
import time


class GpuResource:
    def __init__(self, owner, prefix, home, state, read_process, same_identity, guest=None):
        self.owner = owner
        self.prefix, self.home, self.state = prefix, home, state
        self.read_process, self.same_identity = read_process, same_identity
        self.guest = guest
        self.path = prefix / 'tmp/.tablet-desktop-gpu'
        self.owner.data.setdefault('gpu_record', None)

    def backend(self):
        path = self.home / '.config/tablet-desktop/gpu.json'
        if not path.exists():
            return 'software'
        value = json.loads(path.read_text(encoding='utf-8')).get('backend', 'software')
        if value not in ('software', 'virgl-android', 'freedreno-kgsl'):
            raise RuntimeError('Unsupported desktop GPU backend')
        return value

    def direct_ready(self):
        value = json.loads((self.home / '.config/tablet-desktop/gpu.json').read_text(encoding='utf-8'))
        root = value.get('driver_root', '')
        return bool(self.guest and isinstance(root, str) and re.fullmatch(r'/opt/tablet-mesa-[A-Za-z0-9._-]+', root)
                    and (self.guest / root.lstrip('/') / 'usr/lib/aarch64-linux-gnu/dri/kgsl_dri.so').is_file())

    def alive(self):
        record = self.owner.data.get('gpu_record')
        return bool(record and self.same_identity(record, self.read_process(record['pid'])))

    def socket_identity(self):
        try:
            value = self.path.lstat()
            return (value.st_dev, value.st_ino) if stat.S_ISSOCK(value.st_mode) else None
        except OSError:
            return None

    def listening(self):
        try:
            with socket.socket(socket.AF_UNIX) as connection:
                connection.settimeout(.4)
                connection.connect(str(self.path))
            return True
        except OSError:
            return False

    def ensure(self):
        if self.backend() == 'software':
            return
        if self.backend() == 'freedreno-kgsl':
            if not self.direct_ready():
                raise RuntimeError('Isolated direct GPU bundle missing; reapply the reviewed desktop profile')
            return
        if self.alive():
            if self.path.is_socket() and not self.path.is_symlink():
                record = self.owner.data['gpu_record']
                identity = self.socket_identity()
                if 'socket_inode' in record and identity != (record['socket_device'], record['socket_inode']):
                    raise RuntimeError('Owned GPU socket was replaced; inspect desktop records')
                record.update(socket_device=identity[0], socket_inode=identity[1])
                self.owner.save()
                return
            raise RuntimeError('Owned GPU server lost its socket; inspect desktop records')
        if self.path.exists() or self.path.is_symlink():
            if not self.path.is_socket() or self.path.is_symlink():
                raise RuntimeError('GPU socket path contains an unknown file; inspect before replacing it')
            if self.listening():
                raise RuntimeError('GPU socket is in use by an unregistered process; inspect before adopting it')
            self.path.unlink()
        executable = self.prefix / 'bin/virgl_test_server_android'
        if not executable.is_file():
            raise RuntimeError('GPU backend missing; native Termux: pkg install virglrenderer-android')
        child = self.owner.spawn([executable, '--no-fork', '--multi-clients', '--socket-path', self.path], 'gpu.log')
        self.owner.helpers.append(child)
        deadline = time.monotonic() + 6
        record = None
        while time.monotonic() < deadline and child.poll() is None:
            record = self.read_process(child.pid)
            if record and record['exe'] == str(executable) and self.path.is_socket() and not self.path.is_symlink():
                self.path.chmod(0o600)
                identity = self.socket_identity()
                self.owner.data['gpu_record'] = dict(record, session=self.owner.data['session'], socket_device=identity[0], socket_inode=identity[1])
                self.owner.save()
                self.owner.event('gpu-server-started', backend='virgl-android')
                return
            time.sleep(.1)
        # This Popen child belongs to this start attempt, not a matching process name.
        if child.poll() is None:
            child.terminate()
            try: child.wait(timeout=2)
            except subprocess.TimeoutExpired: child.kill(); child.wait()
        if self.path.is_socket() and not self.path.is_symlink() and not self.listening():
            self.path.unlink()
        raise RuntimeError('GPU server did not become ready; software profile remains available')

    def stop(self):
        record = self.owner.data.get('gpu_record')
        identity = None
        if record and 'socket_inode' in record:
            identity = (record['socket_device'], record['socket_inode'])
        elif self.alive():
            identity = self.socket_identity()
        if record:
            for sig in (signal.SIGTERM, signal.SIGKILL):
                if self.same_identity(record, self.read_process(record['pid'])):
                    try: os.kill(record['pid'], sig)
                    except ProcessLookupError: pass
                    deadline = time.monotonic() + 2
                    while self.same_identity(record, self.read_process(record['pid'])) and time.monotonic() < deadline:
                        time.sleep(.05)
        self.owner.data['gpu_record'] = None
        if identity:
            deadline = time.monotonic() + 2
            while self.socket_identity() == identity and self.listening() and time.monotonic() < deadline:
                time.sleep(.05)
            if self.socket_identity() == identity and not self.listening():
                self.path.unlink()

    def status(self):
        result = {'gpu_backend': self.backend(), 'gpu_server_alive': self.alive()}
        if self.backend() == 'freedreno-kgsl':
            result['gpu_driver_ready'] = self.direct_ready()
        return result
