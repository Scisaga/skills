#!/usr/bin/env python3
"""Copy the reusable inputs of a v2 presentation into a new HTML project."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Sequence
from xml.etree import ElementTree as ET

from html_fonts import ALIASES
from init_project import TEMPLATE_ROOT, safe_filename
from production_common import (
    LEGACY_DELIVERABLES,
    PROJECT_SCHEMA_VERSION,
    approval_status,
    load_object,
    load_project_config,
    load_state,
    project_paths,
    write_object,
)
from qa_presentation import audio_qa


AUDIO_ARTIFACTS = ("audio", "audio_voice_sha256", "audio_synthesis", "audio_fallback_reason")


def migrate_html(old: Path, output: Path, style: Path | None = None) -> dict:
    old, output = old.resolve(), output.resolve()
    config = load_object(old / "project.json")
    mode = LEGACY_DELIVERABLES.get(config.get("deliverable"))
    if config.get("schema_version") != PROJECT_SCHEMA_VERSION or mode is None:
        raise ValueError("migrate-html 需要 v2 PPTX 或旧 video 项目目录")
    if output.exists() or output.is_relative_to(old) or old.is_relative_to(output):
        raise ValueError("迁移目标须是独立且未创建的目录")
    if style is not None and (not style.is_file() or style.suffix.lower() != ".css"):
        raise ValueError("--template-source 须为有效的 .css 文件")

    report = {"old_project": str(old), "deliverable": mode, "missing": [],
              "font_mappings": {}, "approvals_reused": [], "audio_cache": False}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as work:
        project = Path(work) / "project"
        project.mkdir()

        def copy_file(value: str, *, required: bool = False) -> str:
            source = (old / value).resolve()
            if not source.is_relative_to(old):
                raise ValueError(f"迁移文件须在原项目目录内 {value!r}")
            relative = source.relative_to(old).as_posix()
            if not source.is_file():
                if required:
                    raise FileNotFoundError(source)
                report["missing"].append(relative)
                return relative
            destination = project / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            return relative

        def copy_tree(path: str) -> None:
            directory = (old / path).resolve()
            if not directory.is_relative_to(old):
                raise ValueError(f"迁移目录须在原项目目录内 {path!r}")
            for source in directory.rglob("*"):
                if source.is_file() and (
                    source.suffix.lower() != ".pptx" and not source.name.startswith(".env")
                ):
                    copy_file(str(source.relative_to(old)))

        for field in ("document", "gate_report", "review"):
            value = config["source"].get(field)
            if value:
                config["source"][field] = copy_file(value, required=field == "document")
        for field in ("page_script", "binding_audit"):
            value = config["content"].get(field)
            if value:
                config["content"][field] = copy_file(value, required=field == "page_script")
        copy_tree(config["paths"].get("assets", "assets"))
        copy_tree("video/layers")
        for relative in (
            "input-gate.md", "video/animation_manifest.json", "video/svg_layer_plan.json",
            "video/fast_animation_timing.json", "video/narration_director.json",
            "video/narration_review.md", "video/audio_timeline.json",
        ):
            if (old / relative).is_file():
                copy_file(relative)
        if mode == "narrated_html":
            for relative in ("video/audio", "video/scripts"):
                copy_tree(relative)

        if "voice_profile" in config["paths"]:
            config["paths"]["voice_profile"] = copy_file(config["paths"]["voice_profile"])
        old_state = load_state(old / config["paths"]["build_state"])
        config["paths"]["build_state"] = "video/build_state.json"
        config["deliverable"] = mode
        config["template"] = {
            "mode": "provided" if style else "generated",
            "source": "inputs/template-source.css" if style else None,
            "working": "template.css",
            "safe_area": config["template"]["safe_area"],
        }
        name = safe_filename(config["name"])
        config["outputs"] = {
            "html_dir": f"deliverables/{name}_网页",
            "html_zip": f"deliverables/{name}_网页.zip",
            "video": f"deliverables/{name}_演示.mp4",
        }
        shutil.copy2(style or TEMPLATE_ROOT / "template.css", project / "template.css")
        if style:
            preserved = project / "inputs" / "template-source.css"
            preserved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(style, preserved)
        write_object(project / "project.json", config)
        load_project_config(project)
        paths = project_paths(project, config)
        template = TEMPLATE_ROOT / "video"
        for key, filename in (("manifest", "animation_manifest.json"), ("director", "narration_director.json")):
            if not paths[key].is_file():
                report["missing"].append(paths[key].relative_to(project).as_posix())
                shutil.copy2(template / filename, paths[key])
        adapt_visuals(project, paths, copy_file, report, mode != "static_html")
        pending = load_state(paths["build_state"])
        for stage in ("content", "narration"):
            if stage in old_state["approvals"] and (stage == "content" or mode == "narrated_html"):
                pending["approvals"][stage] = old_state["approvals"][stage]
                if approval_status(project, stage, pending)[0]:
                    report["approvals_reused"].append(stage)
                else:
                    pending["approvals"].pop(stage)
        if mode == "narrated_html":
            if not paths["audio_timeline"].is_file():
                report["missing"].append(paths["audio_timeline"].relative_to(project).as_posix())
            for slide in load_object(paths["manifest"])["slides"]:
                audio = paths["audio_dir"] / f"{slide['page']:02d}.mp3"
                if not audio.is_file():
                    report["missing"].append(audio.relative_to(project).as_posix())
        if mode == "narrated_html" and paths["audio_timeline"].is_file():
            errors, warnings = [], []
            try:
                audio_qa(project, errors, warnings)
            except (OSError, ValueError, RuntimeError, KeyError) as exc:
                errors.append(str(exc))
            report["audio_cache"] = not errors
            if errors:
                report["audio_findings"] = errors
            else:
                for key in AUDIO_ARTIFACTS:
                    if key in old_state["artifacts"]:
                        pending["artifacts"][key] = old_state["artifacts"][key]
        write_object(paths["build_state"], pending)
        write_object(project / "video" / "html_migration.json", report)
        project.rename(output)
    return report


def adapt_visuals(project: Path, paths: dict, copy_file, report: dict, animated: bool) -> None:
    manifest = load_object(paths["manifest"])
    plan = load_object(paths["layer_plan"]) if paths["layer_plan"].is_file() else {"version": 2, "canvas": {"width": 1600, "height": 900}, "pages": {}}
    for slide in manifest.get("slides", []):
        number = slide["page"]
        value = slide.get("source_svg")
        if not value:
            report["missing"].append(f"第 {number} 页 source_svg")
            continue
        slide["source_svg"] = copy_file(value)
        page_path = project / slide["source_svg"]
        text = page_path.read_text(encoding="utf-8") if page_path.is_file() else ""
        mappings = [
            family for family in ALIASES
            if family not in {"sans-serif", "serif", "monospace", "system-ui"}
            and family in text.casefold()
            and re.search(r"font-family", text, re.IGNORECASE)
        ]
        if mappings:
            report["font_mappings"][str(number)] = {family: ALIASES[family] for family in mappings}
        if not animated:
            continue
        row = plan["pages"].get(f"{number:02d}", {})
        if row:
            row["source"] = slide["source_svg"]
        layers = row.get("layers", [])
        if layers:
            for layer in layers:
                if layer.get("file"):
                    layer["file"] = copy_file(layer["file"])
                    continue
                name = layer["name"]
                matches = list({
                    path for path in (
                        project / "video" / "layers" / f"{number:02d}" / f"{name}.svg",
                        project / "video" / "layers" / f"{number:02d}_{name}.svg",
                        project / "video" / "layers" / f"s{number:02d}_{name}.svg",
                    ) if path.is_file()
                })
                if len(matches) == 1:
                    layer["file"] = matches[0].relative_to(project).as_posix()
        ids = set()
        if text:
            try:
                ids = {node.get("id") for node in ET.fromstring(text).iter() if node.tag.endswith("}g")}
            except ET.ParseError:
                report["missing"].append(f"第 {number} 页 SVG 无法解析")
        beat_ids = {beat["id"] for beat in slide.get("beats", [])}
        if not layers or not all(layer.get("file") for layer in layers):
            if beat_ids <= ids:
                for layer in layers:
                    layer.pop("file", None)
            else:
                report["missing"].append(f"第 {number} 页图层映射 layers[].file")
    if not manifest.get("slides"):
        report["missing"].append("manifest.slides")
    write_object(paths["manifest"], manifest)
    if animated:
        write_object(paths["layer_plan"], plan)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--template-source", type=Path)
    args = parser.parse_args(argv)
    try:
        report = migrate_html(args.project, args.output, args.template_source)
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    for missing in report["missing"]:
        print(f"WARN 待补 {missing}")
    print(f"OK  HTML 项目: {args.output}，迁移报告位于 video/html_migration.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
