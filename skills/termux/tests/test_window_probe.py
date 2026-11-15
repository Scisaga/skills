"""Diagnostic invariants and recovery: no connected device or display required."""
import contextlib
import base64
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import window_probe as probe
import desktop_verify
from device_transport import Device


def snapshot():
    return {'helper': {'selection_owner': '0x100', 'verified': True, 'redirected_frames': [123]},
            'compositor': {'selection_owner': None, 'configured': False}}


class WindowProbeTests(unittest.TestCase):
    def test_normal_noncomposited_state_is_not_a_gpu_failure(self):
        self.assertEqual(probe.diagnosis(snapshot()), 'non_composited')

    def test_compositor_and_helper_process_presence_alone_are_not_a_conflict(self):
        s = snapshot()
        s['compositor'].update(selection_owner='0x200', configured=True)
        s['helper']['redirected_frames'] = []
        self.assertEqual(probe.diagnosis(s), 'composited')
        s['helper']['redirected_frames'] = [123]
        self.assertEqual(probe.diagnosis(s), 'possible_redirect_conflict')

    def test_stale_state_without_selection_does_not_prove_an_active_redirect(self):
        s = snapshot()
        s['helper'].update(selection_owner=None, verified=False)
        s['compositor'].update(selection_owner='0x200', configured=True)
        self.assertEqual(probe.diagnosis(s), 'composited')

    def test_unknown_owner_and_config_only_success_require_diagnosis(self):
        s = snapshot()
        s['helper']['verified'] = False
        self.assertEqual(probe.diagnosis(s), 'unverified_helper_state')
        s = snapshot()
        s['compositor']['configured'] = True
        self.assertEqual(probe.diagnosis(s), 'compositor_state_mismatch')

    def test_recycled_pid_or_changed_tracer_cannot_be_signalled(self):
        first = {'pid': 123, 'uid': 99, 'start_ticks': 100, 'tracer': 1, 'executable': '/guest/python'}
        for delta in ({'start_ticks': 200}, {'tracer': 2}, {'uid': 100}, {'executable': '/other'}):
            with self.subTest(delta=delta), self.assertRaises(ValueError):
                probe.require_same_identity(first, dict(first, **delta))

    def test_stale_file_wrong_uid_command_or_cohort_is_not_a_verified_helper(self):
        helper = {'uid': 99, 'start_ticks': 12, 'tracer': 10,
                  'cmd': ['/usr/bin/python3', '/usr/local/bin/tablet-panel-edge']}
        with patch.object(probe, 'process_birth', return_value=100):
            self.assertTrue(probe.verified_helper(helper, {'tracer': 10}, uid=99, state_mtime=101))
            for delta in ({'uid': 100}, {'cmd': ['/usr/bin/other']}, {'tracer': 0}, {'tracer': 11}):
                self.assertFalse(probe.verified_helper(dict(helper, **delta), {'tracer': 10}, uid=99, state_mtime=101))
            self.assertFalse(probe.verified_helper(helper, {'tracer': 10}, uid=99, state_mtime=90))

    def test_restore_failure_still_cleans_owned_windows_and_retains_both_errors(self):
        calls = []
        def action():
            calls.append('action')
            raise ValueError('trajectory')
        def restore():
            calls.append('restore')
            raise RuntimeError('recovery')
        errors = probe.run_with_recovery(action, restore, lambda: calls.append('cleanup'))
        self.assertEqual(calls, ['action', 'restore', 'cleanup'])
        self.assertEqual(len(errors), 2)
        self.assertIn('trajectory', errors[0])
        self.assertIn('recovery', errors[1])

    def test_interrupt_restores_before_cleanup(self):
        calls = []
        def action():
            raise KeyboardInterrupt()
        errors = probe.run_with_recovery(action, lambda: calls.append('restore'), lambda: calls.append('cleanup'))
        self.assertEqual(calls, ['restore', 'cleanup'])
        self.assertIn('KeyboardInterrupt', errors[0])

    def test_diagnostic_connections_close_even_when_xlib_close_is_interrupted(self):
        audit = object.__new__(probe.WindowAudit)
        audit.bus, audit.d = Mock(), Mock()
        audit.d.close.side_effect = InterruptedError('I/O deadline')
        with self.assertRaises(InterruptedError):
            audit.close()
        audit.bus.close_sync.assert_called_once()
        audit.d.display.socket.close.assert_called_once()

    def test_helper_is_not_launched_from_an_unrelated_file_manager(self):
        audit = object.__new__(probe.WindowAudit)
        calls = []
        def call(destination, path, interface, method, signature, values):
            calls.append(method)
            return (123,) if method == 'GetConnectionUnixProcessID' else (2,)
        audit.call = call
        with patch.object(probe, 'process_identity', return_value={'tracer': 99}), self.assertRaises(ValueError):
            audit.launch_helper({'tracer': 10})
        self.assertNotIn('Execute', calls)

    def test_native_deadline_targets_only_the_unique_diagnostic_request(self):
        with tempfile.TemporaryDirectory() as folder:
            checkpoint = Path(folder) / 'recovery.json'
            payload = base64.b64encode(json.dumps({'mode': 'compare', 'checkpoint': str(checkpoint)}).encode()).decode()
            saved = {'pid': 321, 'uid': 10, 'start_ticks': 1234, 'executable': '/loader', 'tracer': 300,
                     'cmd': ['/usr/bin/python3', '-', '--guest-request', payload]}
            checkpoint.write_text(json.dumps({'probe_process': saved, 'original_helper': {'pid': 100},
                                             'original_wm': {'pid': 101}}), encoding='utf-8')
            native = dict(saved, uid=9)  # PRoot mapped UID is deliberately different.
            with patch.object(probe.os, 'getuid', return_value=9, create=True), \
                 patch.object(probe.os, 'kill') as kill, patch.object(probe, 'process_identity', return_value=native):
                probe.interrupt_owned_probe(checkpoint)
                kill.assert_called_once_with(321, probe.signal.SIGTERM)
            with patch.object(probe.os, 'getuid', return_value=9, create=True), \
                 patch.object(probe.os, 'kill') as kill, \
                 patch.object(probe, 'process_identity', return_value=dict(native, start_ticks=9999)), self.assertRaises(ValueError):
                probe.interrupt_owned_probe(checkpoint)
            kill.assert_not_called()

    def test_compare_preview_never_contacts_device(self):
        d = Mock()
        self.assertEqual(probe.probe_device(d, probe.options('compare'))['status'], 'skipped')
        d.ssh_script.assert_not_called()

    def test_invalid_or_unbounded_workload_is_rejected_before_transport(self):
        for args in ({'steps': 0}, {'trials': 6}, {'step_ms': True}, {'steps': 300, 'trials': 5, 'step_ms': 50}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                probe.options('compare', **args)

    def test_readonly_report_uses_only_strict_ssh_and_hashes_inputs(self):
        d = Device({'ssh_target': 'user@device.example'})
        with patch.object(d, 'adb', side_effect=AssertionError('No ADB')), \
             patch.object(d, 'ssh_script', return_value=json.dumps({'status': 'passed'})) as ssh:
            value = probe.probe_device(d)
        self.assertEqual(value['status'], 'passed')
        self.assertEqual(value['input_summary']['mode'], 'inspect')
        self.assertEqual(len(value['source_sha256']), 64)
        self.assertIn("base64.b64decode", ssh.call_args.args[0])

    def test_transport_failure_retains_request_and_source_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            connection = root / 'connection.json'
            connection.write_text(json.dumps({'ssh_target': 'user@device.example'}), encoding='utf-8')
            with patch.object(Device, 'ssh_script', side_effect=RuntimeError('transport deadline')), contextlib.redirect_stdout(io.StringIO()):
                code = probe.main(['inspect', '--connection', str(connection), '--state', str(root / 'out.json')])
            result = json.loads((root / 'out.json').read_text())
            self.assertEqual(code, 1)
            self.assertEqual(result['input_summary']['mode'], 'inspect')
            self.assertEqual(len(result['source_sha256']), 64)

    def test_desktop_verify_window_report_preserves_failed_exit_status(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            connection = root / 'connection.json'
            connection.write_text(json.dumps({'ssh_target': 'user@device.example'}), encoding='utf-8')
            with patch.object(probe, 'probe_device', return_value={'status': 'failed', 'diagnosis': 'possible_redirect_conflict'}), \
                 patch.object(Device, 'adb', side_effect=AssertionError('No ADB')), contextlib.redirect_stdout(io.StringIO()):
                code = desktop_verify.main(['window-report', '--connection', str(connection), '--state', str(root / 'result.json')])
            self.assertEqual(code, 1)
            self.assertEqual(json.loads((root / 'result.json').read_text())['diagnosis'], 'possible_redirect_conflict')


if __name__ == '__main__':
    unittest.main()
