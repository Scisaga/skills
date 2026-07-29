# 制作流程

## 交付目标先行

`project.json.deliverable` 决定生产链的停止点：

| 目标 | 必做链路 | 停止点 |
|---|---|---|
| `static_pptx` | 内容、模板、SVG、静态装配、静态 QA | 静态 PPTX |
| `animated_pptx` | 静态链路、SVG 分层、首秒动画 | 动画 PPTX |
| `narrated_pptx` | 动画链路、旁白、逐页音频、自动换页 | 自动旁白 PPTX |
| `video` | 旁白链路、PowerPoint 导出、视频验收 | MP4 |

静态制作不得因为缺少 TTS 或视频依赖而失败。动画 PPTX 默认由演讲者手动换页；没有旁白时不虚构统一自动停留时长。

## 标准流程

```text
确认交付目标
→ 输入 Markdown 质量门禁
→ 整理并批准 page-script.md
→ 创建或适配 template.pptx
→ 制作并批准代表性 SVG
→ 批量生成静态 SVG 与静态 PPTX
→ 按交付目标决定是否停止
→ 按需制作动画
→ 按需生成导演稿、试听声音并批准旁白
→ 按章节连续合成、按 bookmark 切成逐页 MP3
→ 生成自动旁白 PPTX
→ 按需由 Windows PowerPoint 导出 MP4
```

### 内容

输入文档通过门禁后，`init` 创建 `page-script.md` 工作副本。逐页文字稿至少说明页码、页面作用、核心结论、正文、视觉需求、事实来源和页面间关系。执行内容审批前不制作正式模板或批量 SVG。

### 模板与样稿

用户模板原件保存在 `inputs/template-source.pptx`，适配结果保存为 `template.pptx`。没有模板时，根据项目风格创建 `template.pptx`。模板负责背景、标题、Logo、页脚、页码和安全区；透明全页 SVG 只绘制主体。

从复杂流程、高密度逻辑、截图、数据图表等高风险页面中选择 1–4 页作为代表性样稿。使用：

```bash
run.sh approve --project PROJECT --stage visual \
  --pages 3,7,10 --approved-by REVIEWER
```

样稿未通过时只返工模板、样稿和受影响文字，不批量制作全稿。

### 旁白

只有 `narrated_pptx` 和 `video` 才启动声音链路。先确认讲述方式、章节范围、目标时长、音色、语速和术语读法，再运行 `manifest` 生成 `narration_review.md`，试听候选音色，最后批准旁白。

明确禁止一个 MP3 跨多页播放。连续章节采用：

```text
整章一次 TTS
→ 页面起点插入 bookmark
→ 按 bookmark 切成逐页 MP3
→ 每页内嵌一个 MP3
```

章节是连续合成和缓存单位，逐页 MP3 是 PowerPoint 播放、换页和局部替换单位。

## 人工源与派生产物

人工维护：

- 输入 Markdown 与 `page-script.md`
- `template.pptx`
- `assets/*.svg`
- `video/svg_layer_plan.json`
- `video/animation_manifest.json` 的视觉字段
- `video/narration_director.json`
- `video/voice_profile.json`

自动生成：

- `video/narration_review.md`
- `video/layers/`
- `video/scripts/<chapter>.ssml`
- `video/audio/<page>.mp3`
- `video/audio/<chapter>.bookmarks.json`
- 动画和音频时间轴
- `video/build_state.json`
- PPTX 与 MP4 交付物

不要直接编辑 manifest 中派生的 `voice`、`narration` 和 `narration_chapters`。

## 变更影响

| 变化 | 失效与重建 | 保留 |
|---|---|---|
| 输入或逐页文字稿 | 内容审批、视觉审批、旁白审批及下游 | 无 |
| 模板、安全区或代表性样稿 | 视觉审批、相关 SVG/PPTX/视频 | 内容、旁白文字、音频 |
| 其他某页 SVG | 该页视觉检查、PPTX、视频 | 内容、音频 |
| 动画 | 动画时间轴、动画 PPTX 及下游 | 静态 QA、音频 |
| 导演稿文字或章节 | 旁白审批、受影响章节音频及下游 | 内容审批、视觉审批 |
| 音色、全局声音参数或词典 | 旁白审批、全部章节音频及下游 | 内容审批、视觉审批 |
| 局部声音参数 | 旁白审批、该页所在章节及下游 | 其他章节和视觉 |
| 输出分辨率 | PowerPoint 视频导出和 MP4 检查 | PPTX、音频、视觉 |

修改章节中任意一页时重做完整章节。QA 只在自己的依赖或检查工具变化后重跑。

## 只改音频

只改音频要求当前内容、视觉和旁白审批有效，并具有可信构建基线。声音参数变化后先试听并重新批准旁白，再执行：

```bash
run.sh rebuild --project PROJECT --scope audio --qa standard
```

固定链路为：

```text
验证内容/视觉基线与旁白审批
→ 按章节重建逐页音频
→ 更新真实音频时间轴
→ audio QA
→ 从动画基线生成新的自动旁白 PPTX
→ standard QA
→ video 项目按需导出 MP4
```

`narrated_pptx` 项目在标准 QA 后停止；只有 `video` 项目才调用 PowerPoint 视频导出。

## 构建状态

`video/build_state.json` 只保存：

- `approvals`：内容、视觉、旁白审批及摘要；
- `inputs`：source、narration、voice、visual 基线；
- `artifacts`：音频、PPTX 和视频摘要；
- `qa`：各等级的 fingerprint 与报告；
- `powerpoint`：打开、导出和人工完整观看证据。

审批和 QA 都必须与当前文件摘要一致。失败结果不能作为缓存；修改检查脚本也会使相应 QA 缓存失效。

## 来源基线

方法基线来自 Scisaga `md-quiz` 的 [SVG → PPTX → 自动旁白视频制作方法论](https://github.com/Scisaga/md-quiz/blob/main/docs/biz/goodwen_2026/SVG_PPTX_%E8%87%AA%E5%8A%A8%E6%97%81%E7%99%BD%E8%A7%86%E9%A2%91%E5%88%B6%E4%BD%9C%E6%96%B9%E6%B3%95%E8%AE%BA.md)。只复用通用契约，不复制项目事实、文案或品牌视觉。
