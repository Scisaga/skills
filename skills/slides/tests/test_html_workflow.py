from __future__ import annotations

import argparse
import importlib.util
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from approve_project import approve_command
from browser_render import browser_page, open_deck
from html_export import export_pages, export_video
from html_fonts import catalog_files, source_path
from html_production import assemble_html, publish_artifacts, require_current_html
from html_timeline import compile_timeline
from init_project import main as init_project
from migrate_html import migrate_html
from prepare_narration import prepare
from production_common import approval_status, file_hash, load_object, project_paths, write_object
from qa_presentation import qa_command
from validate_project import validate


SOURCE = """## 第 1 页｜结构方案

这一页说明技术方案的组成。先对照基础模块，再看数据如何进入协同流程，最后解释关键输出怎样支持下一步工作。

## 第 2 页｜流程演示

第二页汇总两个阶段。第一阶段记录业务数据和关键状态，第二阶段结合分析结果推进决策并完成反馈。
"""

SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 900">
  <defs><linearGradient id="wash"><stop stop-color="#a2e5ff"/></linearGradient></defs>
  <rect x="120" y="160" width="480" height="260" fill="url(#wash)"/>
  <g id="title"><text x="150" y="220" font-family="Arial, sans-serif" font-size="48">技术资料 V1</text></g>
  <g id="late"><text x="150" y="330" font-family="'Source Han Serif SC', serif" font-size="48">图示</text></g>
  <text x="150" y="500" font-family="'JetBrains Mono', monospace" font-size="32">print(123)</text>
