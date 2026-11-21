from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import approve_project
import audio_production
import doctor
import init_project
import prepare_narration
import qa_presentation
import rebuild_presentation
import refresh_input_gate
import production_common
from page_script_contract import audit_page_script
from production_common import (
    approval_status,
    file_hash,
    load_object,
    load_project_config,
    load_state,
    project_paths,
    write_object,
)
from validate_project import validate
from validate_input_document import INPUT_CONTRACT_VERSION


class ProjectV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "source.md"
        self.source.write_text(
            "# 项目演讲稿\n\n"
            "## 第 1 页｜目标 · 30 秒\n\n"
            "这一页用于说明项目目标，并给出足以直接合成旁白的完整口述正文。\n",
            encoding="utf-8",
        )
        self.source_sha = hashlib.sha256(self.source.read_bytes()).hexdigest()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def create_project(
        self,
        name: str,
        deliverable: str,
        *,
        template_source: Path | None = None,
        prepare_visual: bool = True,
    ) -> Path:
        project = self.root / name
        gate = {
            "schema_version": 1,
            "contract_version": INPUT_CONTRACT_VERSION,
            "passed": True,
            "document": str(self.source),
            "document_sha256": self.source_sha,
            "profile": "page-narration",
            "semantic_review_required": False,
            "metrics": {},
            "findings": [],
        }
        source_metadata = {
            "mode": "document",
            "document": str(self.source),
            "document_sha256": self.source_sha,
            "profile": "page-narration",
            "review": None,
            "gate_report": "input-gate.json",
        }
        page_script_audit = audit_page_script(self.source, source=self.source)
        init_project.copy_template(
            project,
            project_name=name,
            deliverable=deliverable,
            source_document=self.source,
            page_script_source=self.source,
            template_source=template_source,
            visual_style="project-default",
            visual_theme="light",
            force=False,
            source_metadata=source_metadata,
            review_source=None,
            gate_report=gate,
            page_script_audit=page_script_audit,
        )
        if prepare_visual:
            self.prepare_visual(project)
        return project

    def prepare_visual(self, project: Path) -> None:
        paths = project_paths(project)
        manifest = load_object(paths["manifest"])
        manifest["slide_count"] = 1
        manifest["target_total_seconds"] = 12
        manifest["slides"] = [
            {
                "page": 1,
                "source_svg": "assets/00_cover.svg",
                "target_seconds": 12,
                "beats": [
                    {"id": "title", "label": "主标题", "effect": "fade"},
                ],
            }
        ]
        write_object(paths["manifest"], manifest)

    def approve(self, project: Path, stage: str, pages: str | None = None) -> None:
        approve_project.approve_command(
            argparse.Namespace(
                project=project,
                stage=stage,
                approved_by="tester",
                pages=pages,
                allow_substantial_rewrite=False,
            )
        )

    def prepare_narration_review(self, project: Path) -> None:
        prepare_narration.prepare(project, force=False)

    def test_initialization_writes_only_v2_for_all_deliverables(self) -> None:
        supplied_template = self.root / "supplied.css"
        supplied_template.write_text(":root{--slide-background:#fafafa}", encoding="utf-8")
        for index, deliverable in enumerate(
            (
                "narration_audio",
                "static_html",
                "animated_html",
                "narrated_html",
            )
        ):
            with self.subTest(deliverable=deliverable):
                project = self.create_project(
                    f"project-{index}",
                    deliverable,
                    template_source=(
                        supplied_template if deliverable == "static_html" else None
                    ),
                    prepare_visual=False,
                )
                config = load_project_config(project)
                self.assertEqual(config["schema_version"], 2)
                self.assertEqual(config["deliverable"], deliverable)
                self.assertIn("html_dir", config["outputs"])
                self.assertTrue((project / "page-script.md").is_file())
                self.assertEqual(
                    load_object(project / "video" / "animation_manifest.json")[
                        "slides"
                    ],
                    [],
                )
                self.assertEqual(
                    load_object(project / "video" / "narration_director.json")[
                        "pages"
                    ],
                    [],
                )
                self.assertEqual(
                    (project / "page-script.md").read_bytes(),
                    self.source.read_bytes(),
                )
        supplied = self.root / "project-1"
        self.assertEqual(
            (supplied / "inputs" / "template-source.css").read_bytes(),
            supplied_template.read_bytes(),
        )
        self.assertEqual(
            (supplied / "template.css").read_bytes(),
            supplied_template.read_bytes(),
        )

    def test_schema_v1_is_rejected_without_rewrite(self) -> None:
        project = self.create_project("schema-reject", "static_html")
        path = project / "project.json"
        config = load_object(path)
        config["schema_version"] = 1
        write_object(path, config)
        before = path.read_bytes()
        errors, _ = validate(project)
        self.assertTrue(any("expected 2" in error for error in errors))
        self.assertEqual(path.read_bytes(), before)

    def test_legacy_v2_content_metadata_is_upgraded_on_content_approval(self) -> None:
        project = self.create_project(
            "legacy-v2",
            "static_html",
            prepare_visual=False,
        )
        path = project / "project.json"
        config = load_object(path)
        config["content"] = {"page_script": "page-script.md"}
        config["source"].pop("gate_report_sha256", None)
        config["source"].pop("review_sha256", None)
        write_object(path, config)
        project_paths(project)["binding_audit"].unlink()

        self.assertEqual(load_project_config(project)["schema_version"], 2)
        with self.assertRaisesRegex(RuntimeError, "refresh-input-gate"):
            self.approve(project, "content")
        self.assertEqual(refresh_input_gate.refresh(project), 0)
        self.approve(project, "content")
        upgraded = load_project_config(project)
        self.assertIn(upgraded["content"]["binding_mode"], {"identity", "adapted"})
        self.assertIsInstance(upgraded["source"]["gate_report_sha256"], str)
        self.assertIsNone(upgraded["source"]["review_sha256"])
        self.assertTrue(project_paths(project)["binding_audit"].is_file())

    def test_current_v2_static_contract_validates_without_audio(self) -> None:
        project = self.create_project("schema-current", "static_html")
        self.approve(project, "content")
        self.approve(project, "visual", "1")
        errors, warnings = validate(project)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        self.assertFalse(project_paths(project)["audio_timeline"].exists())

    def test_voice_change_only_invalidates_narration_approval(self) -> None:
        project = self.create_project("approval", "narrated_html")
        self.approve(project, "content")
        self.approve(project, "visual", "1")
        self.prepare_narration_review(project)
        self.approve(project, "narration")

        for stage in ("content", "visual", "narration"):
            self.assertTrue(approval_status(project, stage)[0])

        paths = project_paths(project)
        voice = load_object(paths["voice_profile"])
        voice["audition"]["text"] = "只修改试听用短文，不改变生产声音。"
        write_object(paths["voice_profile"], voice)
        self.assertTrue(approval_status(project, "narration")[0])

        voice["voice"] = "zh-CN-XiaoxiaoNeural"
        write_object(paths["voice_profile"], voice)

        self.assertTrue(approval_status(project, "content")[0])
        self.assertTrue(approval_status(project, "visual")[0])
        self.assertFalse(approval_status(project, "narration")[0])
        with self.assertRaisesRegex(RuntimeError, "narration approval is stale"):
            audio_production.synthesize_command(
                argparse.Namespace(
                    project=project,
                    pages=None,
                    voice=None,
                    rate=None,
                    pitch=None,
                    env_file=None,
                    force=False,
                    dry_run=False,
                )
            )

    def test_combined_pitch_blocks_approval_and_synthesis_recheck(self) -> None:
        project = self.create_project(
            "combined-pitch-block",
            "narration_audio",
            prepare_visual=False,
        )
        self.approve(project, "content")
        self.prepare_narration_review(project)
        paths = project_paths(project)
        director = load_object(paths["director"])
        director["pages"][0]["segments"][0]["pitch"] = "+0.1st"
        write_object(paths["director"], director)
        voice = load_object(paths["voice_profile"])
        voice["pitch"] = "+0.1st"
        write_object(paths["voice_profile"], voice)

        with self.assertRaisesRegex(ValueError, r"page 1 segment 1.*\+0.2st"):
            self.approve(project, "narration")

        production_common.record_approval(
            project,
            "narration",
            approved_by="forged-legacy-test",
        )
        with self.assertRaisesRegex(ValueError, r"page 1 segment 1.*\+0.2st"):
            audio_production.synthesize_command(
                argparse.Namespace(
                    project=project,
                    pages=None,
                    voice=None,
                    rate=None,
                    pitch=None,
                    env_file=None,
                    force=False,
                    dry_run=True,
                )
            )

    def test_global_pitch_change_invalidates_all_chapter_fingerprints(self) -> None:
        self.source.write_text(
            "# 项目演讲稿\n\n"
            "## 第 1 页｜开场 · 30 秒\n\n"
            "第一页面向听众建立主题，并提供足以直接合成旁白的完整正文。\n\n"
            "## 第 2 页｜结束 · 30 秒\n\n"
            "第二页收束完整判断，并提供足以直接合成旁白的结束正文。\n",
            encoding="utf-8",
        )
        self.source_sha = hashlib.sha256(self.source.read_bytes()).hexdigest()
        project = self.create_project(
            "pitch-fingerprint",
            "narration_audio",
            prepare_visual=False,
        )
        self.approve(project, "content")
        prepare_narration.prepare(
            project,
            force=False,
            chapter_max_seconds=30,
        )
        self.approve(project, "narration")
        paths = project_paths(project)
        director = load_object(paths["director"])
        pages = production_common.normalize_director_pages(director)
        groups = production_common.chapter_groups(pages)
        self.assertEqual(len(groups), 2)
        original_voice = production_common.load_voice_profile(
            paths["voice_profile"]
        )
        before = [
            production_common.chapter_audio_fingerprint(group, original_voice)[0]
            for group in groups
        ]

        audio_production.configure_voice_command(
            argparse.Namespace(
                project=project,
                voice=None,
                rate=None,
                pitch="+0.1st",
                dry_run=False,
            )
        )

        self.assertFalse(approval_status(project, "narration")[0])
        updated_voice = production_common.load_voice_profile(
            paths["voice_profile"]
        )
        after = [
            production_common.chapter_audio_fingerprint(group, updated_voice)[0]
            for group in groups
        ]
        self.assertTrue(all(left != right for left, right in zip(before, after)))
        pitch_audit = load_object(paths["manifest"])["narration_pitch"]
        self.assertEqual(pitch_audit["min_final_pitch"], "+0st")
        self.assertEqual(pitch_audit["max_final_pitch"], "+0.1st")

    def test_voice_configuration_rejects_invalid_combined_pitch_without_write(self) -> None:
        project = self.create_project(
            "pitch-config-block",
            "narration_audio",
            prepare_visual=False,
        )
        self.approve(project, "content")
        self.prepare_narration_review(project)
        paths = project_paths(project)
        director = load_object(paths["director"])
        director["pages"][0]["segments"][0]["pitch"] = "+0.1st"
        write_object(paths["director"], director)
        original_voice = paths["voice_profile"].read_bytes()

        with self.assertRaisesRegex(ValueError, r"page 1 segment 1.*\+0.2st"):
            audio_production.configure_voice_command(
                argparse.Namespace(
                    project=project,
                    voice=None,
                    rate=None,
                    pitch="+0.1st",
                    dry_run=False,
                )
            )
        self.assertEqual(paths["voice_profile"].read_bytes(), original_voice)

    def test_build_state_and_approval_records_are_strictly_validated(self) -> None:
        project = self.create_project("strict-state", "static_html")
        self.approve(project, "content")
        paths = project_paths(project)
        state = load_state(paths["build_state"])
        state["approvals"]["content"].pop("approved_by")
        write_object(paths["build_state"], state)
        self.assertFalse(approval_status(project, "content")[0])

        state["schema_version"] = 999
        write_object(paths["build_state"], state)
        with self.assertRaisesRegex(ValueError, "build_state schema_version"):
            load_state(paths["build_state"])

    def test_contract_version_bump_invalidates_content_approval(self) -> None:
        project = self.create_project("contract-version", "static_html")
        self.approve(project, "content")
        self.assertTrue(approval_status(project, "content")[0])

        with mock.patch.object(
            production_common,
            "INPUT_CONTRACT_VERSION",
            production_common.INPUT_CONTRACT_VERSION + 1,
        ):
            self.assertFalse(approval_status(project, "content")[0])
        with mock.patch.object(
            production_common,
            "PAGE_SCRIPT_CONTRACT_VERSION",
            production_common.PAGE_SCRIPT_CONTRACT_VERSION + 1,
        ):
            self.assertFalse(approval_status(project, "content")[0])

    def test_performance_contract_bump_invalidates_narration_approval(self) -> None:
        project = self.create_project(
            "performance-contract-version",
            "narration_audio",
            prepare_visual=False,
        )
        self.approve(project, "content")
        self.prepare_narration_review(project)
        self.approve(project, "narration")
        self.assertTrue(approval_status(project, "narration")[0])

        with mock.patch.object(
            production_common,
            "NARRATION_PERFORMANCE_CONTRACT_VERSION",
            production_common.NARRATION_PERFORMANCE_CONTRACT_VERSION + 1,
        ):
            self.assertFalse(approval_status(project, "narration")[0])

    def test_refresh_gate_invalidates_content_without_rebuilding_material(self) -> None:
        project = self.create_project("refresh-gate", "narrated_html")
        self.approve(project, "content")
        self.approve(project, "visual", "1")
        self.prepare_narration_review(project)
        self.approve(project, "narration")

        gate = load_object(project / "input-gate.json")
        gate["contract_version"] = 1
        write_object(project / "input-gate.json", gate)
        config = load_object(project / "project.json")
        config["source"]["gate_report_sha256"] = file_hash(
            project / "input-gate.json"
        )
        write_object(project / "project.json", config)

        self.assertFalse(approval_status(project, "content")[0])
        self.assertTrue(approval_status(project, "visual")[0])
        self.assertTrue(approval_status(project, "narration")[0])

        self.assertEqual(refresh_input_gate.refresh(project), 0)
        self.assertFalse(approval_status(project, "content")[0])
        self.assertTrue(approval_status(project, "visual")[0])
        self.assertTrue(approval_status(project, "narration")[0])

        self.approve(project, "content")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(refresh_input_gate.refresh(project), 0)
        self.assertTrue(approval_status(project, "content")[0])
        self.assertTrue(approval_status(project, "visual")[0])
        self.assertTrue(approval_status(project, "narration")[0])
        self.assertIn("content approval remains current", output.getvalue())

    def test_refresh_gate_auto_corrects_historical_profile(self) -> None:
        project = self.create_project("refresh-profile", "narrated_html")
        self.approve(project, "content")
        self.approve(project, "visual", "1")
        self.prepare_narration_review(project)
        self.approve(project, "narration")
        config = load_object(project / "project.json")
        config["source"]["profile"] = "narrative-plan"
        write_object(project / "project.json", config)

        self.assertTrue(approval_status(project, "visual")[0])
        self.assertTrue(approval_status(project, "narration")[0])
        self.assertEqual(refresh_input_gate.refresh(project), 0)
        refreshed = load_project_config(project)
        self.assertEqual(refreshed["source"]["profile"], "page-narration")
        self.assertIsNone(refreshed["source"]["review"])
        self.assertTrue(approval_status(project, "visual")[0])
        self.assertTrue(approval_status(project, "narration")[0])

    def test_audio_cache_ignores_visual_only_changes(self) -> None:
        project = self.create_project("audio-cache-projection", "narrated_html")
        self.approve(project, "content")
        self.approve(project, "visual", "1")
        self.prepare_narration_review(project)
        paths = project_paths(project)
        state = load_state(paths["build_state"])
        before = qa_presentation.cache_fingerprint(project, "audio", state)

        manifest = load_object(paths["manifest"])
        manifest["slides"][0]["beats"][0]["effect"] = "wipe_left"
        write_object(paths["manifest"], manifest)
        (project / "assets" / "00_cover.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'viewBox="0 0 1600 900"><!-- visual change --></svg>',
            encoding="utf-8",
        )
        after = qa_presentation.cache_fingerprint(project, "audio", state)
        self.assertEqual(before, after)

    def test_static_doctor_does_not_check_audio_modules(self) -> None:
        self.assertIn("playwright", doctor.required_modules("static"))
        self.assertNotIn("azure.cognitiveservices.speech", doctor.required_modules("static"))
        self.assertNotIn("lameenc", doctor.required_modules("video"))
        self.assertNotIn("playwright", doctor.required_modules("audio"))

    def test_voice_configuration_does_not_require_html(self) -> None:
        project = self.create_project("voice-config", "narrated_html")
        args = argparse.Namespace(
            project=project,
            qa="standard",
            voice="zh-CN-XiaoxiaoNeural",
            rate=None,
            pitch=None,
            pages=None,
            force=False,
            dry_run=False,
            skip_export=False,
        )
        with mock.patch.object(rebuild_presentation, "run_script") as run:
            self.assertEqual(rebuild_presentation.rebuild_audio(args), 0)
        run.assert_called_once()

    def test_voice_configuration_survives_invalid_visual_manifest(self) -> None:
        project = self.create_project("voice-invalid-visual", "narrated_html")
        self.approve(project, "content")
        self.prepare_narration_review(project)
        paths = project_paths(project)
        manifest = load_object(paths["manifest"])
        manifest["slides"][0]["page"] = 2
        write_object(paths["manifest"], manifest)

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = audio_production.configure_voice_command(
                argparse.Namespace(
                    project=project,
                    voice="zh-CN-XiaoxiaoNeural",
                    rate=None,
                    pitch=None,
                    dry_run=False,
                )
            )
        self.assertEqual(result, 0)
        self.assertEqual(
            load_object(paths["voice_profile"])["voice"],
            "zh-CN-XiaoxiaoNeural",
        )
        self.assertEqual(load_object(paths["manifest"]), manifest)
        self.assertIn("could not be refreshed", output.getvalue())

    def test_voice_configuration_noop_and_dry_run_messages_are_truthful(self) -> None:
        project = self.create_project("voice-message", "narrated_html")
        paths = project_paths(project)
        original = paths["voice_profile"].read_bytes()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(
                audio_production.configure_voice_command(
                    argparse.Namespace(
                        project=project,
                        voice=None,
                        rate=None,
                        pitch=None,
                        dry_run=False,
                    )
                ),
                0,
            )
        self.assertIn("no changes", output.getvalue())
        self.assertNotIn("approve narration", output.getvalue())

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(
                audio_production.configure_voice_command(
                    argparse.Namespace(
                        project=project,
                        voice="zh-CN-XiaoxiaoNeural",
                        rate=None,
                        pitch=None,
                        dry_run=True,
                    )
                ),
                0,
            )
        self.assertIn("PLAN configure-voice", output.getvalue())
        self.assertEqual(paths["voice_profile"].read_bytes(), original)

    def test_content_rejects_missing_sha_bound_review(self) -> None:
        project = self.create_project(
            "missing-review",
            "static_html",
            prepare_visual=False,
        )
        config = load_object(project / "project.json")
        review = project / "input-review.json"
        review.write_text('{"decision":"pass"}\n', encoding="utf-8")
        gate_path = project / "input-gate.json"
        gate = load_object(gate_path)
        gate["profile"] = "narrative-plan"
        gate["semantic_review_required"] = True
        gate["review"] = "input-review.json"
        write_object(gate_path, gate)
        config["source"]["profile"] = "narrative-plan"
        config["source"]["review"] = "input-review.json"
        config["source"]["review_sha256"] = file_hash(review)
        config["source"]["gate_report_sha256"] = file_hash(gate_path)
        write_object(project / "project.json", config)
        review.unlink()

        with self.assertRaises(FileNotFoundError):
            self.approve(project, "content")
        errors, _ = validate(project, stage="content")
        self.assertTrue(any("Input review not found" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
