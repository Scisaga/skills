#!/usr/bin/env python3
import importlib
import json
import logging
import math
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

VIDEO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = VIDEO_ROOT.parent
SPEECH_ROOT = REPO_ROOT / "speech"
BIN_ROOT = VIDEO_ROOT / "bin"

SILENCE_START_RE = re.compile(r"silence_start:\s*(?P<value>\d+(?:\.\d+)?)")
SILENCE_END_RE = re.compile(r"silence_end:\s*(?P<value>\d+(?:\.\d+)?)")


@dataclass
class Interval:
    start: float
    end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


def configure_logging(*, quiet: bool, verbose: bool) -> None:
    if quiet:
        level = logging.WARNING
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO
    logging.basicConfig(level=level, format="%(message)s")


def get_env_candidates(env_file: str | None) -> list[Path]:
    if env_file:
        return [Path(env_file)]
    return [
        Path.cwd() / ".env",
        VIDEO_ROOT / ".env",
        SCRIPTS_DIR / ".env",
    ]


def load_env(*, env_file: str | None, logger: logging.Logger) -> Path | None:
    candidates = get_env_candidates(env_file)

    try:
        from dotenv import load_dotenv
    except ImportError:
        existing = [candidate for candidate in candidates if candidate.exists()]
        if env_file or existing:
            logger.warning(
                "检测到 .env 配置，但缺少 `python-dotenv`，无法自动加载。请先安装 `python-dotenv` 或手动导出环境变量。"
            )
        return None

    for candidate in candidates:
        if not candidate.exists():
            continue
        load_dotenv(candidate, override=False)
        logger.debug("已加载环境变量文件: %s", candidate)
        return candidate

    if env_file:
        logger.warning("指定的 .env 文件不存在: %s", env_file)
    return None


def ensure_python_modules(
    required_modules: dict[str, str],
    *,
    logger: logging.Logger,
) -> None:
    missing_packages: list[str] = []

    for module_name, package_name in required_modules.items():
        try:
            importlib.import_module(module_name)
        except ImportError:
            missing_packages.append(package_name)

    if not missing_packages:
        return

    deduped = list(dict.fromkeys(missing_packages))
    logger.error("缺少 Python 依赖: %s", ", ".join(deduped))
    raise RuntimeError(f"请先执行 `python3 -m pip install {' '.join(deduped)}`")


