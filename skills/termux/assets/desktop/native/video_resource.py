"""On-demand, identity-bound Android video decoder bridge; no name-based kills."""
import os
import signal
import socket
import stat
import subprocess
import time


class VideoResource:
    def __init__(self, owner, prefix, read_process, same_identity):
        self.owner, self.prefix = owner, prefix
        self.read_process, self.same_identity = read_process, same_identity
        self.path = prefix / 'tmp/termux-va/termux-va.sock'
        owner.data.setdefault('video_record', None)

    def alive(self):
        r = self.owner.data.get('video_record')
        return bool(r and self.same_identity(r, self.read_process(r['pid'])))

    def identity(self):
        try:
            s = self.path.lstat()
            return (s.st_dev, s.st_ino) if stat.S_ISSOCK(s.st_mode) else None
        except OSError:
            return None

    def listening(self):
        try:
            with socket.socket(socket.AF_UNIX) as c:
                c.settimeout(.3)
                c.connect(str(self.path))
            return True
        except OSError:
            return False

    def ensure(self):
        if self.alive():
            r = self.owner.data['video_record']
            if self.identity() != (r['socket_device'], r['socket_inode']):
                raise RuntimeError('Owned video decoder socket was replaced')
            return
        executable = self.prefix / 'bin/termux-va'
        probe = self.prefix / 'bin/tva-probe'
        if not executable.is_file() or not probe.is_file():
            raise RuntimeError('Termux:VA missing; install the pinned optional video bundle')
        if self.path.parent.is_symlink():
            raise RuntimeError('Video socket directory must not be a symlink')
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path.parent.chmod(0o700)
        if self.path.exists() or self.path.is_symlink():
            if not self.identity() or self.path.is_symlink() or self.listening():
                raise RuntimeError('Video socket belongs to an unknown resource; inspect before replacing it')
            self.path.unlink()
        child = self.owner.spawn([executable], 'video-decoder.log')
        self.owner.helpers.append(child)
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline and child.poll() is None:
            r = self.read_process(child.pid)
            identity = self.identity()
            if r and r['exe'] == str(executable) and identity:
                self.path.chmod(0o600)
                self.owner.data['video_record'] = dict(r, session=self.owner.data['session'], socket_device=identity[0], socket_inode=identity[1])
                self.owner.save()
                try:
                    checked = subprocess.run([str(probe), str(self.path), '2500'], stdin=subprocess.DEVNULL,
                                             capture_output=True, text=True, timeout=4)
                    if checked.returncode or 'healthy' not in checked.stdout:
                        raise RuntimeError('Video decoder did not pass the real-frame health probe')
                except (OSError, subprocess.SubprocessError, RuntimeError):
                    self.stop()
                    raise
                self.owner.event('video-decoder-started', backend='termux-va')
                return
            time.sleep(.1)
        if child.poll() is None:
            child.terminate()
            try: child.wait(timeout=2)
            except subprocess.TimeoutExpired: child.kill(); child.wait()
        raise RuntimeError('Video decoder did not start')

    def stop(self):
        r = self.owner.data.get('video_record')
        if not r:
            return
        identity = (r['socket_device'], r['socket_inode'])
        for sig in (signal.SIGTERM, signal.SIGKILL):
            if self.same_identity(r, self.read_process(r['pid'])):
                try: os.kill(r['pid'], sig)
                except ProcessLookupError: pass
                deadline = time.monotonic() + 2
                while self.same_identity(r, self.read_process(r['pid'])) and time.monotonic() < deadline:
                    time.sleep(.05)
        if self.identity() == identity and not self.listening():
            self.path.unlink()
        self.owner.data['video_record'] = None
