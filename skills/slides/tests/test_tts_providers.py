from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import threading
import unittest
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import audio_production
import approve_project
import build_audio_timeline
import doctor
import init_project
import prepare_narration
import qa_presentation
from production_common import (
    approval_status,
    chapter_audio_fingerprint,
    load_object,
    normalize_voice_profile,
    project_paths,
    render_chapter_ssml,
    write_object,
)
from qwen_tts_client import (
    QwenTTSClient,
    QwenTTSError,
    load_tts_environment,
    service_base_url,
)


def pcm_wav(pages: int) -> bytes:
    stream = io.BytesIO()
    with wave.open(stream, "wb") as audio:
        audio.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        audio.writeframes(b"\x01\x00" * 12000 * pages)
    return stream.getvalue()


class StubService:
    def __init__(self):
        self.calls = []
        self.jobs = {}
        self.invalid_plan = False
        self.fail_job = None
        self.pending = False
        self.corrupt_artifact = False

    def plan(self, payload):
        pages = [
            int(p) for p in re.findall(r'<bookmark mark="page-(\d+)"', payload["ssml"])
        ]
        return {
            "valid": not self.invalid_plan,
            "pages": [{"page": p} for p in pages],
            "issues": [
                {
                    "severity": "error",
                    "code": "unsupported_style",
                    "message": "unsupported",
                }
            ]
            if self.invalid_plan
            else [],
        }

    def handle(self, path, payload):
        if path == "/ready":
            return {
                "inference_ready": True,
                "model": {"identity": {"model_id": "test-model"}},
            }
        if path == "/v1/voices":
            return {
                "voices": [
                    {
                        "voice_id": "voice_test",
                        "name": "测试音色",
                        "conditioning_state": "ready",
                        "conditioning_key": "ref-key",
                    }
                ]
            }
        if path == "/v1/narrations/compile":
            return self.plan(payload)
        if path == "/v1/narrations":
            ident = f"job_{len(self.jobs) + 1}"
            pages = self.plan(payload)["pages"]
            timeline = {
                "pages": [
                    {
                        "page": r["page"],
                        "start_seconds": i * 0.5,
                        "end_seconds": (i + 1) * 0.5,
                    }
                    for i, r in enumerate(pages)
                ]
            }
            artifacts = {
                "full-wav": pcm_wav(len(pages)),
                "timeline": json.dumps(timeline).encode(),
                "manifest": b'{"listening_acceptance":"pending"}',
            }
            self.jobs[ident] = artifacts
            return {"job_id": ident, "status": "queued"}
        if path.endswith("/cancel"):
            return {"status": "cancelled"}
        if "/artifacts/" in path:
            ident, name = path.split("/")[3], path.rsplit("/", 1)[1]
            data = self.jobs[ident][name]
            return data + b"bad" if self.corrupt_artifact else data
        if path.startswith("/v1/jobs/"):
            ident = path.rsplit("/", 1)[1]
            return {
                "job_id": ident,
                "status": "queued"
                if self.pending
                else "failed"
                if ident == f"job_{self.fail_job}"
                else "succeeded",
                "error": "inference error" if self.fail_job else None,
                "artifacts": [
                    {
                        "artifact_id": k,
                        "bytes": len(v),
                        "sha256": hashlib.sha256(v).hexdigest(),
                    }
                    for k, v in self.jobs[ident].items()
                ],
            }
        raise AssertionError(path)


@contextlib.contextmanager
def service():
    stub = StubService()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.respond(None)

        def do_POST(self):
            self.respond(
                json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            )

        def respond(self, payload):
            stub.calls.append((self.path, payload, self.headers.get("Authorization")))
            result = stub.handle(self.path, payload)
            body = result if isinstance(result, bytes) else json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    with mock.patch.dict(
        os.environ,
        {
            "QWEN_TTS_API_BASE": f"http://127.0.0.1:{server.server_port}/v1/",
            "QWEN_TTS_API_KEY": "test-secret",
        },
        clear=True,
    ):
        try:
            yield stub
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


class TTSProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.profile = normalize_voice_profile(
            {
                "provider": "auto",
                "voice": "zh-CN-XiaochenNeural",
                "qwen_voice": "voice_test",
            }
        )
        self.chapter = {
            "id": "chapter-01",
            "pages": [
                {
                    "page": p,
                    "segments": [
                        {
                            "text": "这是完整测试正文。",
                            "rate": "-5%",
                            "pause_after_ms": 100,
                        }
                    ],
                }
                for p in (1, 2)
            ],
        }

    def tearDown(self):
        self.temp.cleanup()

    def project(self):
        source = self.root / "source.md"
        source.write_text(
            "# 演讲稿\n\n## 第 1 页｜开场 · 20 秒\n\n欢迎来到技术演示，这一页说明项目目标，并给出足以直接合成旁白的完整口述正文。\n\n## 第 2 页｜结论 · 20 秒\n\n感谢大家，这一页收束完整判断，并给出足以直接合成旁白的结束正文。\n",
            encoding="utf-8",
        )
        project = self.root / "project"
        self.assertEqual(
            init_project.main(
                [
                    "--output",
                    str(project),
                    "--name",
                    "test",
                    "--deliverable",
                    "narration_audio",
                    "--input-document",
                    str(source),
                ]
            ),
            0,
        )
        approve_project.main(
            ["--project", str(project), "--stage", "content", "--approved-by", "test"]
        )
        prepare_narration.prepare(project, force=False, chapter_max_seconds=30)
        audio_production.main(
            [
                "configure-voice",
                "--project",
                str(project),
                "--provider",
                "auto",
                "--qwen-voice",
                "voice_test",
            ]
        )
        approve_project.main(
            ["--project", str(project), "--stage", "narration", "--approved-by", "test"]
        )
        return project

    def test_http_contract_and_actual_pcm_page_boundaries(self):
        with service() as stub:
            client = QwenTTSClient()
            receipt = client.resolve(self.profile)
            marks = client.synthesize(
                render_chapter_ssml(self.chapter, self.profile),
                self.profile,
                self.root / "out.wav",
                self.root / "chapter-01",
            )
        self.assertEqual(marks, {"page-01": 0, "page-02": 5_000_000})
        payload = next(call[1] for call in stub.calls if call[0] == "/v1/narrations")
        self.assertIn("完整测试正文", payload["ssml"])
        self.assertEqual(
            payload["voice_mapping"], {self.profile["voice"]: "voice_test"}
        )
        self.assertFalse(payload["allow_degraded"])
        self.assertFalse(payload["allow_experimental"])
        self.assertTrue(all(call[2] == "Bearer test-secret" for call in stub.calls))
        self.assertNotIn("test-secret", json.dumps(receipt))

    def test_corrupt_download_is_rejected(self):
        with service() as stub:
            stub.corrupt_artifact = True
            with self.assertRaisesRegex(QwenTTSError, "SHA256"):
                QwenTTSClient().synthesize(
                    render_chapter_ssml(self.chapter, self.profile),
                    self.profile,
                    self.root / "out.wav",
                    self.root / "chapter-01",
                )
        self.assertFalse((self.root / "out.wav").exists())

    def test_invalid_preflight_does_not_submit_job(self):
        with service() as stub:
            stub.invalid_plan = True
            with self.assertRaisesRegex(QwenTTSError, "unsupported_style"):
                QwenTTSClient().synthesize(
                    render_chapter_ssml(self.chapter, self.profile),
                    self.profile,
                    self.root / "out.wav",
                    self.root / "chapter-01",
                )
        self.assertFalse(stub.jobs)

    def test_poll_timeout_cancels_our_job_once(self):
        with service() as stub:
            stub.pending = True
            client = QwenTTSClient()
            client.timeout = 0.02
            client.poll_interval = 0.01
            with self.assertRaisesRegex(QwenTTSError, "timed out"):
                client.synthesize(
                    render_chapter_ssml(self.chapter, self.profile),
                    self.profile,
                    self.root / "out.wav",
                    self.root / "chapter-01",
                )
        self.assertEqual(sum(path.endswith("/cancel") for path, _, _ in stub.calls), 1)
        self.assertEqual(len(stub.jobs), 1)

    def test_preflight_auto_falls_back_but_explicit_qwen_stops(self):
        with (
            service() as stub,
            mock.patch.object(audio_production, "speech_config") as azure,
        ):
            stub.invalid_plan = True
            client, receipt, reason = audio_production.select_synthesis(
                self.profile, [self.chapter]
            )
            self.assertIsNone(client)
            self.assertEqual(receipt["provider"], "azure-speech")
            self.assertIn("unsupported_style", reason)
            azure.assert_called_once()
            with self.assertRaises(QwenTTSError):
                audio_production.select_synthesis(
                    {**self.profile, "provider": "qwen3-tts-openai"}, [self.chapter]
                )
            azure.assert_called_once()

    def test_no_azure_dependency_is_touched_when_qwen_succeeds(self):
        with (
            service(),
            mock.patch.object(
                audio_production,
                "speech_config",
                side_effect=AssertionError("Azure must not be touched"),
            ),
        ):
            _, receipt, reason = audio_production.select_synthesis(
                self.profile, [self.chapter]
            )
        self.assertEqual(receipt["provider"], "qwen3-tts-openai")
        self.assertIsNone(reason)
        self.assertNotIn(
            "azure.cognitiveservices.speech", doctor.required_modules("audio", "auto")
        )
        self.assertIn(
            "azure.cognitiveservices.speech",
            doctor.required_modules("audio", "azure-speech"),
        )

    def test_mid_run_failure_replaces_all_chapters_even_with_pages_filter(self):
        def azure_wav(ssml, output, profile):
            pages = [int(p) for p in re.findall(r'<bookmark mark="page-(\d+)"', ssml)]
            output.write_bytes(pcm_wav(len(pages)))
            return {f"page-{page:02d}": i * 5_000_000 for i, page in enumerate(pages)}

        with (
            service() as stub,
            mock.patch.object(audio_production, "load_environment"),
            mock.patch.object(audio_production, "speech_config"),
            mock.patch.object(
                audio_production, "synthesize_chapter_wav", side_effect=azure_wav
            ) as azure,
        ):
            project = self.project()
            stub.fail_job = 2
            audio_production.main(
                ["synthesize", "--project", str(project), "--pages", "2"]
            )
            self.assertEqual(azure.call_count, 2)
            paths = project_paths(project)
            receipts = [
                load_object(p) for p in paths["audio_dir"].glob("*.bookmarks.json")
            ]
            self.assertEqual(
                {r["synthesis"]["provider"] for r in receipts}, {"azure-speech"}
            )
            self.assertTrue(
                all("inference error" in r["fallback_reason"] for r in receipts)
            )
            timeline = build_audio_timeline.build_timeline(
                load_object(paths["manifest"]),
                audio_dir=paths["audio_dir"],
                output=paths["audio_timeline"],
            )
            write_object(paths["audio_timeline"], timeline)
            errors, warnings = [], []
            qa_presentation.audio_qa(project, errors, warnings)
            self.assertEqual(errors, [])

    def test_cache_reuses_jobs_and_voice_change_invalidates_approval(self):
        with (
            service() as stub,
            mock.patch.object(audio_production, "load_environment"),
            mock.patch.object(
                audio_production,
                "speech_config",
                side_effect=AssertionError("No Azure"),
            ),
        ):
            project = self.project()
            audio_production.main(["synthesize", "--project", str(project)])
            audio_production.main(["synthesize", "--project", str(project)])
            self.assertEqual(len(stub.jobs), 2)
            audio_production.main(
                [
                    "configure-voice",
                    "--project",
                    str(project),
                    "--qwen-voice",
                    "voice_changed",
                ]
            )
            self.assertFalse(approval_status(project, "narration")[0])
            with self.assertRaisesRegex(RuntimeError, "narration approval is stale"):
                audio_production.main(["synthesize", "--project", str(project)])

    def test_execution_identity_changes_audio_fingerprint(self):
        with service():
            receipt = QwenTTSClient().resolve(self.profile)
        before = chapter_audio_fingerprint(self.chapter, self.profile, receipt)[0]
        for key in ("base_url", "conditioning_key", "voice", "model"):
            changed = {**receipt, key: "changed"}
            self.assertNotEqual(
                before,
                chapter_audio_fingerprint(self.chapter, self.profile, changed)[0],
            )

    def test_qa_rejects_mixed_actual_providers(self):
        with service(), mock.patch.object(audio_production, "load_environment"):
            project = self.project()
            audio_production.main(["synthesize", "--project", str(project)])
        paths = project_paths(project)
        timeline = build_audio_timeline.build_timeline(
            load_object(paths["manifest"]),
            audio_dir=paths["audio_dir"],
            output=paths["audio_timeline"],
        )
        write_object(paths["audio_timeline"], timeline)
        path = paths["audio_dir"] / "chapter-02.bookmarks.json"
        receipt = load_object(path)
        receipt["synthesis"] = {
            "provider": "azure-speech",
            "voice": self.profile["voice"],
        }
        write_object(path, receipt)
        errors, warnings = [], []
        qa_presentation.audio_qa(project, errors, warnings)
        self.assertTrue(any("mixes different TTS" in error for error in errors))

    def test_corrupt_service_evidence_rebuilds_only_its_chapter(self):
        with service() as stub, mock.patch.object(audio_production, "load_environment"):
            project = self.project()
            audio_production.main(["synthesize", "--project", str(project)])
            paths = project_paths(project)
            (paths["scripts_dir"] / "chapter-01.qwen-timeline.json").write_text(
                "{}", encoding="utf-8"
            )
            audio_production.main(["synthesize", "--project", str(project)])
            self.assertEqual(len(stub.jobs), 3)

    def test_dry_run_has_no_network_or_writes(self):
        with mock.patch.object(audio_production, "load_environment"):
            project = self.project()
        before = {
            str(p.relative_to(project)): p.read_bytes()
            for p in project.rglob("*")
            if p.is_file()
        }
        with (
            mock.patch.object(
                audio_production,
                "QwenTTSClient",
                side_effect=AssertionError("No network"),
            ),
            mock.patch.object(
                audio_production,
                "speech_config",
                side_effect=AssertionError("No Azure"),
            ),
        ):
            audio_production.main(
                ["synthesize", "--project", str(project), "--dry-run"]
            )
        after = {
            str(p.relative_to(project)): p.read_bytes()
            for p in project.rglob("*")
            if p.is_file()
        }
        self.assertEqual(before, after)

    def test_env_precedence_loads_missing_values_from_each_location(self):
        skill = self.root / "skill"
        script = skill / "scripts"
        script.mkdir(parents=True)
        cwd = self.root / "cwd"
        cwd.mkdir()
        (cwd / ".env").write_text("VALUE=current\n", encoding="utf-8")
        (skill / ".env").write_text(
            "VALUE=skill\nSKILL_ONLY=loaded\n", encoding="utf-8"
        )
        (script / ".env").write_text("SCRIPT_ONLY=loaded\n", encoding="utf-8")
        explicit = self.root / "explicit.env"
        explicit.write_text("VALUE=explicit\nPROCESS=from-file\n", encoding="utf-8")
        with (
            mock.patch("qwen_tts_client.SKILL_ROOT", skill),
            mock.patch("qwen_tts_client.Path.cwd", return_value=cwd),
            mock.patch.dict(os.environ, {"PROCESS": "from-process"}, clear=True),
        ):
            load_tts_environment(explicit)
            self.assertEqual(os.environ["VALUE"], "explicit")
            self.assertEqual(os.environ["PROCESS"], "from-process")
            self.assertEqual(os.environ["SKILL_ONLY"], "loaded")
            self.assertEqual(os.environ["SCRIPT_ONLY"], "loaded")

    def test_url_normalization(self):
        self.assertEqual(
            service_base_url("http://localhost:8000/v1/"), "http://localhost:8000"
        )
        self.assertEqual(
            service_base_url("https://example.test/tts/"), "https://example.test/tts"
        )
        with self.assertRaises(QwenTTSError):
            service_base_url("http://user:secret@example.test")


if __name__ == "__main__":
    unittest.main()
