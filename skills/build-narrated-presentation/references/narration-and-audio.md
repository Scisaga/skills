# 旁白与音频

## 目录

- [从逐页正文生成导演稿](#从逐页正文生成导演稿)
- [稳定说话人音高契约](#稳定说话人音高契约)
- [声音配置](#声音配置)
- [专业术语与材料牌号](#专业术语与材料牌号)
- [配置、审阅与试听顺序](#配置审阅与试听顺序)
- [章节连续、按页交付](#章节连续按页交付)
- [合成与缓存](#合成与缓存)
- [真实时长与音频验收](#真实时长与音频验收)
- [纯音频与演示分流](#纯音频与演示分流)

## 从逐页正文生成导演稿

内容审批后运行：

```bash
run.sh prepare-narration --project PROJECT
```

命令从 `page-script.md` 的 `## 第 N 页｜标题` 或 `## PAGE N/T｜标题` 生成：

- `video/narration_director.json`；
- `video/animation_manifest.json` 中的旁白字段；
- `video/narration_review.md`。

初始化时导演稿 `pages` 为空。已有非空导演稿时，`prepare-narration` 默认阻断，避免覆盖人工调整；只有明确确认重新派生时使用 `--force`。

需要由智能体或人工提供更具体的逐页编排时，可传入不含正文的 override plan：

```bash
run.sh prepare-narration --project PROJECT --force \
  --performance-plan performance-plan.json
```

plan 必须覆盖全部页，每页只允许覆盖 `intent`、`direction`、`rationale` 以及与规范化正文段数相同的 rate/pitch/pause cue；出现 `text` 字段直接阻断。这样语气修正可以复用，但永远不能借机改写口述正文。

默认让每个规范化后的可朗读段落生成一个 segment，并按开场、背景、解释、对比、证据、案例、分类、结论和收尾生成一版克制的语气编排。它是可审阅的第一版，不是自然听感已经人工通过的证明。导演稿可继续调整章节、讲述目的和局部节奏，但 `segments[].text` 拼接结果必须与 `page-script.md` 的规范化口述正文完全一致，不能重新摘要成页面要点。

每页字段示例：

```json
{
  "page": 8,
  "chapter": "application",
  "role": "说明工程边界",
  "intent": "comparison",
  "direction": "保持客观克制，对比项使用对称节奏，结论句加重。",
  "rationale": "比较页容易被听成站队，因此使用对称语速并在转折处留停。",
  "target_seconds": 45,
  "segments": [
    {
      "text": "这里保留该页实际口述正文。",
      "rate": "-4%",
      "pitch": "+0st",
      "pause_after_ms": 180
    }
  ]
}
```

`direction`、`intent` 和 `rationale` 是审阅依据，本身不会改变声音。实际进入 SSML 的只有页面 `segments[].rate`、`pitch`、`pause_after_ms`，以及全局 voice/style/rate/pitch/page break 和实际命中的发音规则。不得把书面语气说明去重当成可听编排，也不得用这些参数绑定动画时序。

旁白审批在原有边界内执行一次轻量 performance audit，不增加新门禁或状态文件。四页以上的导演稿若仍使用统一 direction、缺少多个实质可听 profile，或只有统一语速和停顿模板，将直接阻断。审计以有意义的语速区间和非末段停顿/断句组合为 profile 证据；音高不单独计入，机械交替 `-0.1st/+0.1st` 也不能制造新 profile。`+1%` 一类微小语速抖动同样不能冒充语气变化。表现契约版本进入 narration 审批摘要，契约升级后旧审批自动失效。

`narration_review.md` 必须显示当前音色和全局参数，并逐段列出局部与最终 rate/pitch、停顿、表达意图和编排依据。人工或智能体修改 `narration_director.json` 后运行 `manifest` 刷新审阅稿，再进行 narration 审批。

## 稳定说话人音高契约

默认旁白的最终音高按数值相加：

```text
final_pitch = global_pitch + local_pitch
allowed_final_pitch = [-0.1st, +0.1st]
```

全局与局部音高本身也只接受 `-0.1st` 至 `+0.1st`，但分别合法不代表组合合法。全局 `+0.1st` 与局部 `+0.1st` 的最终值为 `+0.2st`，必须在 manifest、narration 审批、合成和 audio QA 阶段阻断；全局 `-0.1st` 与局部 `+0.1st` 的最终值为 `+0st`，允许通过。任何入口都不得自动 clamp，避免审阅意图与实际 SSML 不一致。

默认优先使用 `+0st`，只在明确的轻微抬升、转折或收束处使用 `±0.1st`。段落层次主要由语速、非末段停顿、断句和重音组织；不要按段落奇偶机械交替音高，也不要为了通过 performance audit 扩大或摆动音高。整套旁白保持 `+0st` 是合法状态，只要语速和停顿具有合理变化。

manifest 保存逐页逐段的全局、局部和最终音高，以及最终最小值、最大值和越界段落；`narration_review.md` 显示同一证据。最终 SSML 生成前再次调用同一硬门禁，audio QA 再计算并报告相同范围，三处结果必须一致。

只有显式范围覆盖能够绑定当前 voice/style/global 配置的试听确认时，才允许扩大默认范围。当前 `build_state.json` 尚未记录这种可验证确认，因此本技能当前不提供宽范围覆盖；不能用手工字段或临时 SSML 绕过。

## 声音配置

声音只在 `video/voice_profile.json` 中维护：

```json
{
  "schema_version": 1,
  "provider": "azure-speech",
  "voice": "zh-CN-XiaochenNeural",
  "style": null,
  "rate": "-5%",
  "pitch": "+0st",
  "page_break_ms": 120,
  "pronunciations": {
    "示例术语": {
      "alphabet": "ipa",
      "phoneme": "..."
    }
  },
  "audition": {
    "text": "用固定短文比较音色、节奏、缩写、数字和单位发音。"
  }
}
```

用独立命令修改全局声音：

```bash
run.sh configure-voice --project PROJECT \
  --voice zh-CN-XiaochenNeural \
  --rate=-5% \
  --pitch=+0st
```

发音词典用独立 JSON 文件合并或替换，避免临时改 SSML：

```bash
run.sh configure-voice --project PROJECT \
  --pronunciation-file pronunciation-glossary.json \
  --replace-pronunciations
```

`configure-voice` 更新声音配置并停止；导演稿非空且现有 manifest 可合并时同时刷新旁白 manifest 与 `narration_review.md`。它不修改源稿、逐页稿或导演稿，也不请求 TTS，也不要求视觉审批或动画 PPTX 基线。损坏或未完成的视觉 manifest 不阻断声音配置写入，命令会明确 warning 派生审阅稿未刷新，之后 narration 审批仍会阻断陈旧派生物；空导演稿则明确说明尚无 review。voice、rate 或 pitch 的生产投影实际变化时，旧 narration 审批自动失效；no-op 配置保持 current。`synthesize` 不接受临时声音覆盖；所有生产声音都必须先进入 `voice_profile.json` 并完成审阅。

全局与局部 rate、pitch 按数值相加；pitch 必须按上一节检查最终值。声音变化不触发输入门禁或内容审批，但会重新计算全部段落的最终音高，并使 narration 审批、全部章节缓存及音频下游失效。若新全局音高导致任一段越界，`configure-voice` 直接失败且不写入配置。

默认环境变量：

```text
AZURE_SPEECH_KEY
AZURE_SPEECH_REGION=eastasia
```

`.env` 加载顺序为当前工作目录、skill 根目录、脚本目录；也可显式传入环境文件。不得提交真实密钥。

## 专业术语与材料牌号

导演稿生成后，manifest 会从可听正文中提取混合字母数字、全大写缩写和元素式拉丁串，在 `narration_review.md` 中分别展示：

- 已配置并实际命中的“原词、出现页、规则类型、TTS 实际读法”；
- 尚未配置的技术代号候选及出现页。

候选发现是非阻断审阅，不是新输入门禁。正则只能发现“可能需要处理”，不能决定正确读法；产品名、工艺缩写、材料牌号和单位可能具有相同字形。纯数字通常不进入候选，只有处在“合金/不锈钢，包括……”这类材料牌号列举句中时才作为候选，避免把年份、尺寸和性能值误报成牌号。未覆盖项会进入 audio QA warning，但不能把 warning 当成人工发音已经确认。

按语义选择规则：

| 类型 | 判断与口播 | 建议规则 |
|---|---|---|
| 普通缩写 | `LMD`、`SLM` 等逐字母读 | `say_as: characters` |
| 字母前缀＋体系序号 | `TA1` 读“T A 一”，`TA15` 读“T A 十五” | 中文口播 `alias` |
| 数字牌号 | `6061` 读“六零六一”，`304` 读“三零四” | 中文口播 `alias` |
| 成分型合金牌号 | 把元素符号转为中文元素名，并按牌号语义读数字 | 中文语义 `alias` |
| 复杂标准号或旧式钢牌号 | 结合行业含义拆分前缀、序号和元素含量 | 经确认的完整 `alias` |

`AlSi10Mg` 不是化学分子式，而是成分型铝合金牌号：`Al` 为铝基体，`Si10` 表示名义约 10% 硅，`Mg` 表示镁合金化。中文材料专业口播使用“铝硅十镁”，不要读成连续英文、逐字符 `A-L-S-I-1-0-M-G`，也不要说成“铝硅百分之十镁”；后者会把牌号误说成精确化验值。相同原则适用于元素链牌号。

```json
{
  "pronunciations": {
    "LMD": {"say_as": "characters"},
    "TA1": {"alias": "T A 一"},
    "TA15": {"alias": "T A 十五"},
    "AlSi10Mg": {"alias": "铝硅十镁"},
    "AlMgScZr": {"alias": "铝镁钪锆"},
    "AlMgErZr": {"alias": "铝镁铒锆"},
    "0Cr17Ni4Cu4Nb": {"alias": "零铬十七镍四铜四铌"},
    "6061": {"alias": "六零六一"},
    "316L": {"alias": "三一六 L"}
  }
}
```

`alias` 渲染为 `<sub>`，`phoneme` 渲染为 `<phoneme>`，`say_as` 渲染为 `<say-as>`。字母数字术语使用 ASCII token 边界匹配：`TA1` 不得命中 `TA15` 的前四个字符。一个规则命中多个章节时，所有命中章节都必须重建；未命中正文的规则不进入章节 fingerprint。

生产前把实际专业词组成短试听句，使用当前 voice profile 生成试听。先确认元素名称、字母名称、数字是逐位还是序号、以及连读停顿，再批准 narration；不能只试听普通中文句子。

## 配置、审阅与试听顺序

推荐人工流程：

```text
prepare-narration
→ 可选 configure-voice
→ 自动用当前 voice_profile 刷新 manifest 和 narration_review.md
→ 逐页检查并修正可执行语气参数；修改后运行 manifest
→ voice-audition
→ 人工试听
→ approve narration
→ synthesize
```

手工修改导演稿后，或需要显式合并视觉字段时，使用 `manifest` 重新生成审阅稿。纯音频项目不传视觉 manifest：

```bash
run.sh manifest \
  --director PROJECT/video/narration_director.json \
  --voice-profile PROJECT/video/voice_profile.json \
  --output PROJECT/video/animation_manifest.json \
  --review PROJECT/video/narration_review.md
```

视觉项目增加 `--visual`，将当前视觉字段和旁白字段合并。不要直接编辑 manifest 中派生的 `voice`、`narration` 或 `narration_chapters`。

候选音色试听：

```bash
run.sh voice-audition --project PROJECT \
  --voices zh-CN-XiaochenNeural,zh-CN-XiaoxiaoNeural
```

试听文件位于 `video/audio/auditions/`。至少确认角色气质、中文和中英混读、专有名词、缩写、数字、单位、语速及音高。试听目前不写入 `build_state.json`，也不是脚本强制前置条件；自动 QA 不能证明实际发音自然或正确。正式的机器边界是 narration 审批绑定当前导演稿和生产声音。

确认导演稿、当前声音和审阅稿后执行：

```bash
run.sh approve --project PROJECT \
  --stage narration --approved-by REVIEWER
```

旁白审批只依赖 content、导演稿和声音，不依赖 visual；因此 `narration_audio` 可以在没有模板或 SVG 的情况下完成。

## 章节连续、按页交付

PowerPoint 和逐页音频交付都要求每页一个 MP3。禁止一个 MP3 跨页播放。需要跨页语气连续时，让相邻页面使用相同 `chapter`：

```text
整章生成一个 SSML
→ 每页起点插入 <bookmark mark="page-NN"/>
→ Azure Speech 连续输出音频和 bookmark 偏移
→ 按偏移切分 PCM
→ 分别编码为 NN.mp3
→ 保存 <chapter>.bookmarks.json
```

同一章节必须覆盖一段连续页码，不能在中间穿插其他章节。页面边界停顿由 `page_break_ms` 控制；独立章节等同于逐页合成。

SSML 结构示意：

```xml
<speak version="1.0" xml:lang="zh-CN"
       xmlns="http://www.w3.org/2001/10/synthesis">
  <voice name="zh-CN-XiaochenNeural">
    <bookmark mark="page-08"/>
    <p><prosody rate="+0%" pitch="+0st">第八页正文。</prosody></p>
    <bookmark mark="page-09"/>
    <p><prosody rate="+0%" pitch="+0st">第九页正文。</prosody></p>
  </voice>
</speak>
```

别名渲染为 `<sub>`，phoneme 规则渲染为 `<phoneme>`。修改章节中任一页的文字、局部节奏或实际命中的发音规则时，重做完整章节。纯导演说明、试听文案和未在该章正文出现的发音条目不进入章节 fingerprint。

## 合成与缓存

```bash
run.sh synthesize --project PROJECT
```

命令先验证 content 和 narration 审批，再按章节合成。章节 fingerprint 包含：

- 章节内页面、正文和局部节奏；
- 会影响 SSML 的声音配置与发音词典（试听文案不参与）；
- 最终 SSML；
- 音频生产管线版本。

摘要一致后还要核对最终 SSML、bookmark 元数据、页面集合和实际 MP3 SHA-256，全部一致才复用缓存。文件损坏或元数据缺失时直接重建该章，不等到 QA 才报错。`--pages 8,9` 表示选择受影响页面，实际仍重建其所在完整章节；同时发现其他章节摘要过期时，不得留下混合新旧状态。`--force` 忽略音频缓存，`--dry-run` 只报告计划。

## 真实时长与音频验收

合成后从实际 MP3 建立时间轴：

```bash
run.sh audio-timeline \
  --manifest PROJECT/video/animation_manifest.json \
  --audio-dir PROJECT/video/audio \
  --output PROJECT/video/audio_timeline.json
```

计算规则：

```text
T_slide = T_audio + advance_safety_ms
T_deck = ΣT_slide + ΣT_transition
```

默认 `advance_safety_ms` 为 150。时间轴保留源稿标题中的 `target_seconds`，记录真实偏差；超过 3 秒且超过目标 15% 的页面标记为 `review`，并给出限制在 ±10% 内的语速修正建议。建议只用于审阅，不能自动覆盖语气导演；确认后修改局部 rate，再按章节重建。不得用字数估算代替真实音频时长，也不得缩短换页时间截断旁白。

执行 audio QA：

```bash
run.sh qa --project PROJECT --level audio
```

自动检查页面集合、逐页 MP3、真实时长、bookmark、声音摘要、表现审计和时间轴；同时报告最终音高最小值、最大值及越界页码/段落，任一最终值超出 `±0.1st` 即失败，并确认同一 voice、style 与全局配置贯穿全部章节。人工试听仍负责发音、切分、声音年龄、质感、身份稳定性和整体听感。

## 纯音频与演示分流

### `narration_audio`

audio QA 通过即完成。不得要求 visual 审批，不得读取模板、SVG 或 PowerPoint，也不得创建 `assets/`、SVG 图层计划、占位 PPTX 或其他视觉完成状态。

### `narrated_pptx`

在有效 visual 审批基础上，将逐页 MP3 和真实换页时间写入独立的自动旁白 PPTX，再执行 standard QA。

### `video`

standard QA 后由 Windows PowerPoint 导出 MP4。Office 2019 按导出报告身份把 full-range 像素映射为 limited range 并重新编码 H.264，音频保持 stream copy；Office 2021/2022 或更新版本跳过。随后直接交付，不做 ffprobe、抽帧、观看或 release QA。

只改音频时可使用：

```bash
run.sh rebuild --project PROJECT --scope audio --qa audio
```

`narration_audio` 固定停在 audio；`narrated_pptx` 可使用 `--qa standard`；`video` 按需继续导出。更换声音时先通过 `configure-voice` 写入配置并刷新审阅稿，再重新批准旁白；试听是推荐的人工质量步骤。
