"""Compile the millisecond timeline shared by Chromium and browser playback."""

from __future__ import annotations

import math
import shutil
import subprocess
import wave
from pathlib import Path

from build_audio_timeline import timeline_rows
from generate_fast_animation_timing import build_timing
from production_common import load_object


PCM_RATE = 48_000
BYTES_PER_MS = PCM_RATE // 1000 * 2


def ffmpeg_tool(name: str) -> str:
    executable = shutil.which(name)
    if executable is None:
        raise RuntimeError(f"缺少 {name}，请运行 install_ffmpeg.sh 或 install_ffmpeg.ps1")
    return executable


def millisecond_value(value, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} 必须为非负整数")
    return value


def compile_timeline(
    config: dict, manifest: dict, paths: dict[str, Path],
) -> tuple[dict, list[Path]]:
    mode = config["deliverable"]
    animated = mode != "static_html"
    supplied_timing = load_object(paths["timing"]) if animated and paths["timing"].is_file() else {}
    default_timing = supplied_timing.get("defaults", {})
    parameters = {
        field: millisecond_value(default_timing[field], field)
        for field in ("duration_ms", "first_content_start_ms", "start_step_ms", "animation_window_ms")
        if field in default_timing
    }
    motion = build_timing(manifest, **parameters)["slides"] if animated else []
    defaults = manifest.get("animation_defaults", {})
    if mode == "narrated_html":
        narration = load_object(paths["audio_timeline"])
        rows = timeline_rows(narration)
        if len(rows) != len(manifest["slides"]):
            raise ValueError("逐页音频和 SVG 页数不一致")
        safety = millisecond_value(narration["advance_safety_ms"], "advance_safety_ms")
        transition = millisecond_value(narration["slide_transition_ms"], "slide_transition_ms")
        if safety != defaults.get("advance_safety_ms", 150) or transition != defaults.get("slide_transition_ms", 250):
            raise ValueError("旁白时间轴已过期，请重新运行 audio-timeline")
    else:
        rows = []
        safety = 0
        transition = millisecond_value(defaults.get("slide_transition_ms", 250), "slide_transition_ms") if animated else 0

    start_ms = 0
    slides = []
    audio_files = []
    for index, slide in enumerate(manifest["slides"]):
        page = index + 1
        if slide.get("page") != page:
            raise ValueError("manifest 页码必须按顺序从 1 连续编号")
        if rows:
            row = rows[index]
            seconds = row["audio_duration_seconds"]
            if isinstance(seconds, bool) or not isinstance(seconds, (float, int)) or not math.isfinite(seconds) or seconds <= 0:
                raise ValueError(f"第 {page} 页音频时长无效")
            duration = round(seconds * 1000)
            if row["advance_ms"] != duration + safety:
                raise ValueError(f"第 {page} 页的音频换页时间无效")
            audio_path = (paths["audio_timeline"].parent / row["audio_file"]).resolve()
            expected = (paths["audio_dir"] / f"{page:02d}.mp3").resolve()
            if audio_path != expected or not audio_path.is_file():
                raise ValueError(f"第 {page} 页的音频须位于 {expected}")
            audio_files.append(audio_path)
        else:
            duration = config.get("seconds_per_page", 5) * 1000

        beats = motion[index]["beats"] if animated else []
        hold_ms = duration + safety
        for beat in beats:
            if beat["start_ms"] >= duration or beat["start_ms"] + beat["duration_ms"] > hold_ms:
                raise ValueError(
                    f"第 {page} 页分组 {beat['id']} 的动画时间点超出本页有效时段 "
                    f"（{beat['start_ms']}+{beat['duration_ms']}ms，正文 {duration}ms，换页 {hold_ms}ms）"
                )
        fade_ms = transition if page < len(manifest["slides"]) else 0
        slides.append({
            "page": page,
            "start_ms": start_ms,
            "audio_ms": duration if rows else 0,
            "hold_ms": hold_ms,
            "transition_ms": fade_ms,
            "beats": beats,
        })
        start_ms += hold_ms + fade_ms
    return {"mode": mode, "total_ms": start_ms, "slides": slides}, audio_files


def run_media(command: list[str]) -> bytes:
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        details = result.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"{Path(command[0]).name} 失败（{result.returncode}）\n{details}")
    return result.stdout


def combine_narration(timeline: dict, audio_files: list[Path], output: Path, work: Path) -> None:
    ffmpeg = ffmpeg_tool("ffmpeg")
    wav_path = work / "narration.wav"
    with wave.open(str(wav_path), "wb") as target:
        target.setparams((1, 2, PCM_RATE, 0, "NONE", "not compressed"))
        for row, path in zip(timeline["slides"], audio_files, strict=True):
            pcm = run_media([
                ffmpeg, "-v", "error", "-i", str(path), "-vn", "-ac", "1",
                "-ar", str(PCM_RATE), "-f", "s16le", "pipe:1",
            ])
            if not pcm or len(pcm) > row["hold_ms"] * BYTES_PER_MS:
                raise ValueError(f"第 {row['page']} 页解码的音频时长超出换页时间：{path}")
            target.writeframesraw(pcm)
            remaining = (row["hold_ms"] + row["transition_ms"]) * BYTES_PER_MS - len(pcm)
            target.writeframesraw(bytes(remaining))
    run_media([
        ffmpeg, "-v", "error", "-y", "-i", str(wav_path),
        "-c:a", "libmp3lame", "-q:a", "2", "-write_xing", "1", str(output),
    ])
