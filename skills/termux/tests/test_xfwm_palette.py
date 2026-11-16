import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import xfwm_palette
try:
    from PIL import Image
except ImportError:
    Image = None


@unittest.skipIf(Image is None, 'Pillow is needed for theme artwork verification')
class XfwmPaletteTests(unittest.TestCase):
    def fixture(self, root, color):
        xpm = '/* XPM */\nstatic char *p[]={\n"4 3 2 1",\n". c #aaaaaa s active_mid_2",\n"X c #ffffff s active_text_color",\n"....",\n".XX.",\n"...."};\n'
        (root / 'close-active.xpm').write_text(xpm)
        Image.new('RGBA', (4, 3), color).save(root / 'close-active.png')
        (root / 'themerc').write_text('active_text_color=original\ninactive_text_color=original\nbutton_spacing=6\nframe_border_top=0\n')
        return xpm

    def test_glyph_grid_and_overlay_canvas_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);before = self.fixture(root, (255, 255, 255, 8))
            xfwm_palette.recolor(root, '#26282e', '#dadbe5', '#9699a3')
            after = (root / 'close-active.xpm').read_text()
            self.assertEqual(before.splitlines()[5:], after.splitlines()[5:])
            with Image.open(root / 'close-active.png') as image:
                self.assertEqual(image.size, (4, 3))
                self.assertEqual(image.getextrema()[3], (0, 0))
            self.assertIn('button_spacing=6\nframe_border_top=0', (root / 'themerc').read_text())

    def test_colored_artwork_is_rejected_before_palette_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);before = self.fixture(root, (255, 0, 0, 255))
            with self.assertRaisesRegex(ValueError, 'non-gradient overlay'):
                xfwm_palette.recolor(root, '#26282e', '#dadbe5', '#9699a3')
            self.assertEqual((root / 'close-active.xpm').read_text(), before)


if __name__ == '__main__':
    unittest.main()
