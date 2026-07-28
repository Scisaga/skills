# 输入文档质量门禁

## 目录

- [目的](#目的)
- [为什么采用两层门禁](#为什么采用两层门禁)
- [输入类型](#输入类型)
- [自动预检](#自动预检)
- [语义复核](#语义复核)
- [通过与阻断规则](#通过与阻断规则)
- [返工循环](#返工循环)
- [复核文件契约](#复核文件契约)
- [Goodwen 基线的启示](#goodwen-基线的启示)

## 目的

输入文档是页面叙事、事实边界和旁白的上游事实来源。文档质量不足时，直接制作 SVG、PPTX 或视频只会把缺口固化到更多产物中。

门禁必须位于整个流程最前面：

```text
输入 Markdown
  → 自动预检
  → 语义复核
  → 输入质量门禁
      ├─ PASS：建立演示项目
      └─ BLOCKED：只输出返工报告，停止后续制作
```

不得为了赶进度先做几页“占位设计”。文档发生任何修改后，原语义复核会因 SHA-256 不匹配而失效，必须重新检查。

## 为什么采用两层门禁

自动预检适合检查确定性问题：

- frontmatter 和关键字段是否存在；
- 标题、页码和章节结构是否完整；
- 本地链接和图片是否存在；
- 是否残留 `TODO`、`TBD`、`FIXME` 等未关闭占位符；
- 逐页源稿是否满足渲染器的结构契约。

自动规则不能可靠判断：

- 核心主张是否真的成立；
- 叙事是否前后连贯；
- 证据能否支持结论；
- 某个数字究竟是事实、目标还是假设；
- 内容是否值得做成一页；
- 旁白是否能自然讲述。

因此第二层必须由智能体阅读完整文档并给出有文档内证据的语义复核。两层任一失败都阻断后续。

该门禁能阻止结构缺失、旧复核、空证据和无法定位的证据，但不是防恶意篡改的签名系统。真正的语义质量仍依赖被记录的智能体或人工复核者完成全文审查；不得让脚本自动把所有维度改成 `pass`。

## 输入类型

### `narrative-plan`

适用于产品计划书、投资人材料、课程大纲、方案说明等“先形成完整论证，再映射为演示”的文档。

最低结构包括：

- 目标受众；
- 具体问题；
- 产品答案或解决路径；
- 可感知的案例、任务或场景；
- 事实、证据、假设和待验证边界；
- 价值或采用逻辑；
- 风险、边界或下一步；
- 逐页演示映射。

### `execution-plan`

适用于实施计划、竞赛执行方案、迭代计划和交付操作手册。

最低结构包括：

- 范围和非目标；
- 事实或状态标签；
- 交付物和执行动作；
- owner 与时间安排；
- 验收或完成定义；
- 风险与阻断条件；
- 来源或依据；
- 如果要制作演示，还应说明演示受众和汇报结构。

### `presentation-source`

适用于已经按页编排、由渲染器直接生成 PDF/PPTX 的 Markdown 源稿。

最低结构包括：

- frontmatter 中的页数、画布和事实政策；
- 连续的 `## PAGE N/T｜标题`；
- 每页一个 `layout: visual` 标记；
- 每页恰好一张完整页 SVG；
- 每页一段 `speaker-notes`；
- 所有本地视觉资源真实存在。

`auto` 根据 PAGE 标记、文件身份和标题自动选择 profile。自动判断错误时应显式传入 profile，而不是修改文档伪装类型。

## 自动预检

先运行：

```bash
bash skills/build-narrated-presentation/scripts/run.sh inspect-input \
  --document /path/to/source.md \
  --profile auto \
  --json-output /path/to/input-preflight.json \
  --markdown-output /path/to/input-preflight.md
```

自动预检的 `blocking` 必须全部清零。`warning` 不会单独使命令失败，但必须进入语义复核，不能被忽略。

常见自动阻断包括：

- 缺少 frontmatter、标题、状态、受众或事实政策；
- 普通文档没有唯一 H1；
- 内容短到不足以支撑演示；
- 关键叙事模块缺失；
- 没有逐页映射；
- 未关闭占位符；
- 本地链接或图片失效；
- PAGE 页码不连续或总页数不一致；
- 视觉页不是恰好一张 SVG；
- 页面缺少 speaker notes。

## 语义复核

自动预检通过后，用当前文档生成 SHA-256 绑定的模板；预检未通过时该命令不会创建模板：

```bash
bash skills/build-narrated-presentation/scripts/run.sh prepare-input-review \
  --document /path/to/source.md \
  --profile auto \
  --output /path/to/input-review.json
```

智能体必须阅读完整文档，再逐项填写：

- `status`：`pass`、`revise` 或 `block`；
- `evidence`：结构化的 `heading`、`line`、`quote`，必须能在当前文档真实定位；
- `issues`：当前缺口及其影响；
- `required_changes`：可验收的返工要求。

未通过时还必须填写 `revision_plan`，每项至少说明优先级、文档位置、问题、所需修改和验收标准。标记 `pass` 的维度不能同时保留未关闭的 `issues` 或 `required_changes`。

`narrative-plan` 复核：

- `purpose_audience`
- `narrative_coherence`
- `fact_evidence_integrity`
- `content_completeness`
- `presentation_readiness`
- `language_clarity`

`execution-plan` 复核：

- `purpose_scope`
- `fact_status_integrity`
- `deliverables_ownership`
- `acceptance_readiness`
- `risk_feasibility`
- `presentation_readiness`

`presentation-source` 复核：

- `page_narrative`
- `fact_evidence_integrity`
- `page_completeness`
- `visual_readiness`
- `narration_readiness`
- `language_clarity`

标记 `pass` 时必须至少提供一条文档内证据，六个维度合计至少覆盖四个不同位置。`reviewer` 必须记录复核者名称、类型、`full-document-review` 方法和完整复核声明。不能因为“看起来不错”而通过，也不能由自动脚本伪造语义复核或直接信任外部提供的 `pass` 文件。

## 通过与阻断规则

完整门禁命令：

```bash
bash skills/build-narrated-presentation/scripts/run.sh validate-input \
  --document /path/to/source.md \
  --profile auto \
  --review /path/to/input-review.json \
  --json-output /path/to/input-gate.json \
  --markdown-output /path/to/input-gate.md
```

只有以下条件同时满足才返回退出码 0：

1. 自动预检没有 `blocking`；
2. 复核文件的文档 SHA-256 与当前输入一致；
3. 复核 profile 一致；
4. 所有必需语义维度均为 `pass`；
5. 每个 `pass` 都有可在当前 SHA 文档中核验的章节、行号和摘录；
6. `blocking_findings` 与 `revision_plan` 均存在且为空；
7. 总决策为 `pass`。

其他情况返回非零退出码。`init --input-document` 会再次执行同一门禁，不能用旧复核或手工修改 `project.json` 绕过。

`init` 不提供空白绕过模式。没有输入文档时，先创建一份说明受众、目标、事实边界和演示映射的 Markdown 输入稿，再从自动预检开始。

## 门禁失效边界

输入文档内容变化会改变 SHA-256，旧语义复核立即失效。旁白文字、页面主张或章节归属变化虽然不一定修改输入文件，也必须重新核对其与通过门禁文档的一致性。

下列声音生产参数不属于输入文档语义，不使门禁失效：

- TTS 提供方和音色；
- 全局语速与音高；
- 导演稿中的局部语速、音高与停顿；
- 风格参数；
- 页面边界停顿；
- 品牌别名、IPA/phoneme 和其他发音词典规则。

这些参数只在 `video/voice_profile.json` 中维护，并按音频增量链路处理。

## 返工循环

门禁失败时：

1. 停止生成 SVG、PPTX、动画、音频和视频；
2. 按 Markdown 报告中的 `blocking` 排序返工；
3. 优先修复主张、事实边界和结构，再处理措辞；
4. 修改原输入文档，不在演示稿里偷偷补另一套事实；
5. 重新运行自动预检；
6. 重新生成 SHA-256 绑定的语义复核模板；
7. 重新完整阅读和复核；
8. 门禁通过后才初始化或继续演示项目。

返工要求应写成可验收变化，例如：

- 不写“补充市场数据”，而写“为市场规模数字增加直接来源，并标明数据年份和适用区域”；
- 不写“逻辑更清晰”，而写“在产品定义前增加目标用户和具体任务，并让后续商业模式引用同一对象”；
- 不写“丰富 PPT”，而写“补齐 12 页映射，每页给出标题、单一主判断、证据和视觉意图”。

## 复核文件契约

示意结构：

```json
{
  "schema_version": 1,
  "document": "/absolute/path/to/source.md",
  "document_sha256": "<sha256>",
  "profile": "narrative-plan",
  "reviewer": {
    "name": "Codex",
    "kind": "ai-agent",
    "method": "full-document-review",
    "attestation": "I reviewed the entire current document and the cited evidence supports each assigned category."
  },
  "decision": "pass",
  "categories": {
    "purpose_audience": {
      "status": "pass",
      "evidence": [
        {
          "heading": "1. 第一批客群",
          "line": 221,
          "quote": "首批用户的共同点不是某个职业标签"
        }
      ],
      "issues": [],
      "required_changes": []
    }
  },
  "blocking_findings": [],
  "revision_plan": []
}
```

模板资产 `assets/input-review-template.json` 只展示字段。实际使用必须通过 `prepare-input-review` 生成，以写入当前文档摘要和正确的 profile 维度。

## Goodwen 基线的启示

方法来源目录中的文档展示了三种不同质量契约：

- [`01_Goodwen_Investor_Product_Plan.md`](https://github.com/Scisaga/md-quiz/blob/main/docs/biz/goodwen_2026/01_Goodwen_Investor_Product_Plan.md) 先明确受众、核心主张、具体任务、事实政策、商业路径、风险和 13 页映射，适合作为 `narrative-plan` 基线；
- `02`、`03`、`04` 类执行文档使用“现有/待实现/验收”或“官方要求/内部建议/待团队填写”等显式状态，并把交付动作、owner、检查清单和风险放进同一闭环；
- `Goodwen_SuperAgent_项目计划书.md` 与技术架构附录已经逐页化，每页绑定一张 SVG 和 speaker notes，适合作为 `presentation-source` 基线。

这些共性应被复用，但 Goodwen 的产品事实、页数和业务叙事不能成为其他项目的默认内容。完整目录见 [`docs/biz/goodwen_2026`](https://github.com/Scisaga/md-quiz/tree/main/docs/biz/goodwen_2026)。
