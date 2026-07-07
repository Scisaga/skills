---
name: subtitle-matcher
description: 批量为本地电影、剧集和视频目录查找、筛选、下载、校验并归一化中文字幕。适用于用户要求“找字幕”“匹配字幕”“下载中文字幕”“检查字幕是否同步”“把字幕命名成 VLC 可自动加载格式”，尤其是需要结合 ASSRT、SubHD、现有本地字幕、片源版本名、时长校验、二阶段比对、HTML 报告和 .env 代理环境变量的场景。
---

# Subtitle Matcher

## 概述

这个 skill 用于把“给一批视频找可靠中文字幕”的流程固化下来：先盘点视频和已有字幕，再按片名、年份、集数、片源版本和字幕组筛选候选，下载后做中文、时间码和二阶段比对校验，最后按播放器可自动加载的命名规则落盘并生成 HTML 报告。

它专注字幕匹配与下载判断；视频转码、ASR 生成字幕、封装字幕仍优先使用 `skills/video`。

## 工作流

1. 先确认目标目录、语言偏好和是否允许联网下载。
2. 运行目录盘点，识别视频、已有字幕、可自动加载字幕和缺字幕项目。
3. 对已有字幕先做归一化：优先保留已在视频同目录且命名为 `<视频文件名>.chs/cht.srt|ass` 的字幕。
4. 缺字幕项目再查 ASSRT、SubHD 或用户指定来源，优先中文、简中、繁中、双语字幕。
5. 候选排序时同时看片名、年份、SxxExx、完整文件名、版本 token、字幕组、官方/精校标记和下载页时长。
6. 下载或解压后必须校验：字幕可解析、有足够时间码、含中文、片头/片尾/分布合理；末条字幕时间只能作为初筛信号。
7. 视频内存在英文或其他非中文文本字幕流时，优先抽取该内嵌字幕作为时间轴锚点，比对中文字幕 cue 的分布、偏移和 90 分位误差。
8. 对大片尾间隔、下载失败、签名失败、机器翻译过滤、API 失败的项目建立二阶段队列，不要直接归为最终失败。
9. 对证据强但最后时间码差较大的字幕执行二阶段比对；内嵌字幕锚点强匹配可自动通过，无法自动确认时标记为人工抽查。
10. 只输出 HTML 报告，默认命名为 `_subtitle_download_report.html`；禁止把 CSV 作为用户可见报告。

## 命令模式

```bash
bash skills/subtitle-matcher/scripts/bootstrap.sh
bash skills/subtitle-matcher/scripts/run.sh doctor
bash skills/subtitle-matcher/scripts/run.sh inventory --root "/path/to/videos" --output inventory.json
bash skills/subtitle-matcher/scripts/run.sh normalize-existing --root "/path/to/videos" --dry-run
bash skills/subtitle-matcher/scripts/run.sh validate-subtitle --video movie.mkv --subtitle movie.chs.srt
bash skills/subtitle-matcher/scripts/run.sh search-download --root "/path/to/videos"
bash skills/subtitle-matcher/scripts/run.sh scan-report --root "/path/to/videos"
bash skills/subtitle-matcher/scripts/run.sh audit-report --legacy-csv "/path/to/videos/_subtitle_download_report.csv" --root "/path/to/videos"
```

PowerShell 环境可用：

```powershell
powershell -ExecutionPolicy Bypass -File .\skills\subtitle-matcher\scripts\bootstrap.ps1
powershell -ExecutionPolicy Bypass -File .\skills\subtitle-matcher\scripts\run.ps1 doctor
powershell -ExecutionPolicy Bypass -File .\skills\subtitle-matcher\scripts\run.ps1 search-download --root "\\10.0.6.20\share\7 Download"
powershell -ExecutionPolicy Bypass -File .\skills\subtitle-matcher\scripts\run.ps1 scan-report --root "\\10.0.6.20\share\7 Download"
powershell -ExecutionPolicy Bypass -File .\skills\subtitle-matcher\scripts\run.ps1 register-vlc-protocol
powershell -ExecutionPolicy Bypass -File .\skills\subtitle-matcher\scripts\run.ps1 audit-report --legacy-csv "\\10.0.6.20\share\7 Download\_subtitle_download_report.csv" --root "\\10.0.6.20\share\7 Download"
```

`scan-report` 用于从当前视频目录和已落盘字幕重新生成全量 HTML 报告；默认标题在 Python 脚本内定义，不要通过 PowerShell here-string 临时写中文标题。`--legacy-csv` 只用于导入旧报告并重新生成 HTML。新的字幕流程不要生成 CSV。提供 `--root` 时，HTML 默认写到目标视频根目录的 `_subtitle_download_report.html`；只有用户明确指定 `--html-output` 时才写到其他位置。

Windows 上如需在 HTML 报告中点击直接用 VLC 播放，先运行 `register-vlc-protocol` 注册当前用户的 `vlcfile://` 协议。报告中的 VLC 链接会传入视频路径，并在目标字幕存在时作为 `--sub-file` 交给 VLC；首次点击时浏览器可能会要求确认打开外部应用。

`validate-subtitle` 默认会在时长差超过阈值时使用内嵌非中文字幕流做时间轴锚点。`scan-report` 默认保持轻量；需要全量报告也执行锚点精查时，加 `--embedded-reference`，这会变慢。

联网查找 ASSRT/SubHD 时，先读 `references/sources-assrt-subhd.md`；候选判断先读 `references/matching-rules.md`；发现大时长差或未完成项时读 `references/validation-ladder.md`。

## 资源使用

- `.env` 与代理：读 `references/env-and-proxy.md`。脚本按当前工作目录、skill 根目录、脚本目录的顺序加载 `.env`，支持 `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY`、`NO_PROXY` 及小写形式。
- 匹配规则：读 `references/matching-rules.md`。
- 二阶段比对：读 `references/validation-ladder.md`。
- ASSRT/SubHD 策略：读 `references/sources-assrt-subhd.md`。
- VLC 自动加载命名：读 `references/vlc-naming.md`。
- HTML 报告格式：读 `references/report-schema.md`。

## 输出规则

- 默认不覆盖已有字幕；覆盖必须由用户明确要求或脚本参数明确启用。
- 字幕最终放在视频同目录，优先命名为 `<视频完整文件名>.chs.srt`、`<视频完整文件名>.chs.ass`、`<视频完整文件名>.cht.srt` 或 `<视频完整文件名>.cht.ass`。
- 同等质量下优先下载和落盘简体字幕；繁体字幕仍可接受，但只有版本匹配、官方/精校证据或校验结果明显更强时才排到简体前面。
- 最终报告必须是 HTML，默认写到目标视频根目录的 `_subtitle_download_report.html`。
- HTML 报告在 Windows 上应包含 VLC 播放列；播放链接使用 `vlcfile://` 自定义协议，不要把本地可执行命令直接写进 HTML。
- 不生成 CSV；如果需要机器读取，在 HTML 内嵌 JSON 数据块。
- 每个失败项必须给出拒绝理由，例如 `duration_mismatch`、`non_chinese`、`too_few_cues`、`extract_or_no_subtitle_files`、`download_failed`。
- 大片尾间隔、依赖片源名/字幕组通过、页面时长通过的项目必须进入二阶段比对或人工抽查列表。
- 未完成项不能只写“时长不匹配”；如果候选已下载且差值在 600 秒内，必须保留为 `needs_compare` 或 `manual_check`。
- 因 API、签名、浏览器校验、解压失败而没有完成的项目必须保留候选 URL 和重试策略。
- 不能把机器翻译或未经校验的字幕描述为人工精校版本。
