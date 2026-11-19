"""Regression checks for isolated Code setup using disposable profiles."""
import argparse
import json
from pathlib import Path, PurePosixPath
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import standalone_code as code
from desktop_profile import load_profile


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

    def verify_associations(self):
        settings = self.settings.read_text(encoding="utf-8")
        self.assertIn("// Keep the other settings", settings)
        values = code.parse_settings(settings)[0]
        self.assertEqual(values["editor.fontSize"], 14)
        associations = values[code.EDITOR_SETTING]
        self.assertEqual({k for k, v in associations.items() if v == "cweijan.officeViewer"},
                         {"*.docx", "*.dotx", "*.xls", "*.xlsx", "*.xlsm", "*.ods", "*.pptx", "*.pptm"})
        self.assertEqual(associations["*.md"], "default")
        self.assertEqual(associations["*.csv"], "default")
        self.assertEqual(associations["*.pdf"], "pdf.view")
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
        with patch.object(code, "run") as cli:
            self.args.apply = False
            self.install()
            self.assertEqual(self.settings.read_bytes(), self.original)
            self.args.apply = True
            self.install()
            self.verify_associations()
            self.writer.changed.clear()
            self.install()
            self.assertEqual(self.writer.changed, [])
        cli.assert_not_called()

    def test_failed_install_restores_original_jsonc_bytes(self):
        with patch.object(code, "run", side_effect=RuntimeError("offline")), self.assertRaisesRegex(RuntimeError, "offline"):
            self.install()
        self.assertEqual(self.settings.read_bytes(), self.original)


class LauncherAndPreviewTests(unittest.TestCase):
    def test_launcher_uses_direct_gui_and_rejects_xfce_display(self):
        prefix = PurePosixPath("/data/data/com.termux/files/usr")
        profile = dict(load_profile(), gpu_backend="freedreno-kgsl", code_angle_backend="gles", display=":1")
        launcher = code.render_launcher(prefix, profile, ":2")
        self.assertIn("/usr/local/bin/tablet-gpu-run /usr/share/code/code", launcher)
        self.assertIn('"$@" --user-data-dir', launcher)
        self.assertIn('start --user 0 -n "$activity" -d "$tag"', launcher)
        self.assertIn("x11_args=()", launcher)
        without_shm = code.render_launcher(prefix, dict(profile, x11_mitshm=False), ":2")
        self.assertIn("x11_args=(-extension MIT-SHM)", without_shm)
        self.assertNotIn("--wait", launcher)
        with self.assertRaises(ValueError):
            code.render_launcher(prefix, profile, ":01")

    def test_preview_changes_only_http_default(self):
        source = ("[Default Applications]\r\napplication/pdf=pdf.desktop;\r\n"
                  "x-scheme-handler/http=linux.desktop;\r\nx-scheme-handler/https=linux.desktop;\r\n"
                  "\r\n[Added Associations]\r\nx-scheme-handler/http=linux.desktop;\r\n")
        updated = code.update_http_default(source, code.CHROME_ENTRY)
        self.assertEqual(updated, source.replace("\r\n", "\n").replace(
            "x-scheme-handler/http=linux.desktop;", f"x-scheme-handler/http={code.CHROME_ENTRY};", 1))
        self.assertEqual(code.update_http_default(updated, code.CHROME_ENTRY), updated)


if __name__ == "__main__":
    unittest.main()
