#!/usr/bin/env python3
import argparse
import shutil
import sys
import tempfile
from pathlib import Path

from common import (
    build_speech_segments,
    configure_logging,
    detect_silences,
    extract_audio,
    load_env,
    media_duration,
    seconds_to_srt_timestamp,
    speech_transcribe,
)


def write_srt(
    *,
    cues: list[tuple[float, float, str]],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for idx, (start, end, text) in enumerate(cues, start=1):
        lines.extend(
            [
                str(idx),
                f"{seconds_to_srt_timestamp(start)} --> {seconds_to_srt_timestamp(end)}",
                text.strip(),
                "",
            ]
        )
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate rough SRT subtitles from video audio via speech skill")
    parser.add_argument("--input-file", required=True, help="输入视频路径")
    parser.add_argument("--output-srt", required=True, help="输出 SRT 路径")
    parser.add_argument("--output-text", help="保存合并后的纯文本转写")
    parser.add_argument("--api-base", help="透传给 speech transcribe 的 ASR 地址")
    parser.add_argument("--language", help="语种提示，例如 zh 或 en")
    parser.add_argument("--prompt", help="术语提示词")
    parser.add_argument("--timeout", type=int, default=300, help="单段转写超时秒数")
    parser.add_argument("--env-file", help="可选 .env 路径")
    parser.add_argument("--noise", default="-30dB", help="silencedetect 噪声阈值")
    parser.add_argument("--silence-duration", type=float, default=0.4, help="最短静音秒数")
    parser.add_argument("--min-segment", type=float, default=1.0, help="最短语音段秒数")
    parser.add_argument("--max-segment", type=float, default=10.0, help="最长语音段秒数")
    parser.add_argument("--merge-gap", type=float, default=0.3, help="相邻语音段合并阈值秒数")
    parser.add_argument("--lead-in", type=float, default=0.1, help="字幕开始前预留秒数")
    parser.add_argument("--lead-out", type=float, default=0.2, help="字幕结束后预留秒数")
    parser.add_argument("--keep-temp", help="保留中间切分音频目录")
    parser.add_argument("--quiet", action="store_true", help="仅输出错误")
    parser.add_argument("--verbose", action="store_true", help="输出更多诊断信息")
    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.quiet and args.verbose:
        parser.error("--quiet 和 --verbose 不能同时使用")

    import logging

    logger = logging.getLogger("video.generate_subtitles")
    configure_logging(quiet=args.quiet, verbose=args.verbose)
    load_env(env_file=args.env_file, logger=logger)

    input_path = Path(args.input_file)
    if not input_path.is_file():
        raise RuntimeError(f"视频文件不存在: {input_path}")

    total_duration = media_duration(input_path)
    silences = detect_silences(
        input_path,
        noise=args.noise,
        silence_duration=args.silence_duration,
    )
    segments = build_speech_segments(
        total_duration=total_duration,
        silences=silences,
        min_segment=args.min_segment,
        max_segment=args.max_segment,
        merge_gap=args.merge_gap,
    )

    if args.keep_temp:
        temp_root = Path(args.keep_temp)
        temp_root.mkdir(parents=True, exist_ok=True)
        cleanup_temp = False
    else:
        temp_root = Path(tempfile.mkdtemp(prefix="video-subtitles-"))
        cleanup_temp = True

    cues: list[tuple[float, float, str]] = []
    merged_lines: list[str] = []

    try:
        for idx, segment in enumerate(segments, start=1):
            audio_path = temp_root / f"segment_{idx:04d}.wav"
            text_path = temp_root / f"segment_{idx:04d}.txt"
            extract_audio(
                input_path=input_path,
                output_path=audio_path,
                start=segment.start,
                end=segment.end,
            )
            speech_transcribe(
                input_file=audio_path,
                output_text=text_path,
                api_base=args.api_base,
                language=args.language,
                prompt=args.prompt,
                env_file=args.env_file,
                timeout=args.timeout,
                quiet=args.quiet,
                verbose=args.verbose,
            )
            text = text_path.read_text(encoding="utf-8").strip()
            if not text:
                continue
            start = max(0.0, segment.start - args.lead_in)
            end = min(total_duration, segment.end + args.lead_out)
            cues.append((start, end, text))
            merged_lines.append(text)
            if not args.quiet:
                print(f"已转写片段 {idx}/{len(segments)}: {start:.2f}s - {end:.2f}s")

        if not cues:
            raise RuntimeError("未生成任何有效字幕。请检查视频音频、ASR 服务或切分参数。")

        write_srt(cues=cues, output_path=Path(args.output_srt))
        print(f"字幕已输出到 {args.output_srt}")

        if args.output_text:
            output_text_path = Path(args.output_text)
            output_text_path.parent.mkdir(parents=True, exist_ok=True)
            output_text_path.write_text("\n".join(merged_lines).strip() + "\n", encoding="utf-8")
            print(f"纯文本转写已输出到 {args.output_text}")
        return 0
    finally:
        if cleanup_temp:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
