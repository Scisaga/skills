#!/usr/bin/env python3
import argparse
import logging
import os
import sys
from urllib import error, request

from common import configure_logging, ensure_python_modules, load_env

DEFAULT_API_BASE = "http://127.0.0.1:12301"
DEFAULT_REGION = "eastasia"
logger = logging.getLogger("speech.doctor")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Speech skill runtime checker")
    parser.add_argument(
        "--mode",
        choices=["all", "synthesize", "transcribe"],
        default="all",
        help="检查范围，默认 all",
    )
    parser.add_argument("--api-base", help=f"ASR 服务地址，默认读取 QWEN_ASR_API_BASE 或 {DEFAULT_API_BASE}")
    parser.add_argument(
        "--region",
        help=f"Azure region，默认读取 AZURE_SPEECH_REGION 或 {DEFAULT_REGION}",
    )
    parser.add_argument(
        "--env-file",
        help="指定 .env 文件路径；未指定时依次尝试当前目录 .env、skill 根目录 .env、脚本目录 .env",
    )
    parser.add_argument("--quiet", action="store_true", help="仅输出警告和错误")
    parser.add_argument("--verbose", action="store_true", help="输出更多调试信息")
    return parser


def check_asr_health(api_base: str) -> None:
    endpoint = api_base.rstrip("/") + "/health"
    try:
        with request.urlopen(endpoint, timeout=10) as response:
            body = response.read().decode("utf-8", errors="replace")
    except error.URLError as exc:
        raise RuntimeError(f"ASR 健康检查失败: {exc.reason}") from exc

    print(f"OK  ASR 服务可达: {endpoint}")
    print(f"OK  ASR 健康状态: {body}")


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

    if args.mode in {"all", "synthesize"}:
        ensure_python_modules(
            {"azure.cognitiveservices.speech": "azure-cognitiveservices-speech"},
            logger=logger,
        )
        print("OK  TTS 依赖可用: azure-cognitiveservices-speech")

        if os.getenv("AZURE_SPEECH_KEY"):
            print("OK  已检测到环境变量: AZURE_SPEECH_KEY")
        else:
            raise RuntimeError("缺少环境变量 `AZURE_SPEECH_KEY`，TTS 无法使用。")
        region = args.region or os.getenv("AZURE_SPEECH_REGION") or DEFAULT_REGION
        print(f"OK  Azure Speech region: {region}")

    if args.mode in {"all", "transcribe"}:
        api_base = args.api_base or os.getenv("QWEN_ASR_API_BASE", DEFAULT_API_BASE)
        print(f"OK  ASR 地址: {api_base}")
        check_asr_health(api_base)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
