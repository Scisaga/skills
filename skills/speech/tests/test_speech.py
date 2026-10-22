"""Offline tests for provider selection, output safety, and environment layering."""
import builtins
import importlib
import json
import logging
import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import common
import synthesize as tts
from qwen_tts_client import QwenTTSClient, QwenTTSError


@contextmanager
def cwd(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class SpeechTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="speech-tests-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.output = self.root / "sample.mp3"

    def args(self, *extra):
        return tts.build_parser().parse_args(["--text", "complete first and second paragraphs", "--output-mp3", str(self.output), *extra])

    @staticmethod
    def success_qwen(text, output, work, args):
        output.write_bytes(b"qwen-complete-audio")
        return {"provider": "qwen3-tts-openai", "voice": "registered-voice"}

    def test_qwen_succeeds_without_loading_azure_sdk(self):
        original_import = builtins.__import__
        def no_azure(name, *args, **kwargs):
            if name.startswith("azure"):
                raise AssertionError("Qwen must not import Azure")
            return original_import(name, *args, **kwargs)
        with patch.object(tts, "qwen_to_mp3", side_effect=self.success_qwen), \
             patch.object(builtins, "__import__", side_effect=no_azure), \
             patch.object(tts, "synth_to_mp3") as azure:
            metadata = tts.synthesize_audio("original text", self.args())
        azure.assert_not_called()
        self.assertEqual(metadata["provider"], "qwen3-tts-openai")
        self.assertIsNone(metadata["fallback_reason"])

    def test_partial_qwen_failure_restarts_whole_text_on_azure(self):
        text = "first paragraph\n\nsecond paragraph"
        def partial_qwen(text, output, work, args):
            output.write_bytes(b"first-QWEN-part")
            raise QwenTTSError("second segment failed")
        def azure_output(actual_text, output, **kwargs):
            self.assertEqual(actual_text, text)
            Path(output).write_bytes(b"whole-AZURE-document")
        with patch.object(tts, "qwen_to_mp3", side_effect=partial_qwen), \
             patch.object(tts, "synth_to_mp3", side_effect=azure_output):
            metadata = tts.synthesize_audio(text, self.args())
        self.assertEqual(self.output.read_bytes(), b"whole-AZURE-document")
        self.assertEqual(metadata["provider"], "azure-speech")
        self.assertEqual(metadata["voice"], tts.DEFAULT_VOICE)
        self.assertEqual(metadata["fallback_reason"], "second segment failed")
        self.assertEqual(json.loads(self.output.with_suffix(".tts.json").read_text())["provider"], "azure-speech")

    def test_explicit_provider_never_falls_back(self):
        with patch.object(tts, "qwen_to_mp3", side_effect=QwenTTSError("unavailable")), \
             patch.object(tts, "synth_to_mp3") as azure:
            with self.assertRaisesRegex(QwenTTSError, "unavailable"):
                tts.synthesize_audio("original", self.args("--provider", "qwen3-tts-openai"))
        azure.assert_not_called()

    def test_local_file_error_never_triggers_azure(self):
        with patch.object(tts, "qwen_to_mp3", side_effect=PermissionError("read only")), \
             patch.object(tts, "synth_to_mp3") as azure:
            with self.assertRaises(PermissionError):
                tts.synthesize_audio("original", self.args())
        azure.assert_not_called()

    def test_both_backends_fail_and_preserve_prior_pair(self):
        self.output.write_bytes(b"existing-audio")
        sidecar = self.output.with_suffix(".tts.json")
        sidecar.write_text('{"prior":true}')
        with patch.object(tts, "qwen_to_mp3", side_effect=QwenTTSError("Qwen offline")), \
             patch.object(tts, "synth_to_mp3", side_effect=RuntimeError("Azure offline")):
            with self.assertRaisesRegex(RuntimeError, "Qwen offline.*Azure offline"):
                tts.synthesize_audio("original", self.args())
        self.assertEqual(self.output.read_bytes(), b"existing-audio")
        self.assertEqual(sidecar.read_text(), '{"prior":true}')

    def test_publish_failure_restores_prior_pair(self):
        self.output.write_bytes(b"existing-audio")
        sidecar = self.output.with_suffix(".tts.json")
        sidecar.write_text('{"prior":true}')
        replace = os.replace
        def fail_metadata(source, target):
            if Path(source).name == "metadata.json" and Path(target) == sidecar:
                raise PermissionError("simulated publication failure")
            return replace(source, target)
        with patch.object(tts, "qwen_to_mp3", side_effect=self.success_qwen), \
             patch.object(tts.os, "replace", side_effect=fail_metadata):
            with self.assertRaises(PermissionError):
                tts.synthesize_audio("original", self.args())
        self.assertEqual(self.output.read_bytes(), b"existing-audio")
        self.assertEqual(sidecar.read_text(), '{"prior":true}')

    def test_chunking_preserves_text_with_hard_length_bound(self):
        text = "a" * 91 + "。\n\n" + "b" * 67
        chunks = tts.split_into_chunks(text, 20)
        self.assertTrue(all(len(chunk) <= 20 for chunk in chunks))
        self.assertEqual("".join(chunks), text.replace("\n", ""))
        with self.assertRaises(ValueError):
            tts.split_into_chunks(text, 0)

    def test_ssml_contains_requested_controls_and_escapes_text(self):
        ssml = tts.build_ssml("a & b < c", voice="zh-CN-XiaoxiaoNeural", style="newscast", rate="+8%", pitch="+1st", bookmark="page-01")
        self.assertIn('rate="+8%"', ssml)
        self.assertIn('pitch="+1st"', ssml)
        self.assertIn('style="newscast"', ssml)
        self.assertIn("a &amp; b &lt; c", ssml)
        self.assertIn('mark="page-01"', ssml)

    def test_invalid_paths_and_controls_fail_before_network(self):
        for options in (["--max-chars", "0"], ["--rate", "nonsense"], ["--output-text", str(self.output)], ["--output-mp3", str(self.root)]):
            with patch.object(tts, "load_env"), patch.object(tts, "synthesize_audio") as synth:
                with self.assertRaises(SystemExit):
                    tts.main(["--text", "original", "--output-mp3", str(self.output), *options])
            synth.assert_not_called()

    def test_env_layers_fill_missing_values_and_preserve_process_even_empty(self):
        skill = self.root / "installed-skill"
        scripts = skill / "scripts"
        project = self.root / "project"
        scripts.mkdir(parents=True)
        project.mkdir()
        explicit = self.root / "shared.env"
        explicit.write_text("ORDER=explicit\nPROCESS=wrong\nEXPLICIT=only\nEMPTY=wrong\n")
        (project / ".env").write_text("ORDER=cwd\nCWD=only\n")
        (skill / ".env").write_text("ORDER=skill\nSKILL=only\n")
        (scripts / ".env").write_text("ORDER=scripts\nSCRIPTS=only\n")
        with patch.dict(os.environ, {"PROCESS": "process", "EMPTY": ""}, clear=True), \
             patch.object(common, "SKILL_ROOT", skill), patch.object(common, "SCRIPTS_DIR", scripts), cwd(project):
            common.load_env(env_file=str(explicit), logger=logging.getLogger("test"))
            self.assertEqual(os.environ["ORDER"], "explicit")
            self.assertEqual(os.environ["PROCESS"], "process")
            self.assertEqual(os.environ["EMPTY"], "")
            for name in ("EXPLICIT", "CWD", "SKILL", "SCRIPTS"):
                self.assertEqual(os.environ[name], "only")

    def test_missing_dotenv_reports_install_command_instead_of_skipping(self):
        (self.root / ".env").write_text("TEST=1")
        original_import = builtins.__import__
        def no_dotenv(name, *args, **kwargs):
            if name == "dotenv":
                raise ImportError("test missing dependency")
            return original_import(name, *args, **kwargs)
        with cwd(self.root), patch.object(builtins, "__import__", side_effect=no_dotenv):
            with self.assertRaisesRegex(RuntimeError, "pip install python-dotenv"):
                common.load_env(env_file=None, logger=logging.getLogger("test"))

    def test_asr_import_does_not_require_azure(self):
        original_import = builtins.__import__
        def no_azure(name, *args, **kwargs):
            if name.startswith("azure"):
                raise AssertionError("ASR must not import Azure")
            return original_import(name, *args, **kwargs)
        with patch.object(builtins, "__import__", side_effect=no_azure):
            module = importlib.import_module("transcribe")
            parser = module.build_parser()
            self.assertEqual(parser.parse_args(["--input-file", "input.wav"]).input_file, "input.wav")

    def test_execution_evidence_rejects_wrong_text_voice_model_or_ignored_controls(self):
        client = object.__new__(QwenTTSClient)
        client.resolved_identity = {"model": {"model_id": "expected-model"}}
        plan = {"source_hash": "source", "text_hash": "text", "units": [
            {"unit_id": "unit-1", "postprocessing": {"tempo": 1.08, "pitch_semitones": 1, "gain_db": 0}}
        ]}
        manifest = {"source_hash": "source", "text_hash": "text", "model": {"identity": {"model_id": "expected-model"}},
                    "units": [{"unit_id": "unit-1", "voice_id": "selected-voice", "controls": {"tempo": 1.08, "pitch_semitones": 1, "gain_db": 0},
                               "control_owners": {"tempo": "rubberband", "pitch_semitones": "rubberband"}}]}
        profile = {"qwen_voice": "selected-voice"}
        client.validate_execution(plan, manifest, profile)
        for field in ("text", "voice", "model", "controls", "malformed"):
            corrupt = json.loads(json.dumps(manifest))
            if field == "text":
                corrupt["text_hash"] = "different-text"
            elif field == "voice":
                corrupt["units"][0]["voice_id"] = "different-voice"
            elif field == "model":
                corrupt["model"]["identity"]["model_id"] = "different-model"
            elif field == "controls":
                corrupt["units"][0]["controls"]["tempo"] = 1
            else:
                corrupt["model"] = None
            with self.subTest(field=field), self.assertRaises(QwenTTSError):
                client.validate_execution(plan, corrupt, profile)


if __name__ == "__main__":
    unittest.main()
