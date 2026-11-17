#!/usr/bin/env python3
"""Opt-in guest setup for Android-protected GNOME Keyring. Preview unless --apply."""
from __future__ import annotations

import argparse
import base64
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from jsonc_settings import merge

SKILL = Path(__file__).resolve().parents[1]
HELPER_URL = 'https://raw.githubusercontent.com/git/git/v2.47.3/contrib/credential/libsecret/git-credential-libsecret.c'
HELPER_SHA256 = 'c2521ac2df8cb058423b086d19842c53bcbdcb462ab56a42c956e7f89313899b'
CODE_GUARD = '''# BEGIN tablet Android keyring
if [ -f "$HOME/.local/share/tablet-desktop/android-keyring/master.sealed" ]; then
    /usr/bin/python3 "$HOME/.local/lib/tablet-desktop/android-keyring/tablet-keyring" unlock >/dev/null || {
        echo "Android-protected keyring unavailable; unlock the tablet and retry." >&2
        exit 1
    }
fi
# END tablet Android keyring
'''


def digest(data):
    return hashlib.sha256(data).hexdigest()


def command(args, **kwargs):
    result = subprocess.run([str(a) for a in args], capture_output=True, text=True, timeout=45, **kwargs)
    if result.returncode:
        raise RuntimeError(f'{Path(args[0]).name} failed (exit {result.returncode})')
    return result.stdout


def put(path, data, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError('Refusing to overwrite a symlink')
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temp = Path(stream.name)
        try:
            temp.chmod(mode)
            stream.write(data)
            stream.flush(); os.fsync(stream.fileno())
            stream.close()
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)


