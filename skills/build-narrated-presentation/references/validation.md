# 验收与失败处理

## 目录

- [审批边界](#审批边界)
- [依赖分级](#依赖分级)
- [QA 等级](#qa-等级)
- [来源与空状态检查](#来源与空状态检查)
- [音频验收](#音频验收)
- [单页 SVG 局部检查](#单页-svg-局部检查)
- [视觉、PPTX 与视频验收](#视觉pptx-与视频验收)
- [缓存与失败处理](#缓存与失败处理)
- [完成定义](#完成定义)

## 审批边界

任何生产命令都使用 schema v2 项目。审批要求：

| 动作 | 必须有效的审批 |
|---|---|
| 生成导演稿前的内容确认 | content |
| 合成或验收逐页音频 | content、narration |
| 静态或动画装配 | content、visual |
| 生成旁白 PPTX、standard QA、视频导出 | content、visual、narration |

`narration_audio` 永远不需要 visual。对应 fingerprint 变化后旧审批自动失效；不得手工把空状态、审批或 QA 改成通过。

## 依赖分级

```bash
run.sh doctor --stage static
run.sh doctor --stage audio
run.sh doctor --stage video
```

- `static`：检查代码可见的 SVG/PPTX Python 模块；
- `audio`：只检查代码可见的 TTS、MP3 编码和时长模块，不继承静态依赖；
- `video`：叠加 PowerShell 边界；视频导出后不要求 ffprobe 或其他 MP4 检查工具。

`doctor` 是依赖预检，不证明字体实际可用、Azure 凭据有效、服务可连通、`.env` 内容正确或桌面 PowerPoint 已可自动化；这些条件在对应生产命令和实机检查中验证。

纯音频任务不得因缺少 PowerPoint、SVG 渲染器或视觉模板而失败；静态任务不得因缺少 TTS 或视频环境而失败。

## QA 等级

| 等级 | 适用交付 | 检查内容 |
|---|---|---|
| `static` | static/animated/narrated PPTX、video | 来源绑定、模板、SVG、当前静态或动画基线、内部媒体关系和视觉 provenance |
| `audio` | `narration_audio`、narrated PPTX、video | 导演稿、声音、逐页 MP3、bookmark 和真实时间轴 |
| `standard` | narrated PPTX、video | 复用当前 audio 报告，检查动画基线血缘、旁白 PPTX、内部 MP3、自动播放和换页 |

`narration_audio` 在 audio QA 后停止，不能进入 standard。`video` 的最终 QA 也是 standard；PowerPoint 导出是生产步骤，导出后不再增加视频 QA 等级。

## 来源与空状态检查

项目验证不得重新运行完整输入语义门禁。它核对已保存证据：

- `inputs/source.md` 存在，当前 SHA 与 `project.json.source.document_sha256` 一致；
- `input-gate.json` 为 PASS，且 document SHA 和 profile 与项目一致；
- input gate 的稳定 `contract_version` 当前，且报告 SHA 与 `project.json` 记录一致；
- 需要语义复核的 profile 具有 SHA 一致的 `input-review.json`；
- `page-script.md` 页码连续、标题和每页正文满足逐页契约；
- `page-narration` 的当前逐页稿仍可与项目内源稿进行保真核对；
- `page-script-binding.json` 的契约版本、来源、模式和 SHA 当前；
- content acceptance fingerprint 与当前源稿、逐页稿、门禁、复核和绑定证据一致。

这里的逐页机械检查只证明每页达到可朗读字符阈值且没有渲染标记，不证明它在语义上已是完整口述。identity 依靠字节一致性防止原稿被摘要替换；adapted 的讲述完整性由 content 审批承担。

`validate` 默认把缺失或失效审批报告为 warning，并以“contract valid with warnings”退出；这表示文件结构可继续审阅，不表示生产状态完成。`--strict` 会把 warning 作为失败。来源 SHA、gate、binding audit 等内容血缘错误是 hard error；任何生产和 QA 命令还会通过 `require_approvals` 硬阻断非 current 审批。

初始化产生的空派生容器不是错误，也不是完成：

- 在运行 `prepare-narration` 前，空 `director.pages` 和 `manifest.slides` 表示尚未派生；
- 在视觉制作前，视觉项目的空 `svg_layer_plan.pages` 表示尚未设计；纯音频项目没有该文件；
- 空 `build_state.approvals` 与 `qa` 表示从未审批和验收；
- 一旦进入相应生产或 QA 阶段，页面集合必须完整，不能用空数组通过。

## 音频验收

audio QA 自动检查：

- director、旁白 manifest、声音配置和音频时间轴页码一致；
- performance audit 确认表现契约当前、书面语气不是统一模板，并且实际 SSML 参数包含足够的可听 profile；
- `video/audio/NN.mp3` 恰好覆盖全部页面；
- 每个 MP3 可解析且非空；
- 同一连续章节的 bookmark 元数据、digest、页面集合和逐页 MP3 SHA 一致；自动检查不能证明偏移听感一定正确；
- manifest 的声音摘要对应当前 `voice_profile.json`；
- 旁白审阅稿和 QA 证据列出当前正文已命中的发音规则，以及尚未配置的拉丁技术代号；未覆盖项产生明确 warning，不因正则候选自动阻断生产；
- `advance_ms = 真实 MP3 毫秒 + advance_safety_ms`；
- 时间轴保留目标时长、真实偏差和仅供审阅的 rate 修正建议；偏差过大的页面产生 warning，不自动覆盖导演稿；
- 没有部分章节使用旧 fingerprint、部分章节使用新配置。

人工试听至少确认：

- 专有名词、缩写、工程数字和单位；
- 材料成分牌号是否按元素语义口播，例如 `AlSi10Mg` 读“铝硅十镁”，而不是让中文 TTS 猜测混合字符；
- 中文、英文及中英混读；
- 页边界没有吞字、重复、突兀静音或错误切分；
- 音色、语速和音高符合受众与场景。

自动 QA 不能声称实际发音已经人工通过。

## 单页 SVG 局部检查

单页 SVG 设计改稿且不更新 PPTX、动画或视频时，不运行本文件定义的整套 QA 等级。只按 `visual-and-animation.md` 对目标文件做解析、画布、资源引用、安全区、全尺寸渲染和缩略图目视检查，并在结果中写明目标文件与未同步的下游交付物。

该检查不写入 `build_state.json`，不产生 static QA PASS，也不能维持依赖旧 SVG fingerprint 的 visual 审批或下游 QA 为 current。用户后续要求同步正式演示交付物时，再按实际影响的层级装配和验收；内容与音频未变时不重跑输入、旁白或 audio QA。

## 视觉、PPTX 与视频验收

### Static

- 工作模板存在且是有效 PPTX；
- manifest 页码连续，源 SVG 存在且画布正确；
- 当前静态或动画 PPTX 页数与 manifest 一致，并具有匹配内容字节与视觉输入的 provenance；
- PPTX 包中内嵌 SVG 数量不低于页数；该结构检查不能单独证明每页视觉与对应源 SVG 像素一致；
- 动画输出逐页具有非空 OOXML `timing/tnLst`；每个 beat 以 `sNN_<beat_id>` 唯一稳定对象名映射到一个真实 shape，并具有匹配 manifest 的 entrance `fade`/`wipe(direction)`，时长为 1–1000ms 且匹配 timing sidecar；onClick、畸形 filter、只有 sidecar 或空 `p:timing` 不能通过；
- 图片、音频和媒体关系没有外部绝对路径。

交付前建议在 PowerPoint 中检查字体替换、裁切、重叠、截图清晰度和安全区。当前状态机不记录静态/动画实机观看证据，因此结构 QA 不能冒充这项人工质量确认。

### Standard

- 当前动画基线已有 current static QA PASS；standard fingerprint 同时绑定 static fingerprint、状态记录与报告文件实际 SHA，删除、篡改或跳过该报告都会阻断；
- 当前动画基线的 PPTX SHA、内容字节 fingerprint 和 visual fingerprint 都与记录一致；
- 使用独立的 `outputs.narrated_pptx`，不覆盖动画基线；
- 每页恰好一个内部 MP3，页面之间不共享媒体成员；
- 内嵌字节与逐页 MP3 一致；
- 每页自动播放，`advTm` 来自真实时长；
- 演示启用 timings、narration 和 animation。

### PowerPoint 视频导出

`export-video` 只允许 `deliverable=video`，并要求当前 standard QA 有效。命令确认 PowerPoint 导出过程成功、导出报告存在且输出 MP4 非空；再按 ProductReleaseIds/Build 决定是否把 Office 2019 的 full-range 像素映射为 limited range 并重新编码 H.264，最后记录 PPTX、最终 MP4、PowerPoint 身份、兼容决策与报告摘要。

Office 2019 的重编码是已知兼容修复，不是通过抽帧或观看得出的画面检查。完成后立即停止，不运行 ffprobe、额外时长检查、抽帧、播放、人工完整观看或 release QA。非空文件检查只是确认 PowerPoint/FFmpeg 确实产出交付物，不是视频内容验收。

## 缓存与失败处理

QA 在深度检查前计算当前等级依赖和检查脚本 fingerprint。只有此前状态为 `passed`、报告文件存在，报告摘要、等级、状态、fingerprint、errors、证据结构及相应产物 provenance 都一致且未使用 `--force` 时，才允许缓存命中：

```text
SKIP qa=audio: inputs and tools unchanged
```

失败结果不能缓存为通过。audio fingerprint 不包含模板和 SVG；static fingerprint 不包含声音和 MP3。standard 复用有效 audio 报告，不重复执行整套低层检查。

| 表现 | 处理 |
|---|---|
| `page-narration` 被要求产品计划字段 | 检查 profile；不得改写演讲稿迎合 narrative-plan |
| identity 项目出现摘要型 `page-script.md` | 恢复项目内源稿的逐页正文，重新内容审批 |
| identity 项目确需改写 | 由用户明确授权，使用 `--allow-substantial-rewrite` 在同一次 content 审批中切换为 adapted 并写入新审计 |
| input gate 契约升级但源稿字节未变 | 运行 `refresh-input-gate`，再重新 content 审批；保留内容字节未变的下游产物 |
| adapted 输入没有显式逐页稿 | 停止；使用 `--page-script-source` 提供实际口述正文 |
| 初始化后显示“第 1 页已完成” | 错误；空派生状态不得当成示例页或完成状态 |
| 改声音后仍能直接合成 | 错误；刷新审阅稿并重新批准 narration；试听是推荐的人工质量步骤 |
| `narration_audio` 被视觉依赖阻断 | 使用 audio 阶段与 audio QA，检查是否误走 PPTX 链 |
| 一个音频跨多页 | 整章合成后按 bookmark 切成逐页 MP3 |
| 页面过早切换 | 重新读取真实 MP3 时长并加安全余量 |

## 自动化完成定义

以下定义描述状态机可证明的机器链路；静态视觉、动画播放和自然听感的人工确认属于推荐的最终交付签核，不伪装成已记录状态。视频按用户要求不做导出后检查。

- `narration_audio`：content 与 narration 审批有效，全部逐页 MP3、bookmark、真实时间轴和 audio QA 通过。
- `static_pptx`：content 与 visual 审批有效，静态 PPTX 和 static QA 通过。
- `animated_pptx`：当前动画基线 provenance、首秒动画结构和针对动画输出的 static QA 有效。
- `narrated_pptx`：逐页 MP3、真实时间轴、独立旁白 PPTX 和 standard QA 通过。
- `video`：旁白 PPTX 的 standard QA 通过，PowerPoint 导出成功，适用的 Office 2019 像素色阶重编码完成，导出报告存在且产生非空最终 MP4；到此停止。
