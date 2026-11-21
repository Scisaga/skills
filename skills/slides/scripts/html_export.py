#!/usr/bin/env python3
"""Export approved HTML presentations as PDF, images or an H.264 MP4."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Sequence

from browser_render import browser_page, open_deck
from html_production import output_paths, publish_artifacts, require_current_html
from html_timeline import ffmpeg_tool, run_media
from production_common import file_hash, load_project_config, load_state, project_lock, project_paths, write_object
from qa_presentation import require_qa


VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
FPS = 30


def page_indices(value: str | None, count: int) -> list[int]:
    if value is None:
        return list(range(count))
    result = []
    for part in value.split(","):
        bounds = part.strip().split("-")
        if len(bounds) not in (1, 2) or any(not bound.strip().isdigit() for bound in bounds):
            raise ValueError(f"无效的页码 {part!r}，请使用 1,3-5 的格式")
        first, last = int(bounds[0]), int(bounds[-1])
        if not 1 <= first <= last <= count:
            raise ValueError(f"页码 {part!r} 超出 1–{count}")
        result.extend(range(first - 1, last))
    return list(dict.fromkeys(result))


def export_pages(args: argparse.Namespace) -> int:
    project = args.project.resolve()
    directory, record = require_current_html(project)
    require_qa(project, "static")
    indices = page_indices(args.pages, len(record["timeline"]["slides"]))
    output = args.output.resolve()
    fmt = args.format
    if fmt == "pdf":
        if output.suffix.lower() != ".pdf" or output.is_dir():
            raise ValueError("PDF 请选择 .pdf 输出文件")
        files = [output]
    else:
        accepted = {".png"} if fmt == "png" else {".jpg", ".jpeg"}
        if len(indices) == 1 and output.suffix.lower() in accepted and not output.is_dir():
            files = [output]
        elif output.suffix.lower() not in accepted and (not output.exists() or output.is_dir()):
            files = [output / f"{i + 1:02d}.{fmt}" for i in indices]
        else:
            raise ValueError("多页图像导出请选择输出目录")
    if any(path.exists() and not path.is_file() for path in files):
        raise ValueError("选页导出的目标文件已被目录占用")
    if any(path.is_relative_to(directory) for path in files):
        raise ValueError("请将导出文件放在 HTML 交付目录之外")
    parent = files[0].parent
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=parent) as work:
        temporary = [Path(work) / path.name for path in files]
        with browser_page() as page:
            open_deck(page, directory / "index.html")
            if fmt == "pdf":
                page.evaluate("indices => window.slides.printPages(indices)", indices)
                page.pdf(path=temporary[0], print_background=True, prefer_css_page_size=True)
            else:
                for index, path in zip(indices, temporary, strict=True):
                    page.evaluate("i => window.slides.showFinal(i)", index)
                    page.screenshot(path=path, type="png" if fmt == "png" else "jpeg")
        if any(not path.is_file() or not path.stat().st_size for path in temporary):
            raise RuntimeError("浏览器未产生有效的选页导出文件")
        with project_lock(project):
            require_qa(project, "static")
            if require_current_html(project)[1] != record:
                raise RuntimeError("导出过程中 HTML 已变化，请重试")
            with publish_artifacts(list(zip(temporary, files, strict=True))):
                pass
    print(f"OK  {fmt.upper()} {len(indices)} 页: {output}")
    return 0


def capture_video(page, directory: Path, timeline: dict, output: Path, log: Path) -> int:
    count = math.ceil(timeline["total_ms"] * FPS / 1000)
    duration = f"{count / FPS:.9f}"
    ffmpeg = ffmpeg_tool("ffmpeg")
    command = [
        ffmpeg, "-v", "error", "-y", "-f", "image2pipe", "-framerate", str(FPS),
        "-c:v", "png", "-i", "pipe:0",
    ]
    if timeline["mode"] == "narrated_html":
        audio = directory / "narration.mp3"
        command.extend(["-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac", "-b:a", "128k", "-af", "apad"])
    else:
        command.extend(["-map", "0:v:0"])
    command.extend([
        "-t", duration,
        "-vf", "scale=in_range=pc:out_color_matrix=bt709:out_range=tv,format=yuv420p",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709",
        "-color_trc", "bt709", "-movflags", "+faststart", str(output),
    ])
    with log.open("wb") as errors:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=errors)
        assert process.stdin is not None
        stable = None
        image = b""
        try:
            for frame in range(count):
                state = page.evaluate("ms => window.slides.renderAt(ms)", frame * 1000 / FPS)
                if state is None or state != stable:
                    image = page.screenshot(type="png", animations="allow")
                process.stdin.write(image)
                stable = state
                if frame > 0 and frame % (FPS * 10) == 0:
                    print(f"INFO MP4 frames: {frame}/{count}", flush=True)
            process.stdin.close()
            process.wait()
        except BrokenPipeError:
            process.wait()
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            try:
                process.stdin.close()
            except BrokenPipeError:
                pass
    if process.returncode:
        raise RuntimeError(f"FFmpeg 编码失败\n{log.read_text(encoding='utf-8', errors='replace')}")
    return count


def verify_video(output: Path, frames: int, narrated: bool) -> dict:
    probe = ffmpeg_tool("ffprobe")
    payload = json.loads(run_media([
        probe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(output),
    ]))
    streams = payload["streams"]
    video = [row for row in streams if row["codec_type"] == "video"]
    audio = [row for row in streams if row["codec_type"] == "audio"]
    if len(video) != 1 or len(audio) != int(narrated):
        raise RuntimeError("MP4 轨道数与交付类型不符")
    image = video[0]
    length = frames / FPS
    if (
        image["codec_name"] != "h264"
        or image["width"] != VIDEO_WIDTH or image["height"] != VIDEO_HEIGHT
        or Fraction(image["avg_frame_rate"]) != FPS
        or image.get("color_range") != "tv" or image.get("color_space") != "bt709"
        or int(image.get("nb_frames", 0)) != frames
        or abs(float(image["duration"]) - length) > 1 / FPS
    ):
        raise RuntimeError("MP4 画面编码、分辨率、帧率、色彩或时长与时间轴不符")
    if narrated and (
        audio[0]["codec_name"] != "aac"
        or abs(float(audio[0]["duration"]) - length) > 1 / FPS + 1024 / int(audio[0]["sample_rate"])
    ):
        raise RuntimeError("MP4 旁白编码或时长与时间轴不符")
    return {
        "frame_count": frames,
        "video_seconds": float(image["duration"]),
        "audio_seconds": float(audio[0]["duration"]) if audio else None,
        "width": VIDEO_WIDTH,
        "height": VIDEO_HEIGHT,
        "fps": FPS,
        "color_space": "bt709",
        "color_range": "tv",
    }


def export_video(args: argparse.Namespace) -> int:
    project = args.project.resolve()
    config = load_project_config(project)
    directory, record = require_current_html(project)
    narrated = config["deliverable"] == "narrated_html"
    level = "standard" if narrated else "static"
    qa = require_qa(project, level)
    paths = project_paths(project, config)
    output_paths(project, paths)
    output = paths["video"]
    if args.output_mp4 is not None and args.output_mp4.resolve() != output:
        raise ValueError("--output-mp4 须与项目配置的 outputs.video 一致")
    if output.exists() and not output.is_file():
        raise ValueError(f"MP4 输出须为文件 {output}")
    ffmpeg_tool("ffprobe")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as work:
        staging = Path(work)
        temporary = staging / "render.mp4"
        with browser_page(VIDEO_WIDTH, VIDEO_HEIGHT) as page:
            open_deck(page, directory / "index.html")
            browser_version = page.context.browser.version
            frames = capture_video(page, directory, record["timeline"], temporary, staging / "ffmpeg.log")
        report = verify_video(temporary, frames, narrated)
        with project_lock(project):
            if require_current_html(project)[1] != record or require_qa(project, level) != qa:
                raise RuntimeError("视频导出期间输入或验收发生变化，请重试")
            report.update({
                "schema_version": 1,
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "input_html_sha256": record["files"]["index.html"],
                "qa_fingerprint": qa["fingerprint"],
                "sha256": file_hash(temporary),
                "path": str(output.relative_to(project)),
                "browser": browser_version,
                "ffmpeg": run_media([ffmpeg_tool("ffmpeg"), "-version"]).decode().splitlines()[0],
            })
            report_stage = staging / "video_export.json"
            write_object(report_stage, report)
            report_final = project / "video" / "video_export.json"
            state = load_state(paths["build_state"])
            with publish_artifacts([(temporary, output), (report_stage, report_final)]):
                state["artifacts"]["video"] = {"report": "video/video_export.json", **report}
                write_object(paths["build_state"], state)
    print(f"OK  MP4 {report['video_seconds']:.3f}s: {output}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    video = commands.add_parser("export-video")
    video.add_argument("--project", type=Path, required=True)
    video.add_argument("--output-mp4", type=Path)
    pages = commands.add_parser("export-pages")
    pages.add_argument("--project", type=Path, required=True)
    pages.add_argument("--pages")
    pages.add_argument("--format", choices=("pdf", "png", "jpg"), default="pdf")
    pages.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        return (export_video if args.command == "export-video" else export_pages)(args)
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
