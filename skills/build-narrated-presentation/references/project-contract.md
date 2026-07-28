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
│   ├── voice_profile.json
│   ├── animation_manifest.json
│   ├── narration_review.md
│   ├── fast_animation_timing.json
│   ├── audio_timeline.json
│   ├── build_state.json
│   ├── qa_audio.json
│   ├── qa_standard.json
│   ├── qa_release.json
│   ├── layers/
│   ├── scripts/
│   │   └── <chapter>.ssml
│   └── audio/
│       ├── <page>.mp3
│       ├── <chapter>.sha256
│       └── <chapter>.bookmarks.json
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

`mode: document` 表示所有页面文案、事实和旁白必须追溯到该文档。输入修改后，摘要不匹配会阻断项目校验，必须重新复核。声音配置不属于输入文档摘要。

`project.json.paths` 至少保留：

```json
{
  "voice_profile": "video/voice_profile.json",
  "build_state": "video/build_state.json"
}
```

首次视觉装配需要项目专用适配器时，可以设置：

```json
{
  "production": {
    "assemble_command": "python scripts/build_deck.py"
  }
}
```

适配器会收到追加的 `--project <path>` 参数。

## 页与图层

- 页码使用从 1 开始的连续整数。
- 每页保持一份完整 SVG。
- `base` 固定且不动画。
- `title` 与 `beat_01...beat_05` 是动画层。
- 图层顺序必须与视觉 manifest 中的 beat 顺序一致。
- 每层保持与源页相同画布；除 `base` 外背景透明。
- `expected_source_sha256` 在源 SVG 定稿后更新，防止旧索引静默作用于新结构。

## 视觉 manifest

人工维护的最小结构：

```json
{
  "schema_version": 3,
  "deck": "项目_自动旁白.pptx",
  "animation_defaults": {
    "advance_safety_ms": 150,
    "slide_transition_ms": 250
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

运行 `manifest` 后会派生 `voice`、`narration_policy`、每页 `narration`、`narration_chapters` 和 `slide_count`。不要手工维护这些派生字段。

## 旁白导演稿

每页必须包含：

- `page`：连续页码；
- `chapter`：小写字母、数字和连字符组成的稳定章节 ID；
- `role`：这一页在整套故事中的作用；
- `direction`：语气和表达方式，不进入口播；
- `segments[]`：顺序不变的口述片段；
- `rate`：`+5%` 形式；
- `pitch`：可选，`+0st` 形式；
- `pause_after_ms`：通常 30–150，允许 0–300。

导演稿与视觉 manifest 页码必须完全一致。同一 `chapter` 的页面必须连续，章节不能在后续页面重新出现。

## 声音配置

`voice_profile.json` 使用：

```json
{
  "schema_version": 1,
  "provider": "azure-speech",
  "voice": "zh-CN-XiaochenNeural",
  "style": null,
  "rate": "+0%",
  "pitch": "+0st",
  "page_break_ms": 120,
  "pronunciations": {
    "PsiAI": {"alias": "波塞AI"}
  },
  "audition": {
    "text": "固定试听文案"
  }
}
```

`rate` 必须为带符号的百分比，`pitch` 必须为带符号的半音，`page_break_ms` 允许 0–1000。全局 `rate`、`pitch` 与各 segment 的局部值相加；保持 `+0%`、`+0st` 时不改变导演稿的局部节奏。发音规则二选一：

```json
{"alias": "替代读法"}
```

或：

```json
{"alphabet": "ipa", "phoneme": "音素"}
```

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
  "chapter": "opening",
  "audio_file": "audio/01.mp3",
  "audio_duration_seconds": 11.742,
  "advance_ms": 11892
}
```

`audio_duration_seconds` 必须从实际 MP3 读取。PPTX 换页时间使用该值加 `advance_safety_ms`，不得使用文案估算或统一页时长。

多页章节还必须有 `<chapter>.bookmarks.json`，记录采样率、页码、bookmark 音频偏移、PCM 起止帧和逐页 MP3 摘要。

## 构建状态

`build_state.json` 是机器维护的增量状态，不是内容来源：

```json
{
  "schema_version": 1,
  "inputs": {
    "source": "<sha256>",
    "narration": "<sha256>",
    "voice": "<sha256>",
    "visual": "<sha256>"
  },
  "artifacts": {},
  "qa": {
    "standard": {
      "status": "passed",
      "fingerprint": "<sha256>",
      "checked_at": "<ISO-8601>",
      "report": "video/qa_standard.json"
    }
  },
  "powerpoint": {
    "opened": null,
    "video_exported": null,
    "human_watch": null
  }
}
```

其中 `narration` 只跟踪会改变语义复核的文字、章节、role 和 direction；`voice` 同时跟踪 `voice_profile.json` 与逐段局部语速、音高、停顿，因此这些声音表现参数可以走音频增量链路。

不要手工把 QA 状态改成 `passed`。`release` 通过后才建立可供严格增量重建使用的完整输入基线。

## 版本纪律

- 原始 SVG、静态 PPTX、动画 PPTX 分开保存。
- 同一次构建的 manifest、时间轴、SSML、MP3 和 PPTX 保持同一版本身份。
- 自动生成目录不反向成为产品事实来源。
- 二进制交付物使用 Git LFS 或置于仓库外的交付目录。
- 旧版本移出当前工作目录，不并列参与构建。
- 替换音频或 PPTX 后使旧视频与相应人工验收证据失效。
