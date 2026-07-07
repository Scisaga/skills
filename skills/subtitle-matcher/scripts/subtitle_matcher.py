#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import bisect
import csv
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from dataclasses import dataclass
from html import escape
from pathlib import Path
from statistics import median
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
REPORT_FILENAME = "_subtitle_download_report.html"
DEFAULT_REPORT_TITLE = "字幕重新检索报告"

VIDEO_EXTS = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".wmv", ".ts"}
SUBTITLE_EXTS = {".srt", ".ass", ".ssa", ".vtt"}
LANG_SUFFIXES = ("chs", "cht", "zh")
TEXT_SUBTITLE_CODECS = {"subrip", "ass", "ssa", "webvtt", "mov_text", "text"}
CHINESE_LANGUAGE_TAGS = {"zh", "zho", "chi", "chs", "cht", "cmn", "yue", "cn", "tw", "hk"}
SIMPLIFIED_ONLY_CHARS = set("这为个们来对时会说过还后发见听学国剧里点么没让从关实样间体台与")
TRADITIONAL_ONLY_CHARS = set("這為個們來對時會說過還後發見聽學國劇裡點麼沒讓從關實樣間體臺與")
PROXY_VARS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
)

CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
SRT_TIME_RE = re.compile(
    r"(?P<start>\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})\s*-->\s*"
    r"(?P<end>\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})"
)
ASS_DIALOGUE_RE = re.compile(
    r"^Dialogue:\s*[^,]*,"
    r"(?P<start>\d{1,2}:\d{2}:\d{2}\.\d{1,2}),"
    r"(?P<end>\d{1,2}:\d{2}:\d{2}\.\d{1,2}),",
    re.IGNORECASE,
)
CHS_NAME_RE = re.compile(
    r"(?i)(^|[._\-\[\]\s])(chs|chinese|zh-hans|zh_cn|zh-cn|sc|gb|cn|jian|simp)([._\-\[\]\s]|$)"
)
CHT_NAME_RE = re.compile(
    r"(?i)(^|[._\-\[\]\s])(cht|zh-hant|zh_tw|zh-tw|tc|big5|trad)([._\-\[\]\s]|$)"
)
EN_ONLY_RE = re.compile(r"(?i)(^|[._\-\[\]\s])(eng|english|en)([._\-\[\]\s]|$)")
REASON_DIFF_RE = re.compile(
    r"(?:diff=|最后时间码差\s*|最后对白早于片尾(?:字幕)?(?:约)?\s*)"
    r"(?P<seconds>\d+(?:\.\d+)?)\s*(?:s|秒)",
    re.IGNORECASE,
)
URL_RE = re.compile(r"https?://[^\s|,，；;]+")
RETRY_DOWNLOAD_MARKERS = (
    "api_failed",
    "api_non_json_or_error",
    "signature",
    "签名",
    "下载失败",
    "browser_check",
    "Internal Server Error",
)
RETRY_EXTRACT_MARKERS = (
    "no_sub_files",
    "extract_or_no_subtitle_files",
    "解压失败",
    "压缩包内没有有效字幕文件",
    "未能解出有效文件",
)
RELAXED_FILTER_MARKERS = (
    "found no acceptable non-machine Chinese candidate",
    "machine",
    "机器翻译",
)
HARD_REJECT_MARKERS = (
    "wrong_title_or_year",
    "wrong_episode",
    "没有与本视频片名/年份/集数匹配",
)

CATEGORY_LABELS = {
    "completed": "已完成",
    "completed_subhd": "SubHD 已完成",
    "skipped_existing": "已有字幕",
    "manual_check": "人工抽查",
    "needs_compare": "二阶段比对",
    "retry_download": "重试下载",
    "retry_extract": "重试解压",
    "review_relaxed_filter": "放宽过滤复核",
    "hard_reject": "硬拒绝",
    "unresolved_not_completed": "未完成待判断",
}
STATUS_LABELS = {
    "completed": "已完成",
    "completed_subhd": "SubHD 已完成",
    "skipped_existing": "已有字幕",
    "not_completed": "未完成",
    "manual_check": "人工抽查",
    "needs_compare": "二阶段比对",
    "retry_download": "重试下载",
    "retry_extract": "重试解压",
    "review_relaxed_filter": "放宽过滤复核",
    "hard_reject": "硬拒绝",
}
REFERENCE_CUE_CACHE: dict[str, dict[str, Any] | None] = {}


@dataclass(frozen=True)
class Cue:
    start: float
    end: float


def load_env_files(env_file: str | None = None) -> list[Path]:
    if env_file:
        candidates = [Path(env_file)]
    else:
        candidates = [Path.cwd() / ".env", SKILL_ROOT / ".env", SCRIPT_DIR / ".env"]

    existing = [path for path in candidates if path.exists()]
    if not existing:
        return []

    try:
        from dotenv import load_dotenv
    except ImportError as exc:
        rel_requirements = SKILL_ROOT / "requirements.txt"
        raise RuntimeError(
            "Found .env file(s), but python-dotenv is not installed; cannot load .env automatically. "
            f"Install with: python -m pip install -r {rel_requirements}"
        ) from exc

    loaded: list[Path] = []
    for path in existing:
        load_dotenv(dotenv_path=path, override=False)
        loaded.append(path)
    return loaded


def active_proxy_names() -> list[str]:
    return [name for name in PROXY_VARS if os.environ.get(name)]


def require_modules(module_map: dict[str, str]) -> list[str]:
    missing: list[str] = []
    for import_name, package_name in module_map.items():
        if importlib.util.find_spec(import_name) is None:
            missing.append(package_name)
    return missing


def resolve_ffprobe() -> str | None:
    for env_name in ("SUBTITLE_MATCHER_FFPROBE_BIN", "VIDEO_FFPROBE_BIN", "FFPROBE_BIN"):
        value = os.environ.get(env_name)
        if value:
            path = Path(value)
            if path.exists():
                return str(path)
            found = shutil.which(value)
            if found:
                return found
    bundled_candidates = [
        SKILL_ROOT / ".cache" / "ffmpeg" / "windows-x64" / "bin" / "ffprobe.exe",
        SKILL_ROOT / ".cache" / "ffmpeg" / "windows-arm64" / "bin" / "ffprobe.exe",
        SKILL_ROOT / ".cache" / "ffmpeg" / "linux-x64" / "bin" / "ffprobe",
        SKILL_ROOT / ".cache" / "ffmpeg" / "macos" / "bin" / "ffprobe",
    ]
    for candidate in bundled_candidates:
        if candidate.exists():
            return str(candidate)
    return shutil.which("ffprobe")


