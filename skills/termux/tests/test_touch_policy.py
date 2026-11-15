"""Compile/run gesture regression checks in Debian/Linux, without a display server."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


class TouchPolicyTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('gcc') and Path('/usr/include/X11/extensions/XInput2.h').exists(),
                         'Run this integration check in the Debian guest with the touch build dependencies')
    def test_actual_c_recognizer_keeps_clicks_drag_and_other_apps(self):
        with tempfile.TemporaryDirectory(prefix='tablet-touch-test-') as folder:
            binary=Path(folder)/'test-touch-policy'
            source=Path(__file__).with_suffix('.c')
            subprocess.run(['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror',str(source),'-o',str(binary),
                            '-lXi','-lXtst','-lX11','-lm'],check=True,capture_output=True,text=True)
            result=subprocess.run([str(binary)],check=True,capture_output=True,text=True)
            self.assertIn('PASS:',result.stdout)


if __name__=='__main__':unittest.main()
