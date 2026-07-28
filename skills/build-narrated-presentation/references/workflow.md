# 制作流程

## 目录

- [目标与边界](#目标与边界)
- [数据流](#数据流)
- [唯一事实来源](#唯一事实来源)
- [标准构建](#标准构建)
- [变更影响分析](#变更影响分析)
- [只改音频模式](#只改音频模式)
- [构建状态与缓存](#构建状态与缓存)
- [样板优先](#样板优先)
- [来源基线](#来源基线)

## 目标与边界

使用 SVG 完成页面设计，使用 PPTX 承载动画、逐页音频和换页时间轴，使用 Windows PowerPoint 导出 MP4。不要用动画修复静态页面，不要用 Python 模拟 PowerPoint 最终视频渲染，也不要把某个来源项目的产品叙事复制到新项目。

把以下内容当作独立依赖：

```text
内容：输入文档、逐页映射、旁白文字、章节归属
声音：音色、语速、音高、发音词典、页间停顿
视觉：静态 SVG、分层、动画
装配：内嵌媒体、自动播放、换页时间
导出：PowerPoint 版本、MP4
验收：audio、standard、release、人工完整观看
```

更换声音参数不是内容修改，不得因此要求重新做输入语义复核。旁白文字或章节归属发生变化则属于内容修改，必须重新检查其与已通过输入文档的一致性。

## 数据流

```text
输入 Markdown
  → 自动预检 + 语义复核
  → 输入质量门禁
  → 逐页演示映射
  → 静态 SVG 页面
  → SVG 语义分层计划
  → 全画布 SVG 图层 ┐
                     ├→ PPTX OOXML 装配 → 自动播放 PPTX
视觉 manifest       │                         │
  → 首秒动画时间轴 ──┤                         ├→ PowerPoint 导出 MP4
旁白导演稿           │                         │
声音配置             │                         └→ 人工完整观看
  → 章节连续 SSML    │
  → bookmark 切页    │
  → 逐页 MP3         │
  → 真实音频时间轴 ──┘
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
| `video/narration_director.json` | 页面章节、讲述目的、语气、文本、局部语速和停顿 |
| `video/voice_profile.json` | TTS 提供方、音色、全局语速、音高、发音词典、试听文案 |

自动生成：

| 文件或目录 | 来源 |
|---|---|
| `video/layers/<页码>/*.svg` | SVG 分层器 |
| `video/narration_review.md` | manifest 合并器 |
| `video/scripts/<chapter>.ssml` | 旁白导演稿 + 声音配置 |
| `video/audio/<chapter>.bookmarks.json` | 连续合成返回的 bookmark 与切分边界 |
| `video/audio/<页码>.mp3`、`*.sha256` | 章节连续合成与按页切分 |
| `video/audio_timeline.json` | 逐页 MP3 真实时长 |
| `video/fast_animation_timing.json` | 首秒动画生成器 |
| `video/build_state.json` | 输入摘要、产物摘要、QA 缓存和 PowerPoint 证据 |
| `deliverables/*.pptx` | 项目装配器与音频替换器 |
| `deliverables/*.mp4` | Windows PowerPoint |

只在 `narration_director.json` 修改旁白内容和章节归属，只在 `voice_profile.json` 修改声音。manifest 中的 `narration` 和 `voice` 都是派生结果。

## 标准构建

视觉首次建立或发生变化时：

1. 输入文档通过自动预检和语义复核；不通过时返工文档并停止。
2. 从通过门禁的文档建立逐页映射。
3. 完成静态 SVG。
4. 更新 SVG 分层计划并校验源文件摘要。
5. 生成全画布图层，叠加后与源图做像素比较。
6. 合并视觉 manifest、旁白导演稿和声音配置。
7. 用 10–15 秒固定文案生成候选音色，人工确认音色和专有名词发音。
8. 按章节连续合成，在每页开头插入 bookmark，再切成逐页 MP3。
9. 读取逐页 MP3 的真实时长，生成换页和首秒动画时间轴。
10. 先生成三类样板页并实机检查。
11. 生成完整 PPTX，执行 `qa --level standard`。
12. 用 Windows PowerPoint 导出 MP4，执行自动检查并由人工完整观看。
13. 人工确认后执行 `qa --level release --human-confirmed`，形成可供后续增量重建使用的基线。

## 变更影响分析

先识别真正变化的依赖，再选择最小链路：

| 变化 | 必须重建 | 不重复执行 |
|---|---|---|
| 输入文档 | 输入门禁、受影响内容、视觉/旁白及其下游 | 无条件跳过既有语义复核 |
| 旁白文字或章节归属 | 内容一致性复核、受影响章节音频、时间轴、PPTX、视频 | 未受影响章节的 TTS |
| 音色、全局语速、音高、发音词典 | 全部章节音频、时间轴、PPTX 音频与换页、视频 | 输入门禁、SVG、分层、动画、像素比较 |
| 某页局部停顿、语速或音高 | 该页所在完整章节及其下游 | 输入门禁、其他章节、视觉验收 |
| 动画 | 首秒动画时间轴、PPTX、视频 | 音频合成 |
| 某页 SVG | 该页图层、视觉验证、PPTX、视频 | 音频；除非页面判断也变了 |
| 输出分辨率 | PowerPoint 视频导出和 MP4 检查 | PPTX、音频、视觉 |

章节是音频缓存的最小单位。选择章节中的任意一页都会重新合成整个章节，避免相邻页面出现声线、语气或切分漂移。

## 只改音频模式

已有视觉和 release 基线时：

```bash
bash skills/build-narrated-presentation/scripts/run.sh rebuild \
  --project /path/to/project \
  --scope audio \
  --voice zh-CN-XiaochenNeural \
  --qa standard
```

执行链固定为：

```text
检查 source / narration / visual 基线
→ 更新 voice_profile.json
→ 按章节合成与切页
→ 重建真实音频时间轴
→ audio QA
→ 只替换 PPTX 内嵌 MP3 和 advTm
→ standard QA
→ PowerPoint 导出视频
→ 人工观看待办
```

如果 source、旁白文字、章节映射、SVG 或动画摘要与基线不同，命令必须阻断。老项目尚无 `build_state.json` 时，只能由操作者明确确认现有内容和视觉可信后使用一次 `--allow-unverified-baseline`；该选项不会产生 release 结论。

用 `--dry-run` 查看将受影响的章节。使用 `--pages 8,9` 只重做这些页面所在的完整章节。`--voice`、`--rate`、`--pitch` 是全局配置，不能与 `--pages` 同时使用。使用 `--skip-export` 只适合中间编辑，不能用于 release。

## 构建状态与缓存

`video/build_state.json` 分开保存：

- `inputs`：source、narration、voice、visual 摘要；
- `artifacts`：逐页音频、PPTX、MP4 摘要；
- `qa`：各等级的 fingerprint、状态、时间和报告路径；
- `powerpoint.opened`：当前 PPTX 确实被 PowerPoint 打开的证据；
- `powerpoint.video_exported`：当前 MP4 由 PowerPoint 导出的证据；
- `powerpoint.human_watch`：人工完整观看当前 MP4 的显式确认。

每次 QA 先计算依赖和检查脚本的 fingerprint。只有此前状态为 `passed` 且 fingerprint 完全一致时才打印 `SKIP`。使用 `--force` 可以主动重跑。

替换 PPTX 音频后，旧 MP4 和所有 PowerPoint 证据立即失效；重新导出 MP4 后，人工观看证据仍保持待办。人工确认必须与当前 MP4 SHA-256 绑定。

## 样板优先

新项目先选：

1. 一页普通图文页；
2. 一页截图复杂页；
3. 一页流程或架构页。

验证 SVG 清晰度、截图可读性、首秒动画、音频图标、自动播放和自动换页后，再批量装配全部页面。样板通过不等于人工完整观看整套 MP4。

## 来源基线

本方法提炼自 Scisaga `md-quiz` 仓库的 [SVG → PPTX → 自动旁白视频制作方法论](https://github.com/Scisaga/md-quiz/blob/main/docs/biz/goodwen_2026/SVG_PPTX_%E8%87%AA%E5%8A%A8%E6%97%81%E7%99%BD%E8%A7%86%E9%A2%91%E5%88%B6%E4%BD%9C%E6%96%B9%E6%B3%95%E8%AE%BA.md)，成功基线位于 [`docs/biz/goodwen_2026/video`](https://github.com/Scisaga/md-quiz/tree/main/docs/biz/goodwen_2026/video)，参考提交为 `eda2b2410c8ee36eb4daac2ab180513e342a58ec`。

来源基线验证了 19 页、19 段内嵌旁白、首秒动画和基于真实 MP3 的自动换页。复用时只保留通用契约，不复制 Goodwen 的文案、事实、路径或版本后缀。