def resolve_ffmpeg() -> str | None:
    for env_name in ("SUBTITLE_MATCHER_FFMPEG_BIN", "VIDEO_FFMPEG_BIN", "FFMPEG_BIN"):
        value = os.environ.get(env_name)
        if value:
            path = Path(value)
            if path.exists():
                return str(path)
            found = shutil.which(value)
            if found:
                return found
    bundled_candidates = [
        SKILL_ROOT / ".cache" / "ffmpeg" / "windows-x64" / "bin" / "ffmpeg.exe",
        SKILL_ROOT / ".cache" / "ffmpeg" / "windows-arm64" / "bin" / "ffmpeg.exe",
        SKILL_ROOT / ".cache" / "ffmpeg" / "linux-x64" / "bin" / "ffmpeg",
        SKILL_ROOT / ".cache" / "ffmpeg" / "macos" / "bin" / "ffmpeg",
    ]
    for candidate in bundled_candidates:
        if candidate.exists():
            return str(candidate)
    return shutil.which("ffmpeg")


def probe_duration_seconds(video_path: Path) -> float | None:
    ffprobe = resolve_ffprobe()
    if not ffprobe:
        return None
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def decode_text(path: Path) -> tuple[str, str]:
    data = path.read_bytes()
    encodings = ("utf-8-sig", "utf-8", "gb18030", "big5", "utf-16", "utf-16le", "utf-16be")
    for encoding in encodings:
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            pass

    try:
        from charset_normalizer import from_bytes
    except ImportError as exc:
        raise RuntimeError(
            f"Unable to decode subtitle {path}. Install charset-normalizer or pass a UTF-8/GB18030 subtitle."
        ) from exc

    match = from_bytes(data).best()
    if match is None:
        raise RuntimeError(f"Unable to decode subtitle: {path}")
    encoding = match.encoding or "unknown"
    return str(match), encoding


def parse_time_to_seconds(value: str) -> float:
    value = value.replace(",", ".")
    hour_text, minute_text, second_text = value.split(":")
    return int(hour_text) * 3600 + int(minute_text) * 60 + float(second_text)


def load_cues(path: Path) -> tuple[str, list[Cue], str]:
    text, encoding = decode_text(path)
    cues: list[Cue] = []

    for match in SRT_TIME_RE.finditer(text):
        cues.append(
            Cue(
                start=parse_time_to_seconds(match.group("start")),
                end=parse_time_to_seconds(match.group("end")),
            )
        )

    if not cues:
        for line in text.splitlines():
            match = ASS_DIALOGUE_RE.match(line)
            if match:
                cues.append(
                    Cue(
                        start=parse_time_to_seconds(match.group("start")),
                        end=parse_time_to_seconds(match.group("end")),
                    )
                )

    cues.sort(key=lambda cue: (cue.start, cue.end))
    return text, cues, encoding


def cjk_count(text: str) -> int:
    return len(CJK_RE.findall(text))


def chinese_script_counts(text: str) -> tuple[int, int]:
    simplified = sum(text.count(char) for char in SIMPLIFIED_ONLY_CHARS)
    traditional = sum(text.count(char) for char in TRADITIONAL_ONLY_CHARS)
    return simplified, traditional


def chinese_script_from_text(text: str) -> str | None:
    simplified, traditional = chinese_script_counts(text)
    if traditional >= 12 and traditional >= simplified * 1.25:
        return "cht"
    if simplified >= 12 and simplified >= traditional * 1.25:
        return "chs"
    return None


def language_from_name(path: Path, text: str | None = None) -> str:
    name = path.name
    if CHT_NAME_RE.search(name):
        return "cht"
    if CHS_NAME_RE.search(name):
        return "chs"
    if text:
        detected = chinese_script_from_text(text)
        if detected:
            return detected
    return "chs"


def is_probable_chinese_subtitle(path: Path) -> bool:
    if EN_ONLY_RE.search(path.name) and not (CHS_NAME_RE.search(path.name) or CHT_NAME_RE.search(path.name)):
        return False
    try:
        text, _encoding = decode_text(path)
    except RuntimeError:
        return False
    return cjk_count(text) >= 5


def is_sample_path(path: Path) -> bool:
    lowered = [part.lower() for part in path.parts]
    return "sample" in lowered or path.stem.lower() == "sample"


def iter_videos(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in VIDEO_EXTS and not is_sample_path(path)
    )


def iter_subtitles(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in SUBTITLE_EXTS)


def expected_subtitle_paths(video: Path) -> list[Path]:
    return [
        video.with_name(f"{video.stem}.{lang}{suffix}")
        for lang in LANG_SUFFIXES
        for suffix in (".srt", ".ass", ".ssa", ".vtt")
    ]


def existing_auto_subtitles(video: Path) -> list[Path]:
    return [path for path in expected_subtitle_paths(video) if path.exists()]


def score_local_subtitle(video: Path, subtitle: Path) -> int:
    score = 0
    if subtitle.parent == video.parent:
        score += 30
    if subtitle.parent.name.lower() == "subs":
        score += 15
    if subtitle.stem.lower().startswith(video.stem.lower()):
        score += 40
    if CHS_NAME_RE.search(subtitle.name):
        score += 30
    if CHT_NAME_RE.search(subtitle.name):
        score += 15
    if "official" in subtitle.name.lower() or "webrip" in subtitle.name.lower() or "web-dl" in subtitle.name.lower():
        score += 5
    if is_probable_chinese_subtitle(subtitle):
        score += 50
    return score


def local_subtitle_candidates(video: Path) -> list[Path]:
    search_roots = [video.parent, video.parent / "Subs", video.parent / "subs"]
    candidates: list[Path] = []
    for root in search_roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in SUBTITLE_EXTS:
                candidates.append(path)
    candidates = list(dict.fromkeys(candidates))
    candidates.sort(key=lambda path: score_local_subtitle(video, path), reverse=True)
    return candidates


