"""Check native process evidence and the Debian Code update workflow."""
from contextlib import ExitStack
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import standalone_code as code
import vscode_runtime as runtime

spec = importlib.util.spec_from_file_location("vscode_update", code.ASSETS / "guest/vscode-package-update.py")
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


class CodeRepositoryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)

    def test_accepts_signed_deb822_and_legacy_sources(self):
        signed_by = "/usr/share/keyrings/microsoft.gpg"
        sources = self.directory / "vscode.sources"
        sources.write_text(f"Types: deb\nURIs: {updater.REPOSITORY}\nSuites: stable\nComponents: main\n"
                           f"Architectures: arm64\nSigned-By: {signed_by}\n", encoding="ascii")
        self.assertEqual(updater.configured_source(self.directory), (sources, Path(signed_by)))
        sources.unlink()
        legacy = self.directory / "vscode.list"
        legacy.write_text(f"deb [arch=arm64 signed-by={signed_by}] {updater.REPOSITORY} stable main # Code\n",
                          encoding="ascii")
        self.assertEqual(updater.configured_source(self.directory), (legacy, Path(signed_by)))
        for options in (f"trusted=yes signed-by={signed_by}", f"other-signed-by={signed_by}"):
            with self.subTest(options=options):
                legacy.write_text(f"deb [{options}] {updater.REPOSITORY} stable main\n", encoding="ascii")
                with self.assertRaisesRegex(ValueError, "signature options"):
                    updater.configured_source(self.directory)

    def test_empty_keyring_changes_only_after_full_fingerprint_matches(self):
        key = self.directory / "microsoft.gpg"
        key.touch()

        def fake_commands(args, **_):
            if "--show-keys" in args:
                return SimpleNamespace(stdout="pub:::::::::\nfpr:::::::::" + fingerprint + ":\n")
            if "--dearmor" in args:
                Path(args[args.index("--output") + 1]).write_bytes(b"verified binary fixture")
            return SimpleNamespace(stdout="")

        fingerprint = "0" * 24 + updater.KEY_FINGERPRINT[-16:]
        with patch.object(updater, "DEFAULT_KEY", key), patch.object(updater.shutil, "which", return_value="available"), \
                patch.object(updater, "run", side_effect=fake_commands) as commands:
            with self.assertRaisesRegex(ValueError, "fingerprint mismatch"):
                updater.repair_empty_key(key)
            self.assertEqual(key.read_bytes(), b"")
            self.assertFalse(any("--dearmor" in call.args[0] for call in commands.call_args_list))
            fingerprint = updater.KEY_FINGERPRINT
            self.assertTrue(updater.repair_empty_key(key))
            self.assertEqual(key.read_bytes(), b"verified binary fixture")
            commands.reset_mock()
            self.assertFalse(updater.repair_empty_key(key))
            commands.assert_not_called()


