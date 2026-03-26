#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

from check_subtitle_sync import analyze_sync
from common import resolve_binary, run_command
from subtitle_utils import convert_subtitle_to_utf8


def build_softsub_cmd(
    ffmpeg_bin: str,
    input_path: str,
    subtitle_path: str,
    output_path: str,
    lang: str,
) -> list[str]:
    return [
        ffmpeg_bin,
        "-y",
        "-i",
        input_path,
        "-i",
        subtitle_path,
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-map",
        "1:0",
        "-c:v",
        "copy",
        "-c:a",
        "copy",
        "-c:s",
        "mov_text",
        "-metadata:s:s:0",
        f"language={lang}",
        "-disposition:s:0",
        "default",
        output_path,
    ]


def build_burnin_cmd(
    ffmpeg_bin: str,
    input_path: str,
    subtitle_path: str,
    output_path: str,
) -> list[str]:
    sub_posix = Path(subtitle_path).as_posix().replace(":", r"\:")
    sub_posix = sub_posix.replace("'", r"\'")
    return [
        ffmpeg_bin,
        "-y",
        "-i",
        input_path,
        "-vf",
        f"subtitles='{sub_posix}'",
        "-c:v",
        "libx264",
        "-crf",
        "18",
        "-preset",
        "medium",
        "-c:a",
        "copy",
        output_path,
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Merge subtitles into MP4 and optionally validate sync")
    parser.add_argument("--input-file", required=True, help="输入视频路径")
    parser.add_argument("--subtitle-file", required=True, help="外部字幕路径")
    parser.add_argument("--output-file", required=True, help="输出 MP4 路径")
    parser.add_argument("--lang", default="chi", help="字幕语言元数据，默认 chi")
    parser.add_argument("--sub-charenc", help="字幕源编码，例如 gb18030 或 big5")
    parser.add_argument("--sub-offset", type=float, default=0.0, help="字幕偏移秒数")
    parser.add_argument("--sub-no-newline", action="store_true", help="移除字幕内部换行")
    parser.add_argument("--burn-in", action="store_true", help="将字幕烧录进视频")
    parser.add_argument("--check-sync", action="store_true", help="合并后执行同步检查")
    parser.add_argument("--sync-report-json", help="保存同步检查 JSON")
    parser.add_argument("--noise", default="-30dB", help="同步检查的 silencedetect 阈值")
    parser.add_argument("--silence-duration", type=float, default=0.4, help="同步检查最短静音秒数")
    parser.add_argument("--min-segment", type=float, default=1.0, help="同步检查最短语音段秒数")
    parser.add_argument("--max-segment", type=float, default=12.0, help="同步检查最长语音段秒数")
    parser.add_argument("--merge-gap", type=float, default=0.3, help="同步检查语音段合并间隔秒数")
    parser.add_argument("--tolerance", type=float, default=0.5, help="同步检查中点容差秒数")
    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    ffmpeg_bin = resolve_binary("ffmpeg")
    input_path = str(Path(args.input_file))
    subtitle_path = str(Path(args.subtitle_file))
    output_path = str(Path(args.output_file))

    try:
        utf8_subtitle_path, used_enc, offset_applied, linebreaks_applied = convert_subtitle_to_utf8(
            subtitle_path,
            args.sub_charenc,
            args.sub_offset,
            args.sub_no_newline,
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 3

    print(f"字幕编码已转为 UTF-8，原编码: {used_enc}")
    if args.sub_offset != 0 and not offset_applied:
        print("Warning: 无法识别字幕格式，已跳过 offset 处理。", file=sys.stderr)
    if args.sub_no_newline and not linebreaks_applied:
        print("Warning: 无法识别字幕格式，已跳过换行折叠。", file=sys.stderr)

    try:
        if args.burn_in:
            cmd = build_burnin_cmd(ffmpeg_bin, input_path, utf8_subtitle_path, output_path)
        else:
            cmd = build_softsub_cmd(ffmpeg_bin, input_path, utf8_subtitle_path, output_path, args.lang)

        print("执行合并命令:")
        print(" ".join(cmd))
        run_command(cmd)

        if args.check_sync:
            report = analyze_sync(
                input_path=Path(args.input_file),
                subtitle_path=Path(utf8_subtitle_path),
                noise=args.noise,
                silence_duration=args.silence_duration,
                min_segment=args.min_segment,
                max_segment=args.max_segment,
                merge_gap=args.merge_gap,
                tolerance=args.tolerance,
            )
            print(f"同步检查结果: {report['status'].upper()}")
            if report["offset_hint"]:
                print(f"建议: {report['offset_hint']}")
            if args.sync_report_json:
                path = Path(args.sync_report_json)
                path.parent.mkdir(parents=True, exist_ok=True)
                import json

                path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if report["status"] == "fail":
                return 2
        return 0
    finally:
        try:
            Path(utf8_subtitle_path).unlink()
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
