---
name: build-narrated-presentation
description: 从逐页演讲稿、产品计划、执行方案或渲染型 Markdown 制作逐页旁白 MP3、静态 PPTX、动画 PPTX、自动旁白 PPTX 或 PowerPoint 导出的 MP4；保真绑定已整理的逐页正文，并要求其他输入显式提供 adapted page-script，支持可执行语气编排、音频独立交付、模板复用、技术信息图、章节连续合成后逐页切分、真实音频时长换页、声音重配和分级验收。适用于“把演讲稿逐页配音”“只生成每页音频”“把文档生成 PPT/PPTX”“复用现有 PPT 模板”“制作技术架构演示”“给 PPT 加动画或旁白”“更换音色或发音”“只替换 PPT 音频”“导出旁白视频”及“检查媒体嵌入和换页”的场景。
---

# Build Narrated Presentation

## 概述

把事实源、逐页口述稿、视觉、动画、声音和交付物分开管理。`project.json.deliverable` 决定链路：只要逐页 MP3 时选择 `narration_audio`，不得启动模板、SVG 或 PowerPoint；需要演示时才继续视觉和装配。

## 不变量

1. 只支持 `project.json` schema v2。
2. 正常入口只执行一次完整输入门禁；`inspect-input` 和 `validate-input` 只用于诊断，不串成重复前置流程。
3. `page-narration` 表示用户已经整理好的 `## 第 N 页｜标题` 或纯旁白 `## PAGE N/T｜标题` 口述稿。默认把它原样绑定为 `page-script.md`，不得生成摘要或 `normalized-input.md` 代替正文。
4. 计划或渲染型输入必须显式传入只含口述正文的 `--page-script-source`。已整理逐页源的任何非字节一致改写都需用户明确授权，并切换成 `adapted`；授权绑定当前源稿与逐页稿 SHA，相同字节重批不重复索权，相似旧版本也不能静默通过。
5. `init` 原样保留 `inputs/source.md`，记录两个外部来源路径、SHA、profile、门禁/复核摘要和绑定审计。`identity` 表示逐字节一致，`adapted` 表示显式整理稿。
6. 初始化后的导演稿、manifest、审批和 QA 均为空状态；纯音频项目不复制或读取 SVG、图层计划和模板。空文件不是一页样稿，也不是完成证据。
7. 先批准内容，再生成导演稿、视觉或音频。导演稿中的 TTS 正文必须是 `page-script.md` 的格式化派生，不能再次摘要；每页语气说明还必须编译为实际进入 SSML 的局部语速、音高或停顿，统一模板不能通过 narration 审批。`narration_audio` 只需内容和旁白审批，不需要视觉审批。
8. 声音和发音词典只写入 `video/voice_profile.json`。`narration_review.md` 必须列出正文中的拉丁技术代号、已配置实际读法和未覆盖项；候选发现只产生审阅警告，不根据字形自动猜读或新增阻断门禁。材料成分牌号按元素语义判断，例如 `AlSi10Mg` 是成分型合金牌号，中文专业口播读作“铝硅十镁”，不能按普通英文串或化学分子式裸读。
9. 需要更改声音或词典时由 `configure-voice` 刷新已有旁白审阅稿；音色和术语试听是推荐的人工质量步骤，当前 narration 审批是机器实际执行的正式边界。`synthesize` 不修改声音配置。
10. 连续语气按章节一次合成，在页边界插入 bookmark，再切成逐页 MP3；每页交付一个 MP3。
11. 页面换页使用真实 MP3 时长加安全余量。PowerPoint 打开、视频导出、自动检查和人工完整观看是不同证据。

## 工作流

1. 读取 `references/input-quality-gate.md`，识别输入 profile 和绑定方式。
2. 选择 `narration_audio`、`static_pptx`、`animated_pptx`、`narrated_pptx` 或 `video`，直接运行 `init`。计划类输入只额外准备一次 SHA 绑定的语义复核。
3. 检查 `page-script.md` 后执行 `approve --stage content`。
4. 需要旁白时运行 `prepare-narration`，逐页检查 `narration_review.md` 中的表达意图、编排依据、最终 rate/pitch/pause，以及专业术语的“原词 → 实际读法”。结合上下文为缩写、材料牌号、工程标准号建立发音词典；未确认项保留为警告，不让 TTS 猜读后直接批量生产。必要时修改导演稿或声音词典并刷新 manifest，推荐先合成术语试听，随后批准旁白。
5. `narration_audio` 合成逐页 MP3、生成真实时间轴、执行 audio QA 后停止。
6. 需要演示时，适配模板并制作 1–4 张代表性 SVG；批准视觉后批量生成静态或动画 PPTX。
7. `narrated_pptx` 先要求当前动画基线的 static QA PASS，再将逐页音频嵌入并执行 standard QA；standard 指纹绑定该 static 报告，不能跳过真实 OOXML 动画检查。`video` 再由 Windows PowerPoint 导出 MP4，并在人工完整观看后执行 release QA。