def platform_slug() -> str:
    system_name = platform.system().lower()
    arch = platform.machine().lower()
    arch = {
        "x86_64": "x64",
        "amd64": "x64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }.get(arch, arch)
    if system_name == "darwin":
        return f"macos-{arch}"
    if system_name == "windows":
        return f"windows-{arch}"
    return f"{system_name}-{arch}"


def preferred_local_bin_dirs() -> list[Path]:
    slug = platform_slug()
    return [
        BIN_ROOT / slug / "bin",
        BIN_ROOT / slug,
        BIN_ROOT / "current" / "bin",
        BIN_ROOT / "current",
    ]


def resolve_binary(tool_name: str) -> str:
    env_names = [f"VIDEO_{tool_name.upper()}_BIN"]
    if tool_name == "ffmpeg":
        env_names.append("FFMPEG_BIN")
    if tool_name == "ffprobe":
        env_names.append("FFPROBE_BIN")

    for env_name in env_names:
        candidate = os.getenv(env_name)
        if candidate:
            path = Path(candidate)
            if path.exists():
                return str(path)
            raise RuntimeError(f"{env_name} 指向的文件不存在: {candidate}")

    executable_names = [tool_name]
    if platform.system().lower() == "windows":
        executable_names.insert(0, f"{tool_name}.exe")

    for bin_dir in preferred_local_bin_dirs():
        for executable_name in executable_names:
            candidate = bin_dir / executable_name
            if candidate.exists():
                return str(candidate)

    for executable_name in executable_names:
        resolved = shutil.which(executable_name)
        if resolved:
            return resolved

    raise RuntimeError(
        f"找不到 `{tool_name}`。请先执行 `bash video/scripts/bootstrap.sh` 或运行对应系统的安装脚本。"
    )


def run_command(
    cmd: list[str],
    *,
    capture_output: bool = False,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=check,
        capture_output=capture_output,
        text=True,
        env=env,
    )


def ffprobe_json(input_path: Path) -> dict:
    ffprobe = resolve_binary("ffprobe")
    result = run_command(
        [
            ffprobe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(input_path),
        ],
        capture_output=True,
    )
    return json.loads(result.stdout)


def media_duration(input_path: Path) -> float:
    payload = ffprobe_json(input_path)
    format_section = payload.get("format", {})
    raw = format_section.get("duration")
    if raw is None:
        raise RuntimeError(f"无法读取媒体时长: {input_path}")
    return float(raw)


def detect_silences(
    input_path: Path,
    *,
    noise: str = "-30dB",
    silence_duration: float = 0.4,
) -> list[Interval]:
    ffmpeg = resolve_binary("ffmpeg")
    result = run_command(
        [
            ffmpeg,
            "-hide_banner",
            "-i",
            str(input_path),
            "-af",
            f"silencedetect=noise={noise}:d={silence_duration}",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        check=False,
    )
    output = "\n".join([result.stdout, result.stderr])

    silences: list[Interval] = []
    silence_start: float | None = None
    for line in output.splitlines():
        start_match = SILENCE_START_RE.search(line)
        if start_match:
            silence_start = float(start_match.group("value"))
            continue
        end_match = SILENCE_END_RE.search(line)
        if end_match and silence_start is not None:
            silence_end = float(end_match.group("value"))
            silences.append(Interval(start=silence_start, end=silence_end))
            silence_start = None

    return silences


def build_speech_segments(
    *,
    total_duration: float,
    silences: list[Interval],
    min_segment: float,
    max_segment: float,
    merge_gap: float,
) -> list[Interval]:
    if total_duration <= 0:
        return []

    speech_segments: list[Interval] = []
    cursor = 0.0
    for silence in silences:
        start = max(0.0, cursor)
        end = min(total_duration, silence.start)
        if end - start >= min_segment:
            speech_segments.append(Interval(start=start, end=end))
        cursor = max(cursor, silence.end)

    if total_duration - cursor >= min_segment:
        speech_segments.append(Interval(start=max(0.0, cursor), end=total_duration))

    if not speech_segments:
        speech_segments = [Interval(start=0.0, end=total_duration)]

    merged: list[Interval] = []
    for segment in speech_segments:
        if not merged:
            merged.append(segment)
            continue
        last = merged[-1]
        if segment.start - last.end <= merge_gap:
            merged[-1] = Interval(start=last.start, end=max(last.end, segment.end))
        else:
            merged.append(segment)

    split_segments: list[Interval] = []
    for segment in merged:
        if segment.duration <= max_segment:
            split_segments.append(segment)
            continue

        parts = max(1, math.ceil(segment.duration / max_segment))
        chunk = segment.duration / parts
        for idx in range(parts):
            start = segment.start + idx * chunk
            end = segment.end if idx == parts - 1 else segment.start + (idx + 1) * chunk
            if end - start >= min_segment:
                split_segments.append(Interval(start=start, end=end))

    return split_segments


def format_seconds_for_ffmpeg(value: float) -> str:
    return f"{value:.3f}"


def seconds_to_srt_timestamp(value: float) -> str:
    total_ms = max(0, int(round(value * 1000)))
    hours, rem = divmod(total_ms, 3600 * 1000)
    minutes, rem = divmod(rem, 60 * 1000)
    seconds, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def extract_audio(
    *,
    input_path: Path,
    output_path: Path,
    start: float | None = None,
    end: float | None = None,
    sample_rate: int = 16000,
    mono: bool = True,
) -> None:
    ffmpeg = resolve_binary("ffmpeg")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg, "-y"]
    if start is not None:
        cmd.extend(["-ss", format_seconds_for_ffmpeg(start)])
    cmd.extend(["-i", str(input_path)])
    if end is not None:
        duration = max(0.0, end - (start or 0.0))
        cmd.extend(["-t", format_seconds_for_ffmpeg(duration)])
    cmd.extend(["-vn"])
    if mono:
        cmd.extend(["-ac", "1"])
    cmd.extend(["-ar", str(sample_rate), "-c:a", "pcm_s16le", str(output_path)])
    run_command(cmd)


def speech_transcribe(
    *,
    input_file: Path,
    output_text: Path,
    api_base: str | None,
    language: str | None,
    prompt: str | None,
    env_file: str | None,
    timeout: int,
    quiet: bool,
    verbose: bool,
) -> None:
    transcribe_script = SPEECH_ROOT / "scripts" / "transcribe.py"
    if not transcribe_script.exists():
        raise RuntimeError(f"找不到 speech skill 转写脚本: {transcribe_script}")

    cmd = [
        sys.executable,
        str(transcribe_script),
        "--input-file",
        str(input_file),
        "--output-text",
        str(output_text),
        "--timeout",
        str(timeout),
    ]
    if api_base:
        cmd.extend(["--api-base", api_base])
    if language:
        cmd.extend(["--language", language])
    if prompt:
        cmd.extend(["--prompt", prompt])
    if env_file:
        cmd.extend(["--env-file", env_file])
    if quiet:
        cmd.append("--quiet")
    if verbose:
        cmd.append("--verbose")
    run_command(cmd)


def video_title_guess(input_path: Path) -> str:
    name = input_path.stem
    name = re.sub(r"[._]+", " ", name)
    name = re.sub(r"\b(19|20)\d{2}\b", "", name)
    name = re.sub(r"\b(480p|720p|1080p|2160p|x264|x265|bluray|web[- ]dl|webrip|remux|dts|aac)\b", "", name, flags=re.I)
    name = re.sub(r"\s+", " ", name).strip()
    return name or input_path.stem
