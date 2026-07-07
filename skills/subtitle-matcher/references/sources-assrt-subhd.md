# ASSRT 与 SubHD 来源策略

## ASSRT

- 优先使用片名、年份、集数和完整版本名搜索。
- 候选页如提供片源时长、语言、来源、下载次数和版本字段，应全部纳入理由。
- ASSRT 下载后仍必须执行本地字幕校验，不能只凭页面元数据通过。
- 如果 ASSRT 候选最后时间码超出阈值，但页面标注时长与视频接近，可标记人工抽查。
- 如果 ASSRT 已下载候选唯一问题是最后时间码差在 600 秒内，应进入 `needs_compare`，不要直接归入 `not_completed`。
- 如果 ASSRT 签名地址下载失败，应保留候选标题、下载次数、语言和页面 URL，进入 `retry_download`。

## SubHD

- SubHD 候选排序要保留分数和标签，例如 `title`、`year`、`filename`、`official`、`duration_match_1s`、`tokens:...`。
- SubHD 下载链接可能需要浏览器校验或重定向；脚本应允许使用 `.env` 代理，并把失败原因写入报告。
- 页面只展示候选但无法下载时，报告中保留候选 URL 和下载 URL，状态保持未完成。
- 单条浏览器下载成功后，仍要走解压、中文检查和时间码校验。
- SubHD API 500、非 JSON、Cloudflare、浏览器校验、签名失败都属于 `retry_download`，不是最终失败。
- `found no acceptable non-machine Chinese candidate` 只表示默认过滤未找到理想候选；没有更好字幕时，应进入 `review_relaxed_filter`，由用户决定是否下载机器翻译或低置信候选做二阶段比对。
- `no_sub_files` 或解压失败应进入 `retry_extract`，先尝试其他解压器、浏览器下载文件名和压缩包内容检查。

## 搜索词生成

按从强到弱尝试：

1. 完整文件名去扩展名。
2. 片名 + 年份 + 关键版本 token。
3. 片名 + 年份。
4. 剧集使用片名 + `SxxEyy` + 年份或平台 token。

不要把目录名中的无关标签当成片名；例如 `rarbg`、`YTS.MX`、`x265`、`10bit`、`HDR` 应归入版本 token。

## 报告留痕

对每个候选至少保留：

- 来源：`ASSRT` 或 `SubHD`
- 候选标题
- 候选 URL
- 下载 URL
- 分数或排序依据
- 命中的标题、年份、集数、文件名、版本 token
- 拒绝或通过原因