def is_chinese_language_tag(value: str) -> bool:
    lowered = value.lower().replace("-", "_")
    return any(part in CHINESE_LANGUAGE_TAGS for part in lowered.split("_"))


def probe_subtitle_streams(video: Path) -> list[dict[str, Any]]:
    ffprobe = resolve_ffprobe()
    if not ffprobe:
        return []
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "s",
            "-show_entries",
            "stream=index,codec_name:stream_tags=language,title",
            "-of",
            "json",
            str(video),
        ],
        check=False,
        capture_output=True,
        text=True,
        errors="replace",
    )
    if result.returncode != 0:
        return []
    try:
        return list(json.loads(result.stdout).get("streams", []))
    except json.JSONDecodeError:
        return []


def reference_stream_score(stream: dict[str, Any]) -> int:
    codec = str(stream.get("codec_name", "")).lower()
    tags = stream.get("tags") or {}
    language = str(tags.get("language", "")).lower()
    title = str(tags.get("title", "")).lower()
    if codec not in TEXT_SUBTITLE_CODECS:
        return -999
    if language and is_chinese_language_tag(language):
        return -999

    score = 20
    if language in {"eng", "en"}:
        score += 80
    elif language:
        score += 30
    if "forced" in title:
        score -= 25
    if "sdh" in title or "hearing" in title:
        score -= 5
    if "commentary" in title:
        score -= 40
    return score


def extract_embedded_text_cues(video: Path, stream: dict[str, Any]) -> dict[str, Any] | None:
    ffmpeg = resolve_ffmpeg()
    if not ffmpeg:
        return None
    stream_index = stream.get("index")
    if stream_index is None:
        return None

    with tempfile.TemporaryDirectory(prefix="subtitle_matcher_ref_") as temp_dir:
        output = Path(temp_dir) / f"stream_{stream_index}.srt"
        result = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-v",
                "error",
                "-i",
                str(video),
                "-map",
                f"0:{stream_index}",
                "-c:s",
                "srt",
                str(output),
            ],
            check=False,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=120,
        )
        if result.returncode != 0 or not output.exists():
            return None
        try:
            _text, cues, _encoding = load_cues(output)
        except RuntimeError:
            return None
        if len(cues) < 20:
            return None

    tags = stream.get("tags") or {}
    return {
        "stream_index": stream_index,
        "codec": stream.get("codec_name", ""),
        "language": tags.get("language", ""),
        "title": tags.get("title", ""),
        "cue_count": len(cues),
        "cues": cues,
    }


def reference_cache_path(video: Path) -> Path:
    digest = hashlib.sha1(str(video).encode("utf-8", errors="replace")).hexdigest()
    return SKILL_ROOT / ".cache" / "reference-cues" / f"{digest}.json"


def video_fingerprint(video: Path) -> dict[str, Any]:
    stat = video.stat()
    return {
        "path": str(video),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def load_cached_reference(video: Path) -> dict[str, Any] | None:
    cache_path = reference_cache_path(video)
    if not cache_path.exists():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        if data.get("fingerprint") != video_fingerprint(video):
            return None
        cues = [Cue(float(start), float(end)) for start, end in data.get("cues", [])]
        if len(cues) < 20:
            return None
        reference = dict(data.get("reference", {}))
        reference["cues"] = cues
        reference["cue_count"] = len(cues)
        reference["cache"] = str(cache_path)
        return reference
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def save_cached_reference(video: Path, reference: dict[str, Any]) -> None:
    cache_path = reference_cache_path(video)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fingerprint": video_fingerprint(video),
        "reference": {key: value for key, value in reference.items() if key != "cues"},
        "cues": [[cue.start, cue.end] for cue in reference.get("cues", [])],
    }
    cache_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def embedded_reference_cues(video: Path) -> dict[str, Any] | None:
    cache_key = str(video)
    if cache_key in REFERENCE_CUE_CACHE:
        return REFERENCE_CUE_CACHE[cache_key]

    cached = load_cached_reference(video)
    if cached:
        REFERENCE_CUE_CACHE[cache_key] = cached
        return cached

    streams = sorted(probe_subtitle_streams(video), key=reference_stream_score, reverse=True)
    streams = [stream for stream in streams if reference_stream_score(stream) > 0]
    for stream in streams[:4]:
        try:
            reference = extract_embedded_text_cues(video, stream)
        except (subprocess.TimeoutExpired, OSError):
            reference = None
        if reference:
            save_cached_reference(video, reference)
            REFERENCE_CUE_CACHE[cache_key] = reference
            return reference

    REFERENCE_CUE_CACHE[cache_key] = None
    return None


def filtered_cues(cues: list[Cue]) -> list[Cue]:
    return [
        cue
        for cue in cues
        if cue.end > cue.start and 0.15 <= (cue.end - cue.start) <= 30.0 and cue.start >= 0
    ]


def percentile(values: list[float], ratio: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * ratio))))
    return ordered[index]


