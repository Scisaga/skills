---
name: video
description: 处理本地视频文件并结合联网搜索完成关键帧抽取、字幕检索、音频抽取、基于 speech skill 的字幕生成、字幕合并 MP4、字幕同步校验，以及影片内容简介和用户评价整理。凡是涉及 ffmpeg 安装、视频抽帧、外挂字幕查找、音频转字幕、封装字幕或影片剧情与口碑查询的请求，都应优先使用这个 skill。
---

# Video

## 概述

这个 skill 负责把视频处理任务拆成两类：

1. 本地确定性步骤。
   使用 `video/scripts/` 下的脚本完成 `ffmpeg` 安装、关键帧抽取、音频提取、字幕生成、MP4 合并与同步检查。

2. 联网判断步骤。
   使用 Codex 的联网搜索先找现成字幕和影片信息；只有搜不到可用字幕时，才回退到抽音频并调用 `speech` skill 转写生成 SRT。

## 工作流

1. 先准备运行环境。
   - 首次使用优先执行 `bash video/scripts/bootstrap.sh`。
   - 如果系统里没有 `ffmpeg`/`ffprobe`，优先使用本 skill 自带安装脚本，不要只告诉用户“请自行安装”。
   - `ffmpeg` 自动安装只在 `bootstrap.sh` 或 `run.sh install-ffmpeg` 里触发；`keyframes`、`extract-audio`、`subtitles`、`mux`、`check-sync` 这些命令不会在执行过程中隐式下载。
   - 安装时优先复用系统包管理器；如果没有可用包管理器或当前环境不适合直接装系统包，再回退到下载二进制到 `video/bin/<platform>`。
   - Linux 回退安装目录是 `video/bin/linux-x64` 或 `video/bin/linux-arm64`；macOS 是 `video/bin/macos-x64/bin` 或 `video/bin/macos-arm64/bin`；Windows 是 `video/bin/windows-x64` 或 `video/bin/windows-arm64`。

2. 先判断视频类型与目标。
   - 只是抽图时，直接走关键帧提取。
   - 需要字幕时，先联网搜索字幕。
   - 需要影片介绍、剧情简介、评价时，先确认标题和年份，再联网搜索权威来源。

3. 处理字幕时遵守这个优先级。
   - 优先搜索现成字幕，特别是影片名、年份、分辨率、版本组信息对应的字幕。
   - 如果用户给的是本地影片文件，先从文件名推测标题，再用关键帧或媒体信息辅助确认年份与版本。
   - 如果联网搜索不到可用字幕，提取音频后调用 `video/scripts/generate_subtitles.py`，它会切分语音段并复用 `speech/scripts/transcribe.py` 生成粗 SRT。

4. 合并视频和字幕时优先保留原视频流。
   - 默认使用软字幕封装到 MP4。
   - 只有用户明确要求烧录字幕，或软字幕播放器兼容性不可接受时，才使用 `--burn-in` 重编码。

5. 合并后必须做同步检查。
   - 默认执行 `video/scripts/check_subtitle_sync.py` 或在 `merge_subtitles.py` 上加 `--check-sync`。
   - 如果检查结果提示字幕整体偏前或偏后，再用 `--sub-offset` 微调并重新封装。

6. 如果视频是影片并且用户要内容说明或评价，联网搜索时至少覆盖两类信息。
   - 一类是剧情/内容简介。
   - 一类是用户评价、口碑、评分或评论摘要。
   - 尽量交叉验证标题、年份、地区版名和来源，避免把同名影片混淆。

## 命令模式

```bash
bash video/scripts/bootstrap.sh
bash video/scripts/run.sh keyframes --input-file movie.mkv --output-dir out/frames
bash video/scripts/run.sh extract-audio --input-file movie.mkv --output-file out/movie.wav
bash video/scripts/run.sh subtitles --input-file movie.mkv --output-srt out/movie.srt --language zh
bash video/scripts/run.sh mux --input-file movie.mkv --subtitle-file out/movie.srt --output-file out/movie.mp4 --check-sync
bash video/scripts/run.sh check-sync --input-file movie.mkv --subtitle-file out/movie.srt
```

## 联网搜索规则

- 搜字幕时，优先搜索片名、年份、版本名和 `srt|ass|字幕|subtitles` 组合。
- 如果搜索结果很多，优先看能对应发行年份、片长、分辨率、字幕语言的结果。
- 搜不到时，不要卡住，直接回退到音频转字幕流程。
- 搜影片信息时，优先使用稳定影视资料页和聚合评分来源，输出时保持“简洁剧情 + 用户评价摘要”的结构。
- 如果用户只要“简洁剧情”和“用户评价”，不要长篇复述影评原文。

## 资源使用

- 环境初始化与 `ffmpeg` 安装使用 `scripts/bootstrap.sh`、`scripts/install-*.sh`。
- 运行时查找 `ffmpeg`/`ffprobe` 的顺序是：`VIDEO_FFMPEG_BIN` / `VIDEO_FFPROBE_BIN`、兼容变量 `FFMPEG_BIN` / `FFPROBE_BIN`、`video/bin/<platform>`、系统 `PATH`。
- 统一入口使用 `scripts/run.sh`。
- 关键帧抽取使用 `scripts/extract_keyframes.py`。
- 音频抽取使用 `scripts/extract_audio.py`。
- 音频转字幕使用 `scripts/generate_subtitles.py`，底层复用 `speech` skill 的转写脚本。
- 字幕封装和同步检查使用 `scripts/merge_subtitles.py`、`scripts/check_subtitle_sync.py`。
- 需要命令模板、搜索建议和排障时，读取 `references/usage.md`。

## 输出规则

- 默认不要覆盖源视频。
- 生成关键帧时默认输出到新目录。
- 生成的 ASR 字幕属于粗字幕，除非用户要求，否则不要冒充“官方校对字幕”。
- 联网找到的字幕在封装前要先做同步检查，不要假设天然同步。
- 影片信息输出默认保持简洁，优先给出片名、年份、简要剧情、用户评价摘要和来源线索。
