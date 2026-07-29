---
name: build-narrated-presentation
description: 从产品计划、执行方案等 Markdown 文档制作静态 PPTX、动画 PPTX、逐页旁白 PPTX 或 PowerPoint 导出的 MP4；先执行输入质量门禁，再确认逐页文字稿、PPT 模板和代表性 SVG，按交付目标停止，并支持原创技术信息图预设、章节连续合成后切分逐页 MP3、真实音频时长换页、音频增量重建和分级验收。适用于“把文档生成 PPT/PPTX”“复用现有 PPT 模板”“制作技术架构演示”“给 PPT 加动画或旁白”“更换音色或发音”“只替换 PPT 音频”“导出旁白视频”及“检查媒体嵌入和换页”的场景。
---

# Build Narrated Presentation

## 概述

把输入内容、PPT 模板、静态 SVG、动画、旁白、声音和换页时间分开管理。先做能独立交付的静态演示，再按 `project.json.deliverable` 决定是否继续制作动画、逐页旁白或视频。

## 不变量

1. 只支持 `project.json` schema v2，不兼容或迁移其他版本。
2. 输入 Markdown 未通过自动预检和绑定 SHA-256 的语义复核时，只返工输入文档。
3. 用户确认逐页文字稿后才能确认模板和代表性 SVG；样稿未通过时不得批量生产。
4. 模板层负责背景、标题、Logo、页脚和安全区；主体 SVG 使用完整 `1600×900` 透明画布。
5. 先完成静态 SVG，再按需拆动画层；每页最多六个进入动画组，动画在首秒内完成。
6. PowerPoint 每页恰好内嵌一个 MP3。禁止一个 MP3 跨多页播放。
7. 需要跨页语气连续时，只能整章连续合成、在页边界插入 bookmark，再切成逐页 MP3。
8. 页面换页时间使用 `真实 MP3 时长 + 150ms`，不得用文字估算或提前换页。
9. 声音只写入 `voice_profile.json`；声音变化不重新触发输入文档语义复核。
10. PowerPoint 打开、视频导出、MP4 自动检查和人工完整观看是四种不同证据。

## 工作流

1. 读取 `references/input-quality-gate.md`，检查输入并完成语义复核。
2. 选择 `static_pptx`、`animated_pptx`、`narrated_pptx` 或 `video`，运行 `init --deliverable ...`。
3. 整理 `page-script.md`；确认后执行 `approve --stage content`。
4. 适配用户模板或创建 `template.pptx`，在配置的安全区内制作 1–4 张高风险代表性 SVG；确认后执行 `approve --stage visual --pages ...`。
5. 批量生成剩余 SVG、静态 PPTX，并执行 `qa --level static`。目标为静态 PPTX 时停止。
6. 按需制作首秒动画并生成动画 PPTX。目标为动画 PPTX 时停止。
7. 目标包含旁白时，维护导演稿和声音配置，运行 `manifest` 生成审阅稿，试听候选音色；确认后执行 `approve --stage narration`。
8. 按章节连续合成并切成逐页 MP3，生成真实音频时间轴和自动旁白 PPTX；执行 `audio`、`standard` QA。目标为旁白 PPTX 时停止。
9. 目标为视频时，标准 QA 通过后由 Windows PowerPoint 导出 MP4；人工完整观看后执行 release QA。

详细流程与增量影响分析读取 `references/workflow.md`；项目字段和审批摘要读取 `references/project-contract.md`。

## 命令模式

```bash
bash skills/build-narrated-presentation/scripts/run.sh doctor --stage static
bash skills/build-narrated-presentation/scripts/run.sh inspect-input \
  --document source.md --markdown-output input-preflight.md
bash skills/build-narrated-presentation/scripts/run.sh prepare-input-review \
  --document source.md --output input-review.json
bash skills/build-narrated-presentation/scripts/run.sh validate-input \
  --document source.md --review input-review.json \
  --json-output input-gate.json --markdown-output input-gate.md
bash skills/build-narrated-presentation/scripts/run.sh init \
  --output /path/to/project \
  --name "项目名称" \
  --deliverable narrated_pptx \
  --input-document source.md \
  --input-review input-review.json \
  --template-source existing-template.pptx \
  --visual-style technical-infographic
bash skills/build-narrated-presentation/scripts/run.sh approve \
  --project /path/to/project \
  --stage content \
  --approved-by "reviewer"
bash skills/build-narrated-presentation/scripts/run.sh approve \
  --project /path/to/project \
  --stage visual \
  --pages 3,7,10 \
  --approved-by "reviewer"
bash skills/build-narrated-presentation/scripts/run.sh manifest \
  --visual /path/to/project/video/animation_manifest.json \
  --director /path/to/project/video/narration_director.json \
  --voice-profile /path/to/project/video/voice_profile.json \
  --output /path/to/project/video/animation_manifest.json \
  --review /path/to/project/video/narration_review.md
bash skills/build-narrated-presentation/scripts/run.sh voice-audition \
  --project /path/to/project \
  --voices zh-CN-XiaochenNeural,zh-CN-XiaoxiaoNeural
bash skills/build-narrated-presentation/scripts/run.sh approve \
  --project /path/to/project \
  --stage narration \
  --approved-by "reviewer"
bash skills/build-narrated-presentation/scripts/run.sh synthesize \
  --project /path/to/project
bash skills/build-narrated-presentation/scripts/run.sh audio-timeline \
  --manifest /path/to/project/video/animation_manifest.json \
  --audio-dir /path/to/project/video/audio \
  --output /path/to/project/video/audio_timeline.json
bash skills/build-narrated-presentation/scripts/run.sh assemble-pptx \
  --project /path/to/project \
  --adapter "python /path/to/project/build_deck.py"
bash skills/build-narrated-presentation/scripts/run.sh qa \
  --project /path/to/project \
  --level static
bash skills/build-narrated-presentation/scripts/run.sh export-video \
  --project /path/to/project
bash skills/build-narrated-presentation/scripts/run.sh validate \
  --project /path/to/project \
  --strict
```

`approve` 把当前文件摘要写入 `build_state.json`。内容变化使视觉和旁白审批失效；模板或代表性样稿变化只影响视觉审批；导演稿或声音配置变化只影响旁白审批。不要手工修改审批状态。

`assemble-pptx` 根据 `deliverable` 自动分流。静态和动画模式不得读取音频；旁白和视频模式从动画基线生成独立的自动旁白 PPTX。

更换 `--voice`、`--rate` 或 `--pitch` 会先更新声音配置并停止，必须试听并重新执行旁白审批后才能合成。`rebuild --scope audio` 仍以章节为最小重建单位。

## 资源导航

- 输入门禁：`references/input-quality-gate.md`
- 工作流和增量重建：`references/workflow.md`
- schema v2、目录和审批：`references/project-contract.md`
- 模板、SVG 和动画：`references/visual-and-animation.md`
- 原创技术信息图预设：`references/technical-infographic-style.md`
- 导演稿、声音、bookmark 和逐页 MP3：`references/narration-and-audio.md`
- OOXML、媒体和 PowerPoint 导出：`references/pptx-and-video.md`
- QA 与完成定义：`references/validation.md`

## 输出规则

- 不覆盖输入 Markdown、用户模板原件、原始 SVG 或既有交付物。
- 只生成当前 `deliverable` 所需的链路和交付物。
- 第三方图片只用于风格研究，不进入资产或交付物；不得复刻第三方品牌视觉。
- 没有当前文件摘要对应的 PowerPoint 导出证据时，不声称视频已导出。
- 没有人工完整观看证据时，不声称 release 验收通过。
