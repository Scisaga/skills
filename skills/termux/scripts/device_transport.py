"""Explicit ADB/strict SSH transport; no shell-built host commands or .env files."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path


class Device:
    def __init__(self, config):
        allowed = {'adb', 'serial', 'ssh_target', 'ssh_port', 'identity', 'ssh_bind', 'ssh_config', 'kex_algorithms'}
        if not isinstance(config, dict) or set(config) - allowed:
            raise ValueError('Unknown connection fields; see desktop-verification.md')
        self.config = dict(config)
        target = config.get('ssh_target', '')
        if target and (not isinstance(target, str) or target.startswith('-') or any(c.isspace() for c in target)):
            raise ValueError('ssh_target must be one user@host argument')
        port = config.get('ssh_port', 8022)
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError('ssh_port must be between 1 and 65535')
        if any(not isinstance(v, str) or not v or '\0' in v for k, v in config.items() if k != 'ssh_port'):
            raise ValueError('Connection values must be nonempty strings')
        self.digest = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()

    @classmethod
    def read(cls, path):
        return cls(json.loads(Path(path).read_text(encoding='utf-8-sig')))

    def adb_args(self):
        args = [self.config.get('adb', 'adb')]
        if self.config.get('serial'):
            args += ['-s', self.config['serial']]
        return args

    def ssh_args(self):
        if not self.config.get('ssh_target'):
            raise ValueError('This check needs ssh_target in the private connection file')
        args = ['ssh', '-F', self.config.get('ssh_config', os.devnull),
                '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                '-o', 'ConnectTimeout=8', '-o', 'ServerAliveInterval=5',
                '-o', 'ServerAliveCountMax=2', '-p', str(self.config.get('ssh_port', 8022))]
        if self.config.get('identity'):
            args += ['-i', self.config['identity']]
        if self.config.get('ssh_bind'):
            args += ['-b', self.config['ssh_bind']]
        if self.config.get('kex_algorithms'):
            args += ['-o', 'KexAlgorithms=' + self.config['kex_algorithms']]
        return args

    @staticmethod
    def run(args, script=None, timeout=20):
        try:
            payload = script.replace('\r\n', '\n').encode('utf-8') if script is not None else None
            result = subprocess.run(args, input=payload, capture_output=True, timeout=timeout)
        except FileNotFoundError as error:
            raise RuntimeError(f'{args[0]} not found; use host-tools for ADB/JDK or install OpenSSH client') from error
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(f'{Path(args[0]).name} timed out after {timeout} seconds') from error
        def decode(value):
            return value.decode('utf-8', errors='replace') if isinstance(value, bytes) else (value or '')
        stdout, stderr = decode(result.stdout), decode(result.stderr)
        if result.returncode:
            raise RuntimeError(f'{Path(args[0]).name} exited {result.returncode}: {(stderr or stdout)[-700:]}')
        return stdout.strip()

    def adb(self, *args, timeout=20):
        return self.run(self.adb_args() + list(args), timeout=timeout)

    def shell(self, *args, timeout=20):
        return self.adb('shell', *args, timeout=timeout)

    def shell_script(self, script, timeout=20):
        return self.run(self.adb_args() + ['shell', 'sh'], script.replace('\r\n', '\n'), timeout)

    def ssh_script(self, script, timeout=25):
        return self.run(self.ssh_args() + [self.config['ssh_target'], '/data/data/com.termux/files/usr/bin/bash -s'],
                        script.replace('\r\n', '\n'), timeout)


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.chmod(0o600)
    temporary.replace(path)
