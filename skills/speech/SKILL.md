---
name: speech
description: 将文本合成为 MP3，或通过自托管 qwen3-asr-openai 将音频转写为文本。适用于旁白、演示配音、播报及会议、访谈转写。合成默认优先自托管 qwen3-tts-openai，服务或控制能力不可用时整份回退 Azure Speech；也可显式选择后端。
---

# Speech

## 概述

使用脚本完成确定性的语音输入输出任务。TTS 默认 `auto`：优先使用自托管 Qwen3 TTS，失败后尝试 Azure；ASR 使用独立的自托管 Qwen3 ASR 服务。两者分别配置，不互相要求服务或凭证。普通配音直接运行本技能，无需 Slides 的项目审批流程。

## 工作流

1. 确认输入输出。文本到 MP3 使用 `synthesize`；音频到文本使用 `transcribe`。短文本用 `--text`，稿件用 `--input-file`，管道用 `--stdin`。
2. 初始化本地依赖并检查所选能力。运行 `bootstrap.sh --mode synthesize`；Windows 用 `bootstrap.ps1`。只转写用 `--mode transcribe`。需要 Azure 回退时增加 `--with-azure`。依赖初始化不会部署外部服务。
3. 配置 Qwen 地址和已就绪音色，使用 `list-voices` 查询实际 `voice_id`，不要猜测 ID。配置文件按进程变量、`--env-file`、当前工作目录、技能目录、脚本目录的顺序补充缺失值。从其他项目调用时不会自动读取源码仓库根目录 `.env`。
4. 保持原文及段落顺序。默认不加风格，沿用既有语速 `+5%`、音高 `+0st`；用户有要求时再调整 `--style`、`--rate`、`--pitch`。脚本会预检 SSML，不能执行的控制会触发回退或显式报错。
5. 使用 `--provider auto|qwen3-tts-openai|azure-speech`。`--qwen-voice` 是 Qwen 音色，`--voice` 始终是 Azure 音色。显式选择的后端失败即停；输入和本地文件错误直接修正。
6. 检查 MP3 和同名 `.tts.json` 中的实际服务、音色、回退原因。长文本分段失败时整份切换，不能拼接不同后端或音色的片段。成功后才替换目标音频，失败保留既有音频。

## 命令模式

以下为源码仓库根目录中的命令；安装后以技能所在目录中的脚本为入口。

```bash
bash skills/speech/scripts/bootstrap.sh --mode synthesize
bash skills/speech/scripts/run.sh list-voices
bash skills/speech/scripts/run.sh doctor --mode synthesize --check-service
bash skills/speech/scripts/run.sh synthesize --text "欢迎来到演示。" --output-mp3 out/demo.mp3
bash skills/speech/scripts/run.sh synthesize --input-file script.txt --provider qwen3-tts-openai --qwen-voice xiaochen-hd
bash skills/speech/scripts/run.sh synthesize --input-file script.txt --provider azure-speech --voice zh-CN-XiaoxiaoNeural --style newscast
bash skills/speech/scripts/run.sh transcribe --input-file meeting.wav --language zh --output-text out/meeting.txt
```

Windows PowerShell：

```powershell
& skills/speech/scripts/bootstrap.ps1 --mode synthesize --with-azure
& skills/speech/scripts/run.ps1 synthesize --input-file script.txt --env-file C:/config/speech.env --output-mp3 out/demo.mp3
```

## 资源使用

- 配置、参数、依赖和排障：[usage.md](references/usage.md)。
- 自托管 TTS 协议和控制能力：[qwen3-tts-openai.md](references/qwen3-tts-openai.md)。
- ASR 依赖边界和兼容接口：[qwen3-asr-openai.md](references/qwen3-asr-openai.md)。
- 初始化：`scripts/bootstrap.sh` / `scripts/bootstrap.ps1`；统一入口：`scripts/run.sh` / `scripts/run.ps1`。
- 合成与音色：`scripts/synthesize.py`、`scripts/list_voices.py`；转写：`scripts/transcribe.py`；检查：`scripts/doctor.py`。

## 输出规则

- 不补写源文本没有的口播内容；默认保存原文，可用 `--output-text` 指定位置。
- 报告实际使用的后端与音色，出现回退时说明原因，不能把 Azure 结果称为 Qwen 输出。
- 除非用户明确要求清洗或总结，保留 ASR 返回的原始转写内容。
- 失败时明确呈现依赖、输入、服务或配置错误；不记录密钥，不把本地 `.env` 打包分享。
