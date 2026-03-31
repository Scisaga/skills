import argparse
import gc
import logging
import os
import re
import sys
import time
from pathlib import Path
from textwrap import dedent

from common import configure_logging, ensure_python_modules, load_env

DEFAULT_REGION = "eastasia"
DEFAULT_VOICE = "zh-CN-XiaochenNeural"
DEFAULT_STYLE = "newscast-casual"
DEFAULT_RATE = "+5%"
DEFAULT_PITCH = "+0st"
DEFAULT_OUT_MP3 = "output.mp3"
DEFAULT_OUT_TXT = "output.txt"
DEFAULT_MAX_CHARS = 4500

DEFAULT_TEXT = dedent(
    """
    这是一段用于测试语音合成功能的示例文本，内容尽量保持中性、通用，便于在不同场景下直接复用。

    语音合成通常适用于旁白生成、通知播报、说明文档朗读、演示配音等任务。实际使用时，可以根据需要调整发音人、语速、语调和表达风格，以匹配目标场景。

    当输入文本较长时，程序会自动按段落和句子拆分，以降低单次请求过长带来的失败风险，并在处理完成后合并输出音频文件。

    如果需要更稳定的识别或播报效果，建议在输入文本中保持标点清晰、段落完整，并尽量减少歧义表达或不必要的格式噪声。

    这段默认文本仅用于功能验证，不代表任何具体业务、产品或品牌信息。
    """
).strip()

logger = logging.getLogger("speech.synthesize")


def get_speechsdk():
    try:
        import azure.cognitiveservices.speech as speechsdk
    except ImportError as exc:
        raise RuntimeError(
            "缺少依赖 azure-cognitiveservices-speech，请先执行 `bash skills/speech/scripts/bootstrap.sh`。"
        ) from exc
    return speechsdk


def get_speech_config(*, speech_key: str, region: str):
    if not speech_key or not region:
        raise RuntimeError("请设置 AZURE_SPEECH_KEY，并提供有效的 region。")

    speechsdk = get_speechsdk()
    speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=region)
    speech_config.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Audio48Khz192KBitRateMonoMp3
    )
    return speechsdk, speech_config


def escape_xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_ssml(
    paragraph: str,
    *,
    voice: str,
    style: str,
    rate: str,
    pitch: str,
) -> str:
    paragraph = escape_xml(paragraph)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<speak version="1.0" xml:lang="zh-CN"
       xmlns="http://www.w3.org/2001/10/synthesis"
       xmlns:mstts="https://www.w3.org/2001/mstts">
  <voice name="{voice}">
    <mstts:express-as style="{style}" styledegree="1.0">
      <prosody rate="{rate}" pitch="{pitch}">
        <p>{paragraph}</p>
      </prosody>
    </mstts:express-as>
  </voice>
