# 项目契约

## 单一 Schema

`project.json` 只支持 `schema_version: 2`。版本不匹配时直接阻断；不得补默认字段、静默升级或维护兼容分支。

```json
{
  "schema_version": 2,
  "name": "Project",
  "deliverable": "static_pptx",
  "canvas": {"width": 1600, "height": 900},
  "source": {
    "mode": "document",
    "document": "/absolute/path/source.md",
    "document_sha256": "<sha256>",
    "profile": "narrative-plan",
    "review": "input-review.json",
    "gate_report": "input-gate.json",
    "quality_gate": "passed"
  },
  "content": {
    "page_script": "page-script.md"
  },
  "template": {
    "mode": "provided",
    "source": "inputs/template-source.pptx",
    "working": "template.pptx",
    "safe_area": {
      "x": 120,
      "y": 150,
      "width": 1360,
      "height": 620
    }
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

`deliverable` 只允许：

- `static_pptx`
- `animated_pptx`
- `narrated_pptx`
- `video`

`template.mode` 为 `provided` 时必须保留 `source`；为 `generated` 时 `source` 必须是 `null`。`working` 始终指向适配后或新建的 `template.pptx`。安全区必须完全位于 `1600×900` 画布内。

`style_preset` 允许 `project-default` 或 `technical-infographic`，`theme` 允许 `light` 或 `dark`，`density` 固定为 `presentation`。缺少任何字段都视为契约错误。

## 推荐目录

```text
presentation-project/
├── project.json
├── page-script.md
├── input-review.json
├── input-gate.json
├── input-gate.md
├── inputs/
│   └── template-source.pptx
├── template.pptx
├── assets/
│   └── NN_page.svg
├── video/
│   ├── svg_layer_plan.json
│   ├── narration_director.json
│   ├── voice_profile.json
│   ├── animation_manifest.json
│   ├── narration_review.md
│   ├── fast_animation_timing.json
│   ├── audio_timeline.json
│   ├── build_state.json
│   ├── qa_static.json
│   ├── qa_audio.json
│   ├── qa_standard.json
│   ├── qa_release.json
│   ├── layers/
│   ├── scripts/
│   └── audio/
└── deliverables/
    ├── <name>_静态.pptx
    ├── <name>_动画.pptx
    ├── <name>_自动旁白.pptx
    └── <name>_自动旁白.mp4
```

用户模板原件只保存在 `inputs/`，不得被模板适配器覆盖。没有用户模板时，由项目装配器创建 `template.pptx`。

## 三个审批

审批写入现有 `video/build_state.json`：

```json
{
  "schema_version": 1,
  "approvals": {
    "content": {
      "status": "approved",
      "fingerprint": "<sha256>",
      "approved_at": "<ISO-8601>",
      "approved_by": "reviewer",
      "evidence": {}
    },
    "visual": {
      "status": "approved",
      "fingerprint": "<sha256>",
      "pages": [3, 7, 10],
      "approved_at": "<ISO-8601>",
      "approved_by": "reviewer",
      "evidence": {}
    },
    "narration": {
      "status": "approved",
      "fingerprint": "<sha256>",
      "approved_at": "<ISO-8601>",
      "approved_by": "reviewer",
      "evidence": {}
    }
  }
}
```

- `content` 绑定输入文档与 `page-script.md`。
- `visual` 绑定内容摘要、`template.pptx`、安全区、视觉配置和指定代表性 SVG。
- `narration` 绑定内容摘要、导演稿和完整声音配置。

生产命令实时重算摘要。内容变化使视觉和旁白审批失效；模板或代表性样稿变化只使视觉审批失效；导演稿或声音配置变化只使旁白审批失效。

## 视觉与旁白契约

- 静态项目的 manifest 只需连续页码和每页 `source_svg`；动画项目还必须有 `beats[]` 和图层计划。
- 每页保持一份完整 `1600×900` SVG；动画层也保持完整画布。
- `base` 不动画，`title` 与 `beat_01...beat_05` 使用 `fade` 或方向性 `wipe`。
- 导演稿页码必须与 manifest 一致；相同章节只能覆盖连续页面。
- 声音配置只在 `video/voice_profile.json` 中维护。
- manifest 中的 `voice`、`narration` 和 `narration_chapters` 由 `manifest` 命令派生。

音频时间轴每页记录：

```json
{
  "page": 1,
  "chapter": "opening",
  "audio_file": "audio/01.mp3",
  "audio_duration_seconds": 11.742,
  "advance_ms": 11892
}
```

`audio_duration_seconds` 必须从实际 MP3 读取。多页章节还必须保存 bookmark 偏移和逐页切分摘要。

## 装配器接口

项目可设置：

```json
{
  "production": {
    "assemble_command": "python scripts/build_deck.py"
  }
}
```

命令会收到 `--project <path>`：

- `static_pptx` 必须生成 `outputs.static_pptx`。
- `animated_pptx`、`narrated_pptx` 和 `video` 必须先生成 `outputs.animated_pptx`。
- 旁白链路再从动画基线生成独立的 `outputs.narrated_pptx`，不得覆盖动画基线。

## 版本纪律

- 原始输入、模板原件、工作模板、静态 PPTX、动画 PPTX 和旁白 PPTX 分开保存。
- 自动生成文件不反向成为产品事实来源。
- 二进制交付物使用 Git LFS 或放在仓库外交付目录。
- 替换音频后，旧旁白 PPTX、视频和相应 PowerPoint 证据失效。
- 其他独立产物保留自己的 schema 版本；不要仅因 `project.json` 升级而无意义改号。
