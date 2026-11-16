from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import panel_resources as resources


class ResourceTests(unittest.TestCase):
    def test_memory_uses_available_including_reclaimable_cache(self):
        values = resources.memory_values('MemTotal: 1000 kB\nMemFree: 10 kB\nMemAvailable: 400 kB\n')
        self.assertEqual(values['used_kib'], 600)
        self.assertEqual(values['percent'], 60)
        with self.assertRaises(KeyError):
            resources.memory_values('MemTotal: 1000 kB\nMemFree: 10 kB\n')
        with self.assertRaises(ValueError):
            resources.memory_values('MemTotal: 1000 kB\nMemAvailable: 2000 kB\n')

    def test_cpu_normalizes_all_cores_and_excludes_reused_pids(self):
        before = {'100:500': 100, '200:600': 10}
        after = {'100:500': 180, '200:900': 3000, '300:1000': 8000}
        self.assertEqual(resources.cpu_percent(before, after, 1, 100, 8), 10)

    def test_first_stale_or_reset_samples_never_invent_cpu_usage(self):
        self.assertIsNone(resources.cpu_percent({}, {'100:5': 1000}, 2, 100, 8))
        self.assertIsNone(resources.cpu_percent({'100:5': 10}, {'100:8': 900}, 2, 100, 8))
        for elapsed in (-1, 0, 31):
            self.assertIsNone(resources.cpu_percent({'100:5': 10}, {'100:5': 900}, elapsed, 100, 8))
        self.assertEqual(resources.cpu_percent({'100:5': 100}, {'100:5': 5}, 2, 100, 8), 0)

    def test_display_names_the_cpu_scope_and_memory_accounting(self):
        data = dict(resources.memory_values('MemTotal: 1000 kB\nMemAvailable: 400 kB\n'), cpu_percent=None, cores=8)
        output = resources.render(data)
        self.assertIn('桌面CPU —', output)
        self.assertIn('内存 60%', output)
        self.assertIn('不含其他 Android 应用', output)
        self.assertIn('MemTotal − MemAvailable', output)

    def test_user_edited_widget_is_not_overwritten_on_restore(self):
        import argparse
        import hashlib
        import json
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            helper = home / '.local/bin/tablet-resource-widget'
            helper.parent.mkdir(parents=True)
            helper.write_bytes(b'user edit')
            state = home / 'state.json'
            state.write_text(json.dumps({'schema': 1, 'home': str(home), 'panel': 1, 'plugin': 100,
                                         'helper_sha256': hashlib.sha256(b'installed').hexdigest(), 'rc_sha256': 'unused'}))
            with patch.object(Path, 'home', return_value=home), patch.object(resources, 'query') as query:
                with self.assertRaisesRegex(ValueError, 'changed after install'):
                    resources.restore(argparse.Namespace(state=state, apply=True))
                query.assert_not_called()
            self.assertEqual(helper.read_bytes(), b'user edit')


if __name__ == '__main__':
    unittest.main()
