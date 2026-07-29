# 旁白与音频

## 先写整套故事

每页先回答：

1. 这一页在整套故事中承担什么作用？
2. 它承接上一页的哪个问题？
3. 它把观众带向下一页的哪个判断？

先建立共同问题和通用价值，再用案例证明。案例不能替代产品定位。内部工程名、讲述目的、事实备注和动画提示不要念给观众。

## 口述风格

- 一句只承载一个主要判断；
- 使用动作、对象和结果，少用抽象名词；
- 不逐项读取画面文字；
- 长短句交替，允许自然衔接；
- 局部语速和停顿只服务于口语节奏；
- 产品名和缩写第一次出现时说明作用，并配置稳定发音。

## 声音配置独立于内容

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
    "PsiAI": {
      "alias": "波塞AI"
    },
    "示例术语": {
      "alphabet": "ipa",
      "phoneme": "..."
    }
  },
  "audition": {
    "text": "用十到十五秒的固定文案比较音色、节奏和品牌词发音。"
  }
}
```

`voice`、全局 `rate`、`pitch`、`style`、`page_break_ms` 和 `pronunciations` 都属于声音生产参数，不写入输入文档。更换这些参数只使音频链路及其下游失效。页面 `segments[].rate`、`pitch` 和 `pause_after_ms` 属于旁白导演稿，因为它们表达局部口述节奏。全局与局部 rate、pitch 按数值相加；使用 `+0%` 和 `+0st` 可保持导演稿原速、原音高。

默认环境变量：

```text
AZURE_SPEECH_KEY
AZURE_SPEECH_REGION=eastasia
```

可以通过当前目录、skill 根目录或脚本目录下的 `.env` 提供凭证，也可用 `--env-file` 指定；读取顺序与此一致。不要把 `.env` 提交到版本库。

## 批量前先试听

用同一段 10–15 秒文案生成候选音色：

```bash
bash skills/build-narrated-presentation/scripts/run.sh voice-audition \
  --project /path/to/project \
  --voices zh-CN-XiaochenNeural,zh-CN-XiaoxiaoNeural
```

输出位于 `video/audio/auditions/`，每个音色同时保留 SSML 和 MP3。试听至少确认：

- 角色气质与项目受众匹配；
- 中文、英文和中英混读自然；
- 品牌名、缩写、数字、货币和单位读法正确；
- 语速与音高不造成压迫或拖沓；
- 专有名词规则在整段语境中仍自然。

自动 QA 只能确认文件、时长和规则已渲染，不能确认实际发音悦耳或正确。完成试听后再批量生成。

## 章节连续、按页交付

PowerPoint 要求每页恰好一个 MP3。禁止一个 MP3 跨多页播放。需要连续语气时，在 `narration_director.json` 中给连续页面设置相同 `chapter`：

```json
{
  "pages": [
    {
      "page": 8,
      "chapter": "product-loop",
      "role": "建立机制",
      "direction": "自然承接上一页",
      "segments": [
        {
          "text": "先解释闭环如何开始。",
          "rate": "+5%",
          "pause_after_ms": 80
        }
      ]
    },
    {
      "page": 9,
      "chapter": "product-loop",
      "role": "给出结果",
      "direction": "语气连续，不重新起头",
      "segments": [
        {
          "text": "接下来说明闭环如何完成。",
          "rate": "+5%",
          "pause_after_ms": 80
        }
      ]
    }
  ]
}
```

同一章节必须占据一段连续页码，不能在中间穿插其他章节。生产链：

```text
整章生成一个 SSML
→ 每页开头插入 <bookmark mark="page-NN"/>
→ Azure Speech 连续输出 PCM WAV 和 bookmark 音频偏移
→ 按偏移切分 PCM
→ 分别编码为 NN.mp3
→ 保存 <chapter>.bookmarks.json
```

章节合成保持跨页声音和语气连续；逐页 MP3 仍让 PowerPoint 能在每页独立自动播放、按真实时长换页。页面边界的短停顿由 `page_break_ms` 控制。

如果某页使用独立章节，效果等同于逐页合成。修改章节中任意一页的文字、局部语速、停顿或发音规则时，必须重做整个章节。

完成导演稿、`narration_review.md` 和声音试听后执行：

```bash
bash skills/build-narrated-presentation/scripts/run.sh approve \
  --project /path/to/project \
  --stage narration \
  --approved-by "reviewer"
```

旁白审批绑定当前导演稿、声音配置和内容摘要。导演稿或声音配置变化后，`synthesize` 必须阻断，直到重新生成审阅稿、试听并批准。

## SSML 契约

每页对应一个 `<p>`，但同一章节的多个 `<p>` 位于一个 `<speak>` 中：

```xml
<speak version="1.0" xml:lang="zh-CN"
       xmlns="http://www.w3.org/2001/10/synthesis">
  <voice name="zh-CN-XiaochenNeural">
    <bookmark mark="page-08"/>
    <p>
      <prosody rate="+5%" pitch="+0st">先解释闭环如何开始。</prosody>
      <break time="80ms"/>
    </p>
    <bookmark mark="page-09"/>
    <p>
      <prosody rate="+5%" pitch="+0st">接下来说明闭环如何完成。</prosody>
    </p>
  </voice>
</speak>
```

`segments` 只用于局部语速、音高、停顿和发音，不用于绑定动画。品牌别名渲染为 `<sub alias="…">`，phoneme 规则渲染为 `<phoneme alphabet="…" ph="…">`。

## 合成与复用

```bash
bash skills/build-narrated-presentation/scripts/run.sh synthesize \
  --project /path/to/project
```

每个章节计算包含下列输入的 SHA-256：

- 章节内所有页面、文字和局部节奏；
- 完整声音配置和发音词典；
- 最终 SSML；
- 音频生产管线版本。

命令先验证内容和旁白审批，再用当前导演稿和声音配置刷新 manifest 中派生的 `narration`、`voice` 与审阅稿，然后进入 TTS。摘要一致、所有逐页 MP3 都存在时复用整个章节。`--pages 8,9` 选择的是受影响页面，实际仍重做它们所属的完整章节。`--force` 忽略音频缓存；`--dry-run` 只列出计划，不修改声音配置、manifest 或生成目录，也不请求 TTS。

通过 `synthesize --voice`、`--rate` 或 `--pitch` 更改全局声音时，命令只更新 `voice_profile.json` 并停止。必须重新运行 `manifest`、试听并批准旁白，再次执行 `synthesize`。

## 真实时长与换页

合成后执行：

```bash
bash skills/build-narrated-presentation/scripts/run.sh audio-timeline \
  --manifest /path/to/project/video/animation_manifest.json \
  --audio-dir /path/to/project/video/audio \
  --output /path/to/project/video/audio_timeline.json
```

计算规则：

```text
T_slide = T_audio + 150ms
T_deck = ΣT_slide + ΣT_transition
```

每次构建都重新读取全部 MP3 的真实时长。总时长超标时依次：

1. 删除重复判断；
2. 缩短解释性从句；
3. 合并相近例子；
4. 小幅提高局部语速；
5. 重新合成并读取真实时长。

不要缩短自动换页时间，否则会截断旁白。
