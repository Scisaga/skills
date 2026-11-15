"""Run real shell entrypoints against an isolated fake ADB, never a device."""
import os
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SKILL=Path(__file__).resolve().parents[1]
GIT_BASH=Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Git/bin/bash.exe'
BASH=str(GIT_BASH) if GIT_BASH.is_file() else shutil.which('bash')
if BASH and 'system32' in BASH.lower():BASH=None


@unittest.skipUnless(BASH,'Requires a POSIX shell or Git Bash (WSL launcher is not a shell installation)')
class ShellGateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='termux-gates-')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.adb=self.root/'fake-adb';self.log=self.root/'calls.log'

    def fake(self, cap):
        text='''#!/usr/bin/env bash
printf '%s\\n' "$*" >> LOG_PATH
case "$*" in
 'get-state') echo device ;;
 'shell getprop ro.product.manufacturer') echo Test ;;
 'shell getprop ro.product.model') echo Simulated ;;
 'shell getprop ro.build.version.release') echo 16 ;;
 'shell getprop ro.build.version.sdk') echo 36 ;;
 'shell getprop ro.product.cpu.abi') echo arm64-v8a ;;
 'shell pm path '*) echo package:/simulated.apk ;;
 'shell dumpsys package '*) echo versionName=simulated ;;
 'shell pm list packages -U '*) echo "package:${@: -1} uid:12345" ;;
 'shell dumpsys power') printf '%s\\n' 'mWakefulness=Asleep' "PARTIAL_WAKE_LOCK 'termux:service-wakelock' (uid=12345)" ;;
 'shell device_config get activity_manager max_phantom_processes') echo 128 ;;
 'shell dumpsys activity settings') echo max_phantom_processes=CAP_VALUE ;;
 'shell settings get global settings_enable_monitor_phantom_procs') echo null ;;
 'shell getprop persist.sys.fflag.override.settings_enable_monitor_phantom_procs') echo true ;;
 'shell ss -ltn') echo 'LISTEN 0 128 0.0.0.0:8022' ;;
 'shell cmd deviceidle whitelist') printf 'user,%s,12345\\n' com.termux com.termux.api com.termux.boot com.termux.x11 ;;
esac
'''
        self.adb.write_text(text.replace('LOG_PATH',shlex.quote(self.log.as_posix())).replace('CAP_VALUE',str(cap)),encoding='utf-8')
        self.adb.chmod(0o755)

    def call(self, name, *args):
        return subprocess.run([BASH,str(SKILL/'scripts'/name),'--adb',str(self.adb),*args],capture_output=True,text=True,encoding='utf-8',timeout=45)

    def test_doctor_fails_when_stored_128_is_still_effective_32(self):
        self.fake(32)
        result=self.call('host-doctor.sh','--min-cap','128')
        self.assertEqual(result.returncode,1,result.stderr)
        self.assertIn('stored cap 128 differs from live cap 32',result.stdout)
        self.assertIn('FAIL',result.stdout)

    def test_doctor_passes_actual_required_cap(self):
        self.fake(128)
        result=self.call('host-doctor.sh','--min-cap','128')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_invalid_cap_cannot_silently_disable_the_gate(self):
        self.fake(32)
        result=self.call('host-doctor.sh','--min-cap','0')
        self.assertEqual(result.returncode,2)
        self.assertFalse(self.log.exists())

    def test_battery_does_not_grant_camera_or_location(self):
        self.fake(128)
        result=self.call('host-android-permissions.sh','--api-battery','--apply')
        self.assertEqual(result.returncode,0,result.stderr)
        calls=self.log.read_text()
        self.assertNotIn('pm grant',calls)
        self.assertNotIn('CAMERA',calls)
        self.assertNotIn('ACCESS_FINE_LOCATION',calls)

    def test_camera_is_independent_from_location(self):
        self.fake(128)
        result=self.call('host-android-permissions.sh','--camera','--apply')
        self.assertEqual(result.returncode,0,result.stderr)
        calls=self.log.read_text()
        self.assertIn('android.permission.CAMERA',calls)
        self.assertNotIn('ACCESS_FINE_LOCATION',calls)


if __name__=='__main__':unittest.main()
