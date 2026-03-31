# Video 使用说明

## 初始化

```bash
bash skills/video/scripts/bootstrap.sh
bash skills/video/scripts/bootstrap.sh --check-only
```

`bootstrap.sh` 会优先创建 `skills/video/.venv`，安装 Python 依赖，并在需要时安装 `ffmpeg`。

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
- 同步检查提示整体偏移：重新封装时加 `--sub-offset`
