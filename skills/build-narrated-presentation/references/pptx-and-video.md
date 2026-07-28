# PPTX 装配与视频导出

## 两阶段装配

`python-pptx` 适合创建可回读的基础包，但不能完整创建 SVG 主图、原生音频自动播放和复杂时间轴。采用：

1. 使用 `python-pptx` 创建 16:9 基础 PPTX，每个 SVG 图层先放置 PNG fallback；
2. 修改 PPTX ZIP 内 OOXML，加入 SVG、原生音频、动画和换页计时；
3. 不用 `python-pptx` 再保存注入后的文件，只做只读回读。

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

## OOXML 校验

装配器至少检查：

- content types 与 relationships 全部可解析；
- SVG 和 MP3 均为内部关系；
- 每页 shape、layer、beat 和 timing 一一对应；
- `mediacall playFrom(0.0)` 在入页时触发；
- 不存在 `onClick` 动画触发；
- 自动换页来自实际音频时长；
- narration、animation、timings 已启用；
- 最后一页不循环；
- `python-pptx` 可以只读回读页数。

## PowerPoint 导出

在 Windows PowerPoint：

1. 打开最终 PPTX，确认没有修复提示；
2. 从第一页完整放映一次；
3. 进入“文件 → 导出 → 创建视频”；
4. 选择 Full HD 1080p，必要时选择 4K；
5. 选择“使用录制的计时和旁白”；
6. 不用统一“每张幻灯片秒数”覆盖现有计时；
7. 导出 MP4；
8. 检查开头、页间切换、截图页、最后一页和总时长。

Python 与 OOXML 检查不能替代目标 PowerPoint 版本的实机播放和导出。
