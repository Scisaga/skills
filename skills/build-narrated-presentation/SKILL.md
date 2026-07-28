---
name: build-narrated-presentation
description: 从产品计划、执行方案等 Markdown 文档或既有 SVG 演示内容出发，先执行输入质量门禁，再制作静态 PPTX、带进入动画和逐页连续旁白的自动播放 PPTX，并通过 Windows PowerPoint 导出 MP4。适用于用户要求“把文档生成 PPT/PPTX”“验证演示输入稿”“给 PPT 加动画”“制作自动旁白演示”“把 SVG 做成路演视频”“按音频自动换页”或“检查 PPTX 动画、媒体嵌入和视频导出”的场景，尤其适合需要事实边界、逐页叙事、SVG 保真、首秒动画、真实音频时间轴和 OOXML 验收的产品计划书、课程与路演材料。
---

# Build Narrated Presentation

## 概述

先把输入文档验证为可靠的叙事与事实来源，再把视觉设计、动画、旁白和页面时长分开管理，装配成可靠的 PowerPoint 播放容器。保持通过门禁的文档为内容来源、SVG 为视觉事实来源；让动画在首秒完成；每页只使用一段连续旁白；让真实音频时长决定自动换页；最终由 Windows PowerPoint 使用既有计时和旁白导出 MP4。

## 不变量

1. 有输入文档时，必须先通过自动预检和绑定文档 SHA-256 的语义复核；未通过时只返工文档。
2. 先完成可直接交付的静态 SVG，再拆动画层。
3. 每层保持与页面一致的完整透明画布，默认 `1600×900`。
4. 每页最多六个动画组，只使用 `fade` 和方向性 `wipe` 进入动画。
5. 视觉、旁白、换页使用独立时钟；动画不得跟随旁白逐句排队。
6. 每页只生成一个连续 MP3 和一个 SSML `<p>`。
7. 页面时长使用 `真实 MP3 时长 + 150ms`，页间淡化默认 `250ms`。
8. SVG、截图和 MP3 必须内嵌 PPTX，不使用外部绝对路径。
9. 自动检查通过后仍须在目标版本的 Windows PowerPoint 中完整放映验收。

## 工作流

1. 确认输入类型并读取 `references/input-quality-gate.md`：
   - 产品计划、执行方案等 Markdown：先运行自动预检，完整阅读后填写语义复核；未通过则停止并返工原文档。
   - 已逐页编排的 Markdown：使用 `presentation-source` profile 检查页码、SVG 和 speaker notes。
   - 没有输入文档：先创建并返工一份可审查的 Markdown 输入稿，不初始化演示项目。
   - 已有 SVG 或项目目录：先读取 `project.json`、README、frontmatter 和邻近 Markdown，发现上游文档时仍须执行门禁。
2. 判断交付层级：
   - 只需静态 PPTX：完成静态 SVG、PNG fallback、SVG 嵌入和回读检查。
   - 需要动画 PPTX：再建立语义分层、首秒动画和自动换页。
   - 需要旁白视频：再建立旁白导演稿、逐页 MP3、真实音频时间轴并导出 MP4。
3. 读取 `references/workflow.md` 和 `references/project-contract.md`，确认输入、唯一事实来源、目录和构建模式。
4. 门禁通过后运行 `init --input-document ... --input-review ...` 创建通用模板；已有项目保留现有源文件和命名，不覆盖静态 PPTX。
5. 完成并检查所有静态 SVG。处理分层与动画时读取 `references/visual-and-animation.md`。
6. 分别维护视觉 manifest 与旁白导演稿，再生成合并后的动画 manifest。不要直接编辑 manifest 中派生的 `narration`。
7. 先选普通图文页、截图复杂页、流程或架构页做样板，不要直接批量生成全部页面。
8. 合成逐页旁白、读取 MP3 真实时长并生成首秒动画时间轴。处理脚本和 TTS 时读取 `references/narration-and-audio.md`。
9. 使用项目内经验证的装配器生成静态或动画 PPTX。需要实现或审查 OOXML 时读取 `references/pptx-and-video.md`。
10. 运行本 skill 的输入门禁、项目契约校验、项目装配器的 OOXML 校验和离线测试。
11. 在 Windows PowerPoint 中完整播放，使用“录制的计时和旁白”导出视频，并按 `references/validation.md` 验收。

## 命令模式

以下命令从本 skill 所在仓库根目录执行：

