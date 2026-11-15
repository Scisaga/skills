"""Real timestamp/report boundaries, without a display, ADB or SSH."""
import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import presentation_timing as timing


def dump(actual, period=16666666):
    return str(period) + '\n' + '\n'.join(f'{t - 1} {t} {t - 2}' for t in actual)


class PresentationTimingTests(unittest.TestCase):
    def report(self, before, after, start=0, end=1000000000):
        return timing.analyze(before, after, layer='owned SurfaceView(BLAST)#1', start_ns=start, end_ns=end)

    def test_changed_period_is_not_used_to_calculate_frame_intervals(self):
        result = self.report(dump([100000000], 33333333), dump([100000000, 104000000, 112000000, 124000000]))
        self.assertEqual(result['status'], 'collected')
        self.assertEqual(result['interval_ms'], {'min': 8.0, 'p50': 10.0, 'p95': 12.0, 'max': 12.0})
        self.assertEqual(result['snapshots']['before']['reported_period_ns'], 33333333)
        self.assertEqual(result['snapshots']['after']['reported_period_ns'], 16666666)

    def test_ring_history_invalid_fences_and_duplicates_do_not_create_frames(self):
        result = self.report(dump([100, 200]), dump([0, timing.INT64_MAX, -1, 50, 200, 500, 300, 300]))
        self.assertEqual(result['selected_actual_present_count'], 2)
        self.assertEqual(result['first_actual_present_ns'], 300)
        self.assertEqual(result['last_actual_present_ns'], 500)
        self.assertEqual(result['snapshots']['after']['invalid_actual_rows'], 3)
        self.assertEqual(result['snapshots']['after']['duplicate_actual_rows'], 1)

    def test_motion_bounds_exclude_late_restore_and_unrelated_updates(self):
        result = self.report(dump([100]), dump([100, 200, 250, 300, 400, 450]), start=250, end=400)
        self.assertEqual(result['new_actual_present_count'], 5)
        self.assertEqual(result['selected_actual_present_count'], 3)
        self.assertEqual(result['first_actual_present_ns'], 250)
        self.assertEqual(result['last_actual_present_ns'], 400)
        self.assertEqual(result['observed_span_ns'], 150)

    def test_empty_period_only_old_and_one_frame_data_remain_pending(self):
        for after in ('', '16666666\n', dump([0, timing.INT64_MAX]), dump([100]), dump([100, 200])):
            with self.subTest(after=after):
                result = self.report(dump([100]), after)
                self.assertEqual(result['status'], 'pending')
                self.assertIsNone(result['interval_ms'])

    def test_large_nanosecond_values_preserve_integer_precision(self):
        t = 9_000_000_000_000_000_000
        result = self.report(dump([t]), dump([t + 1, t + 2, t + 5]), start=t, end=t + 10)
        self.assertEqual(result['interval_ms']['min'], .000001)
        self.assertEqual(result['interval_ms']['max'], .000003)

    def test_malformed_dumps_are_not_silently_turned_into_zero_fps(self):
        for text in ('Permission denied', '16666666\n1 2', '16666666\n1 nan 3'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.report('', text)

    def test_cli_records_input_hashes_and_pending_is_nonzero(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); before = root / 'before.txt'; after = root / 'after.txt'; state = root / 'out.json'
            before.write_text(dump([100]), encoding='utf-8'); after.write_text(dump([100]), encoding='utf-8')
            args = ['--before', str(before), '--after', str(after), '--layer', 'SurfaceView#1',
                    '--start-ns', '100', '--end-ns', '1000', '--state', str(state)]
            with contextlib.redirect_stdout(io.StringIO()):
                code = timing.main(args)
            result = json.loads(state.read_text(encoding='utf-8'))
            self.assertEqual(code, 3)
            self.assertEqual(result['input_summary']['before_sha256'], hashlib.sha256(before.read_bytes()).hexdigest())
            first_hash = result['input_sha256']
            after.write_text(dump([100, 200, 300]), encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(timing.main(args), 0)
            result = json.loads(state.read_text(encoding='utf-8'))
            self.assertEqual(result['status'], 'collected')
            self.assertNotEqual(first_hash, result['input_sha256'])

    def test_cli_bad_data_returns_failure_with_evidence_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); before = root / 'before'; after = root / 'after'; state = root / 'out'
            before.write_text('16666666\n', encoding='utf-8'); after.write_text('denied', encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                code = timing.main(['--before', str(before), '--after', str(after), '--layer', 'SurfaceView#1',
                                    '--start-ns', '1', '--end-ns', '2', '--state', str(state)])
            result = json.loads(state.read_text())
            self.assertEqual(code, 1)
            self.assertEqual(result['status'], 'failed')
            self.assertEqual(len(result['source_sha256']), 64)
            self.assertEqual(len(result['input_summary']['after_sha256']), 64)

    def test_invalid_window_or_output_alias_cannot_destroy_raw_input(self):
        with tempfile.TemporaryDirectory() as folder:
            raw = Path(folder) / 'raw'; raw.write_text(dump([100]), encoding='utf-8')
            original = raw.read_bytes()
            for start, end in (('1', '1'), ('2', '1'), ('-1', '2'), ('0', '10')):
                with self.subTest(start=start, end=end), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                    timing.main(['--before', str(raw), '--after', str(raw), '--layer', 'SurfaceView#1',
                                 '--start-ns', start, '--end-ns', end, '--state', str(raw)])
                self.assertEqual(error.exception.code, 2)
                self.assertEqual(raw.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
