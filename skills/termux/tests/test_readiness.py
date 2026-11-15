"""Cold-start races: stale supervisor files and late controller sockets."""
import contextlib
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'assets/desktop/native'))
import service_ready


class ReadinessTests(unittest.TestCase):
    def test_stale_supervisor_is_retried_until_live_response(self):
        responses = [subprocess.CompletedProcess([], 111), subprocess.CompletedProcess([], 111), subprocess.CompletedProcess([], 0)]
        with patch.object(service_ready.subprocess, 'run', side_effect=responses), patch.object(service_ready.time, 'sleep'):
            result = service_ready.wait_ready(Path('/prefix'), Path('/home'), timeout=1)
        self.assertTrue(result['ok'])
        self.assertEqual(result['attempts'], 3)
        self.assertEqual(len(result['input_sha256']), 64)

    def test_running_process_does_not_pass_before_controller_handshake(self):
        with patch.object(service_ready.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)), \
             patch.object(service_ready, 'controller_ready', side_effect=[False, False, True]), patch.object(service_ready.time, 'sleep'):
            result = service_ready.wait_ready(Path('/prefix'), Path('/home'), timeout=1, require_controller=True)
        self.assertTrue(result['ok'])
        self.assertEqual(result['attempts'], 3)

    def test_deadline_failure_is_structured_and_nonzero(self):
        clock = [0.]
        def fail(*args, **kwargs):
            clock[0] += .6
            return subprocess.CompletedProcess([], 111)
        with patch.object(service_ready.subprocess, 'run', side_effect=fail), \
             patch.object(service_ready.time, 'monotonic', side_effect=lambda: clock[0]), patch.object(service_ready.time, 'sleep'):
            result = service_ready.wait_ready(Path('/prefix'), Path('/home'), timeout=1)
        self.assertFalse(result['ok'])
        self.assertEqual(result['attempts'], 2)
        output = io.StringIO()
        with patch.object(service_ready, 'wait_ready', return_value=result), contextlib.redirect_stdout(output):
            code = service_ready.main(['--timeout', '1'])
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(output.getvalue())['ok'])

    def test_invalid_service_cannot_become_a_shell_command(self):
        with self.assertRaises(ValueError):
            service_ready.wait_ready(Path('/prefix'), Path('/home'), service='tablet-touch; exit 0')


if __name__ == '__main__':
    unittest.main()
