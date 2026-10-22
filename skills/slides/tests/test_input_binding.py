from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import approve_project
import audio_production
import init_project
import prepare_narration
import refresh_input_gate
from narration_performance import audit_narration_performance
from page_script_contract import audit_page_script
from production_common import (
    approval_status,
    chapter_groups,
    load_object,
    load_project_config,
    load_voice_profile,
    project_paths,
    render_chapter_ssml,
    normalize_director_pages,
    write_object,
)
from validate_input_document import (
    gate_document,
    inspect_document,
    main as validate_input_main,
    review_template,
)
from validate_project import validate


SYNTHETIC_REPORT_TITLE = "虚构技术系统评审｜测试稿"
SYNTHETIC_PAGE_COUNT = 8
SYNTHETIC_STRENGTH_MPA = 731
SYNTHETIC_COMPONENT_SIZE_MM = "420×260"


def render_page_script(bodies: list[str]) -> str:
    lines = [f"# {SYNTHETIC_REPORT_TITLE}", ""]
    for page, body in enumerate(bodies, 1):
        lines.extend(
            [
                f"## 第 {page} 页｜中文页面标题 {page} · {25 + page * 5} 秒",
                "",
                body,
                "",
                "---",
                "",
            ]
        )
    return "\n".join(lines)


class InputBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "prepared-narration.md"
        bodies = [
            (
                f"第{page}页完整说明本页在整套汇报中的作用、需要观众记住的判断、"
                "工程背景、适用边界和承接关系。这些句子组成可以直接口述的完整正文，"
                "不能被页面标题、核心结论或几行摘要替代；同时保留必要的事实限定和"
                "面向下一页的自然过渡。"
            )
            for page in range(1, SYNTHETIC_PAGE_COUNT + 1)
        ]
        bodies[0] += (
            f"虚构材料强度设为 {SYNTHETIC_STRENGTH_MPA} MPa，"
            "这个合成测试数字必须随正文保留。"
        )
        bodies[1] += (
            f"虚构构件尺寸设为 {SYNTHETIC_COMPONENT_SIZE_MM} mm，"
            "这个合成测试尺寸也必须随正文保留。"
        )
        self.source.write_text(
            render_page_script(bodies),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def initialize_audio_project(self, name: str = "audio-project") -> Path:
        project = self.root / name
        result = init_project.main(
            [
                "--output",
                str(project),
                "--name",
                name,
                "--deliverable",
                "narration_audio",
                "--input-document",
                str(self.source),
            ]
        )
        self.assertEqual(result, 0)
        return project

    def approve(self, project: Path, stage: str) -> None:
        approve_project.approve_command(
            argparse.Namespace(
                project=project,
                stage=stage,
                approved_by="tester",
                pages=None,
                allow_substantial_rewrite=False,
            )
        )

    def test_chinese_multi_page_narration_skips_plan_semantic_gate(self) -> None:
        preflight = inspect_document(self.source, "auto")

        self.assertTrue(preflight["passed"])
        self.assertEqual(preflight["profile"], "page-narration")
        self.assertEqual(
            preflight["metrics"]["pages"],
            SYNTHETIC_PAGE_COUNT,
        )
        self.assertFalse(preflight["semantic_review_required"])

        gate = gate_document(self.source, "auto", None)
        self.assertTrue(gate["passed"])
        self.assertFalse(gate["semantic_review_required"])
        self.assertIsNone(gate["review"])
        cli_gate = self.root / "cli-gate.json"
        self.assertEqual(
            validate_input_main(
                [
                    "gate",
                    "--document",
                    str(self.source),
                    "--json-output",
                    str(cli_gate),
                ]
            ),
            0,
        )
        self.assertTrue(cli_gate.is_file())

        review_template_path = self.root / "should-not-exist-review.json"
        self.assertEqual(
            validate_input_main(
                [
                    "template",
                    "--document",
                    str(self.source),
                    "--output",
                    str(review_template_path),
                ]
            ),
            0,
        )
        self.assertFalse(review_template_path.exists())

        unnecessary_review = self.root / "unnecessary-review.json"
        unnecessary_review.write_text("{}\n", encoding="utf-8")
        ignored_review_gate = gate_document(
            self.source,
            "auto",
            unnecessary_review,
        )
        self.assertTrue(ignored_review_gate["passed"])
        self.assertIsNone(ignored_review_gate["review"])
        self.assertTrue(
            any(row["code"] == "SEM012" for row in ignored_review_gate["findings"])
        )
        ignored_review_project = self.root / "ignored-review-project"
        self.assertEqual(
            init_project.main(
                [
                    "--output",
                    str(ignored_review_project),
                    "--name",
                    "ignored-review-project",
                    "--deliverable",
                    "narration_audio",
                    "--input-document",
                    str(self.source),
                    "--input-review",
                    str(unnecessary_review),
                ]
            ),
            0,
        )
        self.assertFalse((ignored_review_project / "input-review.json").exists())
        self.assertIsNone(
            load_project_config(ignored_review_project)["source"]["review"]
        )

        short = self.root / "short.md"
        short.write_text(
            "## 第 1 页｜短稿 · 20 秒\n\n"
            "这是一段已经整理好、可以直接口述且超过二十个字符的逐页正文。\n",
            encoding="utf-8",
        )
        self.assertTrue(inspect_document(short, "auto")["passed"])

        english = self.root / "english.md"
        english.write_text(
            "## PAGE 1/1 | Ready narration · 20 秒\n\n"
            "This is a complete page narration with enough content for synthesis.\n",
            encoding="utf-8",
        )
        self.assertTrue(inspect_document(english, "auto")["passed"])

        marker_terms = self.root / "marker-terms.md"
        marker_terms.write_text(
            "## PAGE 1/1 | Rendering terminology\n\n"
            "This narration explains why speaker-notes and source_svg are "
            "implementation terms, without embedding any rendering contract.\n",
            encoding="utf-8",
        )
        marker_terms_result = inspect_document(marker_terms, "auto")
        self.assertEqual(marker_terms_result["profile"], "page-narration")
        self.assertTrue(marker_terms_result["passed"])

        wrong_total = self.root / "wrong-total.md"
        wrong_total.write_text(
            "## PAGE 1/2 | Wrong total\n\n"
            "This page has complete narration, but the declared total is incorrect.\n",
            encoding="utf-8",
        )
        self.assertFalse(inspect_document(wrong_total, "auto")["passed"])

        rendered = self.root / "rendered.md"
        rendered.write_text(
            "## PAGE 1/1 | Rendered page\n\n"
            "<svg viewBox=\"0 0 1600 900\"></svg>\n"
            "<!-- speaker-notes: complete narration for the rendered page -->\n",
            encoding="utf-8",
        )
        self.assertEqual(
            inspect_document(rendered, "auto")["profile"],
            "presentation-source",
        )
        self.assertEqual(
            audit_page_script(
                rendered,
                source=rendered,
                enforce_source_fidelity=False,
            )["status"],
            "blocked",
        )
        declared_render = self.root / "declared-render.md"
        declared_render.write_text(
            "---\ndocument_type: presentation-source\n---\n\n"
            "## PAGE 1/1 | Missing render contract\n\n"
            "This is narration text, but required SVG and notes are absent.\n",
            encoding="utf-8",
        )
        declared_result = inspect_document(declared_render, "auto")
        self.assertEqual(declared_result["profile"], "presentation-source")
        self.assertFalse(declared_result["passed"])

        mislabeled_render = self.root / "mislabeled-render.md"
        mislabeled_render.write_text(
            "---\ndocument_type: page-narration\n---\n\n"
            "## PAGE 1/1 | Render markers must not enter TTS\n\n"
            "<!-- layout: visual -->\n"
            "![完整页](missing.svg)\n"
            "<!-- speaker-notes: This is the actual narration for the page. -->\n",
            encoding="utf-8",
        )
        mislabeled_result = inspect_document(mislabeled_render, "auto")
        self.assertEqual(mislabeled_result["profile"], "page-narration")
        self.assertFalse(mislabeled_result["passed"])

        fact_policy_narration = self.root / "fact-policy-narration.md"
        fact_policy_narration.write_text(
            "---\nfact_policy: 保留来源边界\n---\n\n"
            "## PAGE 1/1 | Ready narration\n\n"
            "This is a complete page narration with enough spoken text for synthesis.\n",
            encoding="utf-8",
        )
        fact_result = inspect_document(fact_policy_narration, "auto")
        self.assertEqual(fact_result["profile"], "page-narration")
        self.assertTrue(fact_result["passed"])

        missing_svg = self.root / "missing-svg.md"
        missing_svg.write_text(
            "---\ntarget_pages: 1\ncanvas: 1600x900\nfact_policy: 保留来源边界\n---\n\n"
            "## PAGE 1/1 | Missing local SVG\n\n"
            "<!-- layout: visual -->\n"
            "![完整页](does-not-exist.svg)\n"
            "<!-- speaker-notes: This is the actual narration for the page. -->\n",
            encoding="utf-8",
        )
        missing_svg_result = inspect_document(missing_svg, "auto")
        self.assertEqual(missing_svg_result["profile"], "presentation-source")
        self.assertFalse(missing_svg_result["passed"])
        self.assertTrue(
            any(
                finding["code"].startswith("PRS011A")
                for finding in missing_svg_result["findings"]
            )
        )

    def test_identity_initialization_preserves_source_bytes_and_empty_scaffold(self) -> None:
        project = self.initialize_audio_project()
        config = load_project_config(project)

        self.assertEqual((project / "page-script.md").read_bytes(), self.source.read_bytes())
        self.assertEqual((project / "inputs" / "source.md").read_bytes(), self.source.read_bytes())
        self.assertEqual(config["source"]["profile"], "page-narration")
        self.assertEqual(config["content"]["binding_mode"], "identity")
        self.assertEqual(
            config["content"]["page_count_at_init"],
            SYNTHETIC_PAGE_COUNT,
        )
        self.assertEqual(
            load_object(project / "video" / "animation_manifest.json")["slides"],
            [],
        )
        self.assertEqual(
            load_object(project / "video" / "narration_director.json")["pages"],
            [],
        )
        self.assertFalse((project / "assets").exists())
        self.assertFalse((project / "video" / "svg_layer_plan.json").exists())
        binding = load_object(project / config["content"]["binding_audit"])
        self.assertEqual(binding["binding_mode"], "identity")
        self.assertTrue(binding["fidelity"]["exact_byte_copy"])
        self.assertEqual(
            binding["page_script_origin_document"],
            str(self.source.resolve()),
        )

    def test_summary_cannot_replace_complete_page_narration(self) -> None:
        summary = self.root / "summary.md"
        summary.write_text(
            render_page_script(
                [
                    f"第{page}页只保留标题、核心结论和一句简短摘要说明。"
                    for page in range(1, SYNTHETIC_PAGE_COUNT + 1)
                ]
            ),
            encoding="utf-8",
        )

        audit = audit_page_script(summary, source=self.source)
        self.assertEqual(audit["status"], "blocked")
        self.assertTrue(audit["fidelity"]["low_retention_pages"])
        self.assertTrue(audit["fidelity"]["missing_engineering_numbers"])

        project = self.root / "summary-project"
        result = init_project.main(
            [
                "--output",
                str(project),
                "--name",
                "summary-project",
                "--deliverable",
                "narration_audio",
                "--input-document",
                str(self.source),
                "--page-script-source",
                str(summary),
            ]
        )
        self.assertEqual(result, 1)
        self.assertFalse((project / "project.json").exists())

        similar_version = self.root / "similar-v2.md"
        similar_version.write_text(
            self.source.read_text(encoding="utf-8").replace(
                "工程背景",
                "工程条件",
                1,
            ),
            encoding="utf-8",
        )
        strict_audit = audit_page_script(similar_version, source=self.source)
        self.assertEqual(strict_audit["status"], "blocked")
        authorized = audit_page_script(
            similar_version,
            source=self.source,
            allow_substantial_rewrite=True,
        )
        self.assertEqual(authorized["status"], "pass")
        adapted_project = self.root / "authorized-adapted"
        self.assertEqual(
            init_project.main(
                [
                    "--output",
                    str(adapted_project),
                    "--name",
                    "authorized-adapted",
                    "--deliverable",
                    "narration_audio",
                    "--input-document",
                    str(self.source),
                    "--page-script-source",
                    str(similar_version),
                    "--allow-substantial-rewrite",
                ]
            ),
            0,
        )
        adapted_config = load_project_config(adapted_project)
        self.assertEqual(adapted_config["content"]["binding_mode"], "adapted")
        adapted_binding = load_object(
            adapted_project / adapted_config["content"]["binding_audit"]
        )
        self.assertEqual(
            adapted_binding["page_script_origin_document"],
            str(similar_version.resolve()),
        )
        self.assertTrue(adapted_binding["rewrite_authorized"])
        self.approve(adapted_project, "content")
        self.assertTrue(approval_status(adapted_project, "content")[0])
        upgraded_binding = load_object(
            adapted_project / adapted_config["content"]["binding_audit"]
        )
        upgraded_binding["contract_version"] = 1
        write_object(
            adapted_project / adapted_config["content"]["binding_audit"],
            upgraded_binding,
        )
        self.approve(adapted_project, "content")
        self.approve(adapted_project, "content")
        self.assertEqual(refresh_input_gate.refresh(adapted_project), 0)
        self.approve(adapted_project, "content")
        self.assertTrue(approval_status(adapted_project, "content")[0])

    def test_page_script_requires_actual_spoken_text(self) -> None:
        image_only = self.root / "image-only.md"
        image_only.write_text(
            "## 第 1 页｜图片页 · 20 秒\n\n"
            "![这是一段很长但不应当被当作旁白正文的图片替代文字]"
            "(assets/a-very-long-rendered-technical-diagram-name.svg)\n",
            encoding="utf-8",
        )
        audit = audit_page_script(image_only)
        self.assertEqual(audit["status"], "blocked")
        self.assertEqual(audit["pages"][0]["body_characters"], 0)

    def test_adapted_plan_records_coverage_without_fake_fidelity_pass(self) -> None:
        plan = self.root / "plan.md"
        plan.write_text(
            (
                "# 虚构工程计划\n\n"
                f"目标是保留 {SYNTHETIC_STRENGTH_MPA} MPa 的合成测试边界，"
                "并说明验证路径和风险。\n"
            ),
            encoding="utf-8",
        )
        audit = audit_page_script(
            self.source,
            source=plan,
            enforce_source_fidelity=False,
        )
        self.assertEqual(audit["status"], "pass")
        self.assertEqual(
            audit["fidelity"]["comparison_mode"],
            "document-coverage",
        )
        self.assertIn("source_ngram_coverage", audit["fidelity"])

        lightweight_plan = self.root / "lightweight-plan.md"
        lightweight_plan.write_text(
            "---\ntitle: 技术汇报计划\ndocument_type: narrative-plan\n---\n\n"
            "# 技术汇报计划\n\n"
            + "这份计划描述技术背景、当前判断、材料边界和希望受众理解的重点。"
            * 12
            + "\n",
            encoding="utf-8",
        )
        preflight = inspect_document(lightweight_plan, "auto")
        self.assertTrue(preflight["passed"])
        self.assertTrue(preflight["semantic_review_required"])
        self.assertTrue(preflight["metrics"]["plan_semantics_deferred_to_review"])
        review = review_template(preflight)
        self.assertFalse(review["reviewer"]["attestation"])
        self.assertNotIn("blocking_findings", review)
        self.assertNotIn("revision_plan", review)
        self.assertEqual(len(review["categories"]), 4)
        review["reviewer"]["name"] = "tester"
        review["reviewer"]["attestation"] = True
        review["decision"] = "pass"
        document_lines = lightweight_plan.read_text(encoding="utf-8").splitlines()
        evidence_line = next(
            index
            for index, line in enumerate(document_lines, 1)
            if line.startswith("这份计划描述")
        )
        evidence_quote = "这份计划描述技术背景、当前判断、材料边界"
        for row in review["categories"].values():
            row["status"] = "pass"
            row["evidence"] = [
                {
                    "heading": "技术汇报计划",
                    "line": evidence_line,
                    "quote": evidence_quote,
                }
            ]
            row["issues"] = []
            row["required_changes"] = []
        review_path = self.root / "lightweight-review.json"
        review_path.write_text(
            json.dumps(review, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self.assertTrue(
            gate_document(
                lightweight_plan,
                "auto",
                review_path,
            )["passed"]
        )

    def test_narration_audio_does_not_require_visual_assets_or_approval(self) -> None:
        project = self.initialize_audio_project()
        self.assertFalse((project / "template.pptx").exists())

        self.approve(project, "content")
        self.assertEqual(validate(project, stage="content")[0], [])
        self.assertEqual(prepare_narration.prepare(project, force=False), 0)
        self.approve(project, "narration")

        self.assertTrue(approval_status(project, "content")[0])
        self.assertTrue(approval_status(project, "narration")[0])
        self.assertFalse(approval_status(project, "visual")[0])

        errors, warnings = validate(project, stage="narration_audio")
        self.assertEqual(errors, [])
        self.assertTrue(any("audio_timeline" in warning for warning in warnings))

        result = audio_production.synthesize_command(
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
        self.assertEqual(result, 0)
        self.assertFalse(project_paths(project)["template_working"].exists())

    def test_prepare_narration_compiles_audible_performance_variation(self) -> None:
        project = self.initialize_audio_project("directed-performance")
        self.approve(project, "content")
        prepare_narration.prepare(project, force=False)
        paths = project_paths(project)
        director = load_object(paths["director"])
        audit = audit_narration_performance(director)

        self.assertEqual(audit["status"], "pass")
        self.assertEqual(
            audit["metrics"]["page_count"],
            SYNTHETIC_PAGE_COUNT,
        )
        self.assertGreaterEqual(
            audit["metrics"]["unique_performance_signatures"],
            3,
        )
        self.assertGreaterEqual(audit["metrics"]["unique_intents"], 3)
        self.assertEqual(
            audit["metrics"]["pages_with_executable_cues"],
            SYNTHETIC_PAGE_COUNT,
        )

        pages = normalize_director_pages(director)
        voice = load_voice_profile(paths["voice_profile"])
        prosody = set()
        for chapter in chapter_groups(pages):
            ssml = render_chapter_ssml(chapter, voice)
            prosody.update(
                re.findall(r'<prosody rate="([^"]+)" pitch="([^"]+)"', ssml)
            )
        self.assertGreaterEqual(len(prosody), 3)

        review = (project / "video" / "narration_review.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("声音与编排摘要", review)
        self.assertIn("编排依据与修正", review)
        self.assertIn("最终语速", review)
        self.assertIn("最终音高", review)
        manifest = load_object(paths["manifest"])
        self.assertEqual(manifest["slides"][0]["target_seconds"], 30)

    def test_narration_approval_rejects_uniform_effective_performance(self) -> None:
        project = self.initialize_audio_project("uniform-performance")
        self.approve(project, "content")
        prepare_narration.prepare(project, force=False)
        paths = project_paths(project)
        director = load_object(paths["director"])
        intents = ("opening", "explanation", "comparison", "closing")
        for index, page in enumerate(director["pages"]):
            page["intent"] = intents[index % len(intents)]
            page["direction"] = f"第{index + 1}页使用不同的书面语气说明。"
            page["rationale"] = f"第{index + 1}页具有单独的文字说明，但参数故意保持一致。"
            for segment_index, segment in enumerate(page["segments"]):
                segment["rate"] = "+0%"
                segment["pitch"] = "+0st"
                segment["pause_after_ms"] = (
                    0 if segment_index == len(page["segments"]) - 1 else 100
                )
        write_object(paths["director"], director)

        audit = audit_narration_performance(director)
        self.assertEqual(audit["status"], "blocked")
        self.assertTrue(
            any("audible profiles" in error for error in audit["errors"])
        )
        with self.assertRaisesRegex(
            RuntimeError,
            "Narration performance contract",
        ):
            self.approve(project, "narration")

    def test_performance_plan_overrides_cues_but_cannot_change_text(self) -> None:
        project = self.initialize_audio_project("performance-plan")
        self.approve(project, "content")
        prepare_narration.prepare(project, force=False)
        paths = project_paths(project)
        director = load_object(paths["director"])
        original_text = [
            [segment["text"] for segment in page["segments"]]
            for page in director["pages"]
        ]
        plan = {
            "schema_version": 1,
            "pages": [
                {
                    "page": page["page"],
                    "intent": page["intent"],
                    "direction": page["direction"],
                    "rationale": page["rationale"],
                    "segments": [
                        {
                            "rate": segment["rate"],
                            "pitch": segment.get("pitch", "+0st"),
                            "pause_after_ms": segment["pause_after_ms"],
                        }
                        for segment in page["segments"]
                    ],
                }
                for page in director["pages"]
            ],
        }
        plan_path = self.root / "performance-plan.json"
        plan["pages"][0]["segments"][0]["text"] = "禁止从计划改写正文"
        plan_path.write_text(
            json.dumps(plan, ensure_ascii=False),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "must not contain text"):
            prepare_narration.prepare(
                project,
                force=True,
                performance_plan=plan_path,
            )

        plan["pages"][0]["segments"][0].pop("text")
        plan["pages"][0]["segments"][0]["rate"] = "-9%"
        plan_path.write_text(
            json.dumps(plan, ensure_ascii=False),
            encoding="utf-8",
        )
        prepare_narration.prepare(
            project,
            force=True,
            performance_plan=plan_path,
        )
        updated = load_object(paths["director"])
        self.assertEqual(updated["pages"][0]["segments"][0]["rate"], "-9%")
        self.assertEqual(
            [
                [segment["text"] for segment in page["segments"]]
                for page in updated["pages"]
            ],
            original_text,
        )

    def test_director_cannot_silently_summarize_page_script(self) -> None:
        project = self.initialize_audio_project()
        self.approve(project, "content")
        prepare_narration.prepare(project, force=False)
        paths = project_paths(project)
        director = load_object(paths["director"])
        director["pages"][0]["segments"] = [
            {"text": "这里被错误替换成摘要。", "rate": "+0%", "pause_after_ms": 0}
        ]
        write_object(paths["director"], director)

        with self.assertRaisesRegex(RuntimeError, "Narration source binding"):
            self.approve(project, "narration")

    def test_identity_edit_requires_explicit_adapted_transition(self) -> None:
        project = self.initialize_audio_project()
        page_script = project / "page-script.md"
        page_script.write_text(
            page_script.read_text(encoding="utf-8").replace(
                "工程背景",
                "工程条件",
                1,
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(RuntimeError, "Page script contract"):
            self.approve(project, "content")
        approve_project.approve_command(
            argparse.Namespace(
                project=project,
                stage="content",
                approved_by="tester",
                pages=None,
                allow_substantial_rewrite=True,
            )
        )
        config = load_project_config(project)
        self.assertEqual(config["content"]["binding_mode"], "adapted")
        self.assertEqual(validate(project, stage="content")[0], [])

    def test_configure_voice_refreshes_derived_review(self) -> None:
        project = self.initialize_audio_project()
        self.approve(project, "content")
        prepare_narration.prepare(project, force=False)
        result = audio_production.configure_voice_command(
            argparse.Namespace(
                project=project,
                voice="zh-CN-XiaoxiaoNeural",
                rate="+5%",
                pitch=None,
                dry_run=False,
            )
        )
        self.assertEqual(result, 0)
        manifest = load_object(project_paths(project)["manifest"])
        self.assertEqual(manifest["voice"]["name"], "zh-CN-XiaoxiaoNeural")
        self.assertEqual(manifest["voice"]["rate"], "+5%")
        self.approve(project, "narration")

    def test_content_approval_binds_gate_and_binding_evidence(self) -> None:
        project = self.initialize_audio_project()
        self.approve(project, "content")
        paths = project_paths(project)
        binding = paths["binding_audit"]
        original_binding = binding.read_bytes()
        binding.write_bytes(original_binding + b"\n")
        self.assertFalse(approval_status(project, "content")[0])

        binding.write_bytes(original_binding)
        self.approve(project, "content")
        gate = project / "input-gate.json"
        gate.write_bytes(gate.read_bytes() + b"\n")
        self.assertFalse(approval_status(project, "content")[0])


if __name__ == "__main__":
    unittest.main()
