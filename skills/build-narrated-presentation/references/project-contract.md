# 项目契约

## 推荐目录

```text
presentation-project/
├── project.json
├── input-review.json
├── input-gate.json
├── input-gate.md
├── assets/
│   └── 00_cover.svg
├── video/
│   ├── svg_layer_plan.json
│   ├── narration_director.json
│   ├── animation_manifest.json
│   ├── narration_review.md
│   ├── fast_animation_timing.json
│   ├── audio_timeline.json
│   ├── layers/
│   ├── scripts/
│   └── audio/
└── deliverables/
    ├── <name>_静态.pptx
    ├── <name>_自动旁白.pptx
    └── <name>_自动旁白.mp4
```

## 输入来源

`project.json.source` 必须明确项目起点：

```json
{
  "mode": "document",
  "document": "/absolute/path/to/source.md",
  "document_sha256": "<sha256>",
  "profile": "narrative-plan",
  "review": "input-review.json",
  "gate_report": "input-gate.json",
  "quality_gate": "passed"
}
```

`mode: document` 表示所有页面文案、事实和旁白必须追溯到该文档。输入修改后，摘要不匹配会阻断项目校验，必须重新复核。

## 页与图层

- 页码使用从 1 开始的连续整数。
- 每页保持一份完整 SVG。
- `base` 固定且不动画。
- `title` 与 `beat_01...beat_05` 是动画层。
- 图层顺序必须与视觉 manifest 中的 beat 顺序一致。
- 每层保持与源页相同画布；除 `base` 外背景透明。
- `expected_source_sha256` 在源 SVG 定稿后更新，防止旧索引静默作用于新结构。

## 视觉 manifest

最小结构：

```json
{
  "schema_version": 2,
  "deck": "项目_自动旁白.pptx",
  "narration_policy": {
    "visual_sync": "independent",
    "audio_start_ms": 0,
    "paragraph_per_slide": 1,
    "animation_window_ms": 1000
  },
  "slides": [
    {
      "page": 1,
      "source_svg": "assets/00_cover.svg",
      "target_seconds": 12,
      "beats": [
        {"id": "title", "label": "标题", "effect": "fade"},
        {"id": "beat_01", "label": "问题", "effect": "fade"},
        {"id": "beat_02", "label": "结论", "effect": "wipe_left"}
      ]
    }
  ]
}
```

## 旁白导演稿

每页必须包含：

- `role`：这一页在整套故事中的作用；
- `direction`：语气和表达方式，不进入口播；
- `segments[]`：顺序不变的口述片段；
- `rate`：`+5%` 形式；
- `pause_after_ms`：通常 30–150，允许 0–300。

导演稿与视觉 manifest 页码必须完全一致。

## 首秒动画时间轴

默认：

```text
audio_start_ms = 0
title.start_ms = 0
first_content_start_ms = 120
start_step_ms = 130
duration_ms = 280
animation_window_ms = 1000
advance_safety_ms = 150
```

只记录视觉时钟，不写旁白句段提示点。

## 音频时间轴

每页记录：

```json
{
  "page": 1,
  "audio_file": "audio/01.mp3",
  "audio_duration_seconds": 11.742
}
```

`audio_duration_seconds` 必须从实际 MP3 读取。PPTX 换页时间使用该值加 `advance_safety_ms`，不得使用文案估算或统一页时长。

## 版本纪律

- 原始 SVG、静态 PPTX、动画 PPTX 分开保存。
- 同一次构建的 manifest、时间轴、SSML、MP3 和 PPTX 保持同一版本身份。
- 自动生成目录不反向成为产品事实来源。
- 二进制交付物使用 Git LFS 或置于仓库外的交付目录。
- 旧版本移出当前工作目录，不并列参与构建。
