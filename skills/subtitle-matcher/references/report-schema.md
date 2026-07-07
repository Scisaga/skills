# HTML 报告格式

## 总规则

禁止把 CSV 作为用户可见输出。字幕任务的最终报告统一生成 HTML，默认文件名：

```text
_subtitle_download_report.html
```

报告必须直接写入目标视频根目录，例如 `\\10.0.6.20\share\7 Download\_subtitle_download_report.html`。不要写到临时目录、skill 目录或当前工作目录，除非用户明确指定。

旧 CSV 只允许作为历史报告导入源，用于迁移、审计或重新生成 HTML；新的字幕流程不要再生成 `_subtitle_download_report.csv`。

刷新当前目录报告时使用脚本命令：

```powershell
powershell -ExecutionPolicy Bypass -File .\skills\subtitle-matcher\scripts\run.ps1 scan-report --root "\\10.0.6.20\share\7 Download"
```

`scan-report` 会扫描当前视频目录中已经落盘的自动加载字幕，调用 `ffprobe` 校验时长，并直接写入目标视频根目录的 `_subtitle_download_report.html`。默认中文标题由 Python 源码中的 UTF-8 字符串提供，不要用 PowerShell here-string 或控制台拼接中文标题，以免标题被写成 `????`。

`scan-report` 默认保持轻量，只做 ffprobe 时长校验。需要报告也执行内嵌字幕时间轴锚点精查时，加 `--embedded-reference`；这会在时长差超过阈值的行上用 `ffmpeg` 抽取视频内的英文或其他非中文文本字幕流。报告原因中出现 `timeline_anchor_match` 时，表示内嵌原文 cue 与中文字幕 cue 的时间轴分布高度一致。

Windows 上可注册用户级 VLC 播放协议：

```powershell
powershell -ExecutionPolicy Bypass -File .\skills\subtitle-matcher\scripts\run.ps1 register-vlc-protocol
```

注册后，报告中的 `VLC` 链接使用 `vlcfile://open?path=...&subtitle=...`。`path` 和 `subtitle` 都是 UTF-8 base64url 编码，避免 UNC 路径、空格和中文在浏览器中损坏；处理脚本负责解码后启动 VLC，并在字幕存在时传入 `--sub-file`。

## 报告结构

HTML 报告必须包含：

- 总览：总视频数、已完成、已有字幕、未完成、人工抽查、二阶段比对、重试下载、重试解压。
- 人工抽查：已落盘但存在大时长差、依赖片源名/字幕组或页面时长判断的项目。
- 二阶段比对：候选已下载或可下载，基础条件满足，但不能只凭末条时间码决定。
- 重试下载：API、签名、浏览器校验、网络或代理问题导致没有拿到文件。
- 重试解压：下载包存在或页面明确有字幕，但未解出有效字幕。
- 放宽过滤复核：默认过滤过严时保留的候选，例如机器翻译或低置信候选。
- 未完成/硬拒绝：标题、年份、季集或语言明确不匹配的项目。

## 状态值

```text
completed
completed_subhd
skipped_existing
not_completed
manual_check
needs_compare
retry_download
retry_extract
review_relaxed_filter
hard_reject
```

报告中要把状态转成中文标签，但保留原始状态值，方便后续脚本读取。

## 行字段

每个条目至少显示：

- 视频路径
- VLC 播放入口
- 当前状态
- 来源
- 候选名或候选 URL
- 目标字幕路径
- 可比时长差
- 最大时长差
- 原因
- 相关链接

若使用内嵌字幕锚点，原因中至少写出锚点流、匹配比例、偏移中位数和 90 分位误差，例如 `coverage2s`、`median_abs`、`p90_abs`。

原因较长时要折叠显示，避免页面像 CSV 一样横向爆炸。

## HTML 内嵌数据

可以在 HTML 末尾嵌入 JSON 数据块，供后续脚本读取：

```html
<script type="application/json" id="subtitle-report-data">...</script>
```

内嵌 JSON 不等同于用户可见 CSV；页面主体仍必须是可阅读的分区式 HTML。
