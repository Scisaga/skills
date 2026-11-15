"""Native browser URL boundaries and process ownership; no device or browser required."""
import sys
import os
import runpy
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'assets/desktop/native'))
from browser_resource import NativeBrowser, native_members, normalize_targets


class NativeBrowserTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.prefix, self.home, self.guest = [self.base / p for p in ('prefix', 'home', 'guest')]

    def targets(self, values):
        return normalize_targets(values, self.prefix, self.home, self.guest)

    def test_urls_remain_single_literal_arguments(self):
        urls = ['https://example.test/?q=$(id);a,b#section', 'chrome://gpu', 'about:blank']
        self.assertEqual(self.targets(urls), urls)

    def test_flags_commands_control_characters_and_large_requests_are_rejected(self):
        for values in (['--disable-web-security'], ['javascript:alert(1)'], ['x\nhttps://x.test'],
                       ['file://remote/path'], ['relative.html'], ['https://'], [4], 'https://x.test',
                       ['https://x.test/' + 'a' * 3000], ['https://x.test'] * 9):
            with self.subTest(values=values), self.assertRaises(ValueError): self.targets(values)

    def test_guest_files_shared_tmp_and_fragments_map_to_native_paths(self):
        self.assertEqual(self.targets(['file:///home/developer/report%20a.html#page']),
                         [(self.guest / 'home/developer/report a.html').resolve().as_uri() + '#page'])
        self.assertEqual(self.targets(['/tmp/test.html']), [(self.prefix / 'tmp/test.html').resolve().as_uri()])

    def test_only_descendants_of_verified_native_roots_join_cleanup(self):
        roots = {10: {'pid': 10, 'kind': 'native-browser'}, 20: {'pid': 20, 'kind': 'proot'}}
        processes = {10: {'ppid': 1, 'tracer': 0}, 11: {'ppid': 10, 'tracer': 0},
                     12: {'ppid': 11, 'tracer': 0}, 30: {'ppid': 1, 'tracer': 0},
                     31: {'ppid': 20, 'tracer': 20}}
        self.assertEqual(native_members(roots, processes), {10: 10, 11: 10, 12: 10})
        self.assertEqual(native_members({}, processes), {})

    def test_stale_session_or_closing_desktop_cannot_launch_browser(self):
        owner = Mock()
        owner.data = {'session': 'current', 'phase': 'closing', 'roots': []}
        owner.core_alive.return_value = True
        browser = NativeBrowser(owner, {'browser_backend': 'termux-zink'}, self.prefix, self.home,
                                self.guest, self.base, Mock())
        for request in ({'session': 'old'}, {'session': 'current'}):
            with self.assertRaises(RuntimeError): browser.open(request)
        owner.spawn.assert_not_called()

    def test_return_to_existing_browser_does_not_spawn_another_window(self):
        executable = self.prefix / 'lib/chromium/chrome'
        executable.parent.mkdir(parents=True)
        executable.touch()
        icd = self.prefix / 'share/vulkan/icd.d/driver.json'
        icd.parent.mkdir(parents=True)
        icd.touch()
        owner = Mock()
        owner.data = {'session': 'current', 'phase': 'running', 'roots': [{'kind': 'native-browser', 'pid': 42}]}
        owner.core_alive.return_value = owner.root_valid.return_value = True
        owner.status.return_value = {'ok': True}
        browser = NativeBrowser(owner, {'browser_backend': 'termux-zink', 'native_browser_icd': 'driver.json', 'display': ':3'},
                                self.prefix, self.home, self.guest, self.base, Mock())
        result = browser.open({'session': 'current', 'urls': []})
        self.assertEqual(result['native_browser_pid'], 42)
        self.assertEqual(result['display'], ':3')
        owner.spawn.assert_not_called()

    def launch_environment(self, config, environment=None):
        (self.prefix / 'tmp').mkdir(parents=True, exist_ok=True)
        module = types.ModuleType('desktop_config')
        module.PREFIX, module.HOME, module.GUEST = self.prefix, self.home, self.guest
        module.CONFIG = dict(scale=2, native_browser_icd='driver.json', **config)
        module.DISPLAY = ':3'
        captured = {}
        def capture(executable, command):
            captured.update(executable=executable, command=command, env=dict(os.environ))
        with patch.dict(sys.modules, {'desktop_config': module}), \
             patch.dict(os.environ, environment or {}, clear=True), \
             patch.object(sys, 'argv', ['browser_exec.py']), patch.object(os, 'execv', side_effect=capture):
            runpy.run_path(str(Path(__file__).resolve().parents[1] / 'assets/desktop/native/browser_exec.py'))
        return captured

    def test_mailbox_is_browser_scoped_and_keeps_hardware_rendering(self):
        launched = self.launch_environment({'native_browser_present_mode': 'mailbox'}, {'GDK_GL': 'disable', 'LIBGL_ALWAYS_SOFTWARE': '1'})
        self.assertEqual(launched['env']['MESA_VK_WSI_PRESENT_MODE'], 'mailbox')
        self.assertEqual(launched['env']['GALLIUM_DRIVER'], 'zink')
        self.assertNotIn('LIBGL_ALWAYS_SOFTWARE', launched['env'])
        self.assertIn('--use-angle=gles', launched['command'])
        self.assertNotIn('--disable-gpu', launched['command'])
        self.assertEqual(launched['command'][-1], '--restore-last-session')

    def test_existing_profiles_keep_their_present_environment(self):
        self.assertNotIn('MESA_VK_WSI_PRESENT_MODE', self.launch_environment({})['env'])
        self.assertEqual(self.launch_environment({}, {'MESA_VK_WSI_PRESENT_MODE': 'fifo'})['env']['MESA_VK_WSI_PRESENT_MODE'], 'fifo')
        with self.assertRaises(SystemExit): self.launch_environment({'native_browser_present_mode': 'mailbox; command'})
