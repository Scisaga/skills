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

也可在 `project.json` 中设置 `production.assemble_command`。通用入口会给适配器追加 `--project <path>`，然后用真实音频时间轴更新生成的 PPTX。

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

如果现有 PPTX 不具备上述稳定结构，先用项目适配器完成一次初始装配和 release 验收，不能把局部替换器当作通用 PPTX 修复器。

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
  --project /path/to/project
```

命令通过 PowerPoint `CreateVideo`：

- 打开最终 PPTX；
- 使用既有计时和旁白；
- 默认输出 1080p、30fps、质量 100；
- 轮询导出状态直到完成、失败或超时；
- 写入 `video/powerpoint_export.json`；
- 把“PPTX 已由 PowerPoint 打开”和“MP4 已由 PowerPoint 导出”分别记录到构建状态；
- 将人工完整观看状态重置为待办。

可按需传入 `--vertical-resolution`、`--frames-per-second`、`--quality` 和 `--timeout-minutes`。不要用统一“每张幻灯片秒数”覆盖现有计时。

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

这个命令适合局部审阅，不等同于完整放映或完整视频验收。

## 证据边界

严格区分：

1. PowerPoint 成功打开当前 PPTX；
2. PowerPoint 成功导出当前 MP4；
3. 工具对当前 MP4 做了时长和文件检查；
4. 人工从头到尾观看当前 MP4。

自动化启动或关闭放映窗口不能证明已经完整观看。只有操作者真实看完后，才运行：

```bash
bash skills/build-narrated-presentation/scripts/run.sh qa \
  --project /path/to/project \
  --level release \
  --human-confirmed \
  --confirmed-by "reviewer"
```

确认记录与当前 MP4 SHA-256 绑定；重新导出后自动失效。
