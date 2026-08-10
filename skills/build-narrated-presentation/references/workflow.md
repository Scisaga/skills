# 制作流程

## 目录

- [交付目标先行](#交付目标先行)
- [标准入口](#标准入口)
- [内容绑定与审批](#内容绑定与审批)
- [空派生状态](#空派生状态)
- [逐页音频独立链](#逐页音频独立链)
- [演示视觉链](#演示视觉链)
- [单页 SVG 设计改稿](#单页-svg-设计改稿)
- [变更影响](#变更影响)
- [增量重建](#增量重建)

## 交付目标先行

`project.json.deliverable` 决定生产链和停止点：

| 目标 | 必做链路 | 不进入 |
|---|---|---|
| `narration_audio` | 内容、导演稿、声音、逐页 MP3、audio QA | 模板、SVG、PPTX、PowerPoint、视频 |
| `static_pptx` | 内容、模板、SVG、静态装配、static QA | 动画和声音 |
| `animated_pptx` | 静态链路、SVG 分层、首秒动画 | 声音和视频 |
| `narrated_pptx` | 视觉链、旁白、逐页音频、自动换页、standard QA | 视频导出 |
| `video` | 旁白 PPTX、standard QA、PowerPoint 导出、适用时执行 Office 2019 像素色阶重编码 | MP4 画面检查、ffprobe、抽帧、人工观看、release QA |

不要先初始化最高层级再“暂时只做音频”。只需要逐页 MP3 时明确选择 `narration_audio`，让模板、SVG、PPTX 等实际文件依赖和视觉 QA 退出生产链；同一 schema 的兼容字段仍保留，但不读取对应视觉产物。

## 标准入口

```text
确认 deliverable
→ 识别输入 profile 与 page-script 绑定方式
→ init 内执行一次完整门禁
→ 批准内容
→ 按 deliverable 分流
```

已经逐页整理的 `page-narration` 直接进入 `init`，不预先生成摘要或语义复核。计划与渲染型输入先准备一次 SHA 绑定的语义复核，并显式传入整理好的 `--page-script-source`；不再额外串行执行 `inspect-input` 和 `validate-input`。

初始化固定保留：

- `inputs/source.md`：用户指定的原始输入副本；
- `page-script.md`：实际用于内容、导演稿和旁白的逐页正文；
- `input-gate.json` 与 `input-gate.md`：本次入口门禁结果；
- 可选 `input-review.json`：只有需要语义复核的 profile 才存在。

## 内容绑定与审批

### Identity

`page-narration` 未指定其他逐页稿时，`inputs/source.md` 与 `page-script.md` 字节一致，记录 `content.binding_mode: identity`。这是默认且优先的路径。

不要执行下列转换：

```text
完整逐页演讲稿 → 项目摘要 → 页面映射表 → page-script.md
```

正确路径是：

```text
完整逐页演讲稿 ──原样复制──> page-script.md
```

### Adapted

计划类、执行类或渲染型输入必须显式提供已经整理好的 `--page-script-source`，记录 `content.binding_mode: adapted`。源稿与逐页稿各自保留，不共用同一个“normalized”文件。

内容审批：

```bash
run.sh approve --project PROJECT \
  --stage content --approved-by REVIEWER
```

审批绑定当前源稿、逐页稿及逐页契约审计。对于 `page-narration`，只要逐页稿不再与源稿逐字节一致，就必须由用户明确授权并增加：

```bash
run.sh approve --project PROJECT \
  --stage content --approved-by REVIEWER \
  --allow-substantial-rewrite
```

不得把该选项当成自动修复或默认容错。

identity 项目初始化后，只要 `page-script.md` 发生任何非字节一致修改，就不能继续记录为 identity。显式授权后的同一次 content 审批命令会切换为 adapted、写入新审计并记录审批；授权与当前源稿和逐页稿 SHA 一起持久化，相同字节的重批不重复索权，逐页稿再次变化才重新要求授权。未授权修改直接阻断。若命令中途因文件系统错误失败，先运行 `validate --stage content` 检查部分状态，再重试审批。

## 空派生状态

`init` 只建立项目和内容绑定，不伪造一页示例状态。初始化后：

- `video/narration_director.json.pages` 为空；
- `video/animation_manifest.json.slides` 为空，`slide_count` 为 0；
- 视觉项目的 `video/svg_layer_plan.json.pages` 为空；
- `video/build_state.json` 的 `inputs`、`artifacts`、`approvals` 和 `qa` 为空；
- PowerPoint 证据为 `null`。

这些文件只是 schema 容器。空状态不得被识别成“第 1 页已准备”“导演稿已完成”或“审批通过”。

`narration_audio` 不创建 `assets/`、`svg_layer_plan.json` 或 `video/layers/`，也不读取模板和 SVG。

需要旁白的交付在内容审批后，使用确定性入口生成旁白派生状态：

```bash
run.sh prepare-narration --project PROJECT
```

该命令从 `page-script.md` 建立正文保真、带第一版可执行语气参数的导演稿、旁白 manifest 和 `narration_review.md`。已有非空导演稿时默认阻断；只有确认允许重新生成时使用 `--force`。

导演稿只负责表演参数和章节组织；其中的 TTS 文本由逐页稿确定性派生。先逐页核对表达意图、编排依据和最终 rate/pitch/pause，必要时修改 director 并运行 `manifest` 刷新审阅稿。旁白审批既比较正文保真，也执行轻量 performance audit；任何摘要、删句、统一语气模板或没有进入 SSML 的伪编排都会阻断。

视觉页、SVG 和动画计划仍由视觉制作流程显式填充，不从空模板猜测完成状态。

## 逐页音频独立链

`narration_audio` 的生产主链：

```text
identity/adapted 内容绑定
→ content 审批
→ prepare-narration
→ 逐页语气审阅与修正，并刷新 manifest
→ 可选 configure-voice，并自动刷新 manifest 与审阅稿
→ 推荐候选音色试听与人工确认
→ narration 审批
→ 按章节连续合成并切成逐页 MP3
→ 读取真实 MP3 时长
→ audio QA
→ 停止
```

命令骨架：

```bash
run.sh prepare-narration --project PROJECT
run.sh configure-voice --project PROJECT \
  --voice zh-CN-XiaochenNeural --rate=-5% --pitch=+0st
run.sh voice-audition --project PROJECT \
  --voices zh-CN-XiaochenNeural,zh-CN-XiaoxiaoNeural
run.sh approve --project PROJECT \
  --stage narration --approved-by REVIEWER
run.sh synthesize --project PROJECT
run.sh audio-timeline \
  --manifest PROJECT/video/animation_manifest.json \
  --audio-dir PROJECT/video/audio \
  --output PROJECT/video/audio_timeline.json
run.sh qa --project PROJECT --level audio
```

已有声音配置合适时可省略 `configure-voice`。该命令更新 `voice_profile.json`；导演稿非空时同步刷新 manifest 与审阅稿，但不合成音频。`voice-audition` 是强烈推荐的人工质量步骤，目前不写入 `build_state.json`，也不是脚本可自动证明的前置状态；当前声音与导演稿的 narration 审批才是生产命令实际执行的正式边界。`synthesize` 不接受临时声音覆盖。

## 演示视觉链

### 静态与动画

内容审批后创建或适配 `template.pptx`，建议从复杂流程、高密度图表、截图或架构页中选择 1–4 页作为代表性 SVG：

```bash
run.sh approve --project PROJECT \
  --stage visual --pages 3,7,10 --approved-by REVIEWER
```

样稿通过后批量制作剩余 SVG 和静态 PPTX。`static_pptx` 在 static QA 后停止；`animated_pptx` 再制作首秒动画。针对动画基线的 static QA 会回读每页 OOXML，确认非空 timing tree、每个 manifest beat 对应稳定对象名、实际 entrance `animEffect`、支持的 fade/wipe、真实 shape target 和有限正时长；只有 sidecar JSON 而 PPTX 没有动画节点不能 PASS。实际播放节奏和渲染效果仍由 PowerPoint 实机检查确认。

### 旁白 PPTX 与视频

`narrated_pptx` 和 `video` 同时需要视觉链和逐页音频链。视觉与旁白审批可以独立准备，但装配自动旁白 PPTX 时两者都必须有效。旁白 PPTX 从动画基线生成独立文件，不覆盖静态或动画基线；进入 standard QA 前，动画基线必须已有当前 static QA PASS，standard cache 同时绑定其 fingerprint、状态记录和实际报告 SHA。

`narrated_pptx` 在 standard QA 后停止。`video` 由 Windows PowerPoint 使用现有媒体和时间轴导出 MP4；Office 2019 自动把误用的 full-range 像素映射为标准 limited range 并重新编码 H.264，Office 2021/2022 或更新版本跳过。兼容决策写入导出报告后直接交付，不做视频画面检查、ffprobe、抽帧、人工观看或 release QA。

## 单页 SVG 设计改稿

用户明确只要求调整某一页或少数指定页的 SVG 设计，且没有要求同步 PPTX、动画、旁白或视频时，把它作为独立的局部编辑任务，不进入标准生产入口：

```text
确认目标页和 source_svg
→ 读取该页内容、模板安全区与当前视觉规范
→ 只修改目标 SVG
→ 执行单页 SVG 检查并目视全尺寸与缩略图
→ 交付目标 SVG 后停止
```

局部范围内：

- 保留 `page-script.md`、模板、manifest、图层计划、其他页面、音频、PPTX、视频和 `build_state.json`；只有目标页确实使用的页内资产不可避免时才一起修改，并在交付摘要中列明；
- 不运行 `init`、输入门禁、`approve`、全项目 `validate`、任何等级的 `qa`、PPTX 装配或 PowerPoint 导出；
- 按 `visual-and-animation.md` 检查 XML、`viewBox`、外部引用、安全区、溢出、全尺寸渲染和 400×225 缩略图；这属于单页设计检查，不写入正式 QA PASS；
- 明确报告只更新了哪些 SVG，以及 PPTX、动画和视频没有同步。目标 SVG 变化后，任何依赖旧 SVG 指纹的 visual 审批、PPTX provenance 或 static QA 都不能继续声称 current。

只有用户明确要求把改稿同步到演示交付物时，才扩展到目标页的分层/动画和必要的 PPTX 装配，再按实际更新的交付层级执行相应 QA；内容和音频字节未变时不得重做内容门禁、旁白或 audio QA。若现有装配器只能全稿重建，应先说明这一技术边界，不能把“同步单页”静默扩张成整套内容、音频和视频生产。

## 变更影响

| 变化 | 失效与重建 | 保留 |
|---|---|---|
| `inputs/source.md` | 输入门禁、内容审批及所有下游 | 无 |
| `page-script.md` | 内容、视觉、旁白审批及下游 | 原始源稿 |
| 门禁/复核/绑定证据或输入契约版本 | content acceptance 失效，修复后重新 content 审批 | 内容字节未变时保留视觉、导演稿、音频和 PPTX |
| 模板、安全区或代表性 SVG | 视觉审批、相关 PPTX 与视频 | 内容、导演稿、音频 |
| 其他某页 SVG 或动画 | 仅设计改稿时只检查目标页；同步交付物时才失效并重建受影响视觉、PPTX 与视频 | 内容、音频、其他页面 |
| 导演稿文字、章节或局部节奏 | 旁白审批、受影响章节音频及下游 | 内容、视觉 |
| 音色、全局声音参数或词典 | 旁白审批、受影响音频及下游 | 内容、视觉 |
| 输出分辨率 | PowerPoint 重新导出 | PPTX、音频、视觉内容 |

章节是连续合成和缓存单位。修改章节中任意一页时，重建完整章节；逐页 MP3 仍是最终交付和 PowerPoint 嵌入单位。

缓存命中前同时核对章节摘要、最终 SSML、bookmark 元数据、页面集合和实际 MP3 SHA-256。文件损坏或元数据缺失会重建该章，不等到 QA 才发现。

## 增量重建

声音变化使用独立入口；命令更新配置和已有旁白审阅派生物后停止，不请求 TTS：

```bash
run.sh configure-voice --project PROJECT --voice VOICE
```

这一步是纯配置操作，不读取或要求动画 PPTX 基线；只有真正合成并替换演示音频时才检查视觉基线。

建议重新试听，并必须重新批准旁白后再运行：

```bash
run.sh rebuild --project PROJECT --scope audio --qa audio
```

`narration_audio` 只能停在 audio QA。`narrated_pptx` 可继续到 standard QA。`video --qa audio` 在重建旁白 PPTX 后停止，不导出视频；`video --qa standard` 在 standard QA 后可继续 PowerPoint 导出、执行适用的 Office 2019 像素色阶重编码并直接停止，`--skip-export` 则显式停在导出前。导出后不运行视频画面检查或 release QA。

`video/build_state.json` 只记录已经发生的审批、产物、QA 和 PowerPoint 证据。不得预填未来状态，不得手工把失败或空状态改为通过。
