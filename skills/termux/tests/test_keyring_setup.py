"""Credential rollback preserves secrets and refuses later configuration edits."""
import argparse
import base64
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import keyring_setup as setup


class CredentialRollbackTests(unittest.TestCase):
    def test_later_edit_prevents_all_restoration(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            first, second = home / 'argv.json', home / '.gitconfig'
            first.write_bytes(b'configured')
            second.write_bytes(b'later user edit')
            state = home / 'state.json'
            state.write_text(json.dumps({'files': [
                {'path': str(p), 'before': base64.b64encode(b'original').decode(), 'mode': 0o600,
                 'after_sha256': setup.digest(b'configured')} for p in (first, second)
            ]}))
            with patch.object(setup.Path, 'home', return_value=home):
                with self.assertRaises(ValueError):
                    setup.restore(argparse.Namespace(restore=state, apply=True))
            self.assertEqual(first.read_bytes(), b'configured')
            self.assertEqual(second.read_bytes(), b'later user edit')

    def test_restore_retains_encrypted_credential_data(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            config, sealed = home / 'argv.json', home / 'master.sealed'
            config.write_bytes(b'configured')
            sealed.write_bytes(b'encrypted credential state')
            state = home / 'state.json'
            state.write_text(json.dumps({'files': [{'path': str(config), 'before': None, 'mode': None,
                                                   'after_sha256': setup.digest(b'configured')}]}))
            with patch.object(setup.Path, 'home', return_value=home):
                result = setup.restore(argparse.Namespace(restore=state, apply=True))
            self.assertFalse(config.exists())
            self.assertEqual(sealed.read_bytes(), b'encrypted credential state')
            self.assertTrue(result['credential_data_retained'])


if __name__ == '__main__':
    unittest.main()
