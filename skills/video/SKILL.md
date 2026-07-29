---
name: video
description: 处理本地视频文件并结合联网搜索完成关键帧抽取、音频抽取、字幕检索、语音转字幕、字幕封装、同步校验，以及影片简介和评价整理。适用于 ffmpeg 安装、视频抽帧、字幕生成或电影信息检索场景。
---

# Video

## 概述

这个 skill 负责视频处理的两部分：

1. 本地确定性步骤：抽帧、抽音频、生成字幕、封装字幕、同步检查
2. 联网判断步骤：优先搜索现成字幕和影片信息，找不到再回退到音频转字幕

生成 ASR 字幕时，本 skill 复用 `skills/speech/scripts/transcribe.py`，因此需要使用者按需自行部署并配置可访问的 qwen3-asr-openai 服务。只做抽帧、抽音频、字幕封装或同步检查时不需要 ASR 服务；`video` 不负责部署它。

## 工作流

1. 首次使用先运行 `bash skills/video/scripts/bootstrap.sh`
2. 默认优先通过 `bash skills/video/scripts/run.sh` 调用所有能力
3. `ffmpeg` 自动安装只在 `bootstrap` 或 `run.sh install-ffmpeg` 里触发
4. 需要生成 ASR 字幕时，先按 [`qwen3-asr-openai.md`](../speech/references/qwen3-asr-openai.md) 准备外部服务，再运行 `speech` 的 `doctor --mode transcribe`
5. 系统包不可用时，回退到 `skills/video/.cache/ffmpeg/<platform>` 缓存目录
6. 运行时查找顺序是：
   - `VIDEO_FFMPEG_BIN` / `VIDEO_FFPROBE_BIN`
   - `FFMPEG_BIN` / `FFPROBE_BIN`
   - `skills/video/.cache/ffmpeg/<platform>/bin`
   - `skills/video/.cache/ffmpeg/<platform>`
   - 系统 `PATH`

## 命令模式

```bash
bash skills/video/scripts/bootstrap.sh
bash skills/video/scripts/run.sh keyframes --input-file movie.mkv --output-dir out/frames
bash skills/video/scripts/run.sh extract-audio --input-file movie.mkv --output-file out/movie.wav
bash skills/video/scripts/run.sh subtitles --input-file movie.mkv --output-srt out/movie.srt --language zh
bash skills/video/scripts/run.sh mux --input-file movie.mkv --subtitle-file out/movie.srt --output-file out/movie.mp4 --check-sync
bash skills/video/scripts/run.sh check-sync --input-file movie.mkv --subtitle-file out/movie.srt
```

## 资源使用

- 环境初始化：`scripts/bootstrap.sh`
- 安装脚本：`scripts/install-linux.sh`、`scripts/install-macos.sh`、`scripts/install-windows.ps1`
- 统一入口：`scripts/run.sh`
- 参数与排障：`references/usage.md`
- ASR 依赖与部署入口：[`qwen3-asr-openai.md`](../speech/references/qwen3-asr-openai.md)

## 输出规则

- 默认不覆盖源视频
- 联网找到的字幕在封装前也要先做同步检查
- 自动生成的字幕属于工作字幕，不冒充人工精校版本
