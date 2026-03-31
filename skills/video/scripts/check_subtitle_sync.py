#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

from common import (
    Interval,
    build_speech_segments,
    configure_logging,
    detect_silences,
    media_duration,
)
from subtitle_utils import load_subtitle_cues


def interval_overlap(left: Interval, right: Interval) -> float:
    return max(0.0, min(left.end, right.end) - max(left.start, right.start))


def total_interval_duration(intervals: list[Interval]) -> float:
    return sum(interval.duration for interval in intervals)


def midpoint_hits(cue_midpoint: float, intervals: list[Interval], tolerance: float) -> bool:
    for interval in intervals:
        if interval.start - tolerance <= cue_midpoint <= interval.end + tolerance:
            return True
    return False


def analyze_sync(
    *,
    input_path: Path,
    subtitle_path: Path,
    noise: str,
    silence_duration: float,
    min_segment: float,
    max_segment: float,
    merge_gap: float,
    tolerance: float,
) -> dict:
    cues = [
        cue
        for cue in load_subtitle_cues(subtitle_path)
        if cue.text.strip() and cue.end > cue.start
    ]
    if not cues:
        raise RuntimeError(f"字幕为空或无法解析: {subtitle_path}")

    total_duration = media_duration(input_path)
    silences = detect_silences(
        input_path,
        noise=noise,
        silence_duration=silence_duration,
    )
    speech_segments = build_speech_segments(
        total_duration=total_duration,
        silences=silences,
        min_segment=min_segment,
        max_segment=max_segment,
        merge_gap=merge_gap,
    )

    cue_intervals = [Interval(start=cue.start, end=cue.end) for cue in cues]
    speech_duration = total_interval_duration(speech_segments)
    subtitle_duration = total_interval_duration(cue_intervals)

    overlap_total = 0.0
    for cue_interval in cue_intervals:
        for speech_interval in speech_segments:
            overlap_total += interval_overlap(cue_interval, speech_interval)

    midpoint_match_count = sum(
        1 for cue in cues if midpoint_hits(cue.midpoint, speech_segments, tolerance)
    )

    first_speech_start = speech_segments[0].start if speech_segments else None
    last_speech_end = speech_segments[-1].end if speech_segments else None
    first_subtitle_start = cues[0].start
    last_subtitle_end = cues[-1].end

    first_delta = (
        None if first_speech_start is None else first_subtitle_start - first_speech_start
    )
    last_delta = None if last_speech_end is None else last_subtitle_end - last_speech_end
    midpoint_match_ratio = midpoint_match_count / len(cues)
    subtitle_overlap_ratio = (
        overlap_total / subtitle_duration if subtitle_duration > 0 else 0.0
    )
    speech_coverage_ratio = overlap_total / speech_duration if speech_duration > 0 else 0.0

    status = "pass"
    if (
        midpoint_match_ratio < 0.35
        or subtitle_overlap_ratio < 0.25
        or (first_delta is not None and abs(first_delta) > 8.0)
        or (last_delta is not None and abs(last_delta) > 8.0)
    ):
        status = "fail"
    elif (
        midpoint_match_ratio < 0.60
        or subtitle_overlap_ratio < 0.45
        or (first_delta is not None and abs(first_delta) > 3.0)
        or (last_delta is not None and abs(last_delta) > 3.0)
    ):
        status = "warn"

    offset_hint = None
    if first_delta is not None:
        if first_delta > tolerance:
            offset_hint = "字幕整体偏后，建议尝试负数 offset 让字幕更早出现。"
        elif first_delta < -tolerance:
            offset_hint = "字幕整体偏前，建议尝试正数 offset 让字幕更晚出现。"

    return {
        "status": status,
        "subtitle_count": len(cues),
        "speech_segment_count": len(speech_segments),
        "first_delta_seconds": first_delta,
        "last_delta_seconds": last_delta,
        "subtitle_overlap_ratio": subtitle_overlap_ratio,
        "speech_coverage_ratio": speech_coverage_ratio,
        "midpoint_match_ratio": midpoint_match_ratio,
        "offset_hint": offset_hint,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate whether subtitles roughly align to speech")
    parser.add_argument("--input-file", required=True, help="视频文件路径")
    parser.add_argument("--subtitle-file", required=True, help="字幕文件路径")
    parser.add_argument("--output-json", help="保存检查结果 JSON")
    parser.add_argument("--noise", default="-30dB", help="silencedetect 噪声阈值")
    parser.add_argument("--silence-duration", type=float, default=0.4, help="最短静音秒数")
    parser.add_argument("--min-segment", type=float, default=1.0, help="最短语音段秒数")
    parser.add_argument("--max-segment", type=float, default=12.0, help="最长语音段秒数")
    parser.add_argument("--merge-gap", type=float, default=0.3, help="语音段合并间隔秒数")
    parser.add_argument("--tolerance", type=float, default=0.5, help="中点命中容差秒数")
    parser.add_argument("--quiet", action="store_true", help="只输出错误")
    parser.add_argument("--verbose", action="store_true", help="输出更多诊断信息")
    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.quiet and args.verbose:
        parser.error("--quiet 和 --verbose 不能同时使用")

    configure_logging(quiet=args.quiet, verbose=args.verbose)

    report = analyze_sync(
        input_path=Path(args.input_file),
        subtitle_path=Path(args.subtitle_file),
        noise=args.noise,
        silence_duration=args.silence_duration,
        min_segment=args.min_segment,
        max_segment=args.max_segment,
        merge_gap=args.merge_gap,
        tolerance=args.tolerance,
    )

    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    print(f"同步检查结果: {report['status'].upper()}")
    print(f"字幕条数: {report['subtitle_count']}")
    print(f"语音段数: {report['speech_segment_count']}")
    if report["first_delta_seconds"] is not None:
        print(f"首条字幕与首段语音偏移: {report['first_delta_seconds']:.2f}s")
    if report["last_delta_seconds"] is not None:
        print(f"末条字幕与末段语音偏移: {report['last_delta_seconds']:.2f}s")
    print(f"字幕覆盖语音比例: {report['subtitle_overlap_ratio']:.2%}")
    print(f"语音被字幕覆盖比例: {report['speech_coverage_ratio']:.2%}")
    print(f"字幕中点命中率: {report['midpoint_match_ratio']:.2%}")
    if report["offset_hint"]:
        print(f"建议: {report['offset_hint']}")

    if report["status"] == "fail":
        return 2
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
