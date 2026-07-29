---
name: speech
description: 为中文或多语言场景提供文本转语音与音频转文本能力。适用于生成旁白、演示配音、播报内容，或将会议录音、演示录音、访谈及其他音频文件转写为文本。本 skill 使用 Azure AI Speech 做 TTS，并对接由使用者按需自行部署的开源 qwen3-asr-openai 服务做 ASR。
---

# Speech

## 概述

这个 skill 用于确定性的语音输入输出任务。文本生成 MP3 时使用合成脚本；从音频提取文本时使用转写脚本。ASR 是可选的外部服务依赖，默认地址为 `http://127.0.0.1:12301/`。

## 运行前提与外部依赖

TTS 与 ASR 是两条独立能力：只做转写不需要 Azure Key，只做合成也不需要部署或启动 qwen3-asr-openai。

| 能力 | 外部服务 | 必需配置 | 是否需要 Key |
|---|---|---|---|
| 文本转语音（TTS） | Azure AI Speech 云服务；使用前须有 Azure 订阅并创建 Speech 资源 | `AZURE_SPEECH_KEY`；`AZURE_SPEECH_REGION` 必须与该资源的区域一致，也可分别用 `--speech-key`、`--region` 覆盖 | 需要 Azure Speech resource key |
| 音频转文本（ASR） | 使用者按需自行部署并保持可访问的开源 [`qwen3-asr-openai`](https://github.com/Scisaga/qwen3-asr-openai) 服务 | `QWEN_ASR_API_BASE`，或 `--api-base`；默认 `http://127.0.0.1:12301` | 当前转写接口和客户端不使用 API Key；`ADMIN_TOKEN` 只保护服务端模型热重载，不用于转写 |
| 本地脚本 | Bash、Python 3、pip，以及 `requirements.txt` 中的 Python 包 | 首次运行 `scripts/bootstrap.sh` | 不需要 |

还必须满足相应网络条件：TTS 运行机能访问 Azure Speech；ASR 运行机能访问配置的 qwen3-asr-openai 地址。`bootstrap.sh` 只安装本地 Python 依赖并做检查，不会创建 Azure 资源、申请 Key、部署或启动 ASR 服务，也不会下载 ASR 模型。需要 ASR 时，由使用者按照上游项目说明自行准备服务。

优先从仓库根目录 `.env.example` 复制本地 `.env`，只填写自己环境的值，不要提交真实 Key。完整准备步骤、配置优先级和系统依赖见 `references/usage.md`；ASR 的依赖边界和客户端契约见 `references/qwen3-asr-openai.md`，具体部署与运维以上游仓库 README 为准。

## 工作流

1. 先确认任务方向。
   - 源是文本、目标是 MP3 时，走语音合成。
   - 源是音频、目标是文本时，走语音转写。

2. 如果是合成，再确认输入来源。
   - 短文本直接用 `--text`。
   - 稿件、旁白或长文本用 `--input-file`。
   - 如果文本已经由其他命令生成，用 `--stdin`。

3. 确认运行前置条件。
   - TTS 需要 `AZURE_SPEECH_KEY` 和与资源匹配的 `AZURE_SPEECH_REGION`，也可用命令行参数覆盖。
   - ASR 可使用 `QWEN_ASR_API_BASE`，未设置时默认走 `http://127.0.0.1:12301`。
   - ASR 服务尚未部署或不可访问时，先提示使用者按 `references/qwen3-asr-openai.md` 中的上游链接自行准备，不要由本 skill 擅自部署。
   - 首次使用前优先执行 `skills/speech/scripts/bootstrap.sh --mode synthesize` 或 `--mode transcribe`；只有两项都已配置时才使用默认的 `--mode all`。
   - 只有当前 shell 里没有所需变量时，才使用 `--env-file`。

4. 保守选择参数。
   - 除非用户指定，否则保持默认音色。
   - 默认不设置表达风格。只有用户明确要求语气变化时，才传入 `--style`；脚本会从 Azure 音色清单校验音色与风格是否匹配。
   - 只有用户明确要求语速或音高变化时，再调整 `--rate` 和 `--pitch`。
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
bash skills/speech/scripts/bootstrap.sh --mode synthesize
bash skills/speech/scripts/bootstrap.sh --mode transcribe
bash skills/speech/scripts/run.sh synthesize --text "你好，欢迎使用语音合成。" --output-mp3 out/demo.mp3
bash skills/speech/scripts/run.sh synthesize --input-file script.txt --voice zh-CN-XiaoxiaoNeural --style newscast
cat notes.txt | bash skills/speech/scripts/run.sh synthesize --stdin --output-mp3 out/notes.mp3
bash skills/speech/scripts/run.sh transcribe --input-file demo.mp3 --output-text out/demo.txt
bash skills/speech/scripts/run.sh transcribe --input-file meeting.wav --language zh --prompt "产品名 Servforce.AI"
```

## 资源使用

- 需要参数说明或排障信息时，读取 `references/usage.md`。
- 需要确认自托管 ASR 的依赖边界、兼容接口和上游部署入口时，读取 `references/qwen3-asr-openai.md`。
- 首次初始化使用 `scripts/bootstrap.sh`。
- 日常调试或检查使用 `scripts/run.sh` 和 `scripts/doctor.py`。
- 文本转语音使用 `scripts/synthesize.py`。
- 音频转文字使用 `scripts/transcribe.py`。

## 输出规则

- 不要补写源文本里没有的口播内容。
- 生成语音时保持原文段落顺序。
- 除非用户明确要求清洗或总结，否则保留 ASR 返回的原始转写内容。
- 如果命令失败，要明确暴露依赖、凭证、网络或服务错误，不要吞掉具体原因。