class CodePackageTests(unittest.TestCase):
    old_version = "1.0.0-1"
    target = "1.1.0-2"

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        base = Path(directory.name)
        self.installed = self.old_version
        self.hold = ""
        self.update_error = None
        self.simulation = f"Inst code [{self.old_version}] ({self.target} [arm64])\nConf code ({self.target} [arm64])"
        self.key = base / "microsoft.gpg"
        self.key.write_bytes(b"keyring fixture")
        patches = ExitStack()
        self.addCleanup(patches.close)
        patches.enter_context(patch.object(updater, "configured_source", return_value=(base / "vscode.sources", self.key)))
        self.commands = patches.enter_context(patch.object(updater, "run", side_effect=self.fake_run))

    def fake_run(self, args, **_):
        if args[0] == "dpkg-query":
            output = f"installed\t{self.installed}\tarm64"
        elif args[0] == "apt-cache":
            output = f"  Candidate: {self.target}\n     500 {updater.REPOSITORY} stable/main arm64 Packages"
        elif args[0] == "apt-mark":
            output = self.hold
        elif "-s" in args:
            output = self.simulation
        else:
            if args[-1] == "update" and self.update_error:
                raise RuntimeError(self.update_error)
            if "--no-download" in args:
                self.installed = args[-1].split("=")[1]
            output = ""
        return SimpleNamespace(stdout=output, returncode=0)

    def test_preview_and_prepare_then_apply_exact_version(self):
        result = updater.update_package("preview", "", "stable")
        self.assertEqual(result["candidate"], self.target)
        self.assertEqual([call.args[0][0] for call in self.commands.call_args_list], ["dpkg-query", "apt-cache"])
        self.commands.reset_mock()
        self.assertEqual(updater.update_package("prepare", "", "stable")["status"], "prepared")
        apt_calls = [call.args[0] for call in self.commands.call_args_list if call.args[0][0] == "apt-get"]
        self.assertIn("APT::Get::List-Cleanup=false", apt_calls[0])
        self.assertIn("APT::Update::Error-Mode=any", apt_calls[0])
        self.assertIn("--download-only", apt_calls[-1])
        self.assertEqual(self.installed, self.old_version)
        self.commands.reset_mock()
        result = updater.update_package("apply", self.target, "stable")
        self.assertEqual(result["actual"], self.target)
        installs = [call.args[0] for call in self.commands.call_args_list if "--no-download" in call.args[0]]
        self.assertEqual(len(installs), 1)
        self.assertEqual(installs[0][-1], f"code={self.target}")

    def test_prepare_stops_on_signature_failure_before_any_install(self):
        self.update_error = "Missing key EB3E94ADBE1229CF"
        with self.assertRaisesRegex(RuntimeError, "Missing key"):
            updater.update_package("prepare", "", "stable")
        self.assertFalse(any("install" in call.args[0] for call in self.commands.call_args_list))

    def test_apply_stops_if_another_package_would_change(self):
        for operation in ("Inst", "Conf", "Remv"):
            with self.subTest(operation=operation), patch.object(self, "simulation", self.simulation + f"\n{operation} other"):
                self.commands.reset_mock()
                with self.assertRaisesRegex(ValueError, f"{operation} other"):
                    updater.update_package("apply", self.target, "stable")
                self.assertFalse(any("--no-download" in call.args[0] for call in self.commands.call_args_list))

    def test_respects_profile_pin_and_architecture_qualified_hold(self):
        with self.assertRaisesRegex(ValueError, "pins Code"):
            updater.update_package("apply", self.target, "1.0.0")
        self.hold = "code:arm64\n"
        with self.assertRaisesRegex(ValueError, "on hold"):
            updater.update_package("apply", self.target, "stable")
        self.assertFalse(any("install" in call.args[0] for call in self.commands.call_args_list))


@unittest.skipUnless(sys.platform.startswith("linux"), "requires native /proc and flock")
class NativeCodeTests(unittest.TestCase):
    def test_reads_session_and_owned_process_without_dumping_arguments_or_environment(self):
        with tempfile.TemporaryDirectory() as path:
            state = Path(path) / code.STATE_DIR
            self.assertEqual(runtime.inspect_runtime(state, [])["sessions"], [])
            self.assertFalse(state.exists())
            slot = state / "dock/1"
            slot.mkdir(parents=True)
            with subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", "private-argument"],
                                  env={**os.environ, "DISPLAY": ":3", "TABLET_VSCODE_DOCK_TAG": "vscode-1",
                                       "PRIVATE_TOKEN": "private-environment"}) as process:
                try:
                    start = runtime.selected_process(process.pid, os.getuid())["start_ticks"]
                    (slot / "editor.pid").write_text(f"{process.pid} {start}\n", encoding="ascii")
                    with code.exclusive_lock(slot / "session.lock", "unexpected lock"):
                        report = runtime.inspect_runtime(state, [process.pid])
                    self.assertEqual(report["sessions"][0]["lease"], "held")
                    self.assertTrue(report["sessions"][0]["editor_identity_matches"])
                    self.assertEqual(report["processes"][0]["TABLET_VSCODE_DOCK_TAG"], "vscode-1")
                    self.assertNotIn("private-", str(report))
                finally:
                    process.terminate()
                    process.wait(timeout=5)
            ended = runtime.inspect_runtime(state, [process.pid])
            self.assertEqual(ended["processes"][0]["status"], "unavailable")
            self.assertIsNone(ended["sessions"][0]["editor_identity_matches"])

    def test_update_refuses_active_widget_and_dock_before_launching_debian(self):
        with tempfile.TemporaryDirectory() as path:
            home = Path(path)
            proot = home / "bin/proot-distro"
            proot.parent.mkdir()
            proot.touch()
            args = SimpleNamespace(apply=True, prepare=False, version="1.1.0-2")
            profile = {"container": "debian", "code_version": "stable"}
            for filename in ("session.lock", "dock-settings.lock"):
                with self.subTest(filename=filename), patch.object(code, "run") as launch:
                    with code.exclusive_lock(home / code.STATE_DIR / filename, "unexpected lock"):
                        with self.assertRaisesRegex(ValueError, "Close the standalone Code windows"):
                            code.update_code_package(home, home, profile, args)
                    launch.assert_not_called()