详细分支和变更影响读取 `references/workflow.md`；字段与审批读取 `references/project-contract.md`。

## 命令模式

已整理逐页演讲稿只生成音频：

```bash
bash skills/build-narrated-presentation/scripts/run.sh init \
  --output /path/to/project --name "项目名称" \
  --deliverable narration_audio \
  --input-document 演讲稿.md
bash skills/build-narrated-presentation/scripts/run.sh approve \
  --project /path/to/project --stage content --approved-by "reviewer"
bash skills/build-narrated-presentation/scripts/run.sh prepare-narration \
  --project /path/to/project
bash skills/build-narrated-presentation/scripts/run.sh configure-voice \
  --project /path/to/project --voice zh-CN-XiaochenNeural --rate=-5% \
  --pronunciation-file /path/to/pronunciation-glossary.json \
  --replace-pronunciations
bash skills/build-narrated-presentation/scripts/run.sh voice-audition \
  --project /path/to/project \
  --voices zh-CN-XiaochenNeural,zh-CN-XiaoxiaoNeural
bash skills/build-narrated-presentation/scripts/run.sh approve \
  --project /path/to/project --stage narration --approved-by "reviewer"
bash skills/build-narrated-presentation/scripts/run.sh synthesize \
  --project /path/to/project
bash skills/build-narrated-presentation/scripts/run.sh audio-timeline \
  --manifest /path/to/project/video/animation_manifest.json \
  --audio-dir /path/to/project/video/audio \
  --output /path/to/project/video/audio_timeline.json
bash skills/build-narrated-presentation/scripts/run.sh qa \
  --project /path/to/project --level audio
```

计划类输入先准备复核和显式逐页稿，再初始化：

```bash
bash skills/build-narrated-presentation/scripts/run.sh prepare-input-review \
  --document source.md --output input-review.json
bash skills/build-narrated-presentation/scripts/run.sh init \
  --output /path/to/project --name "项目名称" \
  --deliverable narrated_pptx \
  --input-document source.md --input-review input-review.json \
  --page-script-source prepared-page-script.md
```

门禁契约升级而源稿字节未变时，显式刷新证据，不重建视觉或音频：

```bash
bash skills/build-narrated-presentation/scripts/run.sh refresh-input-gate \
  --project /path/to/project --input-profile auto
bash skills/build-narrated-presentation/scripts/run.sh approve \
  --project /path/to/project --stage content --approved-by "reviewer"
```

刷新默认重新自动识别项目内源稿，可修正旧项目错误 profile；只有计划或渲染型 profile 才传新版 `--input-review`。若刷新后证据字节未变，现有 content 审批保持 current。

## 资源导航

- 输入身份、一次门禁和内容保真：`references/input-quality-gate.md`
- 交付分支、空状态和增量重建：`references/workflow.md`
- schema v2、目录、绑定和审批：`references/project-contract.md`
- 模板、SVG 和动画：`references/visual-and-animation.md`
- 原创技术信息图：`references/technical-infographic-style.md`
- 导演稿、声音、bookmark 和逐页 MP3：`references/narration-and-audio.md`
- OOXML、媒体和 PowerPoint 导出：`references/pptx-and-video.md`
- QA 与完成定义：`references/validation.md`

## 输出规则

- 不覆盖用户输入、模板原件、原始 SVG 或既有交付物。
- 只生成当前 `deliverable` 所需链路；`narration_audio` 不生成 PPTX 或视频。
- 未经用户明确确认，不使用 `--allow-substantial-rewrite`。
- 不把 `direction` 文案当成可听语气；只有进入最终 SSML 的 rate、pitch、pause 或受支持的 voice style 才算实际编排。
- 不把混合字母数字一律逐字符读。缩写可用 `say_as: characters`；材料成分牌号用经专业语境确认的中文 `alias`；纯数字牌号、序号型牌号和标准号分别按行业口播习惯处理。
- 第三方图片只用于风格研究，不进入交付物。
- 没有对应摘要的导出证据或人工完整观看证据时，不声称视频已经完成。
