"""Regression checks for isolated Code setup using disposable profiles."""
import argparse
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import standalone_code as code
from desktop_profile import load_profile
sys.path.insert(0, str(code.ASSETS / "standalone-code"))
import dock_titles


class OfficeAssociationsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.settings = self.base / "code/User/settings.json"
        self.settings.parent.mkdir(parents=True)
        self.original = (
            b'{\r\n  // Keep the other settings and explicit associations\r\n'
            b'  "editor.fontSize": 14,\r\n'
            b'  "workbench.editorAssociations": {"*.svg": "other.viewer", "*": "cweijan.officeViewer"},\r\n}\r\n'
        )
        self.settings.write_bytes(self.original)
        self.guest_base = "/home/developer/.local/share/tablet-vscode"
        self.args = argparse.Namespace(ids=[code.OFFICE_ID], apply=True)
        self.writer = code.Writer(self.base, self.base, self.base)

    def register(self, identifier, version, editors):
        registry = code.extension_registry(self.base)
        location = f"{identifier}-{version}"
        directory = self.base / "extensions" / location
        directory.mkdir(parents=True)
        (directory / "package.json").write_text(json.dumps({"contributes": {"customEditors": editors}}), encoding="utf-8")
        registry[identifier] = {"identifier": {"id": identifier}, "version": version, "relativeLocation": location}
        (directory.parent / "extensions.json").write_text(json.dumps(list(registry.values())), encoding="utf-8")

    def register_office(self):
        self.register(code.OFFICE_ID, code.OFFICE_VERSION, [
            {"viewType": "cweijan.officeViewer", "selector": [
                {"filenamePattern": f"*.{suffix}"} for suffix in sorted(code.OFFICE_TYPES | code.OFFICE_EXTRAS)
            ]},
            {"viewType": "cweijan.imageViewer", "priority": "option", "selector": [{"filenamePattern": "*.png"}]},
        ])

    def install(self):
        return code.extensions(self.base, self.guest_base, ["proot-distro"], self.writer, self.args)

    def verify_associations(self, pdf_editor="pdf.view"):
        settings = self.settings.read_text(encoding="utf-8")
        self.assertIn("// Keep the other settings", settings)
        values = code.parse_settings(settings)[0]
        self.assertEqual(values["editor.fontSize"], 14)
        associations = values[code.EDITOR_SETTING]
        self.assertEqual({k for k, v in associations.items() if v == "cweijan.officeViewer"},
                         {"*.docx", "*.dotx", "*.xls", "*.xlsx", "*.xlsm", "*.ods", "*.pptx", "*.pptm"})
        self.assertEqual(associations["*.md"], "default")
        self.assertEqual(associations["*.csv"], "default")
        self.assertEqual(associations["*.pdf"], pdf_editor)
        self.assertEqual(associations["*.svg"], "other.viewer")
        self.assertNotIn("*.png", associations)

    def test_first_install_sets_defaults_before_code_can_load_extension(self):
        self.register(code.PDF_ID, "0.2.7", [{"viewType": "pdf.view"}])

        def install_on_cli(command, **kwargs):
            self.assertEqual(command[-2:], ["--install-extension", f"{code.OFFICE_ID}@{code.OFFICE_VERSION}"])
            self.assertIn(f"{self.guest_base}/code", command)
            self.assertIn(f"{self.guest_base}/extensions", command)
            self.verify_associations()
            self.register_office()

        with patch.object(code, "run", side_effect=install_on_cli) as cli:
            self.assertEqual(self.install()["installed"][code.OFFICE_ID], code.OFFICE_VERSION)
        cli.assert_called_once()
        self.verify_associations()

    def test_preview_and_reapply_existing_release(self):
        self.register(code.PDF_ID, "0.2.7", [{"viewType": "pdf.view"}])
        self.register_office()
        self.settings.write_bytes(code.office_settings(self.original.decode(), None, None).encode())
        original_settings = self.settings.read_bytes()
        with patch.object(code, "run") as cli:
            self.args.apply = False
            self.install()
            self.assertEqual(self.settings.read_bytes(), original_settings)
            self.args.apply = True
            self.install()
            self.verify_associations()
            self.writer.changed.clear()
            self.install()
            self.assertEqual(self.writer.changed, [])
        cli.assert_not_called()

    def test_installing_pdf_after_office_refreshes_the_fallback(self):
        self.register_office()
        self.install()
        self.verify_associations(pdf_editor="default")
        self.args.ids = [f"{code.PDF_ID}@0.2.7"]

        def install_pdf(command, **kwargs):
            self.assertEqual(command[-2:], ["--install-extension", f"{code.PDF_ID}@0.2.7"])
            self.register(code.PDF_ID, "0.2.7", [{"viewType": "pdf.view"}])

        with patch.object(code, "run", side_effect=install_pdf) as cli:
            self.install()
        cli.assert_called_once()
        self.verify_associations()

    def test_explicit_pdf_viewer_is_preserved(self):
        source = json.dumps({code.EDITOR_SETTING: {"*.pdf": "custom.viewer"}})
        pdf = {"contributes": {"customEditors": [{"viewType": "pdf.view"}]}}
        settings, _ = code.parse_settings(code.office_settings(source, None, pdf))
        self.assertEqual(settings[code.EDITOR_SETTING]["*.pdf"], "custom.viewer")

    def test_failed_install_restores_original_jsonc_bytes(self):
        with patch.object(code, "run", side_effect=RuntimeError("offline")), self.assertRaisesRegex(RuntimeError, "offline"):
            self.install()
        self.assertEqual(self.settings.read_bytes(), self.original)


class LauncherAndPreviewTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "linux", "requires native session locks")
    def test_stopped_host_close_preserves_editor_when_a_sibling_session_is_active(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            state = root / "dock/0"
            state.mkdir(parents=True)
            lease = root / "dock/1/session.lock"
            session = "a" * 32
            env = {"TABLET_VSCODE_WINDOW_TOKEN": session, "PREFIX": folder, "DISPLAY": ":9"}
            (state / "editor-token").write_text(session, encoding="ascii")
            with patch.object(dock_titles, "editor_identity", return_value=(661, 888)), \
                    patch.object(dock_titles, "editor_windows", return_value=[("0x103", "_NET_WM_PID = 661")]), \
                    patch.object(dock_titles.subprocess, "run") as send:
                with code.exclusive_lock(lease, "unexpected lock"):
                    dock_titles.close_editor(env, state, "debian", "developer", sole_session=True)
                    send.assert_not_called()
                dock_titles.close_editor(env, state, "debian", "developer", sole_session=True)
                send.assert_called_once()

    def test_android_close_resolves_only_the_verified_normal_editor_window(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)
            session = "a" * 32
            env = {"TABLET_VSCODE_WINDOW_TOKEN": session, "PREFIX": folder, "DISPLAY": ":9"}
            (state / "editor-token").write_text(session + "\n", encoding="ascii")
            class_name = 'WM_CLASS = "code", "com.microsoft.VSCode"\n'
            normal = class_name + "_NET_WM_WINDOW_TYPE = _NET_WM_WINDOW_TYPE_NORMAL\n"
            dialog = class_name + "_NET_WM_WINDOW_TYPE = _NET_WM_WINDOW_TYPE_DIALOG\n"
            windows = [
                SimpleNamespace(returncode=0, stdout="_NET_CLIENT_LIST = 0x101, 0x102, 0x103"),
                SimpleNamespace(stdout=normal + "_NET_WM_PID = 660"),
                SimpleNamespace(stdout=dialog + "_NET_WM_PID = 661"),
                SimpleNamespace(stdout=normal + "_NET_WM_PID = 661"),
            ]
            with patch.object(dock_titles, "editor_identity", return_value=(661, 888)), \
                    patch.object(dock_titles, "xprop", side_effect=windows), \
                    patch.object(dock_titles.subprocess, "run") as send:
                dock_titles.close_editor(env, state, "debian", "developer")
            send.assert_called_once()
            self.assertEqual(send.call_args.args[0][-5:], ["DISPLAY=:9", "/usr/bin/wmctrl", "-i", "-c", "0x103"])

    def test_android_close_rejects_an_older_slot_token_or_changed_editor_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)
            env = {"TABLET_VSCODE_WINDOW_TOKEN": "a" * 32, "PREFIX": folder, "DISPLAY": ":9"}
            token = state / "editor-token"
            token.write_text("b" * 32, encoding="ascii")
            with patch.object(dock_titles, "editor_windows", return_value=[("0x103", "_NET_WM_PID = 661")]) as windows, \
                    patch.object(dock_titles, "editor_identity", side_effect=[(661, 888), (661, 999)]), \
                    patch.object(dock_titles.subprocess, "run") as send:
                dock_titles.close_editor(env, state, "debian", "developer")
                windows.assert_not_called()
                token.write_text("a" * 32, encoding="ascii")
                dock_titles.close_editor(env, state, "debian", "developer")
                windows.assert_called_once()
                send.assert_not_called()

    def test_launcher_uses_direct_gui_and_rejects_xfce_display(self):
        prefix = PurePosixPath("/data/data/com.termux/files/usr")
        profile = dict(load_profile(), gpu_backend="freedreno-kgsl", code_angle_backend="gles", display=":1")
        launcher = code.render_launcher(prefix, profile, ":2")
        self.assertIn("/usr/local/bin/tablet-gpu-run /usr/share/code/code", launcher)
        self.assertIn("--no-sandbox --no-zygote", launcher)
        self.assertIn('"$HOME/.local/libexec/tablet-vscode/session.py"', launcher)
        self.assertIn('"$@" --user-data-dir', launcher)
        self.assertIn('start --user 0 -n "$activity" -d "$tag"', launcher)
        self.assertIn("x11_args=()", launcher)
        without_shm = code.render_launcher(prefix, dict(profile, x11_mitshm=False), ":2")
        self.assertIn("x11_args=(-extension MIT-SHM)", without_shm)
        self.assertNotIn("--wait", launcher)
        with self.assertRaises(ValueError):
            code.render_launcher(prefix, profile, ":01")

    @unittest.skipUnless(sys.platform == "linux", "Linux child subreaper")
    def test_session_reaps_a_child_after_abrupt_exit(self):
        helper = code.ASSETS / "standalone-code/session.py"
        command = """import os
import signal
import time

read_fd, write_fd = os.pipe()
child = os.fork()
if not child:
    os.close(read_fd)
    os.setsid()
    os.close(1)
    os.write(write_fd, b"R")
    time.sleep(5)
    os._exit(0)
os.close(write_fd)
assert os.read(read_fd, 1) == b"R"
print(child, flush=True)
os.kill(os.getpid(), signal.SIGKILL)
"""
        result = subprocess.run([sys.executable, helper, sys.executable, "-c", command],
                                capture_output=True, text=True, timeout=6)
        self.assertEqual(result.returncode, 137, result.stderr)
        self.assertFalse(Path(f"/proc/{int(result.stdout)}").exists())

    def test_dock_launcher_targets_separate_host_and_isolates_secondary_user_data(self):
        prefix = PurePosixPath("/data/data/com.termux/files/usr")
        dock = prefix.parent / "home" / code.DOCK_HOME
        profile = dict(load_profile(), display=":3")
        launcher = code.render_launcher(prefix, profile, ":2", dock)
        self.assertIn(f"android_package={code.DOCK_PACKAGE}", launcher)
        self.assertIn(f"x11_command=({dock}/x11)", launcher)
        self.assertIn('(( candidate != desktop_display ))', launcher)
        self.assertIn('code_data="$root/windows/$slot/code"', launcher)
        self.assertIn('x11_args=', launcher)
        self.assertIn('tag="vscode-$slot"', launcher)
        self.assertIn('broadcast --user 0 -a "$android_package.WINDOW_READY"', launcher)
        self.assertIn('--es editor_title "$window_title"', launcher)
        self.assertLess(launcher.index("title_args=(initial"), launcher.index('show_window "$tag" "$title" "$editor_token"'))

    @unittest.skipUnless(sys.platform == "linux", "Linux process identity and child subreaper")
    def test_session_cleans_up_a_guest_stuck_after_editor_exit(self):
        helper = code.ASSETS / "standalone-code/session.py"
        command = """
import os
from pathlib import Path
import signal
import sys
import time

editor = os.fork()
if editor == 0:
    fields = Path("/proc/self/stat").read_text().rsplit(") ", 1)[1].split()
    destination = Path(sys.argv[1])
    pending = destination.with_suffix(".tmp")
    pending.write_text(f"{os.getpid()} {fields[19]}")
    pending.replace(destination)
    os.kill(os.getpid(), signal.SIGKILL)
time.sleep(12)
"""
        with tempfile.TemporaryDirectory() as folder:
            marker = str(Path(folder) / "editor.pid")
            result = subprocess.run([sys.executable, helper, "--editor-pid-file", marker, sys.executable, "-c",
                                     command, marker], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 143, result.stderr)
        self.assertIn("editor exited and guest did not stop", result.stderr)

    def test_supervision_upgrade_preserves_the_existing_touch_menu_startup(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            launcher = home / code.DOCK_HOME / "open"
            launcher.parent.mkdir(parents=True)
            generated = code.render_launcher(PurePosixPath("/termux/usr"), load_profile(), ":2", launcher.parent)
            generated = generated.replace(code.CODE_START, code.DOCK_TOUCH_CODE_START)
            legacy = generated.replace(code.GUEST_START, code.LEGACY_GUEST_START).replace(code.EDITOR_START, "")
            legacy = legacy.replace(code.EDITOR_PID_HANDOFF, "")
            legacy = legacy.replace('    rm -f -- "$state/editor.pid" "$state/editor.pid.tmp"\n', '', 1)
            launcher.write_bytes(legacy.encode())
            writer = code.Writer(home, home, home)
            code.supervise_launcher(home, "bash", writer, False)
            self.assertEqual(launcher.read_bytes(), legacy.encode())

            with patch.object(code, "run"):
                code.supervise_launcher(home, "bash", writer, True)
                self.assertEqual(launcher.read_bytes(), generated.encode())
                self.assertEqual(next(writer.backup.rglob("open")).read_bytes(), legacy.encode())
                code.supervise_launcher(home, "bash", writer, True)
            self.assertEqual(len(writer.changed), 2)

    def test_ime_bridge_uses_a_private_socket_only_for_opted_in_dock_windows(self):
        prefix = PurePosixPath("/data/data/com.termux/files/usr")
        dock = prefix.parent / "home" / code.DOCK_HOME
        profile = dict(load_profile(), display=":3")
        self.assertIn("if [[ 0 == 1 ]]; then", code.render_launcher(prefix, profile, ":2", dock))
        self.assertIn("if [[ 0 == 1 ]]; then", code.render_launcher(prefix, profile, ":2", ime_bridge=True))
        launcher = code.render_launcher(prefix, profile, ":2", dock, ime_bridge=True)
        self.assertIn('ime_dir=$(mktemp -d "$TMPDIR/vscode-ime.XXXXXX")', launcher)
        self.assertIn('guest_ime_socket="/tmp/${ime_dir##*/}/commit"', launcher)
        self.assertIn('"$editor_token" "$guest_ime_socket"', launcher)
        self.assertIn('export GTK_IM_MODULE=tablet-vscode', launcher)

    def test_touch_menu_installs_into_the_existing_launchers(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            launcher = home / code.DOCK_HOME / "open"
            launcher.parent.mkdir(parents=True)
            base = home / code.PROFILE_DIR
            generated = code.render_launcher(PurePosixPath("/termux/usr"), load_profile(), ":2", launcher.parent)
            legacy = generated.replace(code.CODE_START, code.LEGACY_CODE_START).encode()
            launcher.write_bytes(legacy)
            writer = code.Writer(home, home, home)

            code.scm_touch_menu(home, base, "bash", writer, False)
            self.assertFalse(base.exists())
            self.assertEqual(launcher.read_bytes(), legacy)

            with patch.object(code, "run"):
                code.scm_touch_menu(home, base, "bash", writer, True)
                self.assertEqual(launcher.read_bytes(), generated.encode())
                self.assertEqual(len(writer.changed), 3)
                self.assertEqual(next(writer.backup.rglob("open")).read_bytes(), legacy)
                code.scm_touch_menu(home, base, "bash", writer, True)
                self.assertEqual(len(writer.changed), 3)

            widget = home / code.WIDGET_ENTRY
            widget.parent.mkdir(parents=True)
            generated = code.render_launcher(PurePosixPath("/termux/usr"), load_profile(), ":2")
            widget.write_bytes(generated.replace(code.CODE_START, code.LEGACY_CODE_START).encode())
            with patch.object(code, "run"):
                code.scm_touch_menu(home, base, "bash", writer, True, "widget")
            self.assertEqual(widget.read_bytes(), generated.encode())
            self.assertEqual(len(writer.changed), 4)

    def test_dock_title_keeps_the_file_and_project_without_duplicate_branding(self):
        self.assertEqual(dock_titles.parse_title('_NET_WM_NAME = "Welcome - sample-project - Visual Studio Code"'),
                         "Welcome - sample-project")
        self.assertEqual(dock_titles.parse_title(r'_NET_WM_NAME = "file \"x\" - \344\270\255 - Visual Studio Code"'),
                         'file "x" - 中')
        self.assertEqual(dock_titles.parse_title('_NET_WM_NAME = "Visual Studio Code"'), "Visual Studio Code")
        self.assertIsNone(dock_titles.parse_title("_NET_WM_NAME:  not found."))

    def test_dock_initial_title_distinguishes_a_fresh_window_from_a_restore(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(dock_titles, "find_editor", return_value=(None, None)):
            state = Path(directory)
            (state / "window-title").write_text("Previous project\n", encoding="utf-8")
            self.assertEqual(dock_titles.initial_title({}, state, None, True), "Visual Studio Code")
            self.assertEqual(dock_titles.initial_title({}, state, None, False), "Previous project")
            self.assertEqual(dock_titles.initial_title({}, state, "/home/developer/skills", True), "skills")

    def test_preview_changes_only_http_default(self):
        source = ("[Default Applications]\r\napplication/pdf=pdf.desktop;\r\n"
                  "x-scheme-handler/http=linux.desktop;\r\nx-scheme-handler/https=linux.desktop;\r\n"
                  "\r\n[Added Associations]\r\nx-scheme-handler/http=linux.desktop;\r\n")
        updated = code.update_http_default(source, code.CHROME_ENTRY)
        self.assertEqual(updated, source.replace("\r\n", "\n").replace(
            "x-scheme-handler/http=linux.desktop;", f"x-scheme-handler/http={code.CHROME_ENTRY};", 1))
        self.assertEqual(code.update_http_default(updated, code.CHROME_ENTRY), updated)

    def test_failed_chrome_setup_rolls_back_all_files(self):
        for has_existing_files in (False, True):
            with self.subTest(has_existing_files=has_existing_files), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                prefix, guest_root = root / "native", root / "guest"
                guest_base = f"/home/developer/{code.PROFILE_DIR}"
                base = guest_root / guest_base.lstrip("/")
                for path in (prefix / "bin/am", guest_root / "usr/bin/gio", guest_root / "usr/bin/xdg-mime",
                             guest_root / "usr/bin/python3", guest_root / "usr/share/applications/linux.desktop"):
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"fixture")
                old_files = {}
                if has_existing_files:
                    old_files = {base / "bin/open-android-chrome-preview": b"old opener\r\n",
                                 base / "data/applications" / code.CHROME_ENTRY: b"old desktop entry\r\n",
                                 base / "config/mimeapps.list": b"[Default Applications]\r\nx-scheme-handler/http=linux.desktop;\r\n"}
                    for path, data in old_files.items():
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(data)
                writer = code.Writer(root / "home", prefix, guest_root)
                with patch.object(code, "run", return_value=SimpleNamespace(stdout="linux.desktop\n")):
                    with self.assertRaisesRegex(ValueError, "did not become the HTTP handler"):
                        code.chrome(prefix, guest_root, base, guest_base, [], writer, SimpleNamespace(apply=True))
                self.assertEqual({p: p.read_bytes() for p in base.rglob("*") if p.is_file()}, old_files)
                self.assertEqual(base.exists(), has_existing_files)


if __name__ == "__main__":
    unittest.main()
