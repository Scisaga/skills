# PPTX 装配与视频导出

## 初次装配

`python-pptx` 适合创建可回读的基础包，但不能完整创建 SVG 主图、原生音频自动播放和复杂时间轴。推荐：

1. 使用项目专用装配器创建 16:9 基础 PPTX，每个 SVG 图层先放置 PNG fallback；
2. 修改 PPTX ZIP 内 OOXML，加入 SVG、原生音频、动画和换页计时；
3. 不用 `python-pptx` 再保存注入后的文件，只做只读回读。

首次视觉装配通过通用入口调用项目适配器：

```bash
bash skills/build-narrated-presentation/scripts/run.sh assemble-pptx \
  --project /path/to/project \
  --adapter "python /path/to/project/scripts/build_deck.py"
```

也可在 `project.json` 中设置 `production.assemble_command`。通用入口会给适配器追加 `--project <path>`：静态和动画模式检查对应视觉 PPTX 后停止；旁白和视频模式再使用真实音频时间轴，从动画基线生成独立的自动旁白 PPTX。

现代 PowerPoint 优先显示 SVG；不支持 SVG 的环境仍显示 PNG fallback。

## 稳定对象名

```text
s01_base
s01_title
s01_beat_01
s01_beat_02
s01_narration
```

稳定名称用于关联 shape id、动画、测试和 PowerPoint 选择窗格。

动画装配器必须把 manifest 的 beat `id` 写成 `sNN_<beat_id>`，例如第 1 页 `title` 对应 `s01_title`。static QA 不信任 sidecar 声明：它只从 `p:timing/p:tnLst` 回读 entrance `p:animEffect`，filter 必须精确为 `fade` 或 `wipe(left|right|up|down)`，目标 `spid` 必须指向唯一 `cNvPr` 稳定名，时长必须为 1–1000ms 并匹配 timing sidecar。`onClick`、`p:transition`、空 `p:timing`、裸时间容器、畸形 filter、重复对象名或不存在的 shape target 都不算动画证据。

## 原生音频对象

每页 MP3 必须内嵌到 `ppt/media/`，并具有：

- `audio/mpeg` content type；
- OOXML `audio` relationship；
- Office 2007 `media` relationship；
- `p14:media` 嵌入关系；
- `a:audioFile` 关系；
- `isNarration="1"`；
- 放映时隐藏的媒体节点；
- 有效的扬声器 poster。

不要使用外部文件关系。透明 1×1 poster 在部分 PowerPoint 版本中会显示黑块，使用正常的小型扬声器图片。

## 自动播放和换页

仅嵌入音频不会自动播放。使用 PowerPoint 原生 `mediacall`：

```text
cmd = playFrom(0.0)
trigger duration = 1ms
start = slide onBegin
```

每页：

```text
advClick = 0
advTm = actual_audio_ms + 150
transition = fade
transition duration = 250ms
```

演示文稿级别显式开启：

```text
useTimings = 1
showNarration = 1
showAnimation = 1
```

不要写循环属性，最后一页结束后退出。

## 只替换音频

视觉、图层和动画已验收后，使用：

```bash
bash skills/build-narrated-presentation/scripts/run.sh replace-audio \
  --project /path/to/project
```

内置替换器要求：

- PPTX 页数与音频时间轴一致；
- 每页恰好引用一个内部 MP3；
- 不允许多个页面共享同一个媒体成员；
- 逐页 MP3 已存在；
- `advance_ms` 已由真实时长生成。

它只允许改变：

```text
ppt/media/<该页媒体>.mp3
ppt/slides/slideN.xml 中的 transition advTm
```

完成后生成 `video/replace_audio_report.json`，报告具体媒体目标和 ZIP 成员变化；若其他包成员变化则失败。该模式不会重做 SVG、PNG fallback、图层、动画或像素比较。

如果动画基线 PPTX 不具备上述稳定结构，先用项目适配器完成一次初始装配和标准验收，不能把局部替换器当作通用 PPTX 修复器。

## OOXML 校验

初始装配器至少检查：

