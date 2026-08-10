---
name: build-narrated-presentation
description: 从逐页演讲稿、产品计划、执行方案或渲染型 Markdown 制作逐页旁白 MP3、静态 PPTX、动画 PPTX、自动旁白 PPTX 或 PowerPoint 导出的 MP4；保真绑定已整理的逐页正文，并要求其他输入显式提供 adapted page-script，支持可执行语气编排、愿景型路线图与商业蓝图表达、音频独立交付、模板复用、技术信息图、章节连续合成后逐页切分、真实音频时长换页、声音重配和分级验收，自动重编码修正 Office 2019 CreateVideo 的像素色阶，并在 PowerPoint 导出后直接交付而不做视频画面检查。适用于“把演讲稿逐页配音”“只生成每页音频”“把文档生成 PPT/PPTX”“制作未来路线、技术愿景或商业蓝图”“复用现有 PPT 模板”“制作技术架构演示”“给 PPT 加动画或旁白”“更换音色或发音”“只替换 PPT 音频”“导出旁白视频”及“检查媒体嵌入和换页”的场景。
---

# Build Narrated Presentation

## 概述

把事实源、逐页口述稿、视觉、动画、声音和交付物分开管理。`project.json.deliverable` 决定链路：只要逐页 MP3 时选择 `narration_audio`，不得启动模板、SVG 或 PowerPoint；需要演示时才继续视觉和装配。若用户只要求调整指定页 SVG 设计且不要求同步 PPTX、动画或视频，则只编辑并验收目标 SVG，不启动整套生产或 QA 链路。

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
11. 页面换页使用真实 MP3 时长加安全余量。`video` 在当前旁白 PPTX 通过 standard QA 后交给 PowerPoint 导出。默认 `--color-range-fix auto`：识别为 Office 2019 时不能只改 H.264 标签，必须用 FFmpeg 把误用的 full-range 像素映射为标准 limited range 并以 libx264 重新编码，音频 stream copy；识别为 Office 2021/2022 或更新版本时跳过。兼容处理后立即停止，不做 ffprobe、抽帧、播放、人工观看或 release QA。
12. 单页 SVG 设计改稿是局部任务：只读取目标页、模板安全区和所选视觉规范，只修改目标 SVG，并做单页解析、画布、资源引用、全尺寸与缩略图检查。除非用户明确要求更新演示交付物，不运行 `init`、输入门禁、审批、全项目 `validate`、PPTX 装配、音频生产或任何等级的 `qa`，也不顺带修改其他页面和既有交付物。
13. 制作未来路线、技术愿景或商业蓝图页时，主体先表达方向、价值、规模化逻辑和明确主张；事实边界集中放在低干扰脚注、来源说明、验收记录或内部 QA。除法律、安全、财务或重大事实误导风险外，不在标题、标签、正文和旁白中反复堆叠防御性限定。规划能力使用“将、面向、形成、推进、成为”等未来时态，不能写成已经实现；该规则不授权改写 `identity` 绑定的逐页稿。
14. 默认旁白必须保持单一、稳定的说话人身份。全局音高与局部音高相加后的最终 SSML 音高必须位于 `-0.1st` 至 `+0.1st`；旁白审批、合成和 audio QA 都检查最终值并在越界时阻断，不能静默截断。音高只作极轻微修饰，不能单独成为 performance profile 证据，也不能机械交替 `-0.1st/+0.1st` 冒充编排；优先用语速、停顿、断句和重音形成层次。只有显式范围覆盖绑定当前音色的试听确认后才可扩大；当前状态机尚未记录该确认，因此不提供范围覆盖。

## 工作流

1. 先判断是完整生产还是单页 SVG 设计改稿；后者直接读取 `references/visual-and-animation.md` 的局部流程并在单页检查后停止。
2. 完整生产读取 `references/input-quality-gate.md`，识别输入 profile 和绑定方式。
3. 选择 `narration_audio`、`static_pptx`、`animated_pptx`、`narrated_pptx` 或 `video`，直接运行 `init`。计划类输入只额外准备一次 SHA 绑定的语义复核。
4. 检查 `page-script.md` 后执行 `approve --stage content`。若包含未来路线、技术愿景或商业蓝图页，先按 `references/vision-and-roadmap-narrative.md` 检查主叙事、时态与事实边界；`identity` 稿只提出修改建议，得到改写授权并切换为 `adapted` 后才能重写。
5. 需要旁白时运行 `prepare-narration`，逐页检查 `narration_review.md` 中的表达意图、编排依据、全局/局部/最终音高、最终 rate 与 pause，以及专业术语的“原词 → 实际读法”。最终音高必须在 `±0.1st` 内，表现差异以语速、停顿、断句和重音为主。结合上下文为缩写、材料牌号、工程标准号建立发音词典；未确认项保留为警告，不让 TTS 猜读后直接批量生产。必要时修改导演稿或声音词典并刷新 manifest，推荐先合成术语试听，随后批准旁白。
6. `narration_audio` 合成逐页 MP3、生成真实时间轴、执行 audio QA 后停止。
7. 需要演示时，适配模板并制作 1–4 张代表性 SVG；批准视觉后批量生成静态或动画 PPTX。
8. `narrated_pptx` 先要求当前动画基线的 static QA PASS，再将逐页音频嵌入并执行 standard QA；standard 指纹绑定该 static 报告，不能跳过真实 OOXML 动画检查。`video` 再由 Windows PowerPoint 导出 MP4，按版本执行 Office 2019 像素色阶重编码，记录结果后直接交付，不做视频画面检查。

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
- 未来路线、技术愿景与商业蓝图叙事：`references/vision-and-roadmap-narrative.md`
- 交付分支、空状态和增量重建：`references/workflow.md`
- schema v2、目录、绑定和审批：`references/project-contract.md`
- 模板、SVG 和动画：`references/visual-and-animation.md`
- 原创技术信息图：`references/technical-infographic-style.md`
- 导演稿、声音、bookmark 和逐页 MP3：`references/narration-and-audio.md`
- OOXML、媒体和 PowerPoint 导出：`references/pptx-and-video.md`
- QA 与完成定义：`references/validation.md`

## 输出规则

- 不覆盖用户输入、模板原件、未指定修改的原始 SVG 或既有交付物。
- 只生成当前 `deliverable` 所需链路；`narration_audio` 不生成 PPTX 或视频。
- 单页 SVG 设计改稿只交付目标 SVG 和局部检查结论；若未重建 PPTX 或视频，明确说明这些交付物未同步，不把局部检查冒充正式 QA PASS。
- 未经用户明确确认，不使用 `--allow-substantial-rewrite`。
- 不把 `direction` 文案当成可听语气；只有进入最终 SSML 的 rate、pitch、pause 或受支持的 voice style 才算实际编排。
- 不把混合字母数字一律逐字符读。缩写可用 `say_as: characters`；材料成分牌号用经专业语境确认的中文 `alias`；纯数字牌号、序号型牌号和标准号分别按行业口播习惯处理。
- 第三方图片只用于风格研究，不进入交付物。
- PowerPoint 导出命令成功并完成适用的 Office 2019 像素色阶重编码，记录当前 PPTX、最终 MP4、PowerPoint Product ID/Build、兼容决策与导出报告后，即可报告视频导出完成；该确定性重编码不是视频 QA，不要再启动画面检查、抽帧、观看或 release QA。
