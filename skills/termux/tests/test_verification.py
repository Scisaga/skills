"""Regression evidence must reject stale configuration and misleading GPU/sleep passes."""
import contextlib
import copy
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from device_transport import Device
import desktop_verify as verify
import gpu_probe


def gpu_record(rate=100):
    sample = {'renderer': 'ANGLE hardware GPU', 'pixel': [128, 128, 217, 255], 'error': 0,
              'contextLost': False, 'visibility': 'visible', 'frames': rate * 10, 'seconds': 10.,
              'fps': rate, 'warmup_seconds': 4, 'canvas': [1280, 720], 'viewport': [1600, 940],
              'dpr': 2, 'workload_sha256': 'a' * 64}
    return {'samples': [copy.deepcopy(sample) for _ in range(3)]}


class VerificationTests(unittest.TestCase):
    def test_stored_cap_does_not_mask_actual_32_limit(self):
        result = verify.policy_values('128', 'max_phantom_processes=32', 'null', 'true', 'none', 128, 'enabled')
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['effective_cap'], 32)
        self.assertEqual(len(result['errors']), 2)

    def test_missing_monitor_is_unknown_and_cannot_pass_explicit_requirement(self):
        result = verify.policy_values('128', 'max_phantom_processes=128', 'null', '', 'none', 128, 'enabled')
        self.assertEqual(result['monitor'], 'unknown')
        self.assertEqual(result['status'], 'failed')

    def test_conflicting_monitor_declarations_need_diagnosis(self):
        result = verify.policy_values('128','max_phantom_processes=128','false','true','none',128,'enabled')
        self.assertEqual(result['monitor'],'conflict')
        self.assertEqual(result['status'],'failed')

    def test_sleep_preview_is_not_a_passing_acceptance_gate(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);connection=root/'device.json';connection.write_text(json.dumps({'ssh_target':'user@device.example'}))
            with patch.object(Device,'adb',side_effect=AssertionError('Preview must not contact ADB')), \
                 patch.object(Device,'ssh_script',side_effect=AssertionError('Preview must not contact SSH')), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(verify.main(['sleep','--connection',str(connection),'--state',str(root/'out.json')]),4)
            self.assertEqual(json.loads((root/'out.json').read_text())['status'],'skipped')

    def test_boot_wait_retains_baseline_and_does_not_probe_locked_data(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);connection=root/'device.json';connection.write_text(json.dumps({'ssh_target':'user@device.example'}))
            state=root/'boot.json';state.write_text(json.dumps({'boot_id_before':'old','connection_sha256':Device.read(connection).digest}))
            def shell(*command,**kwargs):return 'new' if command[0]=='cat' else ''
            with patch.object(Device,'shell',side_effect=shell), patch.object(verify,'native_probe',side_effect=AssertionError('First unlock required')),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(verify.main(['boot-check','--connection',str(connection),'--state',str(state)]),3)
            self.assertEqual(json.loads(state.read_text())['boot_id_before'],'old')

    def test_new_boot_waits_for_unlock_and_does_not_invent_success(self):
        result = verify.boot_result('old', 'new', '', {}, True)
        self.assertEqual(result['status'], 'pending')
        self.assertEqual(verify.boot_result('same', 'same', 'true', {}, True)['status'], 'failed')

    def test_manual_app_start_invalidates_autostart_evidence(self):
        self.assertEqual(verify.boot_result('old', 'new', 'true', {}, False)['status'], 'failed')

    def test_idle_controller_and_matching_boot_prove_only_background_recovery(self):
        probe = {'boot_id': 'new', 'desktop': {'phase': 'stopped', 'registered_processes': 0}, 'boot_helper': {'boot_id': 'old'}}
        result = verify.boot_result('old', 'new', 'true', probe, True)
        self.assertEqual(result['status'], 'passed')
        self.assertFalse(result['this_boot_helper_record'])
        probe['desktop']['phase'] = 'running'
        self.assertEqual(verify.boot_result('old', 'new', 'true', probe, True)['status'], 'failed')

    def test_lit_screen_restarted_desktop_and_stale_battery_cannot_pass_sleep(self):
        baseline = {'boot_id': 'one', 'profile_sha256': 'same', 'desktop': {'session': 'one'}}
        probe = {'boot_id': 'one', 'profile_sha256': 'same', 'desktop': {'session': 'two', 'phase': 'running', 'core_alive': True}, 'battery_age_seconds': 999}
        errors = verify.validate_sleep_sample(baseline, probe, {'wakefulness': 'Awake', 'partial_wake_lock_active': True}, ['new freeze'], [], {'status': 'passed'}, True)
        self.assertEqual(len(errors), 4)

    def test_gpu_rejects_false_success_cases(self):
        changes = [{'renderer': 'ANGLE SwiftShader'}, {'pixel': [0, 0, 217, 255]}, {'contextLost': True},
                   {'visibility': 'hidden'}, {'seconds': 0}, {'frames': float('nan')},
                   {'fps': float('inf')}, {'warmup_seconds': 0}, {'workload_sha256': ''}]
        for change in changes:
            with self.subTest(change=change):
                record = gpu_record()
                record['samples'][0].update(change)
                with self.assertRaises(ValueError):
                    verify.gpu_summary(record)

    def test_gpu_workload_mismatch_and_actual_regression_fail(self):
        record = gpu_record()
        record['samples'][0]['canvas'] = [640, 360]
        with self.assertRaisesRegex(ValueError, 'changed'):
            verify.gpu_summary(record)
        with self.assertRaisesRegex(ValueError, 'below'):
            verify.gpu_summary(gpu_record(17), min_fps=60)

    def test_gpu_report_returns_failure_and_hashes_actual_inputs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder);candidate = root / 'candidate.json';baseline = root / 'baseline.json';state = root / 'result.json'
            candidate.write_text(json.dumps(gpu_record(17)))
            baseline.write_text(json.dumps(gpu_record(100)))
            args = ['gpu-report', '--candidate', str(candidate), '--baseline', str(baseline), '--min-speedup', '2', '--state', str(state)]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(verify.main(args), 1)
            result = json.loads(state.read_text())
            self.assertEqual(result['status'], 'failed')
            self.assertEqual(len(result['input_summary']['candidate_sha256']), 64)

    def test_transport_uses_stdin_without_interpreting_host_shell_characters(self):
        device = Device({'ssh_target': 'user@device.example', 'identity': '/private/key with spaces'})
        with patch('device_transport.subprocess.run', return_value=subprocess.CompletedProcess([], 0, 'ok', '')) as run:
            self.assertEqual(device.ssh_script('printf "%s" "$(literal-test)"\r\n'), 'ok')
        args, kwargs = run.call_args
        self.assertIn('/private/key with spaces', args[0])
        self.assertIn('StrictHostKeyChecking=yes', args[0])
        self.assertNotIn('shell', kwargs)
        self.assertEqual(kwargs['input'], b'printf "%s" "$(literal-test)"\n')

    def test_real_subprocess_keeps_utf8_and_lf_on_windows(self):
        value='first\n\u4e2d\u6587 $(literal-test)\nlast'
        result=Device.run([sys.executable,'-c','import sys;sys.stdout.buffer.write(sys.stdin.buffer.read())'],value)
        self.assertEqual(result,value)
        self.assertNotIn('\r',result)

    def test_transport_timeout_is_a_recordable_verification_failure(self):
        with patch('device_transport.subprocess.run',side_effect=subprocess.TimeoutExpired('ssh',2)):
            with self.assertRaisesRegex(RuntimeError,'timed out'):
                Device.run(['ssh'],timeout=2)

    def test_unknown_profile_is_refused_before_browser_mutation(self):
        self.assertTrue(gpu_probe.owned_profile(['--user-data-dir=/owned/probe'], '/owned/probe'))
        self.assertFalse(gpu_probe.owned_profile(['--user-data-dir=/daily/profile'], '/owned/probe'))
        with self.assertRaises(ValueError):
            Device({'ssh_target': '-oProxyCommand=unexpected'})

    def test_final_check_never_starts_adb(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder);connection = root / 'device.json';connection.write_text(json.dumps({'ssh_target': 'user@device.example'}))
            with patch.object(Device, 'adb', side_effect=AssertionError('ADB must remain stopped')), \
                 patch.object(verify, 'native_probe', return_value={'desktop': {'phase': 'running', 'core_alive': True}}), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(verify.main(['final-check', '--connection', str(connection), '--state', str(root/'out.json')]), 0)


if __name__ == '__main__':
    unittest.main()
