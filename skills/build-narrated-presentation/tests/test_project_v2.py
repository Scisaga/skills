from __future__ import annotations

import argparse
import hashlib
import json
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
import pptx_production
import qa_presentation
from build_manifest import build_manifest, render_review
from production_common import (
    approval_status,
    load_object,
    load_project_config,
    project_paths,
    write_object,
)
from validate_project import validate


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


class ProjectV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "source.md"
        self.source.write_text(
            "# 项目计划\n\n## 目标\n\n生成一页可审查的演示。\n",
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
    ) -> Path:
        project = self.root / name
        gate = {
            "schema_version": 1,
            "passed": True,
            "document": str(self.source),
            "document_sha256": self.source_sha,
            "profile": "auto",
            "metrics": {},
            "findings": [],
        }
        source_metadata = {
            "mode": "document",
            "document": str(self.source),
            "document_sha256": self.source_sha,
            "profile": "auto",
            "review": "input-review.json",
            "gate_report": "input-gate.json",
            "quality_gate": "passed",
        }
        init_project.copy_template(
            project,
            project_name=name,
            deliverable=deliverable,
            page_script_source=self.source,
            template_source=template_source,
            visual_style="project-default",
            visual_theme="light",
            force=False,
            source_metadata=source_metadata,
            review_source=None,
            gate_report=gate,
        )
        if template_source is None:
            make_minimal_pptx(project / "template.pptx")
        return project

    def approve(self, project: Path, stage: str, pages: str | None = None) -> None:
        approve_project.approve_command(
            argparse.Namespace(
                project=project,
                stage=stage,
                approved_by="tester",
                pages=pages,
            )
        )

    def prepare_narration_review(self, project: Path) -> None:
        paths = project_paths(project)
        manifest = load_object(paths["manifest"])
        director = load_object(paths["director"])
        voice = load_object(paths["voice_profile"])
        merged = build_manifest(manifest, director, voice)
        write_object(paths["manifest"], merged)
        (project / "video" / "narration_review.md").write_text(
            render_review(merged),
            encoding="utf-8",
        )

    def test_initialization_writes_only_v2_for_all_deliverables(self) -> None:
        supplied_template = self.root / "supplied.pptx"
        make_minimal_pptx(supplied_template)
        for index, deliverable in enumerate(
            (
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
                    template_source=supplied_template if index == 0 else None,
                )
                config = load_project_config(project)
                self.assertEqual(config["schema_version"], 2)
                self.assertEqual(config["deliverable"], deliverable)
                self.assertIn("narrated_pptx", config["outputs"])
                self.assertTrue((project / "page-script.md").is_file())
        supplied = self.root / "project-0"
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

    def test_current_v2_static_contract_validates_without_audio(self) -> None:
        project = self.create_project("schema-current", "static_pptx")
        self.approve(project, "content")
        self.approve(project, "visual", "1")
        with mock.patch(
            "validate_project.gate_document",
            return_value={
                "document_sha256": self.source_sha,
                "findings": [],
            },
        ):
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
                pptx_production.assemble_command(
                    argparse.Namespace(project=project, adapter=None)
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

    def test_static_qa_does_not_require_audio_artifacts(self) -> None:
        project = self.create_project("static-qa", "static_pptx")
        self.approve(project, "content")
        self.approve(project, "visual", "1")
        paths = project_paths(project)
        make_minimal_pptx(paths["static_pptx"], embedded_svg=True)
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


if __name__ == "__main__":
    unittest.main()
