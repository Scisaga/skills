"""Read-only Android inventory behavior; uses no real ADB transport."""
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import launcher_plan


class LauncherTests(unittest.TestCase):
    def test_optional_absent_plugins_do_not_abort_folder_inventory(self):
        installed = {"com.termux", "com.termux.x11", "com.scisaga.tabletdesktop"}
        def fake(command, **_):
            package = command[-1]
            if "list" in command:
                text = "package:" + package + "\n" if package in installed else ""
            elif package == "com.scisaga.tabletdesktop":
                text = "2 activities found:\ncom.scisaga.tabletdesktop/.ManagerActivity\ncom.scisaga.tabletdesktop/.DesktopEntry\n"
            else:
                text = package + "/.MainActivity\n"
            return subprocess.CompletedProcess(command, 0, text, "")
        with patch.object(launcher_plan.subprocess, "run", side_effect=fake): rows = launcher_plan.inventory("fake-adb", "simulated")
        by_package = {r['package']: r for r in rows}
        self.assertFalse(by_package['com.termux.boot']['installed'])
        self.assertEqual(len(by_package['com.scisaga.tabletdesktop']['launcher_entries']), 2)
        self.assertEqual(sum(r['installed'] for r in rows), 3)

    def test_transport_failure_is_reported_instead_of_claiming_empty_inventory(self):
        failure = subprocess.CompletedProcess([], 1, '', 'device offline')
        with patch.object(launcher_plan.subprocess, "run", return_value=failure):
            with self.assertRaisesRegex(RuntimeError, 'device offline'): launcher_plan.inventory('fake-adb', 'simulated')


if __name__ == "__main__": unittest.main()