def configure(args):
    home = Path.home()
    if not str(home).startswith('/home/') or not Path('/system/bin/getprop').exists():
        raise RuntimeError('Run this setup in the current Xfce guest terminal')
    missing = [name for name in ('gnome-keyring-daemon', 'gdbus', 'git', 'cc', 'pkg-config') if not shutil.which(name)]
    if missing:
        raise RuntimeError('Missing dependencies. Install: apt-get install gnome-keyring libsecret-tools seahorse libsecret-1-dev build-essential')
    if int(command(['/system/bin/getprop', 'ro.build.version.sdk']).strip()) < 35:
        raise RuntimeError('Android 15+ is required')
    if digest(args.bridge_jar.read_bytes()) != args.bridge_sha256:
        raise ValueError('Bridge SHA256 mismatch')
    if digest(args.credential_source.read_bytes()) != HELPER_SHA256:
        raise ValueError('Credential helper source must match the pinned official Git source')
    base = home / '.local/lib/tablet-desktop/android-keyring'
    helper = home / '.local/libexec/git-credential-libsecret'
    existing = subprocess.run(['git', 'config', '--global', '--get-all', 'credential.helper'], capture_output=True, text=True).stdout.splitlines()
    if existing and existing != [str(helper)]:
        raise ValueError('Existing Git credential helpers require a separate migration')
    argv = home / '.vscode/argv.json'
    argv_after = merge(argv.read_text(encoding='utf-8') if argv.exists() else '{}\n', {'password-store': 'gnome-libsecret'})
    entry = home / '.config/autostart/tablet-keyring.desktop'
    executable = str(base / 'tablet-keyring').replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
    entry_after = ('[Desktop Entry]\nType=Application\nName=Desktop credential keyring\n'
                   f'Exec=/usr/bin/python3 "{executable}" unlock\nOnlyShowIn=XFCE;\n'
                   'Terminal=false\nNoDisplay=true\nStartupNotify=false\n')
    service = home / '.local/share/dbus-1/services/org.freedesktop.secrets.service'
    home_argument = ('HOME=' + str(home)).replace('\\', '\\\\').replace('"', '\\"')
    service_after = ('[D-BUS Service]\nName=org.freedesktop.secrets\n'
                     f'Exec=/usr/bin/env "{home_argument}" /usr/bin/python3 "{executable}" unlock\n')
    plan = {'backend': 'AndroidKeyStore + GNOME Secret Service', 'extra_password': False,
            'git_helper': str(helper), 'code_password_store': 'gnome-libsecret', 'autostart': str(entry),
            'inputs': {'bridge_sha256': args.bridge_sha256, 'credential_source_sha256': HELPER_SHA256}}
    wrappers = [p for p in (Path('/usr/local/bin/code-tablet'), Path('/usr/local/bin/code-tablet-software')) if p.exists()]
    needs_guard = any(CODE_GUARD not in p.read_text(encoding='utf-8') for p in wrappers)
    plan['code_launch_guard_required'] = needs_guard
    if not args.apply:
        return {'applied': False, **plan}
    if needs_guard:
        raise RuntimeError('Install the Code launch guard with --launch-guard --state PATH --apply as guest root before applying keyring setup')
    os.umask(0o077)
    backup = home / '.local/state/tablet-desktop' / ('keyring-setup-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    backup.mkdir(parents=True, mode=0o700)
    records = []

    def before(path):
        if path.is_symlink() or not path.resolve().is_relative_to(home.resolve()):
            raise ValueError('Configuration path escapes the guest home')
        return {'path': str(path), 'before': base64.b64encode(path.read_bytes()).decode() if path.exists() else None,
                'mode': path.stat().st_mode & 0o777 if path.exists() else None}

    # Retain executables and all encrypted credential data when undoing configuration.
    # Android 14+ refuses dynamically loaded code that is writable at load time.
    put(base / 'tablet-keyring.jar', args.bridge_jar.read_bytes(), 0o400)
    put(base / 'tablet-keyring', (SKILL / 'assets/desktop/guest/tablet-keyring').read_bytes(), 0o700)
    probe = json.loads(command(['/usr/bin/python3', base / 'tablet-keyring', 'probe']))
    if not probe.get('ok'):
        raise RuntimeError('Android hardware key probe failed')
    sealed = home / '.local/share/tablet-desktop/android-keyring/master.sealed'
    initialized = json.loads(command(['/usr/bin/python3', base / 'tablet-keyring', 'unlock' if sealed.exists() else 'initialize']))
    if not initialized.get('ok') or not initialized.get('login_unlocked'):
        raise RuntimeError('Keyring initialization/unlock verification failed')
    key_info = json.loads(command(['/usr/bin/python3', base / 'tablet-keyring', 'info']))
    with tempfile.TemporaryDirectory(prefix='git-libsecret-', dir=backup) as folder:
        binary = Path(folder) / 'git-credential-libsecret'
        flags = command(['pkg-config', '--cflags', '--libs', 'libsecret-1']).split()
        command(['cc', '-O2', '-Wall', '-Wextra', args.credential_source, '-o', binary, *flags])
        put(helper, binary.read_bytes(), 0o700)
    if os.environ.get('GIT_CONFIG_GLOBAL'):
        raise ValueError('Custom GIT_CONFIG_GLOBAL requires a separate migration')
    git_config = home / '.gitconfig'
    xdg_git = Path(os.environ.get('XDG_CONFIG_HOME', home / '.config')) / 'git/config'
    if not git_config.exists() and xdg_git.exists():
        git_config = xdg_git
    candidate = backup / 'gitconfig.candidate'
    put(candidate, git_config.read_bytes() if git_config.exists() else b'', 0o600)
    command(['git', 'config', '--file', candidate, 'credential.helper', helper])
    changes = ((argv, argv_after.encode('utf-8')), (entry, entry_after.encode('utf-8')),
               (service, service_after.encode('utf-8')),
               (git_config, candidate.read_bytes()))
    for path, content in changes:
        record = before(path)
        record['after_sha256'] = digest(content)
        records.append(record)
    state = backup / 'configuration.json'
    put(state, json.dumps({'files': records, 'credential_data_retained': True}, indent=2).encode(), 0o600)
    for path, content in changes:
        put(path, content, 0o600)
    candidate.unlink()
    command(['gdbus', 'call', '--session', '--dest', 'org.freedesktop.DBus', '--object-path',
             '/org/freedesktop/DBus', '--method', 'org.freedesktop.DBus.ReloadConfig'])
    return {'applied': True, **plan, 'hardware_security_level': key_info['security_level'], 'login_unlocked': True,
            'rollback_state': str(state)}


def restore(args):
    state = json.loads(args.restore.read_text(encoding='utf-8'))
    home = Path.home().resolve()
    for record in state['files']:
        path = Path(record['path'])
        allowed = (path in (Path('/usr/local/bin/code-tablet'), Path('/usr/local/bin/code-tablet-software'))
                   if state.get('scope') == 'code-launch-guard' else path.resolve().is_relative_to(home))
        if path.is_symlink() or not allowed or digest(path.read_bytes()) != record['after_sha256']:
            raise ValueError('Configuration changed after setup; refusing to overwrite it')
    if args.apply:
        for record in state['files']:
            path = Path(record['path'])
            if record['before'] is None:
                path.unlink()
            else:
                put(path, base64.b64decode(record['before']), record['mode'])
    return {'applied': args.apply, 'credential_data_retained': True}


def launch_guard(args):
    records, changes = [], []
    for path in (Path('/usr/local/bin/code-tablet'), Path('/usr/local/bin/code-tablet-software')):
        if not path.exists():
            continue
        original = path.read_text(encoding='utf-8')
        if CODE_GUARD in original:
            continue
        if '# BEGIN tablet Android keyring' in original:
            raise ValueError('A different existing launch guard requires review')
        lines = original.splitlines(keepends=True)
        positions = [i for i, line in enumerate(lines) if line.startswith('exec ') and '/usr/bin/code ' in line]
        if len(positions) != 1:
            raise ValueError('Unrecognized Code wrapper; preserving it')
        lines.insert(positions[0], CODE_GUARD)
        changed = ''.join(lines).encode('utf-8')
        records.append({'path': str(path), 'before': base64.b64encode(path.read_bytes()).decode(),
                        'mode': path.stat().st_mode & 0o777, 'after_sha256': digest(changed)})
        changes.append((path, changed))
    if args.apply and changes:
        if not args.state or args.state.exists():
            raise ValueError('A new --state path is required before writing launch guards')
        put(args.state, json.dumps({'scope': 'code-launch-guard', 'files': records}, indent=2).encode(), 0o600)
        for path, data in changes:
            put(path, data, 0o755)
    return {'applied': args.apply, 'changed': [str(path) for path, _ in changes]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bridge-jar', type=Path)
    parser.add_argument('--bridge-sha256')
    parser.add_argument('--credential-source', type=Path, help=HELPER_URL)
    parser.add_argument('--restore', type=Path)
    parser.add_argument('--launch-guard', action='store_true')
    parser.add_argument('--state', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if args.restore and args.launch_guard:
        parser.error('--restore and --launch-guard are mutually exclusive')
    if not args.restore and not args.launch_guard and not all((args.bridge_jar, args.bridge_sha256, args.credential_source)):
        parser.error('--bridge-jar, --bridge-sha256 and --credential-source are required for setup')
    print(json.dumps(restore(args) if args.restore else launch_guard(args) if args.launch_guard else configure(args), ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error))
