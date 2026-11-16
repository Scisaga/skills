import hashlib
import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import thunar_core


class ThunarCoreTests(unittest.TestCase):
    def test_launchers_preserve_mime_actions_and_other_helpers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);home = root / 'home/developer'
            source = root / 'usr/share/applications/thunar.desktop'
            source.parent.mkdir(parents=True)
            source.write_text('[Desktop Entry]\nName=Thunar\nExec=Thunar %F\nDBusActivatable=true\nMimeType=inode/directory;\nActions=Bulk;\n\n[Desktop Action Bulk]\nExec=Thunar --bulk-rename\n')
            rc = home / '.config/xfce4/helpers.rc';rc.parent.mkdir(parents=True)
            rc.write_text('WebBrowser=existing-browser\nFileManager=Thunar\n')
            files = thunar_core.launcher_files(root, home)
            entry = files[home / '.local/share/applications/thunar.desktop']
            self.assertIn('Exec=/usr/local/bin/tablet-thunar-core %F', entry)
            self.assertIn('DBusActivatable=false', entry)
            self.assertIn('MimeType=inode/directory;', entry)
            self.assertIn('[Desktop Action Bulk]\nExec=Thunar --bulk-rename', entry)
            self.assertIn('WebBrowser=existing-browser', files[rc])
            self.assertIn('FileManager=custom-ThunarCore', files[rc])
            self.assertEqual(rc.read_text(), 'WebBrowser=existing-browser\nFileManager=Thunar\n')

    def test_other_file_manager_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);home = root / 'home/developer'
            source = root / 'usr/share/applications/thunar.desktop';source.parent.mkdir(parents=True)
            source.write_text('[Desktop Entry]\nExec=Thunar %F\n')
            rc = home / '.config/xfce4/helpers.rc';rc.parent.mkdir(parents=True)
            rc.write_text('FileManager=another-file-manager\n')
            with self.assertRaisesRegex(ValueError, 'Another file manager'):
                thunar_core.launcher_files(root, home)

    def test_restore_refuses_later_user_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);file = root / 'launcher';file.write_text('user edit')
            state = root / 'state.json'
            state.write_text(json.dumps({'schema': 1, 'home': str(Path.home()), 'files': [{'path': str(file), 'after': hashlib.sha256(b'generated').hexdigest()}], 'session': []}))
            with self.assertRaisesRegex(ValueError, 'Launcher changed'):
                thunar_core.restore(SimpleNamespace(state=state, apply=True))
            self.assertEqual(file.read_text(), 'user edit')

    def test_already_restored_state_is_checked_without_rewriting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);file = root / 'launcher';file.write_bytes(b'original')
            state = root / 'state.json'
            state.write_text(json.dumps({'schema': 1, 'home': str(Path.home()), 'status': 'restored', 'files': [{'path': str(file), 'before': base64.b64encode(b'original').decode()}], 'session': []}))
            self.assertEqual(thunar_core.restore(SimpleNamespace(state=state, apply=True))['status'], 'restored')
            self.assertEqual(file.read_bytes(), b'original')


if __name__ == '__main__':
    unittest.main()
