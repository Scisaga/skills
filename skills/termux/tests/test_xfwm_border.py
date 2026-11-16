import argparse
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import xfwm_border as border


class BorderTests(unittest.TestCase):
    def test_bundled_png_overlays_match_the_xpm_canvas(self):
        assets = Path(__file__).resolve().parents[1] / 'assets/desktop/theme/xfwm4'
        self.assertEqual(border.normalize_overlays(assets), [])

    def test_overlay_repair_fills_the_whole_canvas_without_changing_xpm(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest('Pillow is an optional overlay repair dependency')
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            xpm = folder / 'close-active.xpm'
            original = border.solid_xpm(80, 80, '#303030')
            xpm.write_text(original)
            Image.new('RGBA', (44, 58), (255, 255, 255, 12)).save(folder / 'close-active.png')
            changes = border.normalize_overlays(folder)
            self.assertEqual(changes, [{'file': 'close-active.png', 'before': [44, 58], 'after': [80, 80]}])
            with Image.open(folder / 'close-active.png') as image:
                self.assertEqual(image.size, (44, 58))
            border.normalize_overlays(folder, apply=True)
            with Image.open(folder / 'close-active.png') as image:
                self.assertEqual(image.size, (80, 80))
                self.assertEqual(image.getpixel((79, 79)), (255, 255, 255, 12))
            self.assertEqual(xpm.read_text(), original)
            self.assertEqual(border.normalize_overlays(folder), [])

    def test_derived_theme_preserves_original_titlebar_and_buttons_and_restores_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            source = home / '.themes/Original/xfwm4'
            source.mkdir(parents=True)
            (source / 'themerc').write_text('button_spacing=6\n')
            (source / 'close-active.png').write_bytes(b'original button')
            (source / 'title-1-active.xpm').write_text(border.solid_xpm(48, 82, '#303030'))
            for mode in ('active', 'inactive'):
                for side in ('left', 'right'):
                    (source / ('top-' + side + '-' + mode + '.xpm')).write_text(border.solid_xpm(12, 82, '#303030'))
                    (source / (side + '-' + mode + '.png')).write_bytes(b'old wide border')
            before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}
            selected = ['Original']
            def query(*argv):
                selected[0] = argv[-1]
            args = argparse.Namespace(name='Thin', state=home / 'state.json', apply=True)
            with patch.object(Path, 'home', return_value=home), patch.object(border, 'value', side_effect=lambda *a: selected[0]), patch.object(border, 'query', side_effect=query):
                result = border.apply(args)
                self.assertEqual(selected[0], 'Thin')
                target = Path(result['target']) / 'xfwm4'
                self.assertEqual((target / 'close-active.png').read_bytes(), b'original button')
                self.assertEqual((target / 'title-1-active.xpm').read_bytes(), (source / 'title-1-active.xpm').read_bytes())
                self.assertEqual((target / 'themerc').read_bytes(), (source / 'themerc').read_bytes())
                self.assertFalse((target / 'left-active.png').exists())
                self.assertIn('"1 82 1 1"', (target / 'top-left-active.xpm').read_text())
                self.assertEqual(before, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()})
                selected[0] = 'New user choice'
                with self.assertRaisesRegex(ValueError, 'changed after apply'):
                    border.restore(args)
                self.assertEqual(selected[0], 'New user choice')
                selected[0] = 'Thin'
                border.restore(args)
                self.assertEqual(selected[0], 'Original')


if __name__ == '__main__':
    unittest.main()
