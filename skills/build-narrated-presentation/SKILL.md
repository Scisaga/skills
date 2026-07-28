---
name: build-narrated-presentation
description: 从产品计划、执行方案等 Markdown 文档或既有 SVG 演示内容出发，先执行输入质量门禁，再制作静态 PPTX、带进入动画和章节连续旁白的自动播放 PPTX，并通过 Windows PowerPoint 导出 MP4；也支持音色试听、发音词典、只重建音频、分级验收和缓存跳过。适用于用户要求“把文档生成 PPT/PPTX”“验证演示输入稿”“给 PPT 加动画”“制作自动旁白演示”“让旁白贯穿多页”“更换音色或发音”“只替换 PPT 音频”“把 SVG 做成路演视频”“按音频自动换页”或“检查 PPTX 动画、媒体嵌入和视频导出”的场景。
---

# Build Narrated Presentation

## 概述

先把输入文档验证为可靠的叙事与事实来源，再把视觉设计、动画、旁白内容、声音配置和页面时长分开管理。需要跨页连贯语气时，按章节一次合成，在页边界插入 bookmark，再切成 PowerPoint 可独立播放的逐页 MP3。让真实音频时长决定自动换页，最终由 Windows PowerPoint 使用既有计时和旁白导出 MP4。

## 不变量

1. 有输入文档时，必须先通过自动预检和绑定文档 SHA-256 的语义复核；未通过时只返工文档。
2. 先完成可直接交付的静态 SVG，再拆动画层。
3. 每层保持与页面一致的完整透明画布，默认 `1600×900`。
4. 每页最多六个动画组，只使用 `fade` 和方向性 `wipe` 进入动画。
5. 视觉、旁白、换页使用独立时钟；动画不得跟随旁白逐句排队。
6. PowerPoint 内每页恰好一个 MP3；同一章节可以贯穿连续多页，并按 bookmark 从一次连续合成结果切分。
7. 页面时长使用 `真实 MP3 时长 + 150ms`，页间淡化默认 `250ms`。
8. SVG、截图和 MP3 必须内嵌 PPTX，不使用外部绝对路径。
9. 声音配置只保存在 `voice_profile.json`；更改音色、全局语速、音高或发音规则不使输入文档语义复核失效。
10. 按变更影响选择最小重建链；已通过且依赖未变的 QA 不重复运行。
11. PowerPoint 打开、视频导出、MP4 自动检查和人工完整观看是四种不同证据，不得互相替代。

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
6. 分别维护视觉 manifest、旁白导演稿和声音配置，再生成合并后的动画 manifest。不要直接编辑 manifest 中派生的 `narration` 或 `voice`。
7. 先选普通图文页、截图复杂页、流程或架构页做样板，不要直接批量生成全部页面。
8. 批量合成前先生成 10–15 秒候选音色样音并人工试听；确认音色、品牌词、缩写和数字读法后再生产。
9. 在导演稿中为连续页面设置相同 `chapter`，按章节连续合成并切成逐页 MP3；读取真实时长并生成首秒动画时间轴。处理脚本和 TTS 时读取 `references/narration-and-audio.md`。
10. 使用项目内经验证的装配器生成静态或动画 PPTX。首次装配需要项目适配器；后续可只替换内嵌音频与换页时间。需要实现或审查 OOXML 时读取 `references/pptx-and-video.md`。
11. 按 `audio`、`standard`、`release` 选择验收等级；先检查缓存，依赖和工具未变化时直接复用通过结果。
12. 在 Windows PowerPoint 中导出视频；自动导出完成后仍须由人工完整观看当前 MP4，再记录 release 证据。

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
  --voice-profile /path/to/project/video/voice_profile.json \
  --output /path/to/project/video/animation_manifest.json \
  --review /path/to/project/video/narration_review.md
bash skills/build-narrated-presentation/scripts/run.sh voice-audition \
  --project /path/to/project \
  --voices zh-CN-XiaochenNeural,zh-CN-XiaoxiaoNeural
bash skills/build-narrated-presentation/scripts/run.sh synthesize \
  --project /path/to/project
bash skills/build-narrated-presentation/scripts/run.sh timing \
  --manifest /path/to/project/video/animation_manifest.json \
  --output /path/to/project/video/fast_animation_timing.json
bash skills/build-narrated-presentation/scripts/run.sh audio-timeline \
  --manifest /path/to/project/video/animation_manifest.json \
  --audio-dir /path/to/project/video/audio \
  --output /path/to/project/video/audio_timeline.json
bash skills/build-narrated-presentation/scripts/run.sh assemble-pptx \
  --project /path/to/project \
  --adapter "python /path/to/project/build_deck.py"
bash skills/build-narrated-presentation/scripts/run.sh replace-audio \
  --project /path/to/project
bash skills/build-narrated-presentation/scripts/run.sh export-video \
  --project /path/to/project
bash skills/build-narrated-presentation/scripts/run.sh export-pages \
  --project /path/to/project \
  --pages 8,9,14 \
  --format pdf \
  --output /path/to/selected-pages.pdf
