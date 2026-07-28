# 制作流程

## 目录

- [目标与边界](#目标与边界)
- [数据流](#数据流)
- [唯一事实来源](#唯一事实来源)
- [标准构建](#标准构建)
- [增量重建](#增量重建)
- [样板优先](#样板优先)
- [来源基线](#来源基线)

## 目标与边界

使用 SVG 完成页面设计，使用 PPTX 承载动画、旁白和换页时间轴，使用 Windows PowerPoint 导出 MP4。不要用动画修复静态页面，不要用 Python 模拟 PowerPoint 最终视频渲染，也不要把某个来源项目的产品叙事复制到新项目。

## 数据流

```text
输入 Markdown
  → 自动预检 + 语义复核
  → 输入质量门禁
  → 逐页演示映射
  → 静态 SVG 页面
  → SVG 语义分层计划
  → 全画布 SVG 图层 ┐
                     ├→ PPTX OOXML 装配 → 自动播放 PPTX → PowerPoint 导出 MP4
旁白导演稿           │
  → 动画与旁白 manifest
  → SSML / 逐页 MP3
  → 真实音频时间轴 ──┤
视觉 manifest
  → 首秒动画时间轴 ──┘
```

## 唯一事实来源

人工维护：

| 文件 | 所有内容 |
|---|---|
| 输入 Markdown | 受众、主张、事实边界、内容结构和逐页演示映射 |
| `input-review.json` | 与输入 SHA-256 绑定的语义复核证据与结论 |
| `assets/*.svg` | 完整静态页面与视觉事实 |
| `video/svg_layer_plan.json` | `base`、`title`、`beat_*` 的拆分 |
| `video/animation_manifest.json` 的视觉字段 | 页序、源 SVG、动画组和效果 |
| `video/narration_director.json` | 讲述目的、语气、文本、局部语速和停顿 |

自动生成：

| 文件或目录 | 来源 |
|---|---|
| `video/layers/<页码>/*.svg` | SVG 分层器 |
| `video/narration_review.md` | manifest 合并器 |
| `video/scripts/*.txt`、`*.ssml` | TTS 脚本 |
| `video/audio/*.mp3`、`*.sha256` | TTS 脚本 |
| `video/audio_timeline.json` | MP3 真实时长 |
| `video/fast_animation_timing.json` | 首秒动画生成器 |
| `deliverables/*.pptx` | PPTX 装配器 |
| `deliverables/*.mp4` | Windows PowerPoint |

只在 `narration_director.json` 修改旁白。manifest 中的 `narration` 是派生结果，不是第二份口播源。

## 标准构建

视觉首次建立或发生变化时：

1. 输入文档通过自动预检和语义复核；不通过时返工文档并停止。
2. 从通过门禁的文档建立逐页映射。
3. 完成静态 SVG。
4. 更新 SVG 分层计划并校验源文件摘要。
5. 生成全画布图层，叠加后与源图做像素比较。
6. 合并视觉 manifest 与旁白导演稿。
7. 合成逐页音频并读取真实时长。
8. 生成首秒动画时间轴。
9. 先生成三类样板页并实机检查。
10. 生成完整 PPTX，做 OOXML、回读和实机检查。
11. 导出 MP4 并检查关键位置与总时长。

## 增量重建

- 只改旁白：重建 manifest、发生变化页的 MP3、音频时间轴和 PPTX。
- 只改动画：重建首秒动画时间轴和 PPTX。
- 只改某页 SVG：重建该页图层、视觉验证、PPTX；如果页面判断变化，再同步改旁白。
- 修改输入文档：旧语义复核立即失效；重新执行完整输入门禁，再判断受影响页面、SVG 和旁白。
- 只改输出分辨率：保留 PPTX 计时，重新由 PowerPoint 导出视频。

每页 SSML 使用 SHA-256。声音、语速、停顿和文本都没变化时复用 MP3，但每次仍重新读取全部 MP3 的真实时长。

## 样板优先

新项目先选：

1. 一页普通图文页；
2. 一页截图复杂页；
3. 一页流程或架构页。

验证 SVG 清晰度、截图可读性、首秒动画、音频图标、自动播放和自动换页后，再批量装配全部页面。

## 来源基线

本方法提炼自 Scisaga `md-quiz` 仓库的 [SVG → PPTX → 自动旁白视频制作方法论](https://github.com/Scisaga/md-quiz/blob/main/docs/biz/goodwen_2026/SVG_PPTX_%E8%87%AA%E5%8A%A8%E6%97%81%E7%99%BD%E8%A7%86%E9%A2%91%E5%88%B6%E4%BD%9C%E6%96%B9%E6%B3%95%E8%AE%BA.md)，成功基线位于 [`docs/biz/goodwen_2026/video`](https://github.com/Scisaga/md-quiz/tree/main/docs/biz/goodwen_2026/video)，参考提交为 `eda2b2410c8ee36eb4daac2ab180513e342a58ec`。

来源基线验证了 19 页、19 段内嵌旁白、首秒动画和基于真实 MP3 的自动换页。复用时只保留通用契约，不复制 Goodwen 的文案、事实、路径或版本后缀。
