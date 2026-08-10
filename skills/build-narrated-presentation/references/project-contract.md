# 项目契约

## 目录

- [单一 Schema](#单一-schema)
- [来源与逐页稿绑定](#来源与逐页稿绑定)
- [交付目标](#交付目标)
- [目录与空状态](#目录与空状态)
- [三个审批](#三个审批)
- [旁白与视觉契约](#旁白与视觉契约)
- [版本纪律](#版本纪律)

## 单一 Schema

`project.json` 只支持 `schema_version: 2`。跨 schema 版本不匹配时直接阻断，不静默升级。早期 v2 项目可能暂缺 `source.gate_report_sha256`、`source.review_sha256`、`binding_mode`、`binding_audit`、`page_count_at_init` 和 `page_script_origin_document`，缺失状态本身不视为已验证。gate/review 摘要必须先由显式 `refresh-input-gate` 补录；`review_sha256` 只对需要语义复核的 profile 必需，`page-narration` 正常为 `null`。随后 content 审批重新审计并补录四个 binding 字段。旧 input gate 的 `contract_version` 也只能通过刷新入口更新。

`page-narration` identity 项目示例：

```json
{
  "schema_version": 2,
  "name": "Project",
  "deliverable": "narration_audio",
  "canvas": {"width": 1600, "height": 900},
  "source": {
    "mode": "document",
    "origin_document": "/absolute/path/to/speech.md",
    "document": "inputs/source.md",
    "document_sha256": "<sha256>",
    "profile": "page-narration",
    "review": null,
    "gate_report": "input-gate.json",
    "gate_report_sha256": "<sha256>",
    "review_sha256": null,
    "page_script_sha256_at_init": "<sha256>"
  },
  "content": {
    "page_script": "page-script.md",
    "binding_mode": "identity",
    "binding_audit": "inputs/page-script-binding.json",
    "page_script_origin_document": "/absolute/path/to/speech.md",
    "page_count_at_init": 28
  },
  "template": {
    "mode": "generated",
    "source": null,
    "working": "template.pptx",
    "safe_area": {"x": 120, "y": 150, "width": 1360, "height": 620}
  },
  "visual": {
    "style_preset": "project-default",
    "theme": "light",
    "density": "presentation"
  },
  "paths": {
    "assets": "assets",
    "video": "video",
    "deliverables": "deliverables",
    "voice_profile": "video/voice_profile.json",
    "build_state": "video/build_state.json"
  },
  "outputs": {
    "static_pptx": "deliverables/Project_静态.pptx",
    "animated_pptx": "deliverables/Project_动画.pptx",
    "narrated_pptx": "deliverables/Project_自动旁白.pptx",
    "video": "deliverables/Project_自动旁白.mp4"
  }
}
```

`narration_audio` 仍使用同一 schema；模板和 PPTX 输出字段保持结构完整，但该交付链不得读取或生成这些视觉产物。

## 来源与逐页稿绑定

### `source`

- `origin_document`：初始化时用户指定文件的绝对路径，只作来源记录；
- `document`：项目内不可隐式替换的 `inputs/source.md`；
- `document_sha256`：项目内源稿摘要；
- `profile`：门禁解析后的实际 profile，不保存 `auto`；
- `review`：`page-narration` 为 `null`，其他 profile 指向 `input-review.json`；
- `gate_report`：指向初始化保存的 `input-gate.json`；
- `gate_report_sha256`：初始化保存的门禁报告摘要；
- `review_sha256`：可选语义复核摘要，`page-narration` 为 `null`；
- `page_script_sha256_at_init`：初始化时逐页稿摘要。

`input-gate.json.document` 必须指向 `inputs/source.md`，且 profile 和 SHA 与 `project.json.source` 一致。删除或修改外部 `origin_document` 不影响已建立的项目；修改项目内源稿会使绑定失效。

### `content`

`page_script` 固定指向 `page-script.md`；`page_script_origin_document` 保存初始化时实际逐页稿来源路径，用于防止相似旧版本被无痕换入。`binding_mode` 只允许：

- `identity`：源稿与逐页稿逐字节一致；
- `adapted`：用户显式提供另一份逐页稿。

`binding_audit` 指向 `inputs/page-script-binding.json`，保存源稿 SHA、逐页稿 SHA、页数和工程数字遗漏；逐页源记录逐页保留率与字符覆盖，计划源记录全文 n-gram 覆盖，供人工审阅 adapted 删改。逐页源的 adapted 授权另记录 `rewrite_authorized` 与 `rewrite_authorized_page_script_sha256`，只对同一源稿、同一逐页稿字节有效。`page_count_at_init` 记录初始化识别页数，不代替当前页数检查。内容审批和项目验证始终重新解析当前 `page-script.md`。

identity 和 adapted 都要求逐页正文使用连续的 `## 第 N 页｜标题` 或 `## PAGE N/T｜标题`。机械契约只证明页码、标题、可朗读字符和渲染标记满足下游条件，不能靠表格/关键词猜测“是否为完整口述”。identity 的字节保真阻止替换原稿；adapted 内容若只是页面映射、项目摘要或核心结论列表，content 审批必须人工拒绝。

## 交付目标

`deliverable` 只允许：

- `narration_audio`
- `static_pptx`
- `animated_pptx`
- `narrated_pptx`
- `video`

| 目标 | 必需审批 | 最终 QA |
|---|---|---|
| `narration_audio` | content、narration | audio |
| `static_pptx` | content、visual | static |
| `animated_pptx` | content、visual | static（针对动画基线的结构 QA；实机播放另行人工确认） |
| `narrated_pptx` | content、visual、narration | standard |
| `video` | content、visual、narration | standard（检查旁白 PPTX；PowerPoint 导出后只做适用的 Office 2019 像素色阶重编码，不做视频画面 QA） |

`template.mode` 为 `provided` 时保存 `inputs/template-source.pptx`；为 `generated` 时 `source` 为 `null`。安全区必须位于 `1600×900` 画布内。`narration_audio` 不要求模板文件实际存在。

## 目录与空状态

```text
presentation-project/
├── project.json
├── page-script.md
├── input-gate.json
├── input-gate.md
├── input-review.json                 # 非 page-narration 时存在
├── inputs/
│   ├── source.md
│   ├── page-script-binding.json      # 来源、保真和逐页差异证据
│   └── template-source.pptx          # 提供用户模板时存在
├── template.pptx                     # 视觉项目准备后存在
├── assets/                            # 仅视觉项目
│   └── NN_page.svg
├── video/
│   ├── svg_layer_plan.json            # 仅视觉项目
│   ├── narration_director.json
│   ├── voice_profile.json
│   ├── animation_manifest.json
│   ├── narration_review.md
│   ├── audio_timeline.json
│   ├── build_state.json
│   ├── qa_static.json
│   ├── qa_audio.json
│   ├── qa_standard.json
│   ├── layers/                        # 仅视觉项目
│   ├── scripts/
│   └── audio/
└── deliverables/
    ├── <name>_静态.pptx
    ├── <name>_动画.pptx
    ├── <name>_自动旁白.pptx
    └── <name>_自动旁白.mp4
```

初始化时派生状态必须为空：

```json
{"pages": []}
```

用于 `narration_director.json`；视觉/旁白 manifest 使用 `"slides": []` 和 `"slide_count": 0`；视觉项目的图层计划使用 `"pages": {}`；`build_state.json` 使用空的 `inputs`、`artifacts`、`approvals`、`qa`，PowerPoint 证据为 `null`。`narration_audio` 不创建 `assets/`、`svg_layer_plan.json` 或 `video/layers/`。

空状态只表示“尚未派生”。旁白交付（`narration_audio`、`narrated_pptx`、`video`）在 content 审批后使用 `prepare-narration` 填充导演稿和旁白 manifest；纯静态/动画交付不运行该命令。视觉制作流程填充 `source_svg`、`beats` 与图层计划。

## 三个审批

审批写入 `video/build_state.json`，每条记录包含当前 fingerprint、审批人、时间和证据。

- `content` 绑定源稿、`page-script.md`、门禁报告、可选语义复核、绑定审计及当前输入契约版本。审计证据记录页数、逐页稿 SHA、保真结果、来源路径及是否使用改写授权。
- `visual` 绑定内容摘要、`template.pptx`、安全区、视觉配置和指定代表性 SVG。
- `narration` 绑定内容字节、导演稿和影响生产声音的配置投影；试听文案、未命中的发音规则以及不进入 SSML 的角色说明不触发章节音频重建。它不绑定视觉，因此 `narration_audio` 不需要 visual 审批。

content acceptance fingerprint 包含 profile、门禁、复核和绑定证据；视觉、旁白和二进制产物只绑定源稿与逐页稿的内容字节 fingerprint，不包含 profile。这样错误 profile 的修正或证据损坏会阻断/失效 content acceptance，但不会在内容字节未变时强迫重做视觉、音频和 PPTX。

生产命令实时重算摘要：

| 变化 | 失效审批 |
|---|---|
| 源稿或逐页稿 | content、visual、narration |
| 模板或代表性视觉 | visual |
| 导演稿或声音配置 | narration |

不得手工修改审批状态。空审批对象不是未通过的缓存，而是从未审批。

## 旁白与视觉契约

`prepare-narration` 从 `page-script.md` 生成 schema v2 导演稿。旁白 manifest 使用 schema v3，并派生：

- 每页 `narration`；
- `voice` 及声音配置摘要；
- `narration_policy`；
- `pronunciation_review`：正文技术代号的已配置读法和非阻断未覆盖清单；
- 连续的 `narration_chapters`；
- 与导演稿一致的 `slide_count`。

导演稿可以调整章节、表达意图、语速、音高和停顿，但各页 `segments[].text` 拼接后必须与 `page-script.md` 的规范化口述正文一致。每页还记录 `intent`、`direction`、`rationale` 和可选 `target_seconds`；前三项用于审阅，真正改变声音的是 segment 参数。正文删改必须先发生在 `page-script.md`，重新通过 content 审批后再派生导演稿。

非空导演稿要求 `policy.performance_contract: rhetorical-v1`。narration 审批摘要记录稳定的表现契约版本和 performance audit；统一书面 direction、统一有效韵律或微小参数抖动不能成为通过证据。旧表现契约仍可读取项目内容，但必须重新准备或修正导演稿后再批准旁白。

`narration_audio` 的 manifest 页面只需要页码和旁白字段。视觉项目再要求每页 `source_svg`；动画项目还要求 `beats[]` 和图层计划。不得因空视觉 manifest 阻断纯音频项目。

静态和动画 PPTX 基线都必须记录 PPTX SHA、当前内容字节 fingerprint 和相应 visual fingerprint。SVG、模板、动画计划或 PPTX 变化后不能复用旧基线，也不能给一个未由当前视觉装配器生成的旧文件补盖“当前”状态。

声音和发音词典只在 `video/voice_profile.json` 维护。`configure-voice` 可合并或替换独立 glossary；导演稿非空时同步刷新 manifest 和 `narration_review.md`，旧 narration 审批自动失效。候选技术代号发现只服务审阅，不自动写入词典或创建新的审批层。

音频时间轴每页记录：

```json
{
  "page": 1,
  "chapter": "opening",
  "audio_file": "audio/01.mp3",
  "audio_duration_seconds": 11.742,
  "advance_ms": 11892,
  "target_seconds": 12.0,
  "duration_delta_seconds": -0.258,
  "timing_status": "within-range",
  "suggested_rate_delta_percent": 0
}
```

`audio_duration_seconds` 必须从实际 MP3 读取。多页章节还保存 bookmark 偏移和切分摘要。

## 版本纪律

- 原始输入、逐页稿、模板原件、工作模板和各级交付物分开保存。
- 自动生成文件不反向成为事实源，外部来源路径不代替项目内源稿。
- input gate 契约只用稳定 `contract_version` 失效，不因脚本注释或内部重构改变；源稿未变时通过 `refresh-input-gate` 更新证据。
- `narration_audio` 不创建虚假 PPTX 或视觉完成状态。
- 替换音频后，旧旁白 PPTX、视频和相关 PowerPoint 证据失效。
- 二进制交付物使用 Git LFS 或放在仓库外交付目录。
- 其他独立产物保留自己的 schema 版本，不因 `project.json` 版本变化而无意义改号。
