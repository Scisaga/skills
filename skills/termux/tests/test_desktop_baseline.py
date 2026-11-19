"""Exercise the recovery checks using private local fixture directories."""
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import desktop_baseline


def snapshot():
    return {
        "schema": 1,
        "architecture": "arm64",
        "native_profile": {"schema": 1},
        "packages": {},
        "xfce": {"xfwm4": {"/general/use_compositing": "true", "/general/vblank_mode": "xpresent"}},
        "code": {"terminal.integrated.gpuAcceleration": "off"},
        "mime": {},
        "files": {},
    }


def write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def run_cli(args):
    output = io.StringIO()
    with redirect_stdout(output):
        rc = desktop_baseline.main(args)
    return rc, json.loads(output.getvalue())


class DesktopBaselineTests(unittest.TestCase):
    def test_approved_code_change_does_not_hide_xfce_regression(self):
        with tempfile.TemporaryDirectory() as folder:
            before = Path(folder) / "before.json"
            after = Path(folder) / "after.json"
            value = snapshot()
            write_json(before, value)
            value["code"]["terminal.integrated.gpuAcceleration"] = "auto"
            value["xfce"]["xfwm4"]["/general/use_compositing"] = "false"
            write_json(after, value)
            args = ["compare", "--baseline", str(before), "--current", str(after),
                    "--allow-change", "/code/terminal.integrated.gpuAcceleration"]
            rc, report = run_cli(args)
            self.assertEqual((rc, report["unexpected"]), (1, ["/xfce/xfwm4/~1general~1use_compositing"]))
            self.assertEqual(report["baseline_sha256"], hashlib.sha256(before.read_bytes()).hexdigest())

            value["xfce"]["xfwm4"]["/general/use_compositing"] = "true"
            write_json(after, value)
            self.assertEqual(run_cli(args)[0], 0)

    def test_reinstall_defaults_and_theme_payload_are_verified(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = snapshot()
            name = "theme/custom/gtk-3.0/close@2.svg"
            data = b'<svg xmlns="http://www.w3.org/2000/svg"/>'
            manifest["files"][name] = {"size": len(data), "mode": 0o644, "sha256": hashlib.sha256(data).hexdigest()}
            asset = root / "files" / name
            asset.parent.mkdir(parents=True)
            asset.write_bytes(data)
            write_json(root / "manifest.json", manifest)
            write_json(root / "profile.json", {"schema": 1})

            rc, report = run_cli(["verify", folder])
            self.assertEqual(rc, 1)
            self.assertEqual(report["mismatched_profile"], ["window_compositing", "window_vblank_mode"])
            self.assertEqual(report["mismatched_files"], [])

            write_json(root / "profile.json", {"schema": 1, "window_compositing": True, "window_vblank_mode": "xpresent"})
            self.assertEqual(run_cli(["verify", folder])[0], 0)
            asset.write_bytes(b"0" * len(data))
            rc, report = run_cli(["verify", folder])
            self.assertEqual((rc, report["mismatched_files"]), (1, [name]))

    def test_paths_outside_bundle_are_invalid(self):
        for name in ("../notes", "theme/custom/../../notes", "C:/notes", "theme\\asset"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                desktop_baseline.asset_path(name)


if __name__ == "__main__":
    unittest.main()
