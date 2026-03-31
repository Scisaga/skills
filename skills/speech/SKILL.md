---
name: speech
description: 为中文或多语言场景提供文本转语音与音频转文本能力。适用于生成旁白、演示配音、播报内容，或将会议录音、演示录音、访谈及其他音频文件转写为文本。本 skill 使用 Azure Speech 做 TTS，使用私有的 Qwen3-ASR-openai 兼容接口做转写。
---

# Speech

## 概述

这个 skill 用于确定性的语音输入输出任务。文本生成 MP3 时使用合成脚本；从音频提取文本时使用转写脚本，ASR 默认地址为 `http://127.0.0.1:12301/`。

## 工作流

1. 先确认任务方向。
   - 源是文本、目标是 MP3 时，走语音合成。
   - 源是音频、目标是文本时，走语音转写。

2. 如果是合成，再确认输入来源。
   - 短文本直接用 `--text`。
   - 稿件、旁白或长文本用 `--input-file`。
   - 如果文本已经由其他命令生成，用 `--stdin`。

3. 确认运行前置条件。
   - TTS 需要环境变量 `AZURE_SPEECH_KEY`，或显式传入 `--speech-key`。
   - ASR 可使用 `QWEN_ASR_API_BASE`，未设置时默认走 `http://127.0.0.1:12301`。
   - 首次使用前优先执行 `skills/speech/scripts/bootstrap.sh` 完成依赖安装和环境检查。
   - 只有当前 shell 里没有所需变量时，才使用 `--env-file`。

4. 保守选择参数。
   - 除非用户指定，否则保持默认音色。
   - 只有用户明确要求语气变化时，再调整 `--style`、`--rate` 和 `--pitch`。
   - `--max-chars` 要足够大以减少分段，但不能超过 Azure 的请求限制。
   - 对 ASR 而言，只有在音频语言已知且稳定时才传 `--language`。
   - `--prompt` 仅在术语、产品名等会明显影响识别效果时使用。

5. 运行入口。
   - 统一入口：`bash skills/speech/scripts/run.sh`
   - 合成入口：`bash skills/speech/scripts/run.sh synthesize`
   - 转写入口：`bash skills/speech/scripts/run.sh transcribe`
   - 环境检查入口：`bash skills/speech/scripts/run.sh doctor`
   - 音频输出用 `--output-mp3`。
   - 如无特殊要求，合成时保留 `--output-text` 以保存源文本。
   - 转写时用 `--output-text` 保存文本；如果需要保留原始响应，再加 `--output-json`。

## 命令模式

```bash
bash skills/speech/scripts/bootstrap.sh
bash skills/speech/scripts/run.sh synthesize --text "你好，欢迎使用语音合成。" --output-mp3 out/demo.mp3
bash skills/speech/scripts/run.sh synthesize --input-file script.txt --voice zh-CN-XiaoxiaoNeural --style cheerful
cat notes.txt | bash skills/speech/scripts/run.sh synthesize --stdin --output-mp3 out/notes.mp3
bash skills/speech/scripts/run.sh transcribe --input-file demo.mp3 --output-text out/demo.txt
bash skills/speech/scripts/run.sh transcribe --input-file meeting.wav --language zh --prompt "产品名 Servforce.AI"
```

## 资源使用

- 需要参数说明或排障信息时，读取 `references/usage.md`。
- 需要了解自托管 ASR 服务本身的接口、部署方式、限制和关键环境变量时，读取 `references/qwen3-asr-openai.md`。
- 首次初始化使用 `scripts/bootstrap.sh`。
- 日常调试或检查使用 `scripts/run.sh` 和 `scripts/doctor.py`。
- 文本转语音使用 `scripts/synthesize.py`。
- 音频转文字使用 `scripts/transcribe.py`。

## 输出规则

- 不要补写源文本里没有的口播内容。
- 生成语音时保持原文段落顺序。
- 除非用户明确要求清洗或总结，否则保留 ASR 返回的原始转写内容。
- 如果命令失败，要明确暴露依赖、凭证、网络或服务错误，不要吞掉具体原因。
