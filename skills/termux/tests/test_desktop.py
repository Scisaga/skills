"""Desktop rendering/ownership tests use temporary roots, never a connected device."""
import argparse
import copy
import configparser
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from unittest.mock import Mock, patch
from xml.etree import ElementTree as ET

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
sys.path.insert(0, str(SKILL / "assets/desktop/native"))
import desktop_profile as profiles
import desktop_setup as setup
import session_manager as sessions
from jsonc_settings import merge as merge_jsonc, parse as parse_jsonc


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="termux-desktop-test-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.native, self.prefix, self.root = [self.base / x for x in ("native", "prefix", "guest")]
        for p in (self.native, self.prefix, self.root): p.mkdir()
        self.p = profiles.load_profile()
        self.writer = setup.Writer(self.native, self.prefix, self.root)

    def render(self, profile=None):
        setup.configure_guest(self.root, PurePosixPath("/data/data/com.termux/files/home"), profile or self.p, self.writer)

    def test_native_termux_platforms_and_host_guard(self):
        getprop_exists = True

        class DevicePath(PurePosixPath):
            def exists(self):
                return str(self) == "/system/bin/getprop" and getprop_exists

            @classmethod
            def home(cls):
                return cls("/data/data/com.termux/files/home")

        with patch.object(setup, "Path", DevicePath), patch.dict(setup.os.environ, {"PREFIX": "/data/data/com.termux/files/usr"}):
            for platform in ("linux", "android"):
                with self.subTest(platform=platform), patch.object(setup.sys, "platform", platform):
                    prefix, _ = setup.require_termux()
                    self.assertEqual(str(prefix), "/data/data/com.termux/files/usr")
            with patch.object(setup.sys, "platform", "win32"), self.assertRaises(RuntimeError):
                setup.require_termux()
            with patch.object(setup.sys, "platform", "android"), patch.dict(setup.os.environ, {"PREFIX": "/usr"}), self.assertRaises(RuntimeError):
                setup.require_termux()
            getprop_exists = False
            with patch.object(setup.sys, "platform", "android"), self.assertRaises(RuntimeError):
                setup.require_termux()

    def test_oci_install_accepts_help_written_to_stderr(self):
        self.root.rmdir()

        def command(args, **kwargs):
            if "--help" in args:
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="install -n, --name [NAME]")
            if "--name" in args:
                raise RuntimeError("rootfs-install-requested")
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

        args = argparse.Namespace(apply=True, adopt_existing=False)
        with patch.object(setup, "require_termux", return_value=(self.prefix, self.native)), patch.object(setup, "guest_root", return_value=self.root), patch.object(setup, "run", side_effect=command), self.assertRaisesRegex(RuntimeError, "rootfs-install-requested"):
            setup.install(self.p, args)

    def test_render_is_repeatable_and_preserves_binary_assets(self):
        self.render()
        self.writer.changed.clear()
        self.render()
        self.assertEqual(self.writer.changed, [])
        for src in (profiles.ASSETS / "theme/xfwm4").glob("*.png"):
            dst = self.root / "home/developer/.themes/Tablet-Touch/xfwm4" / src.name
            self.assertEqual(src.read_bytes(), dst.read_bytes())
        binary = b'\x89PNG\r\n\x1a\nprivate-cookie\r\n'
        dst = self.native / "binary"
        self.writer.put(dst, binary, 0o600)
        self.assertEqual(dst.read_bytes(), binary)

    def test_profile_changes_user_display_and_only_selected_apps(self):
        p = dict(self.p, user="coder", container="workstation", display=":3", scale=1, applications=["chromium"], software_rendering=False)
        self.render(p)
        home = self.root / "home/coder"
        session = (self.root / "usr/local/bin/tablet-desktop-session").read_text(encoding="utf-8")
        self.assertIn("DISPLAY=:3", session)
        self.assertIn("runtime-coder", session)
        self.assertIn("GDK_SCALE=1", session)
        self.assertNotIn("GDK_GL=disable", session)
        self.assertTrue((home / "Desktop/Chromium.desktop").is_file())
        self.assertFalse((home / "Desktop/VSCode.desktop").exists())
        self.assertFalse((home / ".config/autostart/tablet-code.desktop").exists())
        for file in (self.root / "usr/local/bin").iterdir():
            text = file.read_text(encoding="utf-8")
            if text.startswith("#!/usr/bin/python3"): compile(text, str(file), "exec")

    def test_hardware_backend_keeps_gtk_compatibility_and_real_software_fallback(self):
        p = dict(self.p, gpu_backend="virgl-android")
        self.render(p)
        directory = self.root / "usr/local/bin"
        for name in ("code-tablet", "chromium-tablet"):
            text = (directory / name).read_text(encoding="utf-8")
            self.assertIn("exec /usr/local/bin/tablet-gpu-run /usr/bin/", text)
            self.assertNotIn("--disable-gpu", text)
            fallback = (directory / (name + "-software")).read_text(encoding="utf-8")
            self.assertIn("--disable-gpu", fallback)
            self.assertNotIn("tablet-gpu-run", fallback)
        self.assertIn("GDK_GL=disable", (directory / "tablet-desktop-session").read_text(encoding="utf-8"))
        self.assertIn("virglrenderer-android", setup.native_packages(p))
        self.assertNotIn("virglrenderer-android", setup.native_packages(self.p))
        with self.assertRaises(ValueError): profiles.validate_profile(dict(p, gpu_backend="guess"))

    def test_layout_has_four_touch_entries_battery_end_and_autohide(self):
        self.render()
        home = self.root / "home/developer"
        paths = ["Desktop/TouchMode.desktop", ".local/share/applications/tablet-touch-toggle.desktop",
                 ".config/xfce4/panel/launcher-22/tablet-touch.desktop", ".config/xfce4/panel/launcher-25/tablet-touch.desktop"]
        self.assertTrue(all("X-Tablet-Touch-Control=true" in (home / p).read_text(encoding="utf-8") for p in paths))
        xml = ET.parse(home / ".config/xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml")
        panel = xml.find("property[@name='panels']/property[@name='panel-2']")
        self.assertEqual(panel.find("property[@name='autohide-behavior']").get("value"), "2")
        self.assertEqual(panel.find("property[@name='output-name']").get("value"), "builtin")
        self.assertTrue((home / ".config/xfce4/panel/genmon-23.rc").is_file())
        self.assertTrue((home / ".config/xfce4/panel/launcher-24/tablet-end.desktop").is_file())
        for relative, hidden in ((".local/share/applications/tablet-desktop-end.desktop", True),
                                 (".local/share/applications/xfce4-session-logout.desktop", False),
                                 ("Desktop/EndDesktop.desktop", False),
                                 (".config/xfce4/panel/launcher-24/tablet-end.desktop", False)):
            entry = configparser.ConfigParser(interpolation=None)
            entry.read(home / relative, encoding="utf-8")
            self.assertEqual(entry['Desktop Entry'].getboolean('NoDisplay', fallback=False), hidden)
            self.assertEqual(entry['Desktop Entry']['Exec'], '/usr/local/bin/tablet-desktop-end')

    def test_code_gles_is_opt_in_and_preserves_the_software_fallback(self):
        self.render()
        directory = self.root / 'usr/local/bin'
        self.assertNotIn('--use-angle', (directory / 'code-tablet').read_text(encoding='utf-8'))
        profile = profiles.validate_profile(dict(self.p, gpu_backend='freedreno-kgsl', code_angle_backend='gles'))
        self.render(profile)
        command = (directory / 'code-tablet').read_text(encoding='utf-8')
        self.assertIn('tablet-gpu-run /usr/bin/code', command)
        self.assertIn('--use-gl=angle --use-angle=gles', command)
        self.assertNotIn('--disable-gpu', command)
        fallback = (directory / 'code-tablet-software').read_text(encoding='utf-8')
        self.assertIn('--disable-gpu', fallback)
        self.assertNotIn('--use-angle', fallback)
        self.assertNotIn('tablet-gpu-run', fallback)
        self.writer.changed.clear()
        self.render(profile)
        self.assertEqual(self.writer.changed, [])
        for value in (True, 'vulkan', 'gles; command'):
            with self.assertRaises(ValueError): profiles.validate_profile(dict(profile, code_angle_backend=value))
        with self.assertRaises(ValueError): profiles.validate_profile(dict(profile, gpu_backend='software'))

    def test_whole_desktop_compositor_excludes_manual_dock_redirector(self):
        home = self.root / 'home/developer'
        self.render(dict(self.p, window_compositing=True, window_vblank_mode='xpresent', window_shadows=False))
        tree = ET.parse(home / '.config/xfce4/xfconf/xfce-perchannel-xml/xfwm4.xml')
        general = tree.find("property[@name='general']")
        values = {node.get('name'): node.get('value') for node in general.findall('property')}
        self.assertEqual(values['use_compositing'], 'true')
        self.assertEqual(values['vblank_mode'], 'xpresent')
        self.assertEqual(values['show_frame_shadow'], 'false')
        self.assertIn('Hidden=true', (home / '.config/autostart/tablet-panel-edge.desktop').read_text())
        self.render()
        self.assertIn('Hidden=false', (home / '.config/autostart/tablet-panel-edge.desktop').read_text())
        for invalid in ({'window_compositing': 1}, {'window_vblank_mode': 'unverified'}):
            with self.assertRaises(ValueError):
                profiles.validate_profile(dict(self.p, **invalid))

    def test_touch_adaptation_uses_actual_session_slots_and_preserves_other_clients(self):
        default = self.root / 'etc/xdg/xfce4/xfconf/xfce-perchannel-xml/xfce4-session.xml'
        default.parent.mkdir(parents=True)
        default.write_text('<channel name="xfce4-session"><property name="sessions"><property name="Failsafe">'
                           '<property name="Client7_Command" type="array"><value type="string" value="xfdesktop"/></property>'
                           '<property name="Client9_Command" type="array"><value type="string" value="xfce4-panel"/><value type="string" value="--disable-wm-check"/></property>'
                           '<property name="Client3_Command" type="array"><value type="string" value="custom-application"/></property>'
                           '<property name="Client12_Command" type="array"><value type="string" value="Thunar"/><value type="string" value="--daemon"/></property>'
                           '</property></property></channel>')
        path = self.root / 'home/developer/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-session.xml'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('<channel name="xfce4-session"><property name="sessions"><property name="Failsafe">'
                        '<property name="Client7_Command" type="empty"/>'
                        '<property name="Client9_Command" type="empty"/>'
                        '</property><property name="FailsafeWayland">'
                        '<property name="Client7_Command" type="array"><value type="string" value="custom-wayland-shell"/></property>'
                        '</property></property></channel>')
        self.render(dict(self.p, touch_long_press=True, touch_long_press_ms=500))
        tree = ET.parse(path)
        node = tree.find("property[@name='sessions']/property[@name='Failsafe']")
        commands = {n.get('name'): [v.get('value') for v in n.findall('value')] for n in node.findall('property')}
        self.assertEqual(commands['Client7_Command'], ['/usr/local/bin/tablet-xfce-pointer','desktop'])
        self.assertEqual(commands['Client9_Command'], ['/usr/local/bin/tablet-xfce-pointer','panel','--disable-wm-check'])
        self.assertNotIn('Client3_Command',commands)
        self.assertEqual(commands['Client12_Command'], ['/usr/local/bin/tablet-thunar-core', '--daemon'])
        self.assertEqual(tree.find("property[@name='sessions']/property[@name='FailsafeWayland']/property[@name='Client7_Command']/value").get('value'), 'custom-wayland-shell')
        self.assertTrue((self.root/'usr/local/share/tablet-desktop/tablet-touch-longpress.c').is_file())
        self.assertFalse((self.root/'usr/local/bin/tablet-touch-longpress.c').exists())
        pointer = (self.root/'usr/local/bin/tablet-xfce-pointer').read_text(encoding='utf-8')
        self.assertIn('export GDK_CORE_DEVICE_EVENTS=1', pointer)
        self.assertNotIn('LD_PRELOAD', pointer)
        for name in ('code-tablet', 'chromium-tablet', 'libreoffice-tablet', 'vlc-tablet'):
            self.assertIn('unset GDK_CORE_DEVICE_EVENTS', (self.root/'usr/local/bin'/name).read_text(encoding='utf-8'))
        setup.configure_xfce_pointer(self.root,'developer',False,self.writer)
        tree = ET.parse(path)
        self.assertEqual(tree.find("property[@name='sessions']/property[@name='Failsafe']/property[@name='Client7_Command']/value").get('value'),'xfdesktop')
        self.assertEqual(tree.find("property[@name='sessions']/property[@name='Failsafe']/property[@name='Client12_Command']/value").get('value'),'Thunar')

    def test_unknown_shell_startup_is_not_overwritten_to_enable_touch(self):
        with self.assertRaisesRegex(RuntimeError,'Custom Xfce startup'):
            self.render(dict(self.p,touch_long_press=True))

    def test_x11_shared_memory_choice_keeps_transport_local(self):
        for enabled in (False, True):
            manager = Mock()
            manager.core_alive.return_value = False
            manager.data = {'phase': 'stopped', 'processes': {}}
            manager.previous, manager.high, manager.last_notice = {}, {}, {}
            manager.helpers = []
            manager.x11_ready.side_effect = [False, True, True]
            manager.spawn.return_value = Mock(pid=987654)
            with patch.dict(sessions.CONFIG, {'x11_mitshm': enabled}), \
                 patch.object(sessions, 'run', return_value=Mock(returncode=0, stdout='module-native-protocol-tcp')), \
                 patch.object(sessions, 'snapshot', return_value={}), \
                 patch.object(sessions, 'read_process', return_value={'pid': 987654, 'kind': 'proot'}):
                sessions.Manager.start(manager)
            command = manager.spawn.call_args_list[0].args[0]
            self.assertEqual(command[2:4], ['-nolisten', 'tcp'])
            self.assertEqual('-extension' in command, not enabled)
            if not enabled:
                self.assertEqual(command[-2:], ['-extension', 'MIT-SHM'])

    def test_native_browser_keeps_existing_entry_and_guest_fallback(self):
        p = dict(self.p, browser_backend="termux-zink", gpu_backend="virgl-android")
        self.render(p)
        directory = self.root / "usr/local/bin"
        self.assertIn('exec /usr/local/bin/tablet-native-browser "$@"', (directory / 'chromium-tablet').read_text(encoding='utf-8'))
        self.assertIn('tablet-gpu-run /usr/bin/chromium', (directory / 'chromium-tablet-guest').read_text(encoding='utf-8'))
        self.assertTrue((self.root / 'home/developer/.local/share/applications/chromium-tablet-guest.desktop').is_file())
        self.assertIn('chromium', setup.native_packages(p))
        self.writer.changed.clear()
        self.render(p)
        self.assertEqual(self.writer.changed, [])
        with self.assertRaises(ValueError): profiles.validate_profile(dict(p, native_browser_icd='../driver.json'))
        self.assertEqual(profiles.validate_profile(p)['native_browser_present_mode'], 'default')
        self.assertEqual(profiles.validate_profile(dict(p, native_browser_present_mode='mailbox'))['native_browser_present_mode'], 'mailbox')
        for value in (True, 'immediate', 'mailbox; command'):
            with self.assertRaises(ValueError): profiles.validate_profile(dict(p, native_browser_present_mode=value))

    def test_native_office_and_video_redirect_mime_entries_without_losing_types(self):
        system = self.root / 'usr/share/applications'
        system.mkdir(parents=True)
        for name in ('code', 'vlc', 'libreoffice-writer', 'libreoffice-calc', 'libreoffice-impress'):
            (system / (name + '.desktop')).write_text('[Desktop Entry]\nType=Application\nName=Application\nExec=/usr/bin/original %U\nTryExec=/usr/bin/original\nMimeType=application/test;\n')
        p = dict(self.p, office_backend='native-gtk3', media_backend='termux-va', gpu_backend='freedreno-kgsl')
        setup.configure_guest(self.root, self.native, p, self.writer)
        guest = self.root / 'home/developer/.local/share/applications'
        self.assertIn('libreoffice-tablet --writer %U', (guest / 'libreoffice-writer.desktop').read_text())
        self.assertIn('MimeType=application/test;', (guest / 'vlc.desktop').read_text())
        native = (self.native / '.local/share/applications/vlc.desktop').read_text()
        self.assertIn('tablet-session-open-vlc %U', native)
        self.assertNotIn('TryExec=', native)
        directory = self.root / 'usr/local/bin'
        self.assertIn('tablet-video-run', (directory / 'vlc-tablet').read_text())
        self.assertIn('/usr/bin/vlc', (directory / 'vlc-tablet-guest').read_text())
        self.assertIn('/usr/bin/libreoffice', (directory / 'libreoffice-tablet-guest').read_text())
        self.assertNotIn('virglrenderer-android', setup.native_packages(p))
        self.assertIn('libreoffice', setup.native_packages(p))
        with self.assertRaises(ValueError): profiles.validate_profile(dict(p, gpu_backend='software'))

    def test_code_and_browser_configuration_preserve_unrelated_settings(self):
        home = self.root / "home/developer"
        config = home / ".config/Code/User/settings.json"
        config.parent.mkdir(parents=True)
        config.write_text(json.dumps({"files.autoSave": "afterDelay", "editor.fontSize": 9}))
        self.render()
        value = json.loads(config.read_text(encoding="utf-8"))
        self.assertEqual(value["files.autoSave"], "afterDelay")
        self.assertEqual(value["editor.scrollbar.verticalScrollbarSize"], 6)
        self.assertEqual(value["editor.scrollbar.horizontalScrollbarSize"], 6)
        helper = (home / ".local/share/xfce4/helpers/custom-WebBrowser.desktop").read_text(encoding="utf-8")
        self.assertIn("/usr/local/bin/chromium-tablet", helper)
        self.assertIn("WebBrowser=custom-WebBrowser", (home / ".config/xfce4/helpers.rc").read_text(encoding="utf-8"))
        autostart = home / ".config/autostart/tablet-code.desktop"
        self.assertFalse(autostart.exists())
        self.render(dict(self.p, code_autostart=True))
        self.assertIn("Exec=/usr/local/bin/code-tablet", autostart.read_text(encoding="utf-8"))
        self.render()
        self.assertIn("Hidden=true", autostart.read_text(encoding="utf-8"))

    def test_jsonc_comments_unrelated_values_and_urls_are_preserved(self):
        path = self.root / "home/developer/.config/Code/User/settings.json"
        path.parent.mkdir(parents=True)
        path.write_text('{// user notes\n"files.autoSave":"off", // retain this\n"test.url":"https://example.test/a/*b*/",\n"editor.fontSize":12,\n}')
        self.render()
        text = path.read_text(encoding="utf-8")
        self.assertIn('// user notes', text)
        self.assertIn('// retain this', text)
        self.assertIn('https://example.test/a/*b*/', text)
        value, _ = parse_jsonc(text)
        self.assertEqual(value['files.autoSave'], 'off')
        self.assertEqual(value['editor.fontSize'], 14)

    def test_jsonc_nested_settings_and_unchanged_second_merge(self):
        source = '{/* notes */"nested":{"array":[1,2,],"value":"quoted \\\" text"}, "old":true // tail\n}'
        rendered = merge_jsonc(source, {'old': False, 'new': [3, 4]})
        self.assertIn('/* notes */', rendered)
        self.assertIn('// tail', rendered)
        self.assertEqual(parse_jsonc(rendered)[0]['nested']['array'], [1, 2])
        self.assertEqual(merge_jsonc(rendered, {'old': False, 'new': [3, 4]}), rendered)

    def test_backup_and_path_escape(self):
        p = self.native / "settings"
        p.write_text("old")
        self.writer.put(p, "new")
        self.assertIn(b"old", [x.read_bytes() for x in self.writer.backup.rglob("*") if x.is_file()])
        with self.assertRaisesRegex(ValueError, "escapes"): self.writer.put(self.base / "outside", "bad")
        self.assertFalse((self.base / "outside").exists())

    def test_context_preserves_notes_and_updates_without_duplicates(self):
        from managed_context import LEGACY_SSH_RULE
        old_native = '<!-- BEGIN android-termux-ssh managed context -->\n' + LEGACY_SSH_RULE + '\n<!-- END android-termux-ssh managed context -->\n'
        (self.native / "AGENTS.md").write_text("User instructions stay here\n" + old_native, encoding="utf-8")
        setup.context(self.native, self.root, self.p, self.writer)
        setup.context(self.native, self.root, self.p, self.writer)
        text = (self.native / "AGENTS.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("User instructions stay here"))
        self.assertEqual(text.count("<!-- BEGIN termux desktop -->"), 1)
        self.assertNotIn(LEGACY_SSH_RULE, text)
        self.assertIn('<!-- BEGIN android-termux-ssh managed context -->', text)

    def test_invalid_profile_is_rejected(self):
        for fields in ({"user": "../../escape"}, {"scale": True}, {"applications": [{}]}, {"display": ":1;kill"}, {"touch_mode": "reset"}, {"media_hardware_policy": "unverified"}):
            with self.subTest(fields=fields), self.assertRaises(ValueError): profiles.validate_profile(dict(self.p, **fields))

    def test_install_without_apply_does_not_run_any_command(self):
        args = argparse.Namespace(apply=False, adopt_existing=False)
        with patch.object(setup, "require_termux", return_value=(self.prefix, self.native)), patch.object(setup, "run") as run:
            with self.assertRaisesRegex(RuntimeError, "--apply"): setup.install(self.p, args)
        run.assert_not_called()

    def test_active_session_blocks_install_before_package_or_file_changes(self):
        (self.prefix / "bin").mkdir()
        (self.prefix / "bin/desktop").write_text("managed client")
        state = subprocess.CompletedProcess([], 0, json.dumps({"phase": "running"}), "")
        with patch.object(setup, "require_termux", return_value=(self.prefix, self.native)), patch.object(setup, "run", return_value=state) as run:
            with self.assertRaisesRegex(RuntimeError, "Desktop is active"): setup.install(self.p, argparse.Namespace(apply=True, adopt_existing=False))
        self.assertEqual(run.call_count, 1)
        self.assertFalse((self.native / ".config/tablet-desktop/config.json").exists())

    def test_unrelated_container_core_is_not_adopted(self):
        manager = object.__new__(sessions.Manager)
        manager.data = {"roots": [], "core": None, "phase": "stopped", "session": "old", "desired": False}
        uid = sessions.UID
        root = dict(pid=111, start=123, uid=uid, exe="proot", kind="proot", tracer=0)
        core = dict(pid=222, start=124, uid=uid, exe="xfce4-session", kind="xfce-session", tracer=111)
        before = copy.deepcopy(manager.data)
        with patch.object(sessions, "PREFIX", self.prefix), patch.object(sessions, "snapshot", return_value={111: root, 222: core}):
            manager.adopt_existing()
        self.assertEqual(manager.data, before)

    def test_unknown_existing_desktop_status_blocks_install(self):
        (self.prefix / "bin").mkdir()
        (self.prefix / "bin/desktop").write_text("managed client")
        state = subprocess.CompletedProcess([], 1, "", "unavailable")
        with patch.object(setup, "require_termux", return_value=(self.prefix, self.native)), patch.object(setup, "run", return_value=state) as run:
            with self.assertRaisesRegex(RuntimeError, "Cannot establish"): setup.install(self.p, argparse.Namespace(apply=True, adopt_existing=False))
        self.assertEqual(run.call_count, 1)

    def test_unmanaged_running_container_blocks_runtime_changes(self):
        root = profiles.guest_root(self.prefix, self.p['container'])
        root.mkdir(parents=True)
        with patch.object(setup, 'require_termux', return_value=(self.prefix, self.native)), patch.object(setup, 'active_container_roots', return_value=[1234]), patch.object(setup, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'active PRoot sessions'): setup.install(self.p, argparse.Namespace(apply=True, adopt_existing=True))
        run.assert_not_called()

    def test_legacy_desktop_context_is_replaced_and_native_ssh_notes_survive(self):
        path = self.native / "AGENTS.md"
        path.write_text("SSH instructions\n<!-- BEGIN tablet-desktop setup -->\nold desktop\n<!-- END tablet-desktop setup -->\nUser notes\n")
        setup.context(self.native, self.root, self.p, self.writer)
        text = path.read_text(encoding="utf-8")
        self.assertIn("SSH instructions", text)
        self.assertIn("User notes", text)
        self.assertNotIn("old desktop", text)
        self.assertEqual(text.count("<!-- BEGIN termux desktop -->"), 1)


if __name__ == "__main__": unittest.main()
