#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

from common import extract_audio


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract WAV audio from a video file")
    parser.add_argument("--input-file", required=True, help="输入视频路径")
    parser.add_argument("--output-file", required=True, help="输出音频路径，建议 .wav")
    parser.add_argument("--start", type=float, help="起始秒数")
    parser.add_argument("--end", type=float, help="结束秒数")
    parser.add_argument("--sample-rate", type=int, default=16000, help="输出采样率")
    parser.add_argument("--stereo", action="store_true", help="保留双声道；默认转单声道")
    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    extract_audio(
        input_path=Path(args.input_file),
        output_path=Path(args.output_file),
        start=args.start,
        end=args.end,
        sample_rate=args.sample_rate,
        mono=not args.stereo,
    )
    print(f"音频已输出到 {args.output_file}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
