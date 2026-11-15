"""Pinned optional Termux:VA daemon and isolated matching Debian VLC binaries."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import urllib.request
import uuid
import zipfile
from pathlib import PurePosixPath

VLC_ROOT = '/opt/tablet-vlc-va-3.0.24-90'
VLC_FILE = 'vlc_termux-va_debian_3.0.24-90.zip'
VLC_URL = 'https://github.com/lfdevs/vlc/releases/download/release/termux-va/' + VLC_FILE
VLC_SHA256 = '16fd29a95e7981d83da60a93c82b82c7a11f6c994bf7b491ef7ac24f91407e6c'
VA_FILE = 'termux-va_0.1.0_aarch64.deb'
VA_URL = 'https://github.com/lfdevs/termux-va/releases/download/0.1.0/' + VA_FILE
VA_SHA256 = 'e278372d65b11337d6b73d8be2399763f7273637c7b12c975a5afac7939626fb'


def download(cache, filename, url, digest):
    path = cache / filename
    if not path.exists():
        request = urllib.request.Request(url, headers={'User-Agent': 'scisaga-termux-desktop'})
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('Optional video download checksum mismatch')
        path.write_bytes(data)
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError('Optional video cache checksum mismatch')
    return path


def install_video(guest, cache, prefix):
    if os.uname().machine not in ('aarch64', 'arm64'):
        raise RuntimeError('The reviewed video bundle supports Debian 13 ARM64 only')
    cache.mkdir(parents=True, exist_ok=True)
    archive = download(cache, VLC_FILE, VLC_URL, VLC_SHA256)
    package = download(cache, VA_FILE, VA_URL, VA_SHA256)
    destination = guest / VLC_ROOT.lstrip('/')
    marker = destination / 'tablet-video-bundle.json'
    if destination.exists():
        if not marker.is_file() or json.loads(marker.read_text()).get('sha256') != VLC_SHA256:
            raise ValueError('Video destination exists without expected manifest; inspect before overwriting')
    else:
        stage = destination.with_name(destination.name + '.stage-' + uuid.uuid4().hex)
        stage.mkdir(parents=True)
        try:
            with zipfile.ZipFile(archive) as bundle:
                for item in bundle.infolist():
                    name = PurePosixPath(item.filename)
                    if name.is_absolute() or '..' in name.parts:
                        raise ValueError('Unsafe video archive path')
                    if not item.is_dir() and name.suffix == '.deb':
                        if not re.fullmatch(r'[a-zA-Z0-9_.+~-]+\.deb', name.name):
                            raise ValueError('Invalid video package name')
                        deb = cache / name.name
                        deb.write_bytes(bundle.read(item))
                        subprocess.run([str(prefix / 'bin/dpkg-deb'), '-x', str(deb), str(stage)],
                                       stdin=subprocess.DEVNULL, check=True, capture_output=True)
            if not (stage / 'usr/bin/vlc').is_file():
                raise ValueError('Video bundle is missing its matching VLC executable')
            (stage / 'tablet-video-bundle.json').write_text(json.dumps({'sha256': VLC_SHA256, 'url': VLC_URL}) + '\n')
            stage.rename(destination)
        finally:
            if stage.exists():
                if stage.is_symlink() or not stage.resolve().is_relative_to((guest / 'opt').resolve()):
                    raise ValueError('Refusing video stage cleanup outside guest opt')
                shutil.rmtree(stage)
    current = subprocess.run([str(prefix / 'bin/dpkg-query'), '-W', '-f=${Version}', 'termux-va'],
                             stdin=subprocess.DEVNULL, capture_output=True, text=True)
    if current.returncode or current.stdout.strip() != '0.1.0':
        subprocess.run([str(prefix / 'bin/dpkg'), '--install', str(package)], stdin=subprocess.DEVNULL, check=True)
    # Package start/stop scripts use process-name kills. The desktop never invokes them.
