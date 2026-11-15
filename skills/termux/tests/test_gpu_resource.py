"""GPU ownership and failure cases; no live process is signalled."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'assets/desktop/native'))
from gpu_resource import GpuResource
from session_manager import UID, same_identity


class GpuOwnership(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.prefix = self.home / 'prefix'
        (self.prefix / 'tmp').mkdir(parents=True)
        self.owner = SimpleNamespace(data={'session': 'test'}, helpers=[], spawn=Mock(), save=Mock(), event=Mock())
        self.read = Mock(return_value=None)
        self.gpu = GpuResource(self.owner, self.prefix, self.home, self.home, self.read, same_identity)

    def configure(self, backend):
        p = self.home / '.config/tablet-desktop/gpu.json'
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({'backend': backend}))

    def test_software_default_does_not_spawn(self):
        self.gpu.ensure()
        self.owner.spawn.assert_not_called()
        self.assertEqual(self.gpu.status(), {'gpu_backend': 'software', 'gpu_server_alive': False})

    def test_missing_backend_fails_with_install_command(self):
        self.configure('virgl-android')
        with self.assertRaisesRegex(RuntimeError, 'pkg install virglrenderer-android'):
            self.gpu.ensure()
        self.owner.spawn.assert_not_called()

    def test_direct_driver_does_not_spawn_or_stop_a_virgl_service(self):
        self.configure('freedreno-kgsl')
        guest = self.home / 'guest'
        directory = '/opt/tablet-mesa-test'
        driver = guest / directory.lstrip('/') / 'usr/lib/aarch64-linux-gnu/dri/kgsl_dri.so'
        driver.parent.mkdir(parents=True)
        driver.touch()
        p = self.home / '.config/tablet-desktop/gpu.json'
        p.write_text(json.dumps({'backend': 'freedreno-kgsl', 'driver_root': directory}))
        self.gpu.guest = guest
        self.gpu.ensure()
        self.owner.spawn.assert_not_called()
        self.assertTrue(self.gpu.status()['gpu_driver_ready'])

    def test_missing_direct_driver_fails_without_software_fallback(self):
        self.configure('freedreno-kgsl')
        with self.assertRaisesRegex(RuntimeError, 'direct GPU bundle missing'):
            self.gpu.ensure()
        self.owner.spawn.assert_not_called()

    def test_unknown_file_is_preserved(self):
        self.configure('virgl-android')
        self.gpu.path.write_text('unrelated')
        with self.assertRaisesRegex(RuntimeError, 'unknown file'):
            self.gpu.ensure()
        self.assertEqual(self.gpu.path.read_text(), 'unrelated')
        self.owner.spawn.assert_not_called()

    def test_recycled_pid_is_not_signalled(self):
        record = {'pid': 987654, 'start': 123, 'uid': UID, 'exe': '/test/gpu'}
        self.owner.data['gpu_record'] = record
        self.read.return_value = dict(record, start=124)
        with patch('gpu_resource.signal', SimpleNamespace(SIGTERM=15, SIGKILL=9)), \
             patch('gpu_resource.os.kill') as kill:
            self.gpu.stop()
        kill.assert_not_called()
        self.assertIsNone(self.owner.data['gpu_record'])

    def test_unregistered_listener_is_not_adopted_or_removed(self):
        self.configure('virgl-android')
        with patch.object(Path, 'is_socket', return_value=True), \
             patch.object(Path, 'exists', return_value=True), \
             patch.object(self.gpu, 'listening', return_value=True), \
             patch.object(Path, 'unlink') as unlink:
            with self.assertRaisesRegex(RuntimeError, 'unregistered process'):
                self.gpu.ensure()
        unlink.assert_not_called()
        self.owner.spawn.assert_not_called()

    def test_shutdown_waits_for_owned_socket_to_stop_listening(self):
        self.owner.data['gpu_record'] = {'pid': 987654, 'socket_device': 4, 'socket_inode': 9}
        with patch('gpu_resource.signal', SimpleNamespace(SIGTERM=15, SIGKILL=9)), \
             patch.object(self.gpu, 'socket_identity', return_value=(4, 9)), \
             patch.object(self.gpu, 'listening', side_effect=[True, False, False]), \
             patch('gpu_resource.time.sleep'), patch.object(Path, 'unlink') as unlink:
            self.gpu.stop()
        unlink.assert_called_once()

    def test_shutdown_preserves_replacement_socket(self):
        self.owner.data['gpu_record'] = {'pid': 987654, 'socket_device': 4, 'socket_inode': 9}
        with patch('gpu_resource.signal', SimpleNamespace(SIGTERM=15, SIGKILL=9)), \
             patch.object(self.gpu, 'socket_identity', return_value=(4, 10)), \
             patch.object(Path, 'unlink') as unlink:
            self.gpu.stop()
        unlink.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
