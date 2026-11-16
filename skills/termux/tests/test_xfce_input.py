import argparse
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import xfce_input as settings


class InputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.values = {('xsettings', '/Net/DoubleClickTime'): '400',
                       ('xsettings', '/Net/DoubleClickDistance'): '5',
                       ('xsettings', '/Gtk/FontName'): 'Personal font 15',
                       ('xfce4-keyboard-shortcuts', '/commands/custom/<Super>Left'): 'old-command',
                       ('xfce4-keyboard-shortcuts', '/commands/custom/<Primary>space'): 'input-method'}
        self.original = self.values.copy()
        self.args = argparse.Namespace(windows_shortcuts=True, double_click_time=650,
                                       double_click_distance=24, state=self.home / 'backup.json', apply=True)
        self.addCleanup(patch.stopall)
        patch.object(Path, 'home', return_value=self.home).start()
        patch.object(settings.shutil, 'which', return_value='/usr/bin/gcc').start()
        patch.object(settings, 'start_menu', return_value=None).start()
        patch.object(settings, 'compile_menu', return_value=b'compiled menu observer').start()
        patch.object(settings, 'value', side_effect=lambda c, p: self.values.get((c, p))).start()
        def put(item, target):
            key = (item['channel'], item['property'])
            if target is None:
                self.values.pop(key, None)
            else:
                self.values[key] = target
        patch.object(settings, 'put', side_effect=put).start()

    def test_apply_and_restore_preserve_unrelated_settings_and_existing_helper(self):
        helper = self.home / '.local/bin/tablet-window-action'
        helper.parent.mkdir(parents=True)
        helper.write_bytes(b'previous helper')
        settings.apply_settings(self.args)
        self.assertEqual(self.values['xsettings', '/Gtk/FontName'], 'Personal font 15')
        self.assertEqual(self.values['xfce4-keyboard-shortcuts', '/commands/custom/<Primary>space'], 'input-method')
        self.assertTrue(self.values['xfce4-keyboard-shortcuts', '/commands/custom/<Super>Left'].endswith(' left'))
        self.assertNotIn(('xfce4-keyboard-shortcuts', '/xfwm4/custom/<Super>Left'), self.values)
        settings.restore(self.args)
        self.assertEqual(self.values, self.original)
        self.assertEqual(helper.read_bytes(), b'previous helper')
        settings.restore(self.args)

    def test_restore_of_new_helper_is_repeatable_and_backup_is_not_overwritten(self):
        settings.apply_settings(self.args)
        backup = self.args.state.read_bytes()
        with self.assertRaisesRegex(ValueError, 'State already exists'):
            settings.apply_settings(self.args)
        self.assertEqual(self.args.state.read_bytes(), backup)
        settings.restore(self.args)
        settings.restore(self.args)
        self.assertEqual(self.values, self.original)
        self.assertFalse((self.home / '.local/bin/tablet-window-action').exists())

    def test_changed_setting_stops_restore_before_any_write(self):
        settings.apply_settings(self.args)
        self.values['xsettings', '/Net/DoubleClickTime'] = '777'
        before = self.values.copy()
        with self.assertRaisesRegex(ValueError, 'changed after apply'):
            settings.restore(self.args)
        self.assertEqual(self.values, before)
        self.assertEqual(json.loads(self.args.state.read_text())['status'], 'passed')

    def test_preview_does_not_write_settings_helper_or_backup(self):
        self.args.apply = False
        self.assertEqual(settings.apply_settings(self.args)['status'], 'planned')
        self.assertEqual(self.values, self.original)
        self.assertFalse(self.args.state.exists())
        self.assertFalse((self.home / '.local').exists())

    def test_windows_down_restores_before_minimizing_and_up_is_idempotent(self):
        self.assertEqual(settings.window_decision('down', True), 'restore')
        self.assertEqual(settings.window_decision('down', False), 'minimize')
        for maximized in (False, True):
            self.assertEqual(settings.window_decision('up', maximized), 'maximize')

    def test_reused_pid_is_never_signalled(self):
        identity = {'pid': 12345, 'start_ticks': '100', 'session': '1', 'uid': 1000,
                    'argv': ['/private/menu-key', '/private/action']}
        with patch.object(settings, 'process_identity', return_value=dict(identity, start_ticks='200')), patch.object(settings.os, 'kill') as kill:
            with self.assertRaisesRegex(ValueError, 'PID identity changed'):
                settings.stop_menu(identity)
            kill.assert_not_called()

    def test_restore_uses_the_current_display_record_after_autostart(self):
        with patch.dict(settings.os.environ, {'DISPLAY': ':7.0'}):
            settings.apply_settings(self.args)
            _, record = settings.menu_paths()
            record.parent.mkdir(parents=True, exist_ok=True)
            identity = {'pid': 54321, 'start_ticks': '200', 'session': '2', 'uid': 1000,
                        'display': ':7.0', 'argv': [str(self.home / '.local/lib/tablet-desktop/menu-key'),
                                                   str(self.home / '.local/bin/tablet-window-action')]}
            record.write_text(json.dumps(identity))
            with patch.object(settings, 'stop_menu') as stop:
                settings.restore(self.args)
            stop.assert_called_once_with(identity)

    def test_changed_display_record_stops_restore_before_mutation(self):
        settings.apply_settings(self.args)
        _, record = settings.menu_paths()
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(json.dumps({'display': 'another display', 'argv': ['/another/program']}))
        before = self.values.copy()
        with patch.object(settings, 'stop_menu') as stop:
            with self.assertRaisesRegex(ValueError, 'another display or command'):
                settings.restore(self.args)
        stop.assert_not_called()
        self.assertEqual(self.values, before)

    def test_default_screen_alias_uses_the_same_menu_record(self):
        with patch.dict(settings.os.environ, {'DISPLAY': ':7'}):
            short = settings.menu_paths()
        with patch.dict(settings.os.environ, {'DISPLAY': ':7.0'}):
            explicit = settings.menu_paths()
        self.assertEqual(short, explicit)
        self.assertNotEqual(settings.display_identity(':7.1'), settings.display_identity(':7'))


if __name__ == '__main__':
    unittest.main()
