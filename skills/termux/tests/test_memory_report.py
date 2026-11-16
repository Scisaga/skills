import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import memory_report as memory


DETAIL = '''** MEMINFO in pid 42 [example.app] **
    Gfx dev       40 0 0 40 0 0 0
   EGL mtrack    120 0 0 120 0 0 0
    GL mtrack     80 0 0 80 0 0 0
 App Summary
            Graphics: 240
           TOTAL PSS: 700            TOTAL RSS: 900       TOTAL SWAP PSS: 300
'''


class MemoryReportTests(unittest.TestCase):
    def test_android16_total_contains_swap_and_graphics_is_a_subset(self):
        row, = memory.parse_android(DETAIL, total_includes_swap=True)
        self.assertEqual(row['resident_total_kib'], 400)
        self.assertEqual(row['mapped_pss_kib'], 200)
        self.assertEqual(row['graphics_mtrack_kib'], 200)
        self.assertEqual(row['graphics_summary_kib'], 240)
        self.assertEqual(row['logical_total_kib'], 700)

    def test_resident_total_format_is_an_explicit_alternative(self):
        row, = memory.parse_android(DETAIL, total_includes_swap=False)
        self.assertEqual(row['resident_total_kib'], 700)
        self.assertEqual(row['logical_total_kib'], 1000)

    def test_merge_counts_native_pid_once_and_does_not_add_mapped_graphics_twice(self):
        native = dict(processes=[dict(pid=42, group='code', gpu_context=True,
                                     memory_kib=dict(Pss=200, SwapPss=300))])
        rows = memory.parse_android(DETAIL, total_includes_swap=True)
        result = memory.merge_sample(native, rows, rows)
        group = result['groups']['code']
        self.assertEqual(len(result['groups']), 1)
        self.assertEqual(group['process_count'], 1)
        self.assertEqual(group['resident_total_kib'], 400)
        self.assertEqual(group['logical_total_kib'], 700)

    def test_missing_gpu_detail_is_unknown_instead_of_zero(self):
        native = dict(processes=[dict(pid=42, group='code', gpu_context=True,
                                     memory_kib=dict(Pss=200, SwapPss=300))])
        group = memory.merge_sample(native, [], [])['groups']['code']
        self.assertIsNone(group['resident_total_kib'])
        self.assertEqual(group['missing_graphics_pids'], [42])

    def test_reject_incomplete_android_dump(self):
        for text in (DETAIL + 'DUMP TIMEOUT', '', DETAIL.replace('TOTAL SWAP PSS:', 'TOTAL SWAP:')):
            with self.assertRaises(ValueError):
                memory.parse_android(text, total_includes_swap=True)

    def test_zram_physical_is_distinct_from_logical_swap(self):
        result = memory.parse_zram('ZRAM: 102,400K physical used for 1,024,000K in swap (2,048,000K total swap)')
        self.assertEqual(result['mem_used_total_kib'], 102400)
        self.assertEqual(result['swap_used_kib'], 1024000)
        with self.assertRaises(ValueError):
            memory.parse_zram('SwapPss: 1024000')

    def test_package_mapping_groups_dot_and_colon_processes_without_guessing(self):
        raw = '''  *APP* UID 1234 ProcessRecord{abcd 42:example.app.unstable/u0a234}
    packageList={example.app}
  *APP* UID 1234 ProcessRecord{abcd 43:example.app:push/u0a234}
    packageList={example.app}
'''
        owners = memory.parse_app_packages(raw)
        self.assertEqual(memory.app_group(dict(pid=42, name='example.app.unstable'), owners), 'android:example.app')
        self.assertEqual(memory.app_group(dict(pid=43, name='example.app:push'), owners), 'android:example.app')
        self.assertNotEqual(memory.app_group(dict(pid=42, name='recycled.pid'), owners), 'android:example.app')

    def test_snapshot_retries_a_disappearing_android_process_and_retains_evidence(self):
        native = dict(boot_id='boot', session='session', mem_before_kib=dict(MemAvailable=1000),
                      processes=[], coverage_errors=[])
        raw = DETAIL + '\nZRAM: 100K physical used for 1000K in swap (2000K total swap)'
        with tempfile.TemporaryDirectory() as directory:
            args = SimpleNamespace(connection=Path(directory)/'connection.json', state=Path(directory)/'state.json',
                                   samples=1, interval=0, workload='same-tab', android=True, android_total='includes-swap')
            device = SimpleNamespace(digest='digest')
            from unittest.mock import Mock
            device.shell = Mock(side_effect=[raw.replace('TOTAL SWAP PSS:', 'TOTAL SWAP:'), raw, ''])
            with patch('device_transport.Device.read', return_value=device), patch.object(memory, 'remote_native', return_value=native):
                self.assertEqual(memory.snapshot(args), 0)
            result = __import__('json').loads(args.state.read_text(encoding='utf-8'))
            self.assertEqual(len(result['samples'][0]['collection_retries']), 1)

    def test_cli_failure_writes_failed_evidence_and_does_not_overwrite_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = ['snapshot', '--connection', str(root/'missing.json'), '--state', str(root/'state.json'), '--workload', 'same']
            self.assertEqual(memory.main(args), 1)
            result = __import__('json').loads((root/'state.json').read_text(encoding='utf-8'))
            self.assertEqual(result['status'], 'failed')
            self.assertIn('input_sha256', result)
            self.assertIn('connection', result['input_summary']['source_sha256'])
            with self.assertRaises(SystemExit) as error:
                memory.main(['compare', '--before', str(root/'state.json'), '--after', str(root/'after.json'), '--state', str(root/'state.json')])
            self.assertEqual(error.exception.code, 2)
            self.assertEqual((root/'state.json').read_text(encoding='utf-8'), __import__('json').dumps(result, ensure_ascii=False, indent=2)+'\n')

    def comparison_pair(self):
        proc = dict(group='code', pid=42, start_ticks=100, exe='loader', ppid=1, flags=[])
        before = dict(status='passed', input_summary=dict(connection_sha256='a', workload='tabs-code',
                      android=True, android_total='includes-swap', samples=1, interval=3),
                      samples=[dict(native=dict(boot_id='boot', session='session'), processes=[proc])],
                      summary=dict(mem_available_kib=1000, zram_mem_used_total_kib=300, groups={}))
        after = copy.deepcopy(before)
        after['summary'].update(mem_available_kib=1100, zram_mem_used_total_kib=280)
        return before, after

    def test_compare_reports_physical_deltas(self):
        before, after = self.comparison_pair()
        result = memory.compare(before, after)
        self.assertEqual(result['mem_available_delta_kib'], 100)
        self.assertEqual(result['zram_physical_delta_kib'], -20)

    def test_compare_rejects_changed_workload_boot_session_or_process_birth(self):
        for field in ('workload', 'boot_id', 'session', 'start_ticks'):
            before, after = self.comparison_pair()
            if field == 'workload':
                after['input_summary'][field] = 'another-tab'
            elif field == 'start_ticks':
                after['samples'][0]['processes'][0][field] += 1
            else:
                after['samples'][0]['native'][field] += '-new'
            with self.assertRaises(ValueError):
                memory.compare(before, after)


if __name__ == '__main__':
    unittest.main()