- content types 与 relationships 全部可解析；
- SVG 和 MP3 均为内部关系；
- 每页 shape、layer、beat 和 timing 一一对应；
- `mediacall playFrom(0.0)` 在入页时触发；
- 不存在 `onClick` 动画触发；
- 自动换页来自实际音频时长；
- narration、animation、timings 已启用；
- 最后一页不循环；
- `python-pptx` 可以只读回读页数。

`qa --level standard` 负责重新检查与增量音频变更直接相关的媒体内容、自动播放和换页时间，但不重复静态视觉像素比较。

## PowerPoint 视频导出

在 Windows 桌面 PowerPoint 环境运行：

```bash
bash skills/build-narrated-presentation/scripts/run.sh export-video \
  --project /path/to/project \
  --color-range-fix auto
```

命令通过 PowerPoint `CreateVideo`：

- 打开最终 PPTX；
- 使用既有计时和旁白；
- 默认输出 1080p、30fps、质量 100；
- 轮询导出状态直到完成、失败或超时；
- 写入 `video/powerpoint_export.json`；
- 记录 PowerPoint `Version`、`Build`、Product Code 和 Click-to-Run ProductReleaseIds；
- 把“PPTX 已由 PowerPoint 打开”和“MP4 已由 PowerPoint 导出”分别记录到构建状态；
- 按版本执行 Office 2019 像素色阶重编码后停止。

可按需传入 `--vertical-resolution`、`--frames-per-second`、`--quality` 和 `--timeout-minutes`。不要用统一“每张幻灯片秒数”覆盖现有计时。

### Office 2019 色彩范围兼容

实测 Office 2019 `CreateVideo` 可能把实际使用 full-range 像素值的 H.264 标为 limited range，导致播放器扩展色阶后高光变白、暗部压黑；Office 2021/2022 或更新环境未复现。由于 Office 2019 和更新版本都可能报告 `Version=16.0`，零售版 build 也可能重叠，`auto` 优先使用 Click-to-Run ProductReleaseIds；只有明确落在 Office 2019 volume 范围的旧 build 才作为回退证据，其他缺少产品 ID 的 build 归为 `unknown`：

- `office-2019`：不能只改标签；执行 `scale=in_range=pc:out_range=tv` 把像素映射到标准 limited range，以 `libx264 -preset slow -crf 16 -pix_fmt yuv420p` 重编码视频，音频及其他流保持 copy，临时 MP4 成功后原子替换交付文件；
- `newer-office`：不修改 MP4；
- `unknown`：不猜测、不修改，在报告中写 warning；已知是 Office 2019 时显式传 `--color-range-fix on`，已知无问题时传 `off`。

重编码输出固定标记 BT.709 limited range，保留原始尺寸、时间戳和音频流；它会重写视频码流，但不改变动画编排、旁白内容或目标时长，也不属于视频画面检查。Office 2019 需要 FFmpeg 时若未安装，运行 `scripts/install_ffmpeg.ps1`（Windows）或 `scripts/install_ffmpeg.sh`（Linux/WSL）后重试。PowerPoint `Build` 与 ProductReleaseIds、兼容判断、修复前后 SHA、编码器、CRF 和 `reencoded=true` 必须写入 `video/powerpoint_export.json`。

完成兼容处理后直接交付 MP4。不要调用 ffprobe，不抽帧、不播放、不安排人工完整观看，也不运行 release QA；导出前的 standard QA 已负责检查旁白 PPTX 的媒体、自动播放和换页结构。

## 导出指定页面

```bash
bash skills/build-narrated-presentation/scripts/run.sh export-pages \
  --project /path/to/project \
  --pages 8,9,14 \
  --format pdf \
  --output /path/to/selected-pages.pdf
```

- PDF：把所选页复制到临时演示文稿后导出为一个 PDF；
- PNG/JPG：`--output` 是目录，每页输出一个位图；
- 页码必须是逗号分隔的正整数且不能超过总页数。

这个命令适合局部审阅，不触发视频后检。

## 证据边界

只记录：

1. PowerPoint 成功打开当前 PPTX；
2. PowerPoint 成功导出非空 MP4，并记录当前 PPTX、最终 MP4、PowerPoint 身份和色彩范围兼容决策。

Office 2019 的像素色阶重编码是确定性兼容步骤；这些证据不扩展成对 MP4 画面、时长或观看效果的检查。