def compare_cue_timelines(candidate_cues: list[Cue], reference: dict[str, Any]) -> dict[str, Any]:
    candidate = filtered_cues(candidate_cues)
    reference_cues = filtered_cues(reference["cues"])
    if len(candidate) < 20 or len(reference_cues) < 20:
        return {
            "status": "insufficient",
            "sample_count": 0,
            "reason": "too_few_filtered_cues",
        }

    reference_mids = [(cue.start + cue.end) / 2 for cue in reference_cues]
    offsets: list[float] = []
    for cue in candidate:
        mid = (cue.start + cue.end) / 2
        pos = bisect.bisect_left(reference_mids, mid)
        choices = []
        if pos < len(reference_mids):
            choices.append(reference_mids[pos])
        if pos > 0:
            choices.append(reference_mids[pos - 1])
        if not choices:
            continue
        nearest = min(choices, key=lambda ref_mid: abs(mid - ref_mid))
        offsets.append(mid - nearest)

    if len(offsets) < 20:
        return {
            "status": "insufficient",
            "sample_count": len(offsets),
            "reason": "too_few_matched_cues",
        }

    abs_offsets = [abs(value) for value in offsets]
    median_offset = float(median(offsets))
    residuals = [abs(value - median_offset) for value in offsets]
    within_2s = sum(1 for value in abs_offsets if value <= 2.0)
    shifted_within_2s = sum(1 for value in residuals if value <= 2.0)
    coverage_2s = within_2s / len(offsets)
    shifted_coverage_2s = shifted_within_2s / len(offsets)
    median_abs = float(median(abs_offsets))
    p90_abs = float(percentile(abs_offsets, 0.9) or 0.0)
    p90_residual = float(percentile(residuals, 0.9) or 0.0)

    if coverage_2s >= 0.85 and median_abs <= 0.5:
        status = "pass"
    elif coverage_2s >= 0.70 and median_abs <= 0.9 and p90_abs <= 3.0:
        status = "pass"
    elif abs(median_offset) <= 2.5 and shifted_coverage_2s >= 0.78 and p90_residual <= 2.0:
        status = "pass"
    elif abs(median_offset) <= 8.0 and shifted_coverage_2s >= 0.62 and p90_residual <= 4.0:
        status = "manual_check"
    else:
        status = "fail"

    return {
        "status": status,
        "sample_count": len(offsets),
        "candidate_cue_count": len(candidate),
        "reference_cue_count": len(reference_cues),
        "coverage_2s": round(coverage_2s, 4),
        "shifted_coverage_2s": round(shifted_coverage_2s, 4),
        "median_offset_seconds": round(median_offset, 3),
        "median_abs_offset_seconds": round(median_abs, 3),
        "p90_abs_offset_seconds": round(p90_abs, 3),
        "p90_residual_seconds": round(p90_residual, 3),
        "reference_stream_index": reference.get("stream_index"),
        "reference_language": reference.get("language", ""),
        "reference_title": reference.get("title", ""),
        "reference_codec": reference.get("codec", ""),
    }


def timeline_anchor_summary(anchor: dict[str, Any]) -> str:
    label = f"stream={anchor.get('reference_stream_index')}"
    language = anchor.get("reference_language")
    title = anchor.get("reference_title")
    if language:
        label += f" lang={language}"
    if title:
        label += f" title={title}"
    return (
        f"{label} coverage2s={anchor.get('coverage_2s')} "
        f"median_abs={anchor.get('median_abs_offset_seconds')}s "
        f"p90_abs={anchor.get('p90_abs_offset_seconds')}s "
        f"offset={anchor.get('median_offset_seconds')}s"
    )


def rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def validation_threshold(video_duration: float) -> float:
    return max(30.0, min(180.0, video_duration * 0.02))


def extract_reason_diffs(row: dict[str, str]) -> list[float]:
    diffs: list[float] = []
    value = row.get("diff_seconds", "").strip()
    if value:
        try:
            diffs.append(float(value))
        except ValueError:
            pass
    reason = row.get("reason", "")
    for match in REASON_DIFF_RE.finditer(reason):
        try:
            diffs.append(float(match.group("seconds")))
        except ValueError:
            pass
    return diffs


def extract_urls(text: str) -> list[str]:
    urls: list[str] = []
    for match in URL_RE.finditer(text):
        urls.append(match.group(0).rstrip(").,;，；"))
    return list(dict.fromkeys(urls))


def contains_any(text: str, markers: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in markers)


def audit_report_row(row: dict[str, str]) -> dict[str, Any]:
    reason = row.get("reason", "")
    status = row.get("status", "")
    diffs = extract_reason_diffs(row)
    max_diff = max(diffs) if diffs else None
    comparable_diffs = [diff for diff in diffs if diff <= 600]
    comparable_diff = max(comparable_diffs) if comparable_diffs else None
    categories: list[str] = []

    if contains_any(reason, HARD_REJECT_MARKERS):
        categories.append("hard_reject")

    if status == "not_completed":
        if comparable_diff is not None and (
            "duration_mismatch" in reason or "时长不匹配" in reason or "最后时间码差" in reason
        ):
            categories.append("needs_compare")
        if contains_any(reason, RETRY_DOWNLOAD_MARKERS):
            categories.append("retry_download")
        if contains_any(reason, RETRY_EXTRACT_MARKERS):
            categories.append("retry_extract")
        if contains_any(reason, RELAXED_FILTER_MARKERS):
            categories.append("review_relaxed_filter")
        if not categories:
            categories.append("unresolved_not_completed")
    else:
        if max_diff is not None and max_diff >= 180:
            categories.append("manual_check")
        if "人工抽查" in reason or "中风险" in reason or "依赖" in reason:
            categories.append("manual_check")

    categories = list(dict.fromkeys(categories))
    return {
        "video": row.get("video", ""),
        "status": status,
        "source": row.get("source", ""),
        "candidate": row.get("candidate", ""),
        "target": row.get("target", ""),
        "max_diff_seconds": None if max_diff is None else round(max_diff, 3),
        "comparable_diff_seconds": None if comparable_diff is None else round(comparable_diff, 3),
        "categories": categories,
        "urls": extract_urls(reason),
        "reason": reason,
    }