```bash
bash skills/build-narrated-presentation/scripts/bootstrap.sh
bash skills/build-narrated-presentation/scripts/run.sh doctor
bash skills/build-narrated-presentation/scripts/run.sh inspect-input \
  --document /path/to/source.md \
  --markdown-output /path/to/input-preflight.md
bash skills/build-narrated-presentation/scripts/run.sh prepare-input-review \
  --document /path/to/source.md \
  --output /path/to/input-review.json
bash skills/build-narrated-presentation/scripts/run.sh validate-input \
  --document /path/to/source.md \
  --review /path/to/input-review.json \
  --json-output /path/to/input-gate.json \
  --markdown-output /path/to/input-gate.md
bash skills/build-narrated-presentation/scripts/run.sh init \
  --output /path/to/presentation-project \
  --name "项目名称" \
  --input-document /path/to/source.md \
  --input-review /path/to/input-review.json
bash skills/build-narrated-presentation/scripts/run.sh manifest \
  --visual /path/to/project/video/animation_manifest.json \
  --director /path/to/project/video/narration_director.json \
  --output /path/to/project/video/animation_manifest.json \
  --review /path/to/project/video/narration_review.md
bash skills/build-narrated-presentation/scripts/run.sh timing \
  --manifest /path/to/project/video/animation_manifest.json \
  --output /path/to/project/video/fast_animation_timing.json
bash skills/build-narrated-presentation/scripts/run.sh audio-timeline \
  --manifest /path/to/project/video/animation_manifest.json \
  --audio-dir /path/to/project/video/audio \
  --output /path/to/project/video/audio_timeline.json
bash skills/build-narrated-presentation/scripts/run.sh validate \
  --project /path/to/presentation-project \
  --strict
```

PowerShell 使用：

```powershell
powershell -ExecutionPolicy Bypass -File .\skills\build-narrated-presentation\scripts\bootstrap.ps1
powershell -ExecutionPolicy Bypass -File .\skills\build-narrated-presentation\scripts\run.ps1 inspect-input --document C:\work\source.md --markdown-output C:\work\input-preflight.md
powershell -ExecutionPolicy Bypass -File .\skills\build-narrated-presentation\scripts\run.ps1 init --output C:\work\presentation --name "项目名称" --input-document C:\work\source.md --input-review C:\work\input-review.json
powershell -ExecutionPolicy Bypass -File .\skills\build-narrated-presentation\scripts\run.ps1 validate --project C:\work\presentation
```

`inspect-input` 只执行确定性预检；智能体必须完整阅读文档并填写 `prepare-input-review` 生成的模板，`validate-input` 才执行完整门禁。`init` 会再次检查文档摘要和复核结论，没有通过门禁的输入就不能创建演示项目。

`init`、`manifest`、`timing` 和 `validate` 固化项目契约与时间轴，不替代项目自己的 SVG 分层器和 PPTX OOXML 装配器。优先复用目标项目已验证的装配器；没有装配器时，按 `references/pptx-and-video.md` 中的接口实现，并以来源基线为参考，不要在运行时下载或执行远程代码。

`init`、`manifest`、`timing` 和非音频部分的 `validate` 只使用 Python 标准库；`audio-timeline` 需要 `mutagen`。`bootstrap` 安装 TTS、SVG fallback 和 PPTX 装配所需的完整生产依赖，`doctor` 也按完整生产环境检查，因此只准备前期契约时出现依赖缺失是预期结果。编辑过程中可使用普通 `validate` 查看警告；准备装配或交付前必须使用 `validate --strict`。

## 资源使用

- 总体流程、增量重建和来源基线：读取 `references/workflow.md`。
- 输入类型、自动预检、语义复核和返工规则：开始制作前读取 `references/input-quality-gate.md`。
- 目录、JSON 契约和版本纪律：读取 `references/project-contract.md`。
- SVG 设计、全画布分层和动画：读取 `references/visual-and-animation.md`。
- 故事、导演稿、SSML、TTS 和真实音频时间轴：读取 `references/narration-and-audio.md`。
- PNG fallback、SVG/音频嵌入、OOXML 时间轴和视频导出：读取 `references/pptx-and-video.md`。
- 自动检查、PowerPoint 实机检查、失败模式和完成定义：交付前读取 `references/validation.md`。
- 新项目模板：由 `scripts/init_project.py` 从 `assets/project-template/` 复制。

## 输出规则

- 不覆盖原始 SVG、静态 PPTX 或用户已有交付物。
- 门禁失败时不生成 SVG、PPTX、动画、旁白或视频，只输出输入文档返工报告。
- 产品事实、页面文案和旁白只来自当前项目，不复制来源项目的业务叙事。
- 中间产物与人工维护源文件分目录保存；旁白导演稿保持唯一。
- 不用 `final2`、`new-new` 等临时后缀表达版本。
- 没有 Windows PowerPoint 实机结果时，不声称视频已完成验收。
- 最终交付至少报告：PPTX 路径、页数、内嵌旁白数、真实预计时长、自动检查结果、PowerPoint 实机结果和 MP4 路径。
