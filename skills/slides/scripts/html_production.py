#!/usr/bin/env python3
"""Assemble an offline slide deck from the approved project inputs."""

from __future__ import annotations

import argparse
import html
import importlib.util
import json
import shutil
import sys
import tempfile
import zipfile
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Sequence

from browser_render import browser_page, open_deck
from html_assets import Assets
from html_fonts import CATALOG, family_list
from html_timeline import combine_narration, compile_timeline
from page_script_contract import parse_page_script
from production_common import (
    HTML_DELIVERABLES,
    canonical_hash,
    file_hash,
    load_object,
    load_project_config,
    load_state,
    project_lock,
    project_paths,
    require_approvals,
    source_fingerprint,
    visual_fingerprint,
    write_object,
)
from validate_project import validate


HTML_ROOT = CATALOG.parent
STATIC_APPROVALS = ("content", "visual")
NARRATED_APPROVALS = (*STATIC_APPROVALS, "narration")
CONTROLS = """<nav id="controls" aria-label="演示控制">
<button id="previous" type="button" aria-label="上一页">‹</button>
<span id="position">0 / 0</span>
<button id="next" type="button" aria-label="下一页">›</button>
<button id="play" type="button">播放</button>
<input id="seek" type="range" min="0" value="0" aria-label="播放进度">
<button id="read" type="button">阅读</button>
<button id="fullscreen" type="button">全屏</button>
</nav><p id="message" role="alert" hidden></p>"""


def safe_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")


def html_document(name: str, theme: str, css: str, body: str) -> str:
    safe_css = css.replace("</", "<\\/")
    return (
        '<!doctype html>\n<html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{html.escape(name)}</title><style>{safe_css}</style>"
        f'</head><body data-view="play" data-theme="{theme}">{body}</body></html>\n'
    )


def project_resource(project: Path, value: str) -> Path:
    path = (project / value).resolve()
    if not path.is_relative_to(project) or not path.is_file():
        raise ValueError(f"找不到项目内文件 {value!r}")
    return path


def layer_files(project: Path, row: dict, page: int) -> dict[str, Path]:
    rows = row.get("layers", [])
    if not any(layer.get("file") for layer in rows):
        return {}
    result = {}
    for layer in rows:
        value = layer.get("file")
        if not isinstance(value, str) or not value:
            raise ValueError(f"第 {page} 页请为全部现有图层填写 layers[].file")
        result[layer["name"]] = project_resource(project, value)
    return result


def page_markup(assets: Assets, slide: dict, title: str, row: dict, name: str, total: int) -> str:
    index = slide["page"]
    source = project_resource(assets.project, slide["source_svg"])
    assets.track(source)
    groups = {beat["id"] for beat in slide["beats"]}
    layers = layer_files(assets.project, row, index) if groups else {}
    if layers:
        art = []
        for number, (layer, path) in enumerate(layers.items()):
            beat = f' data-beat="{html.escape(layer, quote=True)}"' if layer != "base" else ""
            content = assets.svg(path, f"p{index}-s{number}", set())
            art.append(f'<div class="layer"{beat}>{content}</div>')
        artwork = "".join(art)
    else:
        artwork = assets.svg(source, f"p{index}-s", groups)
    hidden = " hidden" if index > 1 else ""
    cover = " data-cover" if index == 1 else ""
    return (
        f'<section class="page" data-page="{index}"{hidden}>'
        f'<div class="canvas"{cover}><h1>{html.escape(title)}</h1>'
        f'<div class="art">{artwork}</div>'
        f'<footer><span>{html.escape(name)}</span><span>{index} / {total}</span></footer>'
        "</div></section>"
    )


def font_material(assets: Assets, draft: str) -> tuple[str, str, dict[str, Path], list[dict]]:
    if importlib.util.find_spec("fontTools") is None or importlib.util.find_spec("brotli") is None:
        raise RuntimeError("缺少 FontTools 或 Brotli，请运行 bootstrap --stage static")
    with browser_page() as page:
        page.set_content(draft, wait_until="load")
        used = page.evaluate("""() => {
            const rows = [];
            const elements = [...document.body.querySelectorAll("*")];
            for (const [index, element] of elements.entries()) {
                if (element.matches("style, script, title, desc")) continue;
                const own = [...element.childNodes].filter(node => node.nodeType === Node.TEXT_NODE)
                    .map(node => node.textContent).join("");
                const extras = {play: "暂停", read: "演示", position: "0123456789"};
                for (const pseudo of ["", "::before", "::after"]) {
                    const style = getComputedStyle(element, pseudo || null);
                    const generated = style.content;
                    const text = pseudo
                        ? (generated.startsWith('"') ? generated.slice(1, -1) : "")
                        : own + (extras[element.id] || "");
                    if (text.trim()) {
                        rows.push({index, pseudo, text, family: style.fontFamily, weight: style.fontWeight,
                            style: style.fontStyle, page: element.closest(".page")?.dataset.page || "控件"});
                    }
                }
            }
            return rows;
        }""")
        for run in used:
            if not family_list(run["family"]):
                raise ValueError(f"第 {run['page']} 页缺少有效字体族")
            run["stack"] = assets.fonts.select(run)
        body, pseudo_css = page.evaluate("""rows => {
            const elements = [...document.body.querySelectorAll("*")];
            const rules = [];
            for (const row of rows) {
                const element = elements[row.index];
                if (row.pseudo) {
                    element.dataset.fontRun = String(row.index);
                    rules.push('[data-font-run="' + row.index + '"]' + row.pseudo
                        + '{font-family:' + row.stack + ' !important}');
                } else {
                    element.style.setProperty("font-family", row.stack, "important");
                }
            }
            return [document.body.innerHTML, rules.join("\\n")];
        }""", used)
    faces, licenses, inputs = assets.fonts.styles()
    return body, faces + "\n" + pseudo_css, licenses, inputs


