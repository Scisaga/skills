#!/usr/bin/env python3
import argparse
import json
import logging
import os
import sys
import uuid
from pathlib import Path
from urllib import error, request
import mimetypes

from common import configure_logging, load_env

DEFAULT_API_BASE = "http://127.0.0.1:12301"
DEFAULT_OUTPUT_TEXT = "transcript.txt"
DEFAULT_TIMEOUT = 300

logger = logging.getLogger("speech.transcribe")


def encode_multipart_formdata(*, fields: dict[str, str], file_path: Path) -> tuple[bytes, str]:
    boundary = f"----CodexBoundary{uuid.uuid4().hex}"
    content_type = f"multipart/form-data; boundary={boundary}"
    file_bytes = file_path.read_bytes()
    filename = file_path.name
    guessed_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    parts: list[bytes] = []

    for name, value in fields.items():
        parts.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )

    parts.extend(
        [
            f"--{boundary}\r\n".encode(),
            (
                f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                f"Content-Type: {guessed_type}\r\n\r\n"
            ).encode(),
            file_bytes,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )

    return b"".join(parts), content_type


def extract_text(payload: object) -> str:
    if isinstance(payload, dict):
        text = payload.get("text")
        if isinstance(text, str):
            return text.strip()

    raise RuntimeError(f"ASR 响应中未找到 text 字段: {payload!r}")


def post_transcription(
    *,
    api_base: str,
    file_path: Path,
    language: str | None,
    prompt: str | None,
    temperature: float | None,
    timeout: int,
) -> dict:
    fields: dict[str, str] = {}
    if language:
        fields["language"] = language
    if prompt:
        fields["prompt"] = prompt
    if temperature is not None:
        fields["temperature"] = str(temperature)

    body, content_type = encode_multipart_formdata(fields=fields, file_path=file_path)
    endpoint = api_base.rstrip("/") + "/v1/audio/transcriptions"
    req = request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": content_type, "Accept": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            response_body = response.read().decode(charset)
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"ASR 请求失败: HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"ASR 服务不可达: {exc.reason}") from exc

    try:
        payload = json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"ASR 响应不是合法 JSON: {response_body[:200]!r}") from exc

    if not isinstance(payload, dict):
        raise RuntimeError(f"ASR 响应结构异常: {payload!r}")
    return payload


def save_text(text: str, output_path: str) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")


def save_json(payload: dict, output_path: str) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Qwen3-ASR-openai transcription CLI")
    parser.add_argument("--input-file", required=True, help="要转写的音频文件路径")
    parser.add_argument("--output-text", default=DEFAULT_OUTPUT_TEXT, help="输出文本文件路径")
    parser.add_argument("--output-json", help="保存原始 JSON 响应")
    parser.add_argument("--api-base", help=f"ASR 服务地址，默认读取 QWEN_ASR_API_BASE 或 {DEFAULT_API_BASE}")
    parser.add_argument("--language", help="语言提示，例如 zh 或 en")
    parser.add_argument("--prompt", help="可选提示词，适合产品名、术语、专有名词")
    parser.add_argument("--temperature", type=float, help="可选解码温度")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="请求超时秒数")
    parser.add_argument(
        "--env-file",
        help="指定 .env 文件路径；未指定时依次尝试当前目录 .env、skill 根目录 .env、脚本目录 .env",
    )
    parser.add_argument("--quiet", action="store_true", help="仅输出警告和错误")
    parser.add_argument("--verbose", action="store_true", help="输出更多调试信息")
    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.quiet and args.verbose:
        parser.error("--quiet 和 --verbose 不能同时使用")

    configure_logging(quiet=args.quiet, verbose=args.verbose)
    load_env(env_file=args.env_file, logger=logger)

    file_path = Path(args.input_file)
    if not file_path.is_file():
        raise RuntimeError(f"音频文件不存在: {file_path}")

    api_base = args.api_base or os.getenv("QWEN_ASR_API_BASE", DEFAULT_API_BASE)
    logger.info("上传音频到 %s", api_base.rstrip("/") + "/v1/audio/transcriptions")

    payload = post_transcription(
        api_base=api_base,
        file_path=file_path,
        language=args.language,
        prompt=args.prompt,
        temperature=args.temperature,
        timeout=args.timeout,
    )
    text = extract_text(payload)
    save_text(text, args.output_text)
    logger.info("转写文本已保存到 %s", args.output_text)

    if args.output_json:
        save_json(payload, args.output_json)
        logger.info("原始 JSON 已保存到 %s", args.output_json)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