def validate_subtitle(video: Path, subtitle: Path, use_embedded_reference: bool = True) -> dict[str, Any]:
    text, cues, encoding = load_cues(subtitle)
    chinese_chars = cjk_count(text)
    script = chinese_script_from_text(text)
    duration = probe_duration_seconds(video)
    report: dict[str, Any] = {
        "video": str(video),
        "subtitle": str(subtitle),
        "encoding": encoding,
        "script": script,
        "cue_count": len(cues),
        "cjk_count": chinese_chars,
        "video_duration_seconds": duration,
        "last_subtitle_end_seconds": None,
        "diff_seconds": None,
        "threshold_seconds": None,
        "status": "fail",
        "reason": "",
    }

    if not cues:
        report["reason"] = "too_few_cues: no parseable subtitle timecodes"
        return report
    if len(cues) < 10:
        report["reason"] = f"too_few_cues: {len(cues)}"
        return report
    if chinese_chars < 5:
        report["reason"] = "non_chinese"
        return report

    last_end = cues[-1].end
    first_start = cues[0].start
    span = max(0.0, last_end - first_start)
    report["last_subtitle_end_seconds"] = last_end
    report["first_subtitle_start_seconds"] = round(first_start, 3)
    report["subtitle_span_seconds"] = round(span, 3)

    if duration is None:
        report["status"] = "manual_check"
        report["reason"] = "ffprobe_unavailable: Chinese subtitle with parseable cues, duration not checked"
        return report

    diff = abs(duration - last_end)
    ending_gap = duration - last_end
    threshold = validation_threshold(duration)
    report["diff_seconds"] = round(diff, 3)
    report["ending_gap_seconds"] = round(ending_gap, 3)
    report["threshold_seconds"] = round(threshold, 3)
    report["subtitle_span_ratio"] = round(span / duration, 4) if duration > 0 else None

    anchor: dict[str, Any] | None = None
    should_compare_anchor = use_embedded_reference and diff > threshold
    if should_compare_anchor:
        reference = embedded_reference_cues(video)
        if reference:
            anchor = compare_cue_timelines(cues, reference)
            report["embedded_reference"] = {key: value for key, value in anchor.items() if key != "cues"}

    if anchor and anchor.get("status") == "pass":
        report["status"] = "pass"
        report["reason"] = (
            f"timeline_anchor_match {timeline_anchor_summary(anchor)}; "
            f"duration_diff={diff:.1f}s threshold={threshold:.1f}s"
        )
    elif anchor and anchor.get("status") == "fail" and diff <= threshold:
        report["status"] = "manual_check"
        report["reason"] = (
            f"duration_match_but_timeline_anchor_mismatch {timeline_anchor_summary(anchor)}; "
            f"duration_diff={diff:.1f}s threshold={threshold:.1f}s"
        )
    elif diff <= threshold:
        report["status"] = "pass"
        report["reason"] = f"duration_match diff={diff:.1f}s threshold={threshold:.1f}s"
    elif anchor and anchor.get("status") == "manual_check":
        report["status"] = "manual_check"
        report["reason"] = (
            f"timeline_anchor_needs_check {timeline_anchor_summary(anchor)}; "
            f"duration_diff={diff:.1f}s threshold={threshold:.1f}s"
        )
    elif ending_gap >= 0 and diff <= 600:
        report["status"] = "manual_check"
        report["reason"] = (
            f"large_ending_gap diff={diff:.1f}s threshold={threshold:.1f}s; "
            "requires secondary comparison before final rejection or acceptance"
        )
    else:
        report["status"] = "fail"
        report["reason"] = f"duration_mismatch diff={diff:.1f}s threshold={threshold:.1f}s"
    return report