def bundle_hashes(directory: Path) -> dict[str, str]:
    return {
        path.relative_to(directory).as_posix(): file_hash(path)
        for path in sorted(directory.rglob("*")) if path.is_file()
    }


def current_render_inputs(project: Path, config: dict, manifest: dict) -> str:
    animated = config["deliverable"] != "static_html"
    return canonical_hash({
        "content": source_fingerprint(project, config),
        "visual": visual_fingerprint(project, config, manifest, include_timing=animated),
        "mode": config["deliverable"],
        "name": config["name"],
        "seconds_per_page": config.get("seconds_per_page", 5),
        "runtime": {
            p.name: file_hash(p)
            for p in (*sorted(HTML_ROOT.iterdir()), *(
                Path(__file__).with_name(name)
                for name in ("html_production.py", "html_assets.py", "html_fonts.py", "html_timeline.py", "generate_fast_animation_timing.py")
            )) if p.is_file()
        },
    })


def inputs_match(project: Path, files: dict[str, str]) -> bool:
    for relative, checksum in files.items():
        path = (project / relative).resolve()
        if not path.is_relative_to(project) or not path.is_file() or file_hash(path) != checksum:
            return False
    return True


def require_current_html(project: Path, state: dict | None = None) -> tuple[Path, dict]:
    config = load_project_config(project)
    if config["deliverable"] not in HTML_DELIVERABLES:
        raise ValueError("HTML 导出需要 HTML 演示项目")
    paths = project_paths(project, config)
    state = state if state is not None else load_state(paths["build_state"])
    record = state["artifacts"].get("html")
    directory, archive = output_paths(project, paths)
    if (
        not isinstance(record, dict)
        or not isinstance(record.get("dependencies"), dict)
        or not (directory / "index.html").is_file()
        or not archive.is_file()
        or record.get("paths") != [str(directory.relative_to(project)), str(archive.relative_to(project))]
        or record.get("zip_sha256") != file_hash(archive)
        or record.get("files") != bundle_hashes(directory)
        or record.get("inputs") != current_render_inputs(project, config, load_object(paths["manifest"]))
        or not inputs_match(project, record.get("dependencies", {}))
    ):
        raise RuntimeError("HTML 演示已过期或未组装，请运行 assemble-html")
    return directory, record


@contextmanager
def publish_artifacts(pairs: list[tuple[Path, Path]]):
    """Publish a set of staged files and restore the original set if writing fails."""
    with ExitStack() as stack:
        backups = []
        published = []
        try:
            for stage, final in pairs:
                final.parent.mkdir(parents=True, exist_ok=True)
                if final.exists():
                    backup_dir = Path(stack.enter_context(tempfile.TemporaryDirectory(dir=final.parent)))
                    backup = backup_dir / final.name
                    final.replace(backup)
                    backups.append((final, backup))
                stage.replace(final)
                published.append(final)
            yield
        except BaseException:
            for final in reversed(published):
                if final.is_dir():
                    shutil.rmtree(final)
                else:
                    final.unlink()
            for final, backup in reversed(backups):
                backup.replace(final)
            raise


def output_paths(project: Path, paths: dict[str, Path]) -> tuple[Path, Path]:
    directory, archive = paths["html_dir"], paths["html_zip"]
    if not all(path.is_relative_to(project / "deliverables") for path in (directory, archive, paths["video"])):
        raise ValueError("HTML、ZIP 和 MP4 的配置路径应位于 deliverables/ 下")
    if any(
        child.is_relative_to(parent)
        for child in (directory, archive, paths["video"])
        for parent in (directory, archive, paths["video"])
        if child is not parent
    ):
        raise ValueError("HTML、ZIP 和 MP4 的路径必须彼此独立")
    if directory.exists() and not directory.is_dir():
        raise ValueError(f"HTML 输出须为目录 {directory}")
    if archive.exists() and not archive.is_file():
        raise ValueError(f"ZIP 输出须为文件 {archive}")
    if archive.suffix.lower() != ".zip" or paths["video"].suffix.lower() != ".mp4":
        raise ValueError("ZIP 或 MP4 输出扩展名不正确")
    return directory, archive


