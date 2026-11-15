"""UTF-8, marker boundaries, stale input and atomic context replacement."""
import tempfile
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import managed_context as context

NAME = 'test maintenance'
BEGIN = f'<!-- BEGIN {NAME} -->'
END = f'<!-- END {NAME} -->'


class ContextTests(unittest.TestCase):
    def test_chinese_roundtrip_preserves_unmanaged_bytes_and_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path, block = root / 'AGENTS.md', root / 'replacement.txt'
            old = ('用户备注\r\n' + BEGIN + '\r\n???? old\r\n' + END + '\r\nSSH 保持\r\n').encode('utf-8')
            replacement = BEGIN + '\n维护记录：背景重绘与合成冲突分开。\n' + END
            path.write_bytes(old)
            block.write_bytes(replacement.encode('utf-8'))
            preview = context.update_file(path, block, NAME, expected_sha256=context.digest(old))
            self.assertEqual(preview['status'], 'skipped')
            self.assertEqual(path.read_bytes(), old)
            result = context.update_file(path, block, NAME, expected_sha256=context.digest(old), backup_dir=root / 'backups', apply=True)
            self.assertTrue(result['readback_verified'])
            self.assertEqual(Path(result['backup']).read_bytes(), old)
            self.assertEqual(path.read_bytes(), ('用户备注\r\n' + replacement + '\r\nSSH 保持\r\n').encode('utf-8'))

    def test_ambiguous_markers_and_damaged_replacement_are_rejected(self):
        good = BEGIN + '\nvalid\n' + END
        for original, replacement in [(BEGIN + '\nmissing', good), (good + good, good),
                (END + BEGIN, good), (good, BEGIN + '\n????\n' + END),
                (good, BEGIN + '\n\ufffd\n' + END), (good, good + '\nother user text')]:
            with self.subTest(original=original), self.assertRaises(ValueError):
                context.replace_block(original, replacement, NAME)

    def test_stale_review_cannot_overwrite_current_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target, block = root / 'AGENTS.md', root / 'block.txt'
            target.write_text('new user note', encoding='utf-8')
            block.write_text(BEGIN + '\nnew\n' + END, encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'changed since review'):
                context.update_file(target, block, NAME, expected_sha256=context.digest(b'old'), apply=True, backup_dir=root / 'backup')
            self.assertEqual(target.read_text(), 'new user note')
            self.assertFalse((root / 'backup').exists())

    def test_readback_failure_is_not_reported_as_success(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target, block = root / 'AGENTS.md', root / 'block.txt'
            original = (BEGIN + '\nold\n' + END).encode()
            target.write_bytes(original)
            block.write_text(BEGIN + '\nnew\n' + END, encoding='utf-8')
            real_replace = context.os.replace
            def damaged_replace(src, dest):
                real_replace(src, dest)
                Path(dest).write_bytes(b'damaged after write')
            with patch.object(context.os, 'replace', side_effect=damaged_replace), self.assertRaisesRegex(RuntimeError, 'Readback'):
                context.update_file(target, block, NAME, expected_sha256=context.digest(original), apply=True, backup_dir=root / 'backup')
            self.assertEqual(next((root / 'backup').iterdir()).read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
