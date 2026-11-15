import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


path = Path(__file__).resolve().parents[1] / 'assets/desktop/guest/tablet_video_policy.py'
spec = importlib.util.spec_from_file_location('tablet_video_policy', path)
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class VideoPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.video = Path(self.temp.name) / 'video 中文.mp4'
        self.video.write_bytes(b'probe fixture')
        self.stream = dict(codec_name='h264', profile='Constrained Baseline', has_b_frames=0,
                           width=1920, height=1080, pix_fmt='yuv420p', avg_frame_rate='30/1')

    def result(self, stream=None):
        return subprocess.CompletedProcess([], 0, json.dumps({'streams': [stream or self.stream]}), '')

    def test_verified_baseline_file_and_encoded_uri(self):
        for name in (str(self.video), self.video.as_uri()):
            with self.subTest(name=name), patch.object(policy.subprocess, 'run', return_value=self.result()) as run:
                self.assertTrue(policy.hardware_allowed([name], 'h264-baseline'))
                self.assertEqual(run.call_args.args[0][-1], str(self.video.resolve()))
                self.assertEqual(run.call_args.kwargs['timeout'], 5)

    def test_high_profile_and_b_frames_use_compatibility_path(self):
        for fields in ({'profile': 'High'}, {'has_b_frames': 2}):
            stream = dict(self.stream, **fields)
            with self.subTest(fields=fields), patch.object(policy.subprocess, 'run', return_value=self.result(stream)):
                self.assertFalse(policy.hardware_allowed([str(self.video)], 'h264-baseline'))

    def test_unverified_resolution_rate_and_pixel_format(self):
        for fields in ({'width': 3840}, {'height': 2160}, {'avg_frame_rate': '60/1'},
                       {'avg_frame_rate': '0/0'}, {'pix_fmt': 'yuv420p10le'}, {'codec_name': 'hevc'}):
            with self.subTest(fields=fields), patch.object(policy.subprocess, 'run', return_value=self.result(dict(self.stream, **fields))):
                self.assertFalse(policy.hardware_allowed([str(self.video)], 'h264-baseline'))

    def test_no_file_and_network_sources_are_not_prefetched(self):
        for args in ([], ['--fullscreen'], ['https://example.invalid/video.mp4'], ['file://remote/video.mp4']):
            with self.subTest(args=args), patch.object(policy.subprocess, 'run') as run:
                self.assertFalse(policy.hardware_allowed(args, 'h264-baseline'))
                run.assert_not_called()

    def test_probe_failure_keeps_media_openable_via_compatibility_path(self):
        for error in (FileNotFoundError(), subprocess.TimeoutExpired('ffprobe', 5), subprocess.CalledProcessError(1, 'ffprobe')):
            with self.subTest(error=type(error)), patch.object(policy.subprocess, 'run', side_effect=error):
                self.assertFalse(policy.hardware_allowed([str(self.video)], 'h264-baseline'))

    def test_malformed_probe_output_uses_compatibility_path(self):
        for output in ('not json', '[]', '{}', '{"streams":[null]}', '{"streams":null}'):
            with self.subTest(output=output), patch.object(policy.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, output, '')):
                self.assertFalse(policy.hardware_allowed([str(self.video)], 'h264-baseline'))

    def test_mixed_playlist_cannot_force_unverified_decoder(self):
        other = Path(self.temp.name) / 'second.mp4'
        other.write_bytes(b'fixture')
        with patch.object(policy.subprocess, 'run', side_effect=[self.result(), self.result(dict(self.stream, profile='High'))]):
            self.assertFalse(policy.hardware_allowed([str(self.video), str(other)], 'h264-baseline'))

    def test_existing_all_policy_preserves_explicit_hardware_selection(self):
        with patch.object(policy.subprocess, 'run') as run:
            self.assertTrue(policy.hardware_allowed([], 'all'))
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
