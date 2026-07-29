# Video 使用说明

## 初始化

```bash
bash skills/video/scripts/bootstrap.sh
bash skills/video/scripts/bootstrap.sh --check-only
```

`bootstrap.sh` 会优先创建 `skills/video/.venv`，安装 Python 依赖，并在需要时安装 `ffmpeg`。

它不会部署 ASR 服务或下载 ASR 模型。只有执行 `subtitles` / `asr-subtitles` 生成字幕时，才需要使用者按需自行部署并配置 [`Scisaga/qwen3-asr-openai`](https://github.com/Scisaga/qwen3-asr-openai)；其他视频处理能力不依赖该服务。

## ASR 字幕依赖

`video` 复用 `skills/speech/scripts/transcribe.py`，通过 `QWEN_ASR_API_BASE` 或 `--api-base` 访问 qwen3-asr-openai。部署与接入边界见 [`qwen3-asr-openai.md`](../../speech/references/qwen3-asr-openai.md)。

在生成字幕前检查服务：

```bash
bash skills/speech/scripts/run.sh doctor --mode transcribe
```

## `ffmpeg` 安装与查找

- 优先复用系统包管理器
- 无法直接安装系统包时，回退到：
  - Linux: `skills/video/.cache/ffmpeg/linux-x64` 或 `skills/video/.cache/ffmpeg/linux-arm64`
  - macOS: `skills/video/.cache/ffmpeg/macos-x64/bin` 或 `skills/video/.cache/ffmpeg/macos-arm64/bin`
  - Windows: `skills/video/.cache/ffmpeg/windows-x64` 或 `skills/video/.cache/ffmpeg/windows-arm64`

运行时查找顺序：

1. `VIDEO_FFMPEG_BIN` / `VIDEO_FFPROBE_BIN`
2. `FFMPEG_BIN` / `FFPROBE_BIN`
3. `skills/video/.cache/ffmpeg/<platform>/bin`
4. `skills/video/.cache/ffmpeg/<platform>`
5. 系统 `PATH`

## 常用命令

```bash
bash skills/video/scripts/run.sh install-ffmpeg
bash skills/video/scripts/run.sh doctor
bash skills/video/scripts/run.sh keyframes --input-file demo.mp4 --output-dir out/frames
bash skills/video/scripts/run.sh extract-audio --input-file demo.mp4 --output-file out/demo.wav
bash skills/video/scripts/run.sh subtitles --input-file demo.mp4 --output-srt out/demo.srt
bash skills/video/scripts/run.sh mux --input-file demo.mkv --subtitle-file out/demo.srt --output-file out/demo.mp4 --check-sync
bash skills/video/scripts/run.sh check-sync --input-file demo.mp4 --subtitle-file out/demo.srt
```

## 排障

- `ffmpeg` 缺失：运行 `bash skills/video/scripts/bootstrap.sh` 或 `bash skills/video/scripts/run.sh install-ffmpeg`
- 搜不到字幕：直接回退到 `bash skills/video/scripts/run.sh subtitles`
- ASR 服务不可达：确认使用者已部署 qwen3-asr-openai，并检查 `QWEN_ASR_API_BASE` 或 `--api-base`
- 同步检查提示整体偏移：重新封装时加 `--sub-offset`
