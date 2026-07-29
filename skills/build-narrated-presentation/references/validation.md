# 验收与失败处理

## 前置门禁

任何生产命令都必须使用 schema v2 项目。审批要求：

| 动作 | 必须有效的审批 |
|---|---|
| 静态或动画装配 | `content`、`visual` |
| 合成音频 | `content`、`narration` |
| 生成旁白 PPTX、标准 QA、视频导出 | `content`、`visual`、`narration` |

摘要变化后旧审批自动失效。不得手工把审批或 QA 状态改成通过。

## 阶段依赖

```bash
run.sh doctor --stage static
run.sh doctor --stage audio
run.sh doctor --stage video
```

- `static`：SVG、PPTX、字体和静态渲染依赖。
- `audio`：在静态依赖上增加 Azure Speech、MP3 编码、时长和 `.env` 读取。
- `video`：再增加 PowerShell、ffprobe 和 Windows PowerPoint 边界。

静态阶段不得检查 Azure Speech、`lameenc`、`mutagen` 或视频导出环境。

## QA 等级

| 等级 | 检查内容 |
|---|---|
| `static` | schema、输入、模板、完整 SVG、静态 PPTX ZIP、页数、内嵌 SVG 和外部媒体关系 |
| `audio` | 逐页 MP3、真实时长、换页时长、章节 bookmark 和发音规则适用项 |
| `standard` | `audio` 全部内容、旁白 PPTX、每页唯一内部 MP3、媒体字节、自动播放和 `advTm` |
| `release` | `standard`、严格项目检查、PowerPoint 打开/导出证据、MP4、ffprobe 和人工完整观看 |

`static` 不读取音频。`audio` 不重复静态画面验收。只有 `video` 项目允许 release。

## QA 缓存

QA 在深度检查前计算当前等级依赖和检查脚本的 fingerprint。仅当此前为 `passed`、fingerprint 完全一致且未指定 `--force` 时打印：

```text
SKIP qa=static: inputs and tools unchanged
```

失败结果不能缓存为通过。静态 fingerprint 不包含音频和动画时间轴；声音变化不会使静态 QA 失效。

## 静态验收

自动检查：

- 输入文档和 `page-script.md` 仍与审批摘要一致；
- 工作模板存在且是有效 PPTX；
- manifest 页码连续，所有源 SVG 存在且画布正确；
- 静态 PPTX 是有效 ZIP，页数与 manifest 一致；
- 每页主体 SVG 已内嵌；
- 图片、音频或媒体关系没有指向外部路径。

PowerPoint 实际渲染仍需检查字体替换、裁切、重叠、截图清晰度和模板安全区。结构检查不能冒充实机视觉验收。

## 音频与标准验收

音频自动检查：

- director、manifest、声音配置和音频时间轴页码一致；
- `video/audio/NN.mp3` 恰好覆盖所有页面；
- 每个 MP3 可解析且非空；
- `advance_ms = 真实 MP3 毫秒 + advance_safety_ms`；
- 多页章节具有正确 bookmark 元数据。

人工试听确认音色、专有名词、数字、中英混读和跨页切分。自动 QA 不能声称发音已经人工通过。

标准 PPTX 检查：

- 使用独立的 `outputs.narrated_pptx`；
- 每页恰好一个内部 MP3，页面之间不共享媒体成员；
- 内嵌字节与逐页 MP3 一致；
- 每页自动播放且 `advTm` 来自真实时长；
- 演示启用 timings、narration 和 animation。

## 视频与人工观看

`export-video` 只允许 `deliverable=video`，并要求当前标准 QA 已通过。视频导出完成不等于已经观看。

人工完整观看当前 MP4 后才能执行：

```bash
run.sh qa --project PROJECT --level release \
  --human-confirmed --confirmed-by REVIEWER
```

人工确认必须与当前 MP4 SHA-256 绑定，至少检查黑帧、跳变、音频截断、错误换页、重复或静音页、截图清晰度和结尾行为。

## 常见失败

| 表现 | 处理 |
|---|---|
| schema 不是 v2 | 停止；按当前契约重建配置，不运行兼容或迁移逻辑 |
| 静态任务被 TTS 依赖阻断 | 使用 `doctor --stage static`，检查是否误进入声音链 |
| 审批突然失效 | 查看报错指出的 content、visual 或 narration 摘要，返工并重新批准该阶段 |
| 改声音后仍能直接合成 | 错误；应先试听并重新批准 narration |
| 一个音频跨多页 | 错误；整章合成后按 bookmark 切成逐页 MP3 |
| 页面过早切换 | 重新读取真实 MP3 时长并加安全余量 |
| 误称已经完整观看 | 分开报告 PowerPoint 打开、导出、自动检查和人工观看 |

## 完成定义

- `static_pptx`：内容与视觉审批有效，静态 QA 通过。
- `animated_pptx`：静态基线有效，首秒动画实机检查通过。
- `narrated_pptx`：逐页 MP3、真实时间轴和 standard QA 通过。
- `video`：PowerPoint 导出成功，MP4 自动检查和人工完整观看完成，release QA 通过。
