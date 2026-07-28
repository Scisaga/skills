# 验收与失败处理

## 先完成输入门禁

在生成任何 SVG 前确认：

1. 输入自动预检没有阻断项；
2. 语义复核与当前文档 SHA-256 一致；
3. 所有语义维度和总决策均为 `pass`；
4. `init --input-document` 成功。

输入门禁未通过时，完成定义是“已输出可执行返工报告并停止”，不是继续制作占位页面。声音配置变化不修改输入文档 SHA-256，也不单独触发该门禁。

## QA 等级

使用统一入口：

```bash
bash skills/build-narrated-presentation/scripts/run.sh qa \
  --project /path/to/project \
  --level audio
```

| 等级 | 检查内容 | 不代表 |
|---|---|---|
| `audio` | 逐页 MP3 数量、可解析性、真实时长、换页时长、章节 bookmark 元数据、发音规则适用项 | 发音已被人听过、PPTX 已更新 |
| `standard` | `audio` 全部内容；PPTX ZIP、每页唯一内部 MP3、媒体字节一致、`playFrom`、`advTm`、演示级 timings/narration/animation | 静态画面重新像素比较、PowerPoint 已导出、人工完整观看 |
| `release` | `standard` 全部内容；严格项目契约、当前 MP4、ffprobe 时长、当前 PPTX 的 PowerPoint 打开证据、当前 MP4 的 PowerPoint 导出证据、人工完整观看证据 | 无 |

视觉、动画结构已通过且没有变化时，音频增量修改使用 `audio` 和 `standard` 即可，不重新做全量视觉检查。正式交付仍要求当前构建最终通过 `release`。

## 缓存规则

QA 在深度检查前计算 fingerprint。fingerprint 包含该等级的依赖文件摘要和 QA 工具脚本摘要。

只有下列条件同时成立才跳过：

- 同一等级此前状态为 `passed`；
- 当前 fingerprint 与此前完全一致；
- 未指定 `--force`。

命令打印：

```text
SKIP qa=standard: inputs and tools unchanged
```

失败结果永不作为可跳过缓存。检查脚本变化也会使缓存失效。

## 音频验收

自动检查：

- director、manifest、声音配置和音频时间轴页码完全一致；
- `video/audio/NN.mp3` 恰好覆盖所有页面；
- 每个 MP3 可解析且非空；
- 记录时长与真实时长误差不超过容差；
- `advance_ms = 真实 MP3 毫秒 + advance_safety_ms`；
- 跨多页章节具有 bookmark 元数据，页码和顺序正确。

人工试听：

- 候选音色符合受众和材料气质；
- 品牌名、缩写、数字、币种和单位读法正确；
- 跨页处语气连续，切分没有吞字、爆音或异常长静音；
- 声音没有机械停顿、过快或过慢。

工具只报告“需要人工试听”，不得自动写成“发音已通过”。

## 标准 PPTX 验收

检查：

- PPTX 是有效 ZIP，页数与时间轴一致；
- 每页恰好一个内部 MP3，且页面之间不共享媒体文件；
- 内嵌媒体字节与对应逐页 MP3 完全一致；
- 每页 `advTm` 与真实音频时间轴一致；
- 每页存在自动 `playFrom` 命令；
- 演示文稿启用 `useTimings`、`showNarration` 和 `showAnimation`。

`replace-audio` 还会证明本次 ZIP 改动只涉及 MP3 和各页换页时间。它不证明 PowerPoint 能无修复提示打开，也不证明最终视频画面正确。

## release 验收

先由 Windows PowerPoint 导出当前 MP4：

```bash
bash skills/build-narrated-presentation/scripts/run.sh export-video \
  --project /path/to/project
```

自动检查：

- 完整项目在严格模式下无错误和警告；
- 当前 PPTX 有匹配 SHA-256 的 PowerPoint 打开证据；
- 当前 MP4 有匹配 SHA-256 的 PowerPoint 导出证据；
- MP4 存在、非空，ffprobe 可用时读取真实时长；
- MP4 时长与音频时间轴估算值在合理容差内。

人工从头到尾观看当前 MP4 后：

```bash
bash skills/build-narrated-presentation/scripts/run.sh qa \
  --project /path/to/project \
  --level release \
  --human-confirmed \
  --confirmed-by "reviewer"
```

`--human-confirmed` 是操作者的显式断言，不能由智能体根据“PowerPoint 已打开”“导出已完成”或“自动抽帧通过”推断。

人工完整观看确认：

- 开头、页间切换、截图页和结尾没有黑帧或跳变；
- 入页立即自动播放声音，全程无需点击；
- 动画在一秒内完成；
- 音频开头不丢字、结尾不截断；
- 音频结束后自然换页；
- SVG 和截图清晰；
- 最后一页结束后不循环；
- 音画完整，无重复或静音页；
- 总时长符合交付要求。

## 常见失败

| 表现 | 原因 | 处理 |
|---|---|---|
| 换音色却重做全部视觉 | 未区分声音与内容依赖 | 使用独立 `voice_profile.json` 和 `rebuild --scope audio` |
| QA 每次都耗时很长 | 未记录依赖 fingerprint | 复用通过且依赖未变的等级缓存 |
| 跨页语气重置 | 每页独立请求 TTS | 同章节连续合成，用 bookmark 切成逐页 MP3 |
| 修改一页后同章声线漂移 | 只重做单个切片 | 章节作为音频缓存和重建最小单位 |
| 品牌名读错 | 批量前未试听或无词典 | 先 voice-audition，再配置 alias/phoneme |
| 动画拖沓 | 按旁白逐句排动画 | 解耦三套时钟，首秒完成 |
| 旁白机械讲图 | 每层绑定一句 | 每页连续口述，先讲判断 |
| 没声音 | 只嵌入媒体 | 写入原生 `mediacall` |
| 音频图标黑块 | poster 无效或全透明 | 使用正常扬声器图片 |
| 页面过早切换 | 使用估算时长 | 读取 MP3 实际时长并加 150ms |
| 总时长失控 | 先写死页时长 | 先合成音频，再改文案 |
| PowerPoint 修复文件 | OOXML 节点、关系或顺序错误 | 校验包结构与 XML 顺序 |
| 误称已经完整观看 | 把自动打开或导出当成人工验收 | 四类证据分开记录，人工确认绑定 MP4 摘要 |

## 完成定义

只有以下条件同时满足才算 release 完成：

- 输入文档通过自动预检和语义复核；
- 静态 SVG 本身成立；
- 分层叠加与原图一致；
- 动画在首秒完成；
- PowerPoint 内每页只有一段内嵌旁白；
- 多页章节的连续合成和 bookmark 切分有效；
- 页面时长来自真实 MP3；
- 所有媒体内嵌；
- PowerPoint 成功打开当前 PPTX 并导出当前 MP4；
- MP4 自动检查通过；
- 人工已经完整观看当前 MP4；
- `qa --level release` 对当前依赖通过。
