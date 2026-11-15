"""Pinned optional glibc KGSL driver; extract into /opt, keeping distro Mesa intact."""
import hashlib
import json
import os
import posixpath
import re
import shutil
import tarfile
import urllib.request
import uuid
from pathlib import PurePosixPath

VERSION = '27.0.0-devel-20261025-r2'
DRIVER_ROOT = '/opt/tablet-mesa-' + VERSION
FILENAME = 'mesa-for-android-container_' + VERSION + '_debian_trixie_arm64.tar.gz'
URL = 'https://github.com/lfdevs/mesa-for-android-container/releases/download/mesa-' + VERSION + '/' + FILENAME
SHA256 = '79e1aaf5a49e204fae68a5c87c76248701ba723f4349bda87d310f456c5705cf'


def installed_driver_ready(guest, config):
    """Inspect the selected bundle, including installations using an older directory alias."""
    try:
        name = config.get('driver_root', '')
        if config.get('backend') != 'freedreno-kgsl' or not isinstance(name, str) or not re.fullmatch(r'/opt/tablet-mesa-[A-Za-z0-9._-]+', name):
            return False
        directory = guest / name.lstrip('/')
        if not directory.resolve().is_relative_to((guest / 'opt').resolve()):
            return False
        marker = json.loads((directory / 'tablet-gpu-bundle.json').read_text())
        return (marker.get('sha256') == SHA256 and marker.get('version') == VERSION
                and (directory / 'usr/lib/aarch64-linux-gnu/dri/kgsl_dri.so').is_file())
    except (OSError, ValueError, AttributeError):
        return False


def extract_bundle(archive, guest):
    if hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
        raise ValueError('GPU bundle checksum mismatch; nothing extracted')
    destination = guest / DRIVER_ROOT.lstrip('/')
    marker = destination / 'tablet-gpu-bundle.json'
    if destination.exists():
        if marker.is_file() and json.loads(marker.read_text()).get('sha256') == SHA256:
            return
        raise ValueError('GPU destination exists without expected manifest; inspect instead of overwriting')
    stage = destination.with_name(destination.name + '.stage-' + uuid.uuid4().hex)
    stage.mkdir(parents=True)
    try:
        with tarfile.open(archive) as bundle:
            for member in bundle.getmembers():
                path = PurePosixPath(member.name)
                if path.is_absolute() or '..' in path.parts or member.isdev() or member.isfifo():
                    raise ValueError('Unsafe GPU archive member')
                if member.issym() or member.islnk():
                    target = PurePosixPath(member.linkname)
                    combined = posixpath.normpath(posixpath.join(str(path.parent) if member.issym() else '', str(target)))
                    if target.is_absolute() or combined == '..' or combined.startswith('../'):
                        raise ValueError('GPU archive link escapes its isolated directory')
            options = {'filter': 'data'} if hasattr(tarfile, 'data_filter') else {}
            bundle.extractall(stage, **options)
        icd = stage / 'usr/share/vulkan/icd.d/freedreno_icd.aarch64.json'
        value = json.loads(icd.read_text())
        value['ICD']['library_path'] = DRIVER_ROOT + '/usr/lib/aarch64-linux-gnu/libvulkan_freedreno.so'
        icd.write_text(json.dumps(value) + '\n')
        (stage / 'tablet-gpu-bundle.json').write_text(json.dumps({'version': VERSION, 'sha256': SHA256, 'url': URL}) + '\n')
        stage.rename(destination)
    finally:
        if stage.exists():
            if stage.is_symlink() or not stage.resolve().is_relative_to((guest / 'opt').resolve()):
                raise ValueError('Refusing GPU stage cleanup outside guest opt')
            shutil.rmtree(stage)


def install_bundle(guest, cache):
    if os.uname().machine not in ('aarch64', 'arm64'):
        raise RuntimeError('The reviewed KGSL bundle supports Debian 13 ARM64 only')
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / FILENAME
    if not archive.exists():
        request = urllib.request.Request(URL, headers={'User-Agent': 'scisaga-termux-desktop'})
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != SHA256:
            raise ValueError('Downloaded GPU bundle checksum mismatch')
        archive.write_bytes(data)
    extract_bundle(archive, guest)
