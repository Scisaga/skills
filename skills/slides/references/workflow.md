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

`project.json.deliverable` 决定本次生产链。

| 目标 | 需要的制作与验收 |
|---|---|
| `narration_audio` | 内容、旁白、逐页 MP3 与 audio QA |
| `static_html` | CSS、SVG、HTML 组装与 static QA |
| `animated_html` | 静态链加 SVG 分组及分组时间点 |
| `narrated_html` | 动画、旁白、实际换页时间、static 与 standard QA |

HTML 项目可另行导出 PDF、图像和 MP4。只要逐页 MP3 时直接初始化 `narration_audio`。

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
→ 优先 Qwen3 章节任务（自然句/短段生成）；不可用时整套回退 Azure 连续合成
→ 按实际 PCM 时间轴或 bookmark 切成逐页 MP3
→ 读取真实 MP3 时长
→ audio QA
→ 停止
```

命令骨架：

```bash
run.sh prepare-narration --project PROJECT
run.sh configure-voice --project PROJECT \
  --provider auto --qwen-voice REGISTERED_VOICE_ID \
  --voice zh-CN-XiaochenNeural --rate=-5% --pitch=+0st
run.sh voice-audition --project PROJECT \
  --provider qwen3-tts-openai
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

准备 `template.css` 和代表页 SVG。确认版式、字体、图示与模板安全区后，运行以下命令。

```bash
bash skills/slides/scripts/run.sh approve --project PROJECT --stage visual \
  --pages 3,7,10 --approved-by REVIEWER
```

补齐全稿 SVG，并在动画项目中为 `beats[]` 设置分组和时间点。旁白项目须有当前音频 QA。依次组装和验收。

```bash
bash skills/slides/scripts/run.sh assemble-html --project PROJECT
bash skills/slides/scripts/run.sh qa --project PROJECT --level static
bash skills/slides/scripts/run.sh qa --project PROJECT --level standard
```

`standard` 适用于带旁白的网页，绑定 static 和 audio 报告。选页或录制按 [HTML 组装和导出](html-and-video.md) 执行。

## 单页 SVG 设计改稿

仅编辑目标页的 `source_svg`，检查对应安全区、引用、全尺寸和缩略图。需要同步正式演示时，依变动范围重新组装和验收。 [单页流程](visual-and-animation.md)

## 变更影响

| 变更 | 重新制作的内容 |
|---|---|
| 源文本或逐页稿 | 内容审批及受影响的派生项 |
| CSS、字体或 SVG | 视觉审批或当前视觉资料、HTML、导出 |
| 动画时点与分层 | HTML 和受影响的导出 |
| 语气或音色 | 受影响章节、逐页 MP3、HTML、MP4 |

视觉改动可复用现有旁白。仅变更声音时先配置并审阅旁白，批准后运行 `rebuild --scope audio --qa standard`。纯音频项目使用 `--qa audio`。合成按章节检查实际 MP3 和旁白证据，复用当前缓存。网页与音频已更新后另行执行视频导出。