def assemble_html(project: Path) -> dict:
    project = project.resolve()
    config = load_project_config(project)
    mode = config["deliverable"]
    if mode not in HTML_DELIVERABLES:
        raise ValueError("assemble-html 需要 HTML 演示项目")
    narrated = mode == "narrated_html"
    approvals = NARRATED_APPROVALS if narrated else STATIC_APPROVALS
    require_approvals(project, approvals)
    errors, _ = validate(project)
    if errors:
        raise ValueError("\n".join(errors))
    paths = project_paths(project, config)
    if narrated:
        from qa_presentation import require_qa

        require_qa(project, "audio")
    manifest = load_object(paths["manifest"])
    inputs = current_render_inputs(project, config, manifest)
    timeline, audio_files = compile_timeline(config, manifest, paths)
    notes = parse_page_script(paths["page_script"])
    layers = load_object(paths["layer_plan"])["pages"] if paths["layer_plan"].is_file() and mode != "static_html" else {}

    assets = Assets(project)
    name, theme = config["name"], config["visual"]["theme"]
    template_path = paths["template_working"]
    if not template_path.is_relative_to(project):
        raise ValueError("CSS 模板须在项目目录内")
    assets.track(template_path)
    player_css = (HTML_ROOT / "player.css").read_text(encoding="utf-8")
    css = player_css + "\n" + assets.css(template_path.read_text(encoding="utf-8"), template_path.parent)
    safe = config["template"]["safe_area"]
    css += (
        f"\n:root{{--safe-left:{safe['x']}px;"
        f"--safe-right:{1600 - safe['x'] - safe['width']}px;"
        f"--safe-top:{safe['y']}px;--safe-bottom:{900 - safe['y'] - safe['height']}px}}"
    )
    pages = [
        page_markup(assets, slide | timing, note["title"], layers.get(f"{timing['page']:02d}", {}), name, len(notes))
        for slide, timing, note in zip(manifest["slides"], timeline["slides"], notes, strict=True)
    ]
    body = '<main id="deck">' + "".join(pages) + "</main>" + CONTROLS
    body, font_css, licenses, fonts = font_material(assets, html_document(name, theme, css, body))
    if narrated:
        assets.track(paths["audio_timeline"])
        for path in audio_files:
            if not path.is_relative_to(project):
                raise ValueError("逐页音频须在项目目录内")
            assets.track(path)
        body += '<audio id="narration" src="narration.mp3" preload="metadata"></audio>'
    body += f'<script type="application/json" id="timeline">{safe_json(timeline)}</script>'
    body += "<script>" + (HTML_ROOT / "player.js").read_text(encoding="utf-8") + "</script>"
    document = html_document(name, theme, font_css + "\n" + css, body)
    directory, archive = output_paths(project, paths)
    directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=directory.parent) as temporary:
        work = Path(temporary)
        bundle = work / "deck"
        bundle.mkdir()
        (bundle / "index.html").write_text(document, encoding="utf-8")
        (bundle / "licenses").mkdir()
        for filename, license in licenses.items():
            shutil.copyfile(license, bundle / "licenses" / Path(filename).name)
        if narrated:
            combine_narration(timeline, audio_files, bundle / "narration.mp3", work)
        with browser_page() as page:
            open_deck(page, bundle / "index.html")
            if narrated:
                page.wait_for_function("document.querySelector('#narration').readyState >= 1")
        zipped = work / "deck.zip"
        with zipfile.ZipFile(zipped, "w", compression=zipfile.ZIP_DEFLATED) as output:
            for filename in bundle_hashes(bundle):
                output.write(bundle / filename, filename)
        with project_lock(project):
            if not inputs_match(project, assets.files) or inputs != current_render_inputs(
                project, load_project_config(project), load_object(paths["manifest"]),
            ):
                raise RuntimeError("组装过程中输入发生变化，请重新组装")
            require_approvals(project, approvals)
            if narrated:
                require_qa(project, "audio")
            state = load_state(paths["build_state"])
            if directory.exists() and any(directory.iterdir()):
                previous = state["artifacts"].get("html") or {}
                if (previous.get("paths") or [None])[0] != str(directory.relative_to(project)):
                    raise ValueError(f"HTML 输出目录已存在且非本技能产物 {directory}")
            record = {
                "paths": [str(directory.relative_to(project)), str(archive.relative_to(project))],
                "inputs": inputs,
                "dependencies": assets.files,
                "files": bundle_hashes(bundle),
                "zip_sha256": file_hash(zipped),
                "timeline": timeline,
                "fonts": fonts,
                "font_substitutions": {
                    label: sorted(items) for label, items in sorted(assets.fonts.substitutions.items())
                },
            }
            with publish_artifacts([(bundle, directory), (zipped, archive)]):
                state["artifacts"]["html"] = record
                write_object(paths["build_state"], state)
    print(f"OK  HTML: {directory / 'index.html'}")
    print(f"OK  ZIP: {archive}")
    return record


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--replace-audio", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        if args.replace_audio and load_project_config(args.project.resolve())["deliverable"] != "narrated_html":
            raise ValueError("replace-audio 需要 narrated_html 项目")
        assemble_html(args.project)
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