</speak>"""


def split_into_chunks(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    chunks: list[str] = []
    buf = ""

    for p in paras:
        if len(buf) + len(p) + 2 <= max_chars:
            buf = (buf + "\n\n" + p).strip() if buf else p
            continue

        if buf:
            chunks.append(buf)

        if len(p) <= max_chars:
            buf = p
            continue

        sents = re.split(r"(?<=[。！？!?.])", p)
        buf = ""
        for s in sents:
            if len(buf) + len(s) <= max_chars:
                buf += s
            else:
                if buf:
                    chunks.append(buf)
                buf = s

    if buf:
        chunks.append(buf)

    return chunks


def synth_to_mp3(
    text: str,
    out_mp3: str,
    *,
    speech_key: str,
    region: str,
    voice: str,
    style: str,
    rate: str,
    pitch: str,
    max_chars: int,
) -> None:
    speechsdk, _ = get_speech_config(speech_key=speech_key, region=region)

    output_path = Path(out_mp3)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    tmp_files: list[Path] = []
    chunks = split_into_chunks(text, max_chars=max_chars)

    try:
        for index, chunk in enumerate(chunks, start=1):
            ssml = build_ssml(
                chunk,
                voice=voice,
                style=style,
                rate=rate,
                pitch=pitch,
            )
            tmp_name = output_path.with_name(f"{output_path.stem}.__part{index:02d}.mp3")
            tmp_files.append(tmp_name)

            logger.info("合成第 %s/%s 段: %s", index, len(chunks), tmp_name.name)

            _, speech_config = get_speech_config(speech_key=speech_key, region=region)
            audio_config = speechsdk.audio.AudioOutputConfig(filename=str(tmp_name))
            synthesizer = speechsdk.SpeechSynthesizer(
                speech_config=speech_config,
                audio_config=audio_config,
            )
            result = synthesizer.speak_ssml_async(ssml).get()

            if result is None:
                del audio_config
                del synthesizer
                raise RuntimeError("TTS 返回空结果。")

            if result.reason == speechsdk.ResultReason.Canceled:
                details = speechsdk.CancellationDetails(result)
                raise RuntimeError(
                    f"TTS 已取消: reason={details.reason}, error_details={details.error_details}"
                )
            if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
                raise RuntimeError(f"TTS 未完成，reason={result.reason}")

            del audio_config
            del synthesizer

        gc.collect()

        logger.info("合并音频文件到 %s", output_path)
        with output_path.open("wb") as out_f:
            for part in tmp_files:
                with part.open("rb") as pf:
                    out_f.write(pf.read())
    finally:
        for part in tmp_files:
            if not part.exists():
                continue
            try:
                part.unlink()
            except PermissionError:
                time.sleep(0.5)
                try:
                    part.unlink()
                except OSError as exc:
                    logger.warning("临时文件删除失败: %s (%s)", part, exc)


def save_text(text: str, out_txt: str) -> None:
    output_path = Path(out_txt)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text.strip() + "\n", encoding="utf-8")


def read_text(args: argparse.Namespace) -> str:
    if args.text is not None:
        return args.text.strip()

    if args.input_file is not None:
        return Path(args.input_file).read_text(encoding="utf-8").strip()

    if args.stdin:
        return sys.stdin.read().strip()

    return DEFAULT_TEXT


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Azure Speech TTS CLI")
    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument("--text", help="直接传入要合成的文本")
    source_group.add_argument("--input-file", help="从文本文件读取内容")
    source_group.add_argument("--stdin", action="store_true", help="从标准输入读取文本")

    parser.add_argument("--output-mp3", default=DEFAULT_OUT_MP3, help="输出 MP3 文件路径")
    parser.add_argument("--output-text", default=DEFAULT_OUT_TXT, help="输出文本文件路径")
    parser.add_argument("--skip-text-save", action="store_true", help="不落盘保存文本")
    parser.add_argument("--region", default=DEFAULT_REGION, help=f"Azure region，默认 {DEFAULT_REGION}")
    parser.add_argument("--voice", default=DEFAULT_VOICE, help=f"语音，默认 {DEFAULT_VOICE}")
    parser.add_argument("--style", default=DEFAULT_STYLE, help=f"风格，默认 {DEFAULT_STYLE}")
    parser.add_argument("--rate", default=DEFAULT_RATE, help=f"语速，默认 {DEFAULT_RATE.replace('%', '%%')}")
    parser.add_argument("--pitch", default=DEFAULT_PITCH, help=f"音高，默认 {DEFAULT_PITCH}")
    parser.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS, help="单段最大字符数")
    parser.add_argument("--speech-key", help="Azure Speech Key，默认读取 AZURE_SPEECH_KEY")
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
    ensure_python_modules(
        {"azure.cognitiveservices.speech": "azure-cognitiveservices-speech"},
        logger=logger,
    )

    text = read_text(args)
    if not text:
        raise RuntimeError("输入文本为空。")

    speech_key = args.speech_key or os.getenv("AZURE_SPEECH_KEY", "")

    if not args.skip_text_save:
        save_text(text, args.output_text)
        logger.info("文本已保存到 %s", args.output_text)

    synth_to_mp3(
        text,
        args.output_mp3,
        speech_key=speech_key,
        region=args.region,
        voice=args.voice,
        style=args.style,
        rate=args.rate,
        pitch=args.pitch,
        max_chars=args.max_chars,
    )
    logger.info("MP3 已生成: %s", args.output_mp3)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
