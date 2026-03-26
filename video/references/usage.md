# Usage Guide

## 初始化

首次执行：

```bash
bash video/scripts/bootstrap.sh
```

`bootstrap.sh` 会优先在 `video/.venv` 创建本地虚拟环境，并把 Python 依赖安装进去。
如果系统里缺少 `ffmpeg` 或 `ffprobe`，它还会尝试自动安装。

只检查环境：

```bash
bash video/scripts/bootstrap.sh --check-only
```

`--check-only` 只做检查，不创建虚拟环境，也不会触发 `ffmpeg` 自动安装。

只安装或检查 `ffmpeg`：

```bash
bash video/scripts/run.sh install-ffmpeg
bash video/scripts/run.sh doctor
```

需要注意：

- `keyframes`、`extract-audio`、`subtitles`、`mux`、`check-sync` 不会在执行过程中隐式下载 `ffmpeg`。
- 这些命令只会查找已有 `ffmpeg`/`ffprobe`；如果缺失，会提示先执行 `bootstrap.sh` 或 `run.sh install-ffmpeg`。

## ffmpeg 安装位置

安装顺序分两层：

1. 优先使用系统现成安装方式。
   - Linux 且当前用户是 root 时，优先尝试 `apt-get`、`dnf`、`yum`、`pacman`、`zypper`、`apk`
   - macOS 优先尝试 `brew install ffmpeg`
   - Windows 优先尝试 `winget`、`choco`、`scoop`

2. 如果上面不可用，再下载到 skill 自己的目录。
   - Linux: `video/bin/linux-x64` 或 `video/bin/linux-arm64`
   - macOS: `video/bin/macos-x64/bin` 或 `video/bin/macos-arm64/bin`
   - Windows: `video/bin/windows-x64` 或 `video/bin/windows-arm64`

临时下载文件会放在系统临时目录，安装完成后删除，不作为长期存放位置。

运行时查找顺序：

1. `VIDEO_FFMPEG_BIN` / `VIDEO_FFPROBE_BIN`
2. 兼容变量 `FFMPEG_BIN` / `FFPROBE_BIN`
3. `video/bin/<platform>/bin`
4. `video/bin/<platform>`
5. 系统 `PATH`

## Dependencies

Install Python dependency:

```bash
pip install -r video/requirements.txt
```

This skill expects:

- `ffmpeg`
- `ffprobe`
- `python-dotenv`
- `speech/scripts/transcribe.py` 可用

`.env` 加载顺序：

- 当前工作目录 `.env`
- `video/.env`
- `video/scripts/.env`

## 关键帧抽取

按场景抽关键帧：

```bash
bash video/scripts/run.sh keyframes \
  --input-file movie.mkv \
  --output-dir out/frames \
  --max-frames 16
```

重要参数：

- `--max-frames`: 最多导出几张图
- `--scene-threshold`: 场景切换阈值，默认 `0.35`
- `--width`: 输出图片最大宽度

## 音频抽取

抽整段音频：

```bash
bash video/scripts/run.sh extract-audio \
  --input-file movie.mkv \
  --output-file out/movie.wav
```

只抽局部片段：

```bash
bash video/scripts/run.sh extract-audio \
  --input-file movie.mkv \
  --output-file out/clip.wav \
  --start 120 \
  --end 180
```

## 用 speech skill 生成粗字幕

```bash
bash video/scripts/run.sh subtitles \
  --input-file movie.mkv \
  --output-srt out/movie.srt \
  --output-text out/movie.txt \
  --language zh
```

带术语提示：

```bash
bash video/scripts/run.sh subtitles \
  --input-file lesson.mp4 \
  --output-srt out/lesson.srt \
  --prompt "Servforce.AI, Kubernetes, Qwen3-ASR-openai"
```

重要参数：

- `--noise`: `silencedetect` 噪声阈值
- `--silence-duration`: 最短静音时长
- `--min-segment`: 最短切分片段
- `--max-segment`: 最长切分片段
- `--lead-in` / `--lead-out`: 字幕前后留白

## 合并字幕到 MP4

默认软字幕：

```bash
bash video/scripts/run.sh mux \
  --input-file movie.mkv \
  --subtitle-file out/movie.srt \
  --output-file out/movie.mp4 \
  --check-sync
```

烧录字幕：

```bash
bash video/scripts/run.sh mux \
  --input-file movie.mkv \
  --subtitle-file out/movie.srt \
  --output-file out/movie-burned.mp4 \
  --burn-in \
  --check-sync
```

如果字幕已知有偏移：

```bash
bash video/scripts/run.sh mux \
  --input-file movie.mkv \
  --subtitle-file found.ass \
  --output-file out/movie.mp4 \
  --sub-offset -1.4 \
  --check-sync
```

## 单独验证字幕同步

```bash
bash video/scripts/run.sh check-sync \
  --input-file movie.mkv \
  --subtitle-file out/movie.srt \
  --output-json out/movie-sync.json
```

同步检查会输出：

- 首条字幕与首段语音偏移
- 末条字幕与末段语音偏移
- 字幕覆盖语音比例
- 语音被字幕覆盖比例
- 中点命中率

## 联网搜索建议

搜字幕时建议先确认片名和年份，再使用这些模式：

- `"<片名>" <年份> subtitles srt ass`
- `"<片名>" <年份> 中文字幕`
- `"<片名>" <年份> <分辨率或版本组> 字幕`
- `site:opensubtitles.com "<片名>" <年份>`
- `site:subhd.tv "<片名>" <年份>`

如果文件名不干净，先做这两步：

1. 用文件名推测标题和年份。
2. 如有歧义，先抽 4 到 8 张关键帧辅助确认。

搜影片信息时建议覆盖：

- 剧情简介：片名 + 年份 + `plot` / `剧情`
- 用户评价：片名 + 年份 + `reviews` / `评价` / `评分`

## Troubleshooting

- `ffmpeg` 缺失：运行 `bash video/scripts/bootstrap.sh` 或 `bash video/scripts/run.sh install-ffmpeg`
- 搜不到字幕：直接走 `video/scripts/run.sh subtitles`
- 转写切分过碎：增大 `--silence-duration` 或 `--merge-gap`
- 字幕太晚出现：尝试 `--sub-offset -0.5`
- 字幕太早出现：尝试 `--sub-offset 0.5`
- 同步检查失败：优先调整 offset，再重新封装
- 烧录失败：确认本机 `ffmpeg` 编译包含字幕滤镜支持
