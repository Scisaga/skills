#!/usr/bin/env python3
import argparse
import logging
import subprocess
import sys

from common import (
    SPEECH_ROOT,
    configure_logging,
    ensure_python_modules,
    load_env,
    resolve_binary,
)

logger = logging.getLogger("video.doctor")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Video skill runtime checker")
    parser.add_argument(
        "--env-file",
        help="指定 .env 文件路径；未指定时依次尝试当前目录 .env、skill 根目录 .env、脚本目录 .env",
    )
    parser.add_argument("--quiet", action="store_true", help="仅输出错误")
    parser.add_argument("--verbose", action="store_true", help="输出更多诊断信息")
    return parser


def tool_version(binary: str) -> str:
    result = subprocess.run(
        [binary, "-version"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.splitlines()[0]


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.quiet and args.verbose:
        parser.error("--quiet 和 --verbose 不能同时使用")

    configure_logging(quiet=args.quiet, verbose=args.verbose)
    loaded_env = load_env(env_file=args.env_file, logger=logger)
    if loaded_env:
        print(f"OK  已加载 .env: {loaded_env}")
    else:
        print("OK  未加载 .env，继续使用当前 shell 环境变量")

    ensure_python_modules({"dotenv": "python-dotenv"}, logger=logger)
    print("OK  Python 依赖可用: python-dotenv")

    ffmpeg_bin = resolve_binary("ffmpeg")
    ffprobe_bin = resolve_binary("ffprobe")
    print(f"OK  ffmpeg: {ffmpeg_bin}")
    print(f"OK  ffmpeg 版本: {tool_version(ffmpeg_bin)}")
    print(f"OK  ffprobe: {ffprobe_bin}")
    print(f"OK  ffprobe 版本: {tool_version(ffprobe_bin)}")

    transcribe_script = SPEECH_ROOT / "scripts" / "transcribe.py"
    if not transcribe_script.exists():
        raise RuntimeError(f"找不到 speech skill 转写脚本: {transcribe_script}")
    print(f"OK  speech 转写脚本存在: {transcribe_script}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