def write_json(data: Any, output: str | None) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if output:
        Path(output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


def cmd_doctor(args: argparse.Namespace) -> int:
    loaded_env = load_env_files(args.env_file)
    if loaded_env:
        print("OK env files loaded:")
        for path in loaded_env:
            print(f"  {path}")
    else:
        print("OK no .env files found; using current shell environment")

    missing = require_modules(
        {
            "dotenv": "python-dotenv",
            "requests": "requests",
            "bs4": "beautifulsoup4",
            "charset_normalizer": "charset-normalizer",
        }
    )
    if missing:
        print("Error: missing Python dependencies:", ", ".join(missing), file=sys.stderr)
        print(f"Install with: python -m pip install -r {SKILL_ROOT / 'requirements.txt'}", file=sys.stderr)
        return 1
    print("OK Python dependencies available")

    proxy_names = active_proxy_names()
    if proxy_names:
        print("OK proxy environment variables enabled:", ", ".join(proxy_names))
    else:
        print("OK no proxy environment variables enabled")

    ffprobe = resolve_ffprobe()
    if ffprobe:
        print(f"OK ffprobe: {ffprobe}")
    else:
        print("Warning: ffprobe not found; duration validation will fall back to manual_check")
    ffmpeg = resolve_ffmpeg()
    if ffmpeg:
        print(f"OK ffmpeg: {ffmpeg}")
    else:
        print("Warning: ffmpeg not found; embedded subtitle timeline validation will be skipped")
    return 0


def cmd_inventory(args: argparse.Namespace) -> int:
    load_env_files(args.env_file)
    root = Path(args.root).resolve()
    videos = iter_videos(root)
    subtitles = iter_subtitles(root)
    rows: list[dict[str, Any]] = []
    for video in videos:
        auto = existing_auto_subtitles(video)
        row: dict[str, Any] = {
            "video": rel(video, root),
            "auto_subtitles": [rel(path, root) for path in auto],
            "has_auto_subtitle": bool(auto),
        }
        if args.durations:
            row["duration_seconds"] = probe_duration_seconds(video)
        rows.append(row)

    data = {
        "root": str(root),
        "video_count": len(videos),
        "subtitle_count": len(subtitles),
        "videos": rows,
    }
    write_json(data, args.output)
    return 0


def cmd_normalize_existing(args: argparse.Namespace) -> int:
    load_env_files(args.env_file)
    root = Path(args.root).resolve()
    actions: list[dict[str, Any]] = []
    for video in iter_videos(root):
        if existing_auto_subtitles(video):
            actions.append({"video": rel(video, root), "status": "skipped_existing"})
            continue

        candidates = [path for path in local_subtitle_candidates(video) if is_probable_chinese_subtitle(path)]
        if not candidates:
            actions.append({"video": rel(video, root), "status": "not_completed", "reason": "no_local_chinese_subtitle"})
            continue

        source = candidates[0]
        lang = language_from_name(source)
        target = video.with_name(f"{video.stem}.{lang}{source.suffix.lower()}")
        action = {
            "video": rel(video, root),
            "status": "would_copy" if not args.apply else "copied",
            "source": rel(source, root),
            "target": rel(target, root),
        }
        if args.apply:
            if target.exists() and not args.overwrite:
                action["status"] = "skipped_target_exists"
            else:
                shutil.copy2(source, target)
        actions.append(action)

    write_json({"root": str(root), "apply": args.apply, "actions": actions}, args.output)
    return 0


def cmd_validate_subtitle(args: argparse.Namespace) -> int:
    load_env_files(args.env_file)
    report = validate_subtitle(
        Path(args.video).resolve(),
        Path(args.subtitle).resolve(),
        use_embedded_reference=not args.no_embedded_reference,
    )
    if args.format == "json":
        write_json(report, args.output)
    else:
        print(f"status: {report['status']}")
        print(f"reason: {report['reason']}")
        print(f"cue_count: {report['cue_count']}")
        print(f"cjk_count: {report['cjk_count']}")
        if report["diff_seconds"] is not None:
            print(f"diff_seconds: {report['diff_seconds']}")
            print(f"threshold_seconds: {report['threshold_seconds']}")
    return 0 if report["status"] in {"pass", "manual_check"} else 2


def format_seconds(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        return f"{float(value):.1f}s"
    except (TypeError, ValueError):
        return str(value)


def badge(text: str, kind: str = "") -> str:
    class_name = "badge"
    if kind:
        class_name += f" {escape(kind)}"
    return f'<span class="{class_name}">{escape(text)}</span>'


def links_html(urls: list[str]) -> str:
    if not urls:
        return ""
    parts = []
    for url in urls:
        safe_url = escape(url, quote=True)
        parts.append(f'<a href="{safe_url}" target="_blank" rel="noreferrer">{safe_url}</a>')
    return "<br>".join(parts)


def reason_html(reason: str) -> str:
    if not reason:
        return ""
    safe_reason = escape(reason)
    if len(reason) <= 260:
        return f'<div class="reason">{safe_reason}</div>'
    lead = escape(reason[:260].rstrip())
    return (
        '<details class="reason">'
        f"<summary>{lead}...</summary>"
        f"<div>{safe_reason}</div>"
        "</details>"
    )


def report_abs_path(root_text: str, value: str) -> str:
    if not value:
        return ""
    path = Path(value)
    if path.is_absolute() or not root_text:
        return str(path)
    return str(Path(root_text) / path)


def b64url_text(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


def vlc_play_uri(item: dict[str, Any], root_text: str) -> str:
    video = report_abs_path(root_text, str(item.get("video") or ""))
    if not video:
        return ""

    params = [f"path={b64url_text(video)}"]
    subtitle = report_abs_path(root_text, str(item.get("target") or ""))
    if subtitle:
        params.append(f"subtitle={b64url_text(subtitle)}")
    return f"vlcfile://open?{'&'.join(params)}"


def play_html(item: dict[str, Any], root_text: str) -> str:
    uri = vlc_play_uri(item, root_text)
    if not uri:
        return ""
    return f'<a class="play-link" href="{escape(uri, quote=True)}" title="用 VLC 打开视频">VLC</a>'


def render_items_table(items: list[dict[str, Any]], root_text: str = "") -> str:
    if not items:
        return '<p class="empty">无</p>'

    rows = []
    for item in items:
        categories = list(item.get("categories", []))
        status_text = STATUS_LABELS.get(item.get("status", ""), item.get("status", ""))
        category_badges = " ".join(
            badge(CATEGORY_LABELS.get(category, category), category)
            for category in categories
            if category != item.get("status", "")
        )
        status_cell = badge(status_text, item.get("status", ""))
        if category_badges:
            status_cell += f"<br>{category_badges}"
        rows.append(
            "<tr>"
            f'<td class="video">{escape(item.get("video", ""))}</td>'
            f"<td>{play_html(item, root_text)}</td>"
            f"<td>{status_cell}</td>"
            f"<td>{escape(item.get('source', ''))}</td>"
            f"<td>{escape(item.get('candidate', ''))}</td>"
            f"<td>{escape(item.get('target', ''))}</td>"
            f"<td>{format_seconds(item.get('comparable_diff_seconds'))}</td>"
            f"<td>{format_seconds(item.get('max_diff_seconds'))}</td>"
            f"<td>{links_html(item.get('urls', []))}</td>"
            f"<td>{reason_html(item.get('reason', ''))}</td>"
            "</tr>"
        )
    return (
        '<table class="report-table">'
        "<thead><tr>"
        "<th>视频</th><th>播放</th><th>状态</th><th>来源</th><th>候选</th><th>目标字幕</th>"
        "<th>可比差值</th><th>最大差值</th><th>链接</th><th>原因</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def render_html_report(data: dict[str, Any], title: str) -> str:
    category_counts = data.get("category_counts", {})
    by_category = data.get("by_category", {})
    root_text = str(data.get("root", ""))
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sections = [
        ("completed_subhd", "SubHD 已完成", "已下载到视频同目录，并通过基础中文与时长校验。"),
        ("completed", "已完成", "已有字幕或其他来源字幕已通过基础校验。"),
        ("skipped_existing", "已有字幕", "视频同目录已有可自动加载字幕，本轮未覆盖。"),
        ("needs_compare", "二阶段比对", "候选存在且差值未超过可比范围，不能只凭末条时间码拒绝。"),
        ("manual_check", "人工抽查", "已完成或强候选中存在大间隔、片源依赖或其他需要快速确认的问题。"),
        ("retry_download", "重试下载", "候选存在，但网络、API、签名或浏览器校验失败。"),
        ("retry_extract", "重试解压", "页面或下载包存在字幕线索，但没有解出有效字幕文件。"),
        ("review_relaxed_filter", "放宽过滤复核", "默认过滤可能过严，低置信或机器翻译候选需要人工决定。"),
        ("hard_reject", "硬拒绝", "标题、年份、季集或语言明确不匹配。"),
        ("unresolved_not_completed", "未完成待判断", "还没有足够线索分类的未完成项。"),
    ]

    stat_cards = []
    for key, label, _description in sections:
        count = int(category_counts.get(key, 0))
        stat_cards.append(
            f'<div class="stat"><div class="stat-value">{count}</div><div class="stat-label">{escape(label)}</div></div>'
        )

    section_html = []
    for key, label, description in sections:
        items = by_category.get(key, [])
        if not items:
            continue
        section_html.append(
            f'<section><h2>{escape(label)} <span>{len(items)}</span></h2>'
            f'<p class="section-intro">{escape(description)}</p>'
            f"{render_items_table(items, root_text)}</section>"
        )

    embedded_json = escape(json.dumps(data, ensure_ascii=False), quote=False)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>
:root {{
  color-scheme: light;
  --bg: #f7f7f4;
  --text: #202124;
  --muted: #6b6f76;
  --line: #d8d8d0;
  --panel: #ffffff;
  --blue: #2563eb;
  --amber: #b45309;
  --red: #b91c1c;
  --green: #15803d;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  font: 14px/1.55 "Segoe UI", "Microsoft YaHei", Arial, sans-serif;
  color: var(--text);
  background: var(--bg);
}}
header {{
  padding: 28px 32px 18px;
  border-bottom: 1px solid var(--line);
  background: var(--panel);
}}
h1 {{ margin: 0 0 6px; font-size: 26px; font-weight: 650; }}
.meta {{ color: var(--muted); }}
main {{ padding: 22px 32px 40px; }}
.stats {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px;
  margin-bottom: 24px;
}}
.stat {{
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 14px 16px;
}}
.stat-value {{ font-size: 28px; font-weight: 700; }}
.stat-label {{ color: var(--muted); }}
section {{ margin: 24px 0 32px; }}
h2 {{ font-size: 20px; margin: 0 0 6px; }}
h2 span {{ color: var(--muted); font-size: 15px; }}
.section-intro {{ margin: 0 0 12px; color: var(--muted); }}
.report-table {{
  width: 100%;
  border-collapse: collapse;
  background: var(--panel);
  border: 1px solid var(--line);
}}
th, td {{
  border-top: 1px solid var(--line);
  padding: 8px 10px;
  text-align: left;
  vertical-align: top;
}}
th {{
  position: sticky;
  top: 0;
  background: #efeee8;
  z-index: 1;
}}
.video {{ min-width: 260px; overflow-wrap: anywhere; }}
td {{ overflow-wrap: anywhere; }}
a {{ color: var(--blue); text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.play-link {{
  display: inline-block;
  min-width: 44px;
  padding: 3px 8px;
  border-radius: 4px;
  background: #e0f2fe;
  color: #075985;
  font-weight: 650;
  text-align: center;
}}
.play-link:hover {{ background: #bae6fd; text-decoration: none; }}
.badge {{
  display: inline-block;
  margin: 0 4px 4px 0;
  padding: 2px 6px;
  border-radius: 4px;
  background: #e7e5dd;
  color: #303030;
  font-size: 12px;
  white-space: nowrap;
}}
.needs_compare, .manual_check {{ background: #fef3c7; color: var(--amber); }}
.retry_download, .retry_extract, .review_relaxed_filter {{ background: #dbeafe; color: var(--blue); }}
.hard_reject, .not_completed {{ background: #fee2e2; color: var(--red); }}
.completed, .completed_subhd, .skipped_existing {{ background: #dcfce7; color: var(--green); }}
.reason summary {{ cursor: pointer; color: var(--muted); }}
.reason div {{ margin-top: 6px; white-space: pre-wrap; }}
.empty {{ color: var(--muted); }}
@media (max-width: 900px) {{
  header, main {{ padding-left: 14px; padding-right: 14px; }}
  .report-table {{ display: block; overflow-x: auto; }}
}}
</style>
</head>
<body>
<header>
  <h1>{escape(title)}</h1>
  <div class="meta">生成时间：{escape(generated)}；来源：{escape(str(data.get("source_report", data.get("csv", ""))))}</div>
  <div class="meta">说明：本报告为 HTML 输出；旧 CSV 仅作为导入源，不再作为用户可见报告。</div>
  <div class="meta">播放：点击 VLC 会调用本机 vlcfile 协议；首次点击时浏览器可能会询问是否允许打开外部应用。</div>
</header>
<main>
  <div class="stats">{''.join(stat_cards)}</div>
  {''.join(section_html) if section_html else '<p class="empty">没有需要展示的异常队列。</p>'}
</main>
<script type="application/json" id="subtitle-report-data">{embedded_json}</script>
</body>
</html>
"""


def write_html_report(data: dict[str, Any], output: str | Path, title: str = "字幕下载报告") -> Path:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_html_report(data, title), encoding="utf-8")
    return output_path


def group_report_rows(rows: list[dict[str, Any]], root: Path, source_report: str) -> dict[str, Any]:
    category_counts: dict[str, int] = {}
    by_category: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        for category in row.get("categories", []):
            category_counts[category] = category_counts.get(category, 0) + 1
            by_category.setdefault(category, []).append(row)
    return {
        "source_report": source_report,
        "root": str(root),
        "row_count": len(rows),
        "category_counts": category_counts,
        "by_category": by_category,
        "rows": rows,
    }


def scan_report_row(root: Path, video: Path, use_embedded_reference: bool = True) -> dict[str, Any]:
    subtitles = existing_auto_subtitles(video)
    if not subtitles:
        return {
            "video": rel(video, root),
            "status": "not_completed",
            "source": "current-scan",
            "candidate": "",
            "target": "",
            "max_diff_seconds": None,
            "comparable_diff_seconds": None,
            "categories": ["unresolved_not_completed"],
            "urls": [],
            "reason": "当前目录未发现自动加载命名的中文字幕",
        }

    subtitle = subtitles[0]
    try:
        report = validate_subtitle(video, subtitle, use_embedded_reference=use_embedded_reference)
    except Exception as exc:
        return {
            "video": rel(video, root),
            "status": "needs_compare",
            "source": "current-scan",
            "candidate": subtitle.name,
            "target": rel(subtitle, root),
            "max_diff_seconds": None,
            "comparable_diff_seconds": None,
            "categories": ["needs_compare"],
            "urls": [],
            "reason": f"校验失败：{type(exc).__name__}: {exc}",
        }

    diff = report.get("diff_seconds")
    if report["status"] == "pass":
        status = "completed"
        category = "completed"
    elif report["status"] == "manual_check":
        status = "manual_check"
        category = "manual_check"
    else:
        status = "needs_compare"
        category = "needs_compare"

    return {
        "video": rel(video, root),
        "status": status,
        "source": "current-scan",
        "candidate": subtitle.name,
        "target": rel(subtitle, root),
        "max_diff_seconds": diff,
        "comparable_diff_seconds": diff if isinstance(diff, (int, float)) and diff <= 600 else None,
        "categories": [category],
        "urls": [],
        "reason": (
            f"ffprobe validation: {report['status']} {report.get('reason')} "
            f"cues={report.get('cue_count')} cjk={report.get('cjk_count')}"
        ),
    }


def cmd_scan_report(args: argparse.Namespace) -> int:
    load_env_files(args.env_file)
    root = Path(args.root).resolve()
    videos = iter_videos(root)
    rows = []
    use_embedded_reference = args.embedded_reference and not args.no_embedded_reference
    for index, video in enumerate(videos, start=1):
        if args.verbose:
            print(f"[{index}/{len(videos)}] {rel(video, root)}", flush=True)
        rows.append(scan_report_row(root, video, use_embedded_reference=use_embedded_reference))
    source = "current video folder scan + ffprobe validation"
    if use_embedded_reference:
        source += " + embedded subtitle timeline anchor"
    data = group_report_rows(rows, root, source)

    output = Path(args.html_output) if args.html_output else root / REPORT_FILENAME
    output_path = write_html_report(data, output, title=args.title)
    print(f"HTML report written: {output_path}")
    if args.json_output:
        write_json(data, args.json_output)
    return 0


def cmd_audit_report(args: argparse.Namespace) -> int:
    load_env_files(args.env_file)
    source_arg = args.legacy_csv or args.csv
    if not source_arg:
        raise RuntimeError("audit-report requires --legacy-csv for old report import")
    csv_path = Path(source_arg)
    audited: list[dict[str, Any]] = []
    with csv_path.open("r", encoding=args.encoding, newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            audited.append(audit_report_row(row))

    category_counts: dict[str, int] = {}
    by_category: dict[str, list[dict[str, Any]]] = {}
    for item in audited:
        for category in item["categories"]:
            category_counts[category] = category_counts.get(category, 0) + 1
            by_category.setdefault(category, []).append(item)

    data = {
        "source_report": str(csv_path),
        "row_count": len(audited),
        "category_counts": category_counts,
        "by_category": by_category,
    }

    if args.html_output or args.output:
        html_output = args.html_output or args.output
    elif args.root:
        html_output = str(Path(args.root) / REPORT_FILENAME)
    else:
        html_output = str(csv_path.with_suffix(".html"))
    output_path = write_html_report(data, html_output)
    print(f"HTML report written: {output_path}")
    if args.json_output:
        write_json(data, args.json_output)
    return 0


def add_env_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--env-file", help="Load this .env file instead of the standard .env search order")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Chinese subtitle matching helpers")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Check dependencies, .env loading, proxy vars, and ffprobe")
    add_env_arg(doctor)
    doctor.set_defaults(func=cmd_doctor)

    inventory = subparsers.add_parser("inventory", help="Scan videos and existing auto-load subtitles")
    add_env_arg(inventory)
    inventory.add_argument("--root", required=True, help="Video directory to scan")
    inventory.add_argument("--output", help="Write JSON output to this file")
    inventory.add_argument("--durations", action="store_true", help="Probe video durations with ffprobe")
    inventory.set_defaults(func=cmd_inventory)

    normalize = subparsers.add_parser("normalize-existing", help="Copy local Chinese subtitles to VLC auto-load names")
    add_env_arg(normalize)
    normalize.add_argument("--root", required=True, help="Video directory to scan")
    normalize.add_argument("--output", help="Write JSON output to this file")
    normalize.add_argument("--dry-run", action="store_true", help="Preview only; this is the default unless --apply is set")
    normalize.add_argument("--apply", action="store_true", help="Actually copy subtitle files")
    normalize.add_argument("--overwrite", action="store_true", help="Allow replacing an existing target subtitle")
    normalize.set_defaults(func=cmd_normalize_existing)

    validate = subparsers.add_parser("validate-subtitle", help="Validate one subtitle against one video")
    add_env_arg(validate)
    validate.add_argument("--video", required=True, help="Video file")
    validate.add_argument("--subtitle", required=True, help="Subtitle file")
    validate.add_argument("--output", help="Write JSON output to this file")
    validate.add_argument("--format", choices=("json", "text"), default="json")
    validate.add_argument(
        "--no-embedded-reference",
        action="store_true",
        help="Skip embedded non-Chinese subtitle timeline comparison",
    )
    validate.set_defaults(func=cmd_validate_subtitle)

    scan_report = subparsers.add_parser(
        "scan-report",
        help="Generate the HTML report from the current video folder and auto-load subtitles",
    )
    add_env_arg(scan_report)
    scan_report.add_argument("--root", required=True, help="Target video root")
    scan_report.add_argument("--html-output", help=f"Write HTML report to this file; default is <root>/{REPORT_FILENAME}")
    scan_report.add_argument("--json-output", help="Optional machine-readable JSON sidecar")
    scan_report.add_argument(
        "--embedded-reference",
        action="store_true",
        help="Use embedded non-Chinese subtitle timeline comparison for rows with large duration gaps; slower",
    )
    scan_report.add_argument(
        "--no-embedded-reference",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    scan_report.add_argument("--verbose", action="store_true", help="Print per-video scan progress")
    scan_report.add_argument(
        "--title",
        default=DEFAULT_REPORT_TITLE,
        help="HTML page title; default is encoded safely inside Python",
    )
    scan_report.set_defaults(func=cmd_scan_report)

    audit = subparsers.add_parser(
        "audit-report",
        help="Render an HTML report from a legacy report import",
    )
    add_env_arg(audit)
    audit.add_argument("--legacy-csv", help="Legacy CSV report path to import; do not use CSV as final output")
    audit.add_argument("--root", help="Target video root; default HTML output is <root>/_subtitle_download_report.html")
    audit.add_argument("--csv", help=argparse.SUPPRESS)
    audit.add_argument("--html-output", help="Write HTML report to this file")
    audit.add_argument("--output", help="Deprecated alias for --html-output")
    audit.add_argument("--json-output", help="Optional machine-readable JSON sidecar")
    audit.add_argument("--encoding", default="utf-8-sig", help="CSV encoding")
    audit.set_defaults(func=cmd_audit_report)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