bash skills/build-narrated-presentation/scripts/run.sh qa \
  --project /path/to/project \
  --level standard
bash skills/build-narrated-presentation/scripts/run.sh rebuild \
  --project /path/to/project \
  --scope audio \
  --voice zh-CN-XiaochenNeural \
  --qa standard
bash skills/build-narrated-presentation/scripts/run.sh validate \
  --project /path/to/presentation-project \
  --strict
```

PowerShell 使用：

```powershell
powershell -ExecutionPolicy Bypass -File .\skills\build-narrated-presentation\scripts\bootstrap.ps1
powershell -ExecutionPolicy Bypass -File .\skills\build-narrated-presentation\scripts\run.ps1 inspect-input --document C:\work\source.md --markdown-output C:\work\input-preflight.md
powershell -ExecutionPolicy Bypass -File .\skills\build-narrated-presentation\scripts\run.ps1 init --output C:\work\presentation --name "项目名称" --input-document C:\work\source.md --input-review C:\work\input-review.json
powershell -ExecutionPolicy Bypass -File .\skills\build-narrated-presentation\scripts\run.ps1 rebuild --project C:\work\presentation --scope audio --voice zh-CN-XiaochenNeural --qa standard
powershell -ExecutionPolicy Bypass -File .\skills\build-narrated-presentation\scripts\run.ps1 qa --project C:\work\presentation --level release --human-confirmed --confirmed-by "reviewer"
```

`inspect-input` 只执行确定性预检；智能体必须完整阅读文档并填写 `prepare-input-review` 生成的模板，`validate-input` 才执行完整门禁。`init` 会再次检查文档摘要和复核结论，没有通过门禁的输入就不能创建演示项目。

`rebuild --scope audio` 的固定链路是“合成与验证音频 → 更新真实时长 → 替换 PPTX 内嵌音频与换页时间 → 标准 QA → PowerPoint 导出”。它要求已有可信构建基线；若输入文档、旁白文字、章节映射、SVG 或动画发生变化则阻断。只有音色、全局语速、音高或发音规则变化时，不重跑输入门禁和视觉验收。

`qa --level audio` 检查逐页 MP3、真实时长和章节切分；`standard` 再检查 PPTX 媒体嵌入、自动播放和自动换页；`release` 再执行完整项目、PowerPoint 导出证据和 MP4 检查。人工完整观看后才可使用 `--human-confirmed`，该确认与当前 MP4 的 SHA-256 绑定。

`init`、`manifest`、`timing` 和 `validate` 固化项目契约与时间轴。`assemble-pptx` 首次生成视觉 PPTX 时要求 `--adapter` 或 `project.production.assemble_command`；已有 PPTX 时只更新音频和换页时间。优先复用目标项目已验证的装配器；没有装配器时，按 `references/pptx-and-video.md` 中的接口实现，不要在运行时下载或执行远程代码。

`init`、`manifest`、`timing` 和非音频部分的 `validate` 只使用 Python 标准库；音频生产与验收需要 `mutagen`、`lameenc` 和 Azure Speech SDK，PPTX 局部替换需要 `lxml`。`bootstrap` 安装完整依赖。编辑过程中可使用普通 `validate` 查看警告；准备装配或交付前必须使用 `validate --strict`。

## 资源使用

- 总体流程、变更影响分析、增量重建和来源基线：读取 `references/workflow.md`。
- 输入类型、自动预检、语义复核和返工规则：开始制作前读取 `references/input-quality-gate.md`。
- 目录、JSON 契约和版本纪律：读取 `references/project-contract.md`。
- SVG 设计、全画布分层和动画：读取 `references/visual-and-animation.md`。
- 故事、声音配置、试听、发音词典、章节 bookmark、TTS 和真实音频时间轴：读取 `references/narration-and-audio.md`。
- PNG fallback、SVG/音频嵌入、OOXML 时间轴和视频导出：读取 `references/pptx-and-video.md`。
- QA 分级、缓存、PowerPoint 证据、人工验收和完成定义：交付前读取 `references/validation.md`。
- 新项目模板：由 `scripts/init_project.py` 从 `assets/project-template/` 复制。

## 输出规则

- 不覆盖原始 SVG、静态 PPTX 或用户已有交付物。
- 门禁失败时不生成 SVG、PPTX、动画、旁白或视频，只输出输入文档返工报告。
- 产品事实、页面文案和旁白只来自当前项目，不复制来源项目的业务叙事。
- 中间产物与人工维护源文件分目录保存；旁白导演稿保持唯一。
- 不把音色、音高或发音词典写回输入文档或旁白内容源。
- 不用 `final2`、`new-new` 等临时后缀表达版本。
- 没有与当前文件摘要绑定的 PowerPoint 导出证据时，不声称视频已导出；没有人工完整观看证据时，不声称 release 验收通过。
- 最终交付至少报告：PPTX 路径、页数、内嵌旁白数、真实预计时长、自动检查结果、PowerPoint 实机结果和 MP4 路径。
