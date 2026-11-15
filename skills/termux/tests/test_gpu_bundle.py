"""The optional binary bundle must fail closed and stay isolated from distro files."""
import hashlib
import io
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import desktop_gpu_bundle as bundle


class GpuBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / 'bundle.tar.gz'
        self.guest = self.root / 'guest'

    def archive_with(self, name, data=b'{}', link=None):
        with tarfile.open(self.archive, 'w:gz') as archive:
            entry = tarfile.TarInfo(name)
            if link:
                entry.type = tarfile.SYMTYPE
                entry.linkname = link
                archive.addfile(entry)
            else:
                entry.size = len(data)
                archive.addfile(entry, io.BytesIO(data))
        return hashlib.sha256(self.archive.read_bytes()).hexdigest()

    def test_checksum_failure_leaves_system_and_opt_untouched(self):
        self.archive_with('usr/file')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            bundle.extract_bundle(self.archive, self.guest)
        self.assertFalse(self.guest.exists())

    def test_traversal_and_escaping_links_are_rejected(self):
        for name, link in (('../outside', None), ('usr/link', '../../../outside')):
            digest = self.archive_with(name, link=link)
            with self.subTest(name=name), patch.object(bundle, 'SHA256', digest), self.assertRaises(ValueError):
                bundle.extract_bundle(self.archive, self.guest)
        self.assertFalse((self.root / 'outside').exists())

    def test_valid_bundle_rewrites_only_its_own_icd_and_is_repeatable(self):
        name = 'usr/share/vulkan/icd.d/freedreno_icd.aarch64.json'
        digest = self.archive_with(name, json.dumps({'ICD': {'library_path': '/usr/lib/old.so'}}).encode())
        stock = self.guest / 'usr/lib/stock'
        stock.parent.mkdir(parents=True)
        stock.write_text('unchanged')
        with patch.object(bundle, 'SHA256', digest):
            bundle.extract_bundle(self.archive, self.guest)
            bundle.extract_bundle(self.archive, self.guest)
        installed = self.guest / bundle.DRIVER_ROOT.lstrip('/')
        self.assertTrue((installed / 'tablet-gpu-bundle.json').is_file())
        self.assertTrue(json.loads((installed / name).read_text())['ICD']['library_path'].startswith(bundle.DRIVER_ROOT))
        self.assertEqual(stock.read_text(), 'unchanged')

    def test_selected_legacy_directory_requires_matching_manifest_and_driver(self):
        name = '/opt/tablet-mesa-legacy-alias'
        directory = self.guest / name.lstrip('/')
        driver = directory / 'usr/lib/aarch64-linux-gnu/dri/kgsl_dri.so'
        driver.parent.mkdir(parents=True)
        driver.write_bytes(b'fixture')
        marker = directory / 'tablet-gpu-bundle.json'
        selected = {'backend': 'freedreno-kgsl', 'driver_root': name}
        self.assertFalse(bundle.installed_driver_ready(self.guest, selected))
        marker.write_text(json.dumps({'sha256': bundle.SHA256, 'version': bundle.VERSION}))
        self.assertTrue(bundle.installed_driver_ready(self.guest, selected))
        for invalid in ('/opt/tablet-mesa-../../outside', '/usr/lib', None):
            self.assertFalse(bundle.installed_driver_ready(self.guest, dict(selected, driver_root=invalid)))
        marker.write_text(json.dumps({'sha256': 'wrong', 'version': bundle.VERSION}))
        self.assertFalse(bundle.installed_driver_ready(self.guest, selected))
        marker.write_text(json.dumps({'sha256': bundle.SHA256, 'version': bundle.VERSION}))
        driver.unlink()
        self.assertFalse(bundle.installed_driver_ready(self.guest, selected))
