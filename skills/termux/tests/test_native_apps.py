"""Native office and decoder ownership boundaries; no real application is signalled."""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'assets/desktop/native'))
from office_resource import NativeOffice
from video_resource import VideoResource
from session_manager import UID, same_identity
from browser_resource import native_members


class NativeApps(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.owner = SimpleNamespace(data={'session': 'current', 'phase': 'running', 'roots': []},
                                     helpers=[], spawn=Mock(), save=Mock(), event=Mock(), core_alive=Mock(return_value=True))
        self.read = Mock(return_value=None)

    def test_office_rejects_stale_session_and_non_document_commands(self):
        office = NativeOffice(self.owner, {'office_backend': 'native-gtk3'}, self.base, self.base, self.base, self.read)
        for request in ({'session': 'old'}, {'session': 'current', 'mode': 'shell'},
                        {'session': 'current', 'urls': ['--headless']},
                        {'session': 'current', 'urls': ['chrome://gpu']}):
            with self.subTest(request=request), self.assertRaises((RuntimeError, ValueError)):
                office.open(request)
        self.owner.spawn.assert_not_called()

    def test_office_descendants_join_only_their_verified_native_root(self):
        roots = {10: {'kind': 'native-office'}}
        processes = {10: {'ppid': 1, 'tracer': 0}, 11: {'ppid': 10, 'tracer': 0}, 12: {'ppid': 11, 'tracer': 0},
                     20: {'ppid': 1, 'tracer': 0}}
        self.assertEqual(native_members(roots, processes), {10: 10, 11: 10, 12: 10})

    def test_decoder_preserves_unknown_file(self):
        video = VideoResource(self.owner, self.base, self.read, same_identity)
        (self.base / 'bin').mkdir()
        for name in ('termux-va', 'tva-probe'): (self.base / 'bin' / name).touch()
        video.path.parent.mkdir(parents=True)
        video.path.write_text('unrelated')
        with self.assertRaisesRegex(RuntimeError, 'unknown resource'): video.ensure()
        self.assertEqual(video.path.read_text(), 'unrelated')
        self.owner.spawn.assert_not_called()

    def test_decoder_does_not_signal_recycled_pid_or_remove_replacement_socket(self):
        video = VideoResource(self.owner, self.base, self.read, same_identity)
        r = {'pid': 987654, 'start': 10, 'exe': '/test/decoder', 'uid': UID, 'socket_device': 2, 'socket_inode': 3}
        self.owner.data['video_record'] = r
        self.read.return_value = dict(r, start=11)
        with patch('video_resource.signal', SimpleNamespace(SIGTERM=15, SIGKILL=9)), \
             patch('video_resource.os.kill') as kill, patch.object(video, 'identity', return_value=(2, 4)), \
             patch.object(Path, 'unlink') as unlink:
            video.stop()
        kill.assert_not_called()
        unlink.assert_not_called()

    def test_decoder_detects_socket_replacement_without_starting_another_daemon(self):
        video = VideoResource(self.owner, self.base, self.read, same_identity)
        r = {'pid': 987654, 'start': 10, 'exe': '/test/decoder', 'uid': UID, 'socket_device': 2, 'socket_inode': 3}
        self.owner.data['video_record'] = r
        self.read.return_value = dict(r)
        with patch.object(video, 'identity', return_value=(2, 4)), self.assertRaisesRegex(RuntimeError, 'replaced'):
            video.ensure()
        self.owner.spawn.assert_not_called()
