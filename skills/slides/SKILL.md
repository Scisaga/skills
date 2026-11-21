---
name: slides
description: 从逐页演讲稿、执行方案或渲染型 Markdown 制作离线 HTML 演示、PDF、逐页图片、MP4 或逐页旁白 MP3。适用于技术图示、架构流程、路线图、分组动画、旁白时间点、字体与模板复用、重配声音、单页 SVG 改稿及旧演示项目迁移。
---

# Slides

## 概述

在 `project.json` schema v2 选择当前需要的交付。`narration_audio` 只生产逐页 MP3。`static_html`、`animated_html`、`narrated_html` 交付可双击打开的 `index.html` 和离线 ZIP，可进一步导出 PDF、图片或 MP4。

单页 SVG 改稿按 [视觉与动画](references/visual-and-animation.md) 的局部流程处理。首次打开旧演示项目时，使用 `migrate-html` 在新目录重建项目，再检查模板和迁移报告。 [项目契约](references/project-contract.md)

## 工作流

1. 识别输入 profile。已整理的 `## 第 N 页｜标题` 或 `## PAGE N/T｜标题` 默认原样绑定为 `page-script.md`。计划和渲染型输入准备一次 SHA 绑定的复核及单独的逐页口述稿，再执行 `init`。逐页稿需改写时，先取得对当前稿件的授权，再以 `adapted` 绑定。 [输入门禁](references/input-quality-gate.md)
2. 确认内容并执行 `approve --stage content`，再制作导演稿、SVG 或音频。未来路线和技术愿景按事实状态选择表述。 [技术愿景叙事](references/vision-and-roadmap-narrative.md)
3. 配音走 `prepare-narration`、`configure-voice`、`approve --stage narration`、`synthesize`、`audio-timeline`、`qa --level audio`。默认 Qwen3 自托管优先，整套回退 Azure。核对实际语速、停顿、术语读法和最终 `±0.1st` 音高约束。使用真实 PCM 或 bookmark 边界切页，换页依据实际 MP3 时长。 [旁白与音频](references/narration-and-audio.md) · [Qwen3 配置](references/qwen3-tts-openai.md)
4. HTML 采用 CSS 模板和逐页 SVG。先完成代表页并批准视觉，再补齐全稿。使用思源黑体、思源宋体、Inter、JetBrains Mono 或可分发的项目字体。动画用 SVG 分组和 `beats[]`；`start_ms` 可指定本页旁白中的触发时间。 [视觉与动画](references/visual-and-animation.md) · [技术图示参考](references/visual-reference-cases.md)
5. 执行 `assemble-html` 和 `qa --level static`。带旁白的网页同时要求当前 audio 和 standard 通过。按需执行 `export-pages` 或 `export-video`，以导出脚本的返回值和当前报告为准。 [HTML 与导出](references/html-and-video.md) · [验收](references/validation.md)

## 命令模式

```bash
bash skills/slides/scripts/run.sh bootstrap --stage static
```

将实际命令中的项目路径替换为交付目录。

```bash
bash skills/slides/scripts/run.sh init \
  --output /path/to/project --name "项目名称" \
  --deliverable animated_html --input-document 演讲稿.md
bash skills/slides/scripts/run.sh approve \
  --project /path/to/project --stage content --approved-by reviewer
bash skills/slides/scripts/run.sh approve \
  --project /path/to/project --stage visual --pages 1 --approved-by reviewer
bash skills/slides/scripts/run.sh assemble-html --project /path/to/project
bash skills/slides/scripts/run.sh qa --project /path/to/project --level static
```

Windows 使用 `scripts/run.ps1` 和相同的子命令。按交付选择 bootstrap 阶段。更多命令见 [制作流程](references/workflow.md)。

## 输出规则

- 保留原始输入和工作模板的来源。内容审批、旁白审批和视觉审批绑定实际输入，在对应生产命令检查。
- `narration_audio` 在 audio QA 结束。局部 SVG 改稿只验收目标页。
- 发布网页时交付整个目录或 ZIP。导出前检查当前网页与验收证据。
- 技术案例图仅用于风格和表达参考，交付图示采用项目自身材料。
