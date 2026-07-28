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

## 一页一段连续旁白

每页使用一个 MP3 和一个 SSML `<p>`。`segments` 只用于语速、停顿和发音，不用于绑定动画。

```xml
<speak version="1.0" xml:lang="zh-CN"
       xmlns="http://www.w3.org/2001/10/synthesis">
  <voice name="zh-CN-XiaochenNeural">
    <p>
      <prosody rate="+8%" pitch="+0st">第一句。</prosody>
      <break time="80ms"/>
      <prosody rate="+5%" pitch="+0st">第二句。</prosody>
    </p>
  </voice>
</speak>
```

默认可使用：

```text
AZURE_SPEECH_KEY
AZURE_SPEECH_REGION=eastasia
Voice=zh-CN-XiaochenNeural
Default rate=+5%
Pitch=+0st
```

也可替换 TTS 提供方，但必须保持“一页一段连续音频”和真实时长契约。本仓库已有 `skills/speech/` 时，可显式读取其 `SKILL.md` 并复用合成入口。

## 内容摘要

对完整 SSML 计算 SHA-256：

- 摘要一致且 MP3 存在时复用；
- 文案、音色、语速、停顿或发音替换变化时只重做该页；
- `.sha256` 与 MP3 同目录；
- 每次构建都重新读取所有 MP3 时长并重建时间轴。

## 时长控制

```text
T_slide = T_audio + 150ms
T_deck = ΣT_slide + ΣT_transition
```

总时长超标时依次：

1. 删除重复判断；
2. 缩短解释性从句；
3. 合并相近例子；
4. 小幅提高局部语速；
5. 重新合成并读取真实时长。

不要缩短自动换页时间，否则会截断旁白。