</svg>"""


def make_project(root: Path, mode: str = "animated_html") -> Path:
    root.mkdir()
    source = root / "source.md"
    source.write_text(SOURCE, encoding="utf-8")
    project = root / "本地 演示"
    result = init_project([
        "--output", str(project), "--name", "离线演示",
        "--deliverable", mode, "--input-document", str(source),
    ])
    if result:
        raise AssertionError("test source did not pass input gate")
    paths = project_paths(project)
    manifest = load_object(paths["manifest"])
    manifest["slide_count"] = 2
    manifest["slides"] = []
    for page in (1, 2):
        source_svg = f"assets/{page:02d}.svg"
        (project / source_svg).write_text(SVG, encoding="utf-8")
        manifest["slides"].append({
            "page": page, "source_svg": source_svg,
            "beats": [
                {"id": "title", "effect": "fade"},
                {"id": "late", "effect": "wipe_right", "start_ms": 3200, "duration_ms": 240},
            ],
        })
    write_object(paths["manifest"], manifest)
    approve_command(argparse.Namespace(
        project=project, stage="content", approved_by="test", pages=None,
        allow_substantial_rewrite=False,
    ))
    return project


class TimelineAndMigrationTests(unittest.TestCase):
    def test_page_cues_share_one_millisecond_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = {"timing": Path(temp) / "timing.json"}
            config = {"deliverable": "animated_html", "seconds_per_page": 4}
            cue = {"id": "title", "effect": "fade", "start_ms": 3200, "duration_ms": 250}
            manifest = {"slides": [
                {"page": page, "beats": [cue.copy()]} for page in (1, 2)
            ]}
            timeline, audio = compile_timeline(config, manifest, paths)
            self.assertEqual(timeline["slides"][0]["beats"][0]["start_ms"], 3200)
            self.assertEqual(timeline["slides"][1]["start_ms"], 4250)
            self.assertEqual(timeline["total_ms"], 8250)
            self.assertEqual(audio, [])
            config["seconds_per_page"] = 3
            with self.assertRaisesRegex(ValueError, r"1 页分组 title"):
                compile_timeline(config, manifest, paths)

    def test_migration_reuses_source_and_content_approval_for_each_legacy_mode(self) -> None:
        targets = {
            "static_pptx": "static_html", "animated_pptx": "animated_html",
            "narrated_pptx": "narrated_html", "video": "narrated_html",
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = make_project(root / "original")
            config_path = project / "project.json"
            config = load_object(config_path)
            config["template"]["working"] = "template.pptx"
            for legacy, mode in targets.items():
                with self.subTest(legacy=legacy):
                    config["deliverable"] = legacy
                    write_object(config_path, config)
                    before = file_hash(config_path)
                    output = root / legacy
                    report = migrate_html(project, output)
                    self.assertEqual(report["deliverable"], mode)
                    self.assertEqual(report["approvals_reused"], ["content"])
                    expected_missing = ["video/audio_timeline.json", "video/audio/01.mp3", "video/audio/02.mp3"]
                    self.assertEqual(report["missing"], expected_missing if mode == "narrated_html" else [])
                    self.assertEqual(file_hash(config_path), before)
                    self.assertTrue(approval_status(output, "content")[0])
                    self.assertFalse(approval_status(output, "visual")[0])
                    self.assertEqual((output / "assets/01.svg").read_text(encoding="utf-8"), SVG)

    def test_narrated_contract_validates_visual_and_narration_together(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp) / "narrated", "narrated_html")
            prepare(project, force=False)
            errors, warnings = validate(project)
            self.assertEqual(errors, [])
            self.assertTrue(any("audio_timeline.json" in warning for warning in warnings))

    def test_failed_publish_restores_previous_group_of_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            originals = [root / "original", root / "report"]
            for path in originals:
                path.write_text("previous")
            staged = [root / "first", root / "second"]
            for path in staged:
                path.write_text("new")
            with self.assertRaisesRegex(RuntimeError, "failed state write"):
                with publish_artifacts(list(zip(staged, originals, strict=True))):
                    raise RuntimeError("failed state write")
            self.assertEqual([path.read_text() for path in originals], ["previous", "previous"])


@unittest.skipUnless(
    importlib.util.find_spec("playwright") and all(source_path(item).is_file() for item in catalog_files().values()),
    "requires bootstrap --stage static",
)
class BrowserWorkflowTests(unittest.TestCase):
    def test_offline_fonts_delayed_wipe_exports_and_failed_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = make_project(root / "project")
            approve_command(argparse.Namespace(
                project=project, stage="visual", pages="1,2", approved_by="test",
                allow_substantial_rewrite=False,
            ))
            record = assemble_html(project)
            self.assertEqual({font["family"] for font in record["fonts"]}, {
                "Inter", "Source Han Sans SC", "Source Han Serif SC", "JetBrains Mono",
            })
            self.assertEqual(qa_command(argparse.Namespace(project=project, level="static", force=False)), 0)
            paths = project_paths(project)
            unpack = root / "解压 空格"
            with zipfile.ZipFile(paths["html_zip"]) as package:
                package.extractall(unpack)
            with browser_page() as page:
                open_deck(page, unpack / "index.html")
                self.assertEqual(page.evaluate("document.fonts.status"), "loaded")
                page.evaluate("window.slides.renderAt(3100)")
                target = page.locator('.page[data-page="1"] [data-beat="late"]')
                self.assertEqual(target.evaluate("el => getComputedStyle(el).visibility"), "hidden")
                page.evaluate("window.slides.renderAt(3320)")
                self.assertIn("50%", target.evaluate("el => getComputedStyle(el).clipPath"))
                page.evaluate("window.slides.renderAt(3600)")
                self.assertEqual(target.evaluate("el => getComputedStyle(el).clipPath"), "none")
                ids = page.locator("svg defs [id]").evaluate_all("els => els.map(el => el.id)")
                self.assertEqual(len(set(ids)), 2)
            pdf = root / "selected.pdf"
            self.assertEqual(export_pages(argparse.Namespace(
                project=project, pages="2,1", format="pdf", output=pdf,
            )), 0)
            self.assertTrue(pdf.read_bytes().startswith(b"%PDF"))
            paths["video"].write_bytes(b"previous video")
            with mock.patch("html_export.ffmpeg_tool", return_value="ffprobe"), mock.patch(
                "html_export.capture_video", side_effect=RuntimeError("encode failed"),
            ):
                with self.assertRaisesRegex(RuntimeError, "encode failed"):
                    export_video(argparse.Namespace(project=project, output_mp4=None))
            self.assertEqual(paths["video"].read_bytes(), b"previous video")
            before = file_hash(paths["html_zip"])
            manifest = load_object(paths["manifest"])
            manifest["slides"][0]["beats"][1]["start_ms"] = 9000
            write_object(paths["manifest"], manifest)
            with self.assertRaisesRegex(ValueError, "第 1 页分组 late"):
                assemble_html(project)
            self.assertEqual(file_hash(paths["html_zip"]), before)
            with self.assertRaisesRegex(RuntimeError, "已过期"):
                require_current_html(project)


if __name__ == "__main__":
    unittest.main()
