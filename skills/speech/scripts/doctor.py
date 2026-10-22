#!/usr/bin/env python3
"""Check the selected speech mode/provider; network checks are explicit."""
import argparse
import logging
import os
import sys
from urllib import error, request

from common import configure_logging, ensure_python_modules, load_env
from qwen_tts_client import QwenTTSClient, QwenTTSError

DEFAULT_API_BASE = "http://127.0.0.1:12301"
DEFAULT_REGION = "eastasia"
logger = logging.getLogger("speech.doctor")


def check_azure(region, service):
    if not os.getenv("AZURE_SPEECH_KEY"):
        raise RuntimeError("缺少 AZURE_SPEECH_KEY；Azure 回退未配置")
    ensure_python_modules({"azure.cognitiveservices.speech": "azure-cognitiveservices-speech"}, logger=logger)
    if service:
        from synthesize import get_speech_config
        sdk, config = get_speech_config(speech_key=os.environ["AZURE_SPEECH_KEY"], region=region)
        result = sdk.SpeechSynthesizer(speech_config=config, audio_config=None).get_voices_async("").get()
        if result.reason != sdk.ResultReason.VoicesListRetrieved:
            raise RuntimeError("Azure 音色查询失败；请检查 Key、区域与网络")
    print(f"OK  Azure 配置与 SDK: {region}" + ("；服务已验证" if service else "；未发网络请求"))


def check_qwen(voice, service):
    client = QwenTTSClient()
    ensure_python_modules({"lameenc": "lameenc"}, logger=logger)
    if not voice:
        raise QwenTTSError("缺少 QWEN_TTS_VOICE_ID 或 --qwen-voice；先运行 list-voices")
    if service:
        client.resolve({"qwen_voice": voice, "voice": "zh-CN-XiaochenNeural"})
    print(f"OK  Qwen 配置: {client.base_url} voice={voice}" + ("；就绪状态已验证" if service else "；未发网络请求"))


def check_asr_health(api_base):
    endpoint = api_base.rstrip("/") + "/health"
    try:
        with request.urlopen(endpoint, timeout=10) as response:
            response.read()
    except error.URLError as exc:
        raise RuntimeError(f"ASR 健康检查失败: {exc.reason}") from exc
    print(f"OK  ASR 服务可达: {endpoint}")


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("all", "synthesize", "transcribe"), default="all")
    parser.add_argument("--provider", choices=("auto", "qwen3-tts-openai", "azure-speech"), default="auto")
    parser.add_argument("--qwen-voice")
    parser.add_argument("--api-base", help="ASR 地址，默认读取 QWEN_ASR_API_BASE")
    parser.add_argument("--region")
    parser.add_argument("--env-file")
    parser.add_argument("--check-service", action="store_true", help="请求就绪状态或音色列表，不生成语音")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.quiet and args.verbose:
        parser.error("--quiet 和 --verbose 不能同时使用")
    configure_logging(quiet=args.quiet, verbose=args.verbose)
    loaded = load_env(env_file=args.env_file, logger=logger)
    print(f"INFO 配置来源: {loaded or '进程环境变量'}")
    if args.mode in {"all", "synthesize"}:
        if args.provider == "azure-speech":
            check_azure(args.region or os.getenv("AZURE_SPEECH_REGION", DEFAULT_REGION), args.check_service)
        else:
            try:
                check_qwen(args.qwen_voice or os.getenv("QWEN_TTS_VOICE_ID"), args.check_service)
            except (QwenTTSError, RuntimeError) as exc:
                if args.provider != "auto":
                    raise
                print(f"WARN Qwen 检查未通过: {exc}")
                try:
                    check_azure(args.region or os.getenv("AZURE_SPEECH_REGION", DEFAULT_REGION), args.check_service)
                except RuntimeError as azure:
                    raise RuntimeError(f"Qwen: {exc}; Azure: {azure}") from azure
            else:
                print("INFO auto 优先 Qwen；Azure 仅在失败且已配置时回退")
    if args.mode in {"all", "transcribe"}:
        api_base = args.api_base or os.getenv("QWEN_ASR_API_BASE", DEFAULT_API_BASE)
        if args.check_service:
            check_asr_health(api_base)
        else:
            print(f"OK  ASR 地址配置: {api_base}；未发网络请求")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, ValueError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        raise SystemExit(1)
