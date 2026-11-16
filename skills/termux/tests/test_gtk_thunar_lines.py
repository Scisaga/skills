from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import gtk_thunar_lines as theme


class ThunarThemeTests(unittest.TestCase):
    def test_both_css_variants_receive_the_rules(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            (target / 'gtk-3.0').mkdir()
            for name in ('gtk.css', 'gtk-dark.css'):
                (target / 'gtk-3.0' / name).write_bytes(b'original variant')
            rules = b'.thunar toolbar { border-top-width: 1px; }'
            self.assertEqual(set(theme.patch_variants(target, rules)), {'gtk.css', 'gtk-dark.css'})
            for name in ('gtk.css', 'gtk-dark.css'):
                self.assertEqual((target / 'gtk-3.0' / name).read_bytes(), b'original variant\n' + rules)

    def test_restore_refuses_a_later_user_theme_choice(self):
        import argparse
        import json
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / 'state.json'
            state.write_text(json.dumps({'schema': 1, 'home': str(Path.home()), 'theme_before': 'Original', 'theme_after': 'Derived'}))
            with patch.object(theme, 'value', return_value='User theme'), patch.object(theme, 'query') as query:
                with self.assertRaisesRegex(ValueError, 'changed after apply'):
                    theme.restore(argparse.Namespace(state=state, apply=True))
                query.assert_not_called()


if __name__ == '__main__':
    unittest.main()
