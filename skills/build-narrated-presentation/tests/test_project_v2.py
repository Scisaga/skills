from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import approve_project
import audio_production
import doctor
import init_project
import powerpoint_production
import pptx_production
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


def make_minimal_pptx(
    path: Path,
    *,
    slides: int = 1,
    embedded_svg: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        for page in range(1, slides + 1):
            archive.writestr(
                f"ppt/slides/slide{page}.xml",
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"/>',
            )
            if embedded_svg:
                archive.writestr(
                    f"ppt/media/page-{page}.svg",
                    '<svg xmlns="http://www.w3.org/2000/svg" '
                    'viewBox="0 0 1600 900"/>',
                )


def make_animated_pptx(
    path: Path,
    *,
    animation_filter: str = "fade",
    target_name: str = "s01_title",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    slide = f'''<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:spTree><p:sp><p:nvSpPr>
    <p:cNvPr id="2" name="{target_name}"/>
  </p:nvSpPr></p:sp></p:spTree></p:cSld>
  <p:timing><p:tnLst><p:par><p:cTn id="1" dur="indefinite" nodeType="tmRoot">
    <p:childTnLst><p:seq><p:cTn id="2" dur="indefinite" nodeType="mainSeq">
      <p:childTnLst><p:par><p:cTn id="3" dur="indefinite" presetClass="entr">
        <p:childTnLst><p:animEffect transition="in" filter="{animation_filter}">
          <p:cBhvr><p:cTn id="4" dur="280"/><p:tgtEl><p:spTgt spid="2"/></p:tgtEl></p:cBhvr>
        </p:animEffect></p:childTnLst>
      </p:cTn></p:par></p:childTnLst>
    </p:cTn></p:seq></p:childTnLst>
  </p:cTn></p:par></p:tnLst></p:timing>
</p:sld>'''
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        archive.writestr("ppt/slides/slide1.xml", slide)
        archive.writestr(
            "ppt/presentation.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<p:presentation '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
            'showAnimation="1"/>',
        )
        archive.writestr(
            "ppt/media/page-1.svg",
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 900"/>',
        )


def write_one_page_animation_timing(project: Path) -> None:
    write_object(
        project_paths(project)["timing"],
        {
            "schema_version": 1,
            "strategy": "fast-parallel-entrance",
            "defaults": {},
            "slides": [
                {
                    "page": 1,
                    "audio_start_ms": 0,
                    "animation_window_ms": 1000,
                    "animation_end_ms": 280,
                    "advance_safety_ms": 150,
                    "beats": [
                        {
                            "id": "title",
                            "effect": "fade",
                            "start_ms": 0,
                            "duration_ms": 280,
                        }
                    ],
                }
            ],
        },
    )


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
        if template_source is None and deliverable != "narration_audio":
            make_minimal_pptx(project / "template.pptx")
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
        supplied_template = self.root / "supplied.pptx"
        make_minimal_pptx(supplied_template)
        for index, deliverable in enumerate(
            (
                "narration_audio",
                "static_pptx",
                "animated_pptx",
                "narrated_pptx",
                "video",
            )
        ):
            with self.subTest(deliverable=deliverable):
                project = self.create_project(
                    f"project-{index}",
                    deliverable,
                    template_source=(
                        supplied_template if deliverable == "static_pptx" else None
                    ),
                    prepare_visual=False,
                )
                config = load_project_config(project)
                self.assertEqual(config["schema_version"], 2)
                self.assertEqual(config["deliverable"], deliverable)
                self.assertIn("narrated_pptx", config["outputs"])
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
            (supplied / "inputs" / "template-source.pptx").read_bytes(),
            supplied_template.read_bytes(),
        )
        self.assertEqual(
            (supplied / "template.pptx").read_bytes(),
            supplied_template.read_bytes(),
        )

    def test_schema_v1_is_rejected_without_rewrite(self) -> None:
        project = self.create_project("schema-reject", "static_pptx")
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
            "static_pptx",
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
        project = self.create_project("schema-current", "static_pptx")
        self.approve(project, "content")
        self.approve(project, "visual", "1")
        errors, warnings = validate(project)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        self.assertFalse(project_paths(project)["audio_timeline"].exists())

    def test_voice_change_only_invalidates_narration_approval(self) -> None:
        project = self.create_project("approval", "narrated_pptx")
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

    def test_build_state_and_approval_records_are_strictly_validated(self) -> None:
        project = self.create_project("strict-state", "static_pptx")
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
        project = self.create_project("contract-version", "static_pptx")
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
        project = self.create_project("refresh-gate", "narrated_pptx")
        self.approve(project, "content")
        self.approve(project, "visual", "1")
        self.prepare_narration_review(project)
        self.approve(project, "narration")
        paths = project_paths(project)

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
        project = self.create_project("refresh-profile", "narrated_pptx")
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
        project = self.create_project("audio-cache-projection", "narrated_pptx")
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

    def test_visual_baseline_rejected_after_svg_change(self) -> None:
        project = self.create_project("visual-provenance", "narrated_pptx")
        paths = project_paths(project)
        make_minimal_pptx(paths["animated_pptx"])
        pptx_production.record_visual_baseline(
            project,
            paths["animated_pptx"],
        )
        (project / "assets" / "00_cover.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'viewBox="0 0 1600 900"><!-- changed later --></svg>',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(RuntimeError, "visual baseline"):
            pptx_production.require_current_visual_baseline(
                project,
                paths["animated_pptx"],
            )

    def test_static_and_animated_assembly_do_not_read_audio(self) -> None:
        for deliverable, output_key in (
            ("static_pptx", "static_pptx"),
            ("animated_pptx", "animated_pptx"),
        ):
            with self.subTest(deliverable=deliverable):
                project = self.create_project(deliverable, deliverable)
                self.approve(project, "content")
                self.approve(project, "visual", "1")
                output = project_paths(project)[output_key]
                make_minimal_pptx(output)
                audio_timeline = project / "video" / "audio_timeline.json"
                self.assertFalse(audio_timeline.exists())
                with mock.patch.object(pptx_production, "run_adapter"):
                    pptx_production.assemble_command(
                        argparse.Namespace(project=project, adapter="test-adapter")
                    )
                self.assertTrue(output.is_file())
                self.assertFalse(
                    project_paths(project)["narrated_pptx"].exists()
                )

    def test_static_doctor_does_not_check_audio_modules(self) -> None:
        checked: list[str] = []

        def available(module: str) -> bool:
            checked.append(module)
            return True

        with mock.patch.object(doctor, "module_available", side_effect=available):
            self.assertEqual(doctor.check_stage("static"), [])
        self.assertTrue(set(checked).issubset(set(doctor.STATIC_MODULES)))
        self.assertFalse(set(checked).intersection(doctor.AUDIO_MODULES))

    def test_video_doctor_does_not_require_ffprobe(self) -> None:
        executables: list[str] = []

        def which(name: str) -> str | None:
            executables.append(name)
            if name == "powershell.exe":
                return "/mock/powershell.exe"
            return None

        with (
            mock.patch.object(doctor, "module_available", return_value=True),
            mock.patch.object(doctor.shutil, "which", side_effect=which),
        ):
            self.assertEqual(doctor.check_stage("video"), [])
        self.assertNotIn("ffprobe", executables)

    def test_office_2019_product_id_selects_color_range_fix(self) -> None:
        generation, reason = powerpoint_production.classify_powerpoint_generation(
            {
                "powerpoint_version": "16.0",
                "powerpoint_build": "14701",
                "office_product_release_ids": "ProPlus2019Retail",
            }
        )
        self.assertEqual(generation, "office-2019")
        self.assertIn("ProductReleaseIds", reason)

    def test_newer_office_build_skips_color_range_fix(self) -> None:
        report = {
            "powerpoint_version": "16.0",
            "powerpoint_build": "14332",
            "office_product_release_ids": "ProPlus2021Volume",
        }
        video = self.root / "newer-office.mp4"
        video.write_bytes(b"newer")
        with mock.patch.object(powerpoint_production, "reencode_office2019_color_range") as reencode:
            compatibility = powerpoint_production.apply_color_range_compatibility(
                video,
                report,
                "auto",
            )
        reencode.assert_not_called()
        self.assertEqual(compatibility["powerpoint_generation"], "newer-office")
        self.assertEqual(compatibility["action"], "skipped")

    def test_shared_retail_build_without_product_id_is_unknown(self) -> None:
        generation, reason = powerpoint_production.classify_powerpoint_generation(
            {
                "powerpoint_version": "16.0",
                "powerpoint_build": "14701",
            }
        )
        self.assertEqual(generation, "unknown")
        self.assertIn("shared", reason)

    def test_unknown_office_generation_requires_explicit_override(self) -> None:
        video = self.root / "unknown-office.mp4"
        video.write_bytes(b"unknown")
        compatibility = powerpoint_production.apply_color_range_compatibility(
            video,
            {"powerpoint_version": "16.0"},
            "auto",
        )
        self.assertEqual(compatibility["action"], "skipped")
        self.assertIn("warning", compatibility)

    def test_office_2019_fix_reencodes_pixels_to_limited_range(self) -> None:
        video = self.root / "office-2019.mp4"
        video.write_bytes(b"raw-video")
        commands: list[list[str]] = []

        def run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            commands.append(command)
            Path(command[-1]).write_bytes(b"fixed-video")
            return subprocess.CompletedProcess(command, 0, "", "")

        with (
            mock.patch.object(powerpoint_production, "find_ffmpeg", return_value="ffmpeg"),
            mock.patch.object(powerpoint_production.subprocess, "run", side_effect=run),
        ):
            compatibility = powerpoint_production.apply_color_range_compatibility(
                video,
                {"office_product_release_ids": "PowerPoint2019Volume"},
                "auto",
            )

        self.assertEqual(video.read_bytes(), b"fixed-video")
        self.assertEqual(compatibility["action"], "applied")
        self.assertTrue(compatibility["reencoded"])
        self.assertIn("libx264", commands[0])
        self.assertIn("scale=in_range=pc:out_range=tv", commands[0])
        self.assertEqual(compatibility["audio_reencoded"], False)

    def test_static_qa_does_not_require_audio_artifacts(self) -> None:
        project = self.create_project("static-qa", "static_pptx")
        self.approve(project, "content")
        self.approve(project, "visual", "1")
        paths = project_paths(project)
        make_minimal_pptx(paths["static_pptx"], embedded_svg=True)
        pptx_production.record_visual_baseline(
            project,
            paths["static_pptx"],
            artifact_key="static_pptx",
            include_timing=False,
        )
        errors: list[str] = []
        warnings: list[str] = []
        with mock.patch.object(
            qa_presentation,
            "validate_full_project",
            return_value=([], []),
        ):
            _, report = qa_presentation.static_qa(
                project,
                errors,
                warnings,
            )
        self.assertEqual(errors, [])
        self.assertEqual(report["pptx"]["slides"], 1)
        self.assertFalse(paths["audio_timeline"].exists())

        state = load_state(paths["build_state"])
        before = qa_presentation.cache_fingerprint(project, "static", state)
        state["artifacts"].pop("static_pptx")
        write_object(paths["build_state"], state)
        after = qa_presentation.cache_fingerprint(project, "static", state)
        self.assertNotEqual(before, after)

    def test_animated_static_qa_requires_actual_ooxml_entrance_effect(self) -> None:
        project = self.create_project("animated-qa", "animated_pptx")
        self.approve(project, "content")
        self.approve(project, "visual", "1")
        paths = project_paths(project)

        make_minimal_pptx(paths["animated_pptx"], embedded_svg=True)
        pptx_production.record_visual_baseline(
            project,
            paths["animated_pptx"],
            artifact_key="animated_pptx",
            include_timing=True,
        )
        errors: list[str] = []
        warnings: list[str] = []
        with mock.patch.object(
            qa_presentation,
            "validate_full_project",
            return_value=([], []),
        ):
            qa_presentation.static_qa(project, errors, warnings)
        self.assertTrue(any("p:timing" in message for message in errors))

        write_one_page_animation_timing(project)
        make_animated_pptx(paths["animated_pptx"])
        pptx_production.record_visual_baseline(
            project,
            paths["animated_pptx"],
            artifact_key="animated_pptx",
            include_timing=True,
        )
        errors = []
        warnings = []
        with mock.patch.object(
            qa_presentation,
            "validate_full_project",
            return_value=([], []),
        ):
            _, report = qa_presentation.static_qa(project, errors, warnings)
        self.assertEqual(errors, [])
        self.assertTrue(report["pptx"]["animations"][0]["matched"])

    def test_animation_evidence_rejects_malformed_filters_clicks_and_duration(self) -> None:
        pptx = self.root / "animation-evidence.pptx"
        make_animated_pptx(pptx)
        with zipfile.ZipFile(pptx) as archive:
            valid = archive.read("ppt/slides/slide1.xml")
        beats = [{"id": "title", "effect": "fade"}]
        timing_beats = [
            {"id": "title", "effect": "fade", "duration_ms": 280}
        ]
        evidence, errors = qa_presentation.animation_slide_evidence(
            valid,
            page=1,
            beats=beats,
            timing_beats=timing_beats,
        )
        self.assertEqual(errors, [])
        self.assertTrue(evidence["matched"])

        mutations = (
            valid.replace(b'filter="fade"', b'filter="fade(bogus"'),
            valid.replace(b'dur="280"', b'dur="999999999"'),
            valid.replace(
                b'<p:tnLst><p:par>',
                b'<p:tnLst><p:cond evt="onClick"/><p:par>',
            ),
            valid.replace(
                b'<p:cNvPr id="2" name="s01_title"/>',
                b'<p:cNvPr id="2" name="s01_title"/>'
                b'<p:cNvPr id="3" name="s01_title"/>',
            ),
            valid.replace(
                b"</p:timing>",
                b'<p:animEffect transition="in" filter="fade(bogus"/>'
                b"</p:timing>",
            ),
            valid.replace(
                b"</p:timing>",
                b'<p:cond evt="onClick"/></p:timing>',
            ),
        )
        for payload in mutations:
            with self.subTest(payload=payload[:80]):
                evidence, errors = qa_presentation.animation_slide_evidence(
                    payload,
                    page=1,
                    beats=beats,
                    timing_beats=timing_beats,
                )
                self.assertTrue(errors)
                self.assertFalse(evidence["matched"])

    def test_standard_fingerprint_binds_current_static_qa_report(self) -> None:
        project = self.create_project("standard-static-dependency", "narrated_pptx")
        state = load_state(project_paths(project)["build_state"])
        errors: list[str] = []
        warnings: list[str] = []
        with mock.patch.object(
            qa_presentation,
            "validate_full_project",
            return_value=([], []),
        ):
            qa_presentation.standard_qa(
                project,
                errors,
                warnings,
                cached_audio_report={"fingerprint": "audio", "evidence": {}},
                cached_static_report=None,
            )
        self.assertTrue(
            any("no current static QA PASS" in message for message in errors)
        )
        without_static = qa_presentation.cache_fingerprint(
            project,
            "standard",
            state,
        )
        static_fingerprint = qa_presentation.cache_fingerprint(
            project,
            "static",
            state,
        )
        report_path = project / "video" / "qa_static.json"
        write_object(
            report_path,
            {
                "schema_version": 1,
                "level": "static",
                "status": "passed",
                "fingerprint": static_fingerprint,
                "errors": [],
                "warnings": [],
                "evidence": {},
            },
        )
        state["qa"]["static"] = {
            "status": "passed",
            "fingerprint": static_fingerprint,
            "report": "video/qa_static.json",
            "report_sha256": file_hash(report_path),
        }
        write_object(project_paths(project)["build_state"], state)
        with_static = qa_presentation.cache_fingerprint(
            project,
            "standard",
            state,
        )
        self.assertNotEqual(without_static, with_static)
        report_path.write_bytes(report_path.read_bytes() + b"\n")
        tampered = qa_presentation.cache_fingerprint(project, "standard", state)
        self.assertNotEqual(with_static, tampered)

    def test_voice_configuration_does_not_require_visual_baseline(self) -> None:
        project = self.create_project("voice-config", "narrated_pptx")
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
        with mock.patch.object(rebuild_presentation, "run_script") as run, mock.patch.object(
            rebuild_presentation,
            "require_current_visual_baseline",
        ) as require_baseline:
            self.assertEqual(rebuild_presentation.rebuild_audio(args), 0)
        run.assert_called_once()
        require_baseline.assert_not_called()

    def test_voice_configuration_survives_invalid_visual_manifest(self) -> None:
        project = self.create_project("voice-invalid-visual", "narrated_pptx")
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
        project = self.create_project("voice-message", "narrated_pptx")
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

    def test_release_cache_binds_powerpoint_export_report_file(self) -> None:
        project = self.create_project("release-report-cache", "video")
        self.approve(project, "content")
        self.prepare_narration_review(project)
        paths = project_paths(project)
        paths["video"].parent.mkdir(parents=True, exist_ok=True)
        paths["video"].write_bytes(b"video-bytes")
        export_report = project / "video" / "powerpoint_export.json"
        export_report.write_text('{"status":"ok"}\n', encoding="utf-8")
        state = load_state(paths["build_state"])
        state["powerpoint"]["video_exported"] = {
            "status": "passed",
            "video_sha256": file_hash(paths["video"]),
            "pptx_sha256": "0" * 64,
            "report": "video/powerpoint_export.json",
            "report_sha256": file_hash(export_report),
        }
        before = qa_presentation.cache_fingerprint(project, "release", state)
        export_report.unlink()
        after = qa_presentation.cache_fingerprint(project, "release", state)
        self.assertNotEqual(before, after)

    def test_video_probe_reports_missing_ffprobe_as_unavailable(self) -> None:
        video = self.root / "sample.mp4"
        video.write_bytes(b"not-a-real-video")
        with mock.patch.object(qa_presentation.shutil, "which", return_value=None):
            report = qa_presentation.probe_video(video)
        self.assertEqual(report["ffprobe"], "unavailable")
        self.assertNotIn("duration_seconds", report)

    def test_video_export_rejects_forged_standard_qa_state(self) -> None:
        project = self.create_project("forged-standard", "video")
        self.approve(project, "content")
        self.approve(project, "visual", "1")
        self.prepare_narration_review(project)
        self.approve(project, "narration")
        paths = project_paths(project)
        state = load_state(paths["build_state"])
        fingerprint = qa_presentation.cache_fingerprint(
            project,
            "standard",
            state,
        )
        state["qa"]["standard"] = {
            "status": "passed",
            "fingerprint": fingerprint,
            "report": "video/qa_standard.json",
            "report_sha256": "0" * 64,
        }
        write_object(paths["build_state"], state)

        with mock.patch.object(powerpoint_production, "run_powershell") as run:
            with self.assertRaisesRegex(RuntimeError, "standard QA"):
                powerpoint_production.export_video_command(
                    argparse.Namespace(
                        project=project,
                        input_pptx=None,
                        output_mp4=None,
                        timeout_minutes=90,
                        vertical_resolution=1080,
                        frames_per_second=30,
                        quality=100,
                    )
                )
            run.assert_not_called()

    def test_content_rejects_missing_sha_bound_review(self) -> None:
        project = self.create_project(
            "missing-review",
            "static_pptx",
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
