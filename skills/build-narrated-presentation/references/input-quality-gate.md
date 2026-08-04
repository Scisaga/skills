# 输入身份、门禁与逐页稿绑定

## 目录

- [目标](#目标)
- [输入 Profile](#输入-profile)
- [正常入口只执行一次门禁](#正常入口只执行一次门禁)
- [逐页演讲稿的 identity 绑定](#逐页演讲稿的-identity-绑定)
- [其他输入的 adapted 绑定](#其他输入的-adapted-绑定)
- [诊断命令](#诊断命令)
- [失效与返工](#失效与返工)

## 目标

门禁回答两个问题：

1. 当前文件属于哪种输入身份，是否满足该身份的确定性契约；
2. 初始化后的 `page-script.md` 与用户指定内容源是什么关系。

门禁不得把“结构不匹配”解释成“需要自动摘要”。尤其是已经逐页写好的演讲稿，必须保留完整口述正文；禁止另建 `normalized-input.md`、摘要表或项目说明来替换用户源稿。

`init` 将原始输入原样复制为 `inputs/source.md`，把当前 SHA-256、profile、门禁报告和逐页稿绑定写入项目。后续验证使用项目内副本，不依赖外部文件继续存在。

## 输入 Profile

| Profile | 用途 | 确定性要求 | 语义复核 |
|---|---|---|---|
| `page-narration` | 已经整理好的逐页口述稿 | 连续的 `## 第 N 页｜标题` 或纯旁白 `## PAGE N/T｜标题`、每页至少 20 个实际可朗读字符 | 不要求 |
| `narrative-plan` | 产品计划、课程大纲、方案说明 | UTF-8、基本可读、引用路径可解析；内容充分性留给一次语义复核 | 要求 |
| `execution-plan` | 实施计划、执行方案、操作手册 | UTF-8、基本可读、引用路径可解析；执行闭环留给一次语义复核 | 要求 |
| `presentation-source` | 已含 SVG 和 speaker notes 的渲染型 Markdown | `## PAGE N/T｜标题`、完整视觉资源和 notes | 要求 |

`auto` 先区分带实际 SVG、`<!-- speaker-notes: ... -->`、`<!-- layout: visual -->` 或结构化 `source_svg:` 字段的渲染型 PAGE 契约，再把中文标题或不含这些结构标记的 PAGE 稿识别为逐页口述稿，最后才判断计划类型。正文中只是讨论 `speaker-notes`、`source_svg` 等术语不会触发渲染识别。识别不正确时显式传入 `--input-profile`；不要改写正文来伪装 profile。

### `page-narration` 契约

逐页标题采用：

```markdown
## 第 1 页｜开场 · 30 秒

各位领导、各位同事，大家好……
```

阻断性硬检查只覆盖下游真正需要的机械条件：

- 页码从 1 连续排列；
- 标题至少 2 个字符；
- 每页至少有 20 个从 Markdown 正文规范化得到的实际可朗读字符；图片路径、SVG、HTML 注释和排版标记不能充当正文；
- 不得包含 SVG、`layout: visual`、speaker-notes 等渲染标记。

审计还会从标题读取可选目标秒数，并记录正文摘要、字符保留率、覆盖率和工程数字遗漏。这些字段用于差异审阅，不单独阻断 identity；真正的默认阻断是非字节一致。

这个机械阈值只证明页面确实有可朗读内容，不判断观点是否完整或讲述是否优质。对于已经整理好的逐页稿，防止“摘要替换原稿”的主要约束是字节级 identity 绑定；对于 adapted 稿，内容审批负责审阅差异证据。工程数字检查用于发现改写遗漏，不代表数字已经获得事实来源或工程验证。

### 计划与渲染型输入

这些输入不是逐页口述稿。计划类输入的确定性预检检查 UTF-8、至少 200 字符的基本正文和本地引用；占位符只提示 warning，不再强制标题、关键词、固定 H2 数量或映射表行数。`presentation-source` 走另一套专用契约：PAGE 连续性和总数、标题、单一 layout 标记、实际存在且为 1600×900 的本地 SVG，以及非空 speaker-notes。语义复核集中判断主张、证据边界、内容完整性、执行闭环和演示可制作性，并绑定当前输入 SHA-256。

## 正常入口只执行一次门禁

不要按 `inspect-input → prepare-input-review → validate-input → init` 连续执行四遍。正常入口如下。

### 已整理逐页演讲稿

直接初始化；`init` 内部执行一次完整门禁，并写入 `input-gate.json` 与 `input-gate.md`：

```bash
run.sh init \
  --output PROJECT \
  --name "项目名称" \
  --deliverable narration_audio \
  --input-document 演讲稿.md
```

`page-narration` 不需要 `input-review.json`。即使调用方误传 review，门禁也只记录“已忽略”的 info，不执行计划类语义复核，也不把该文件复制进项目。

对 `page-narration` 误运行 `prepare-input-review` 时命令直接 SKIP 且不写文件，避免重新引入无用复核状态。

### 计划或渲染型输入

先生成一次 SHA 绑定的语义复核模板，完整阅读并填写；然后让 `init` 执行唯一一次完整 gate：

```bash
run.sh prepare-input-review \
  --document source.md \
  --profile auto \
  --output input-review.json

run.sh init \
  --output PROJECT \
  --name "项目名称" \
  --deliverable narrated_pptx \
  --input-document source.md \
  --input-review input-review.json \
  --page-script-source prepared-page-script.md
```

不要在这两个命令之间再运行 `validate-input`。`prepare-input-review` 已执行确定性预检，`init` 会验证当前文件、复核 SHA、profile 和结论，并保存门禁报告。

语义复核只保留一层分类状态和一个总决策。每个必需维度使用 `pass`、`revise` 或 `block`，并提供当前文档中可定位的 `line`、`quote` 和可选 `heading`；未通过时直接在该维度填写 `issues` 与 `required_changes`。模板中的 `attestation` 初始为 `false`，只有实际读完全文后才改为 `true`。不再重复维护 `blocking_findings`、`revision_plan`、“至少四个证据位置”或为了门禁强制补 Markdown 标题等派生状态。

## 逐页演讲稿的 identity 绑定

当输入是 `page-narration` 且未提供 `--page-script-source` 时：

```text
用户输入 ──原样复制──> inputs/source.md
    └──────原样复制──> page-script.md
```

初始化记录：

- `source.document_sha256`：项目内原始源稿摘要；
- `source.gate_report_sha256` 与 `source.review_sha256`：入口门禁和可选语义复核的证据摘要；
- `source.page_script_sha256_at_init`：初始化时逐页稿摘要；
- `content.binding_mode: identity`：源稿与逐页稿逐字节一致；
- `content.binding_audit`：指向源 SHA、逐页稿 SHA、字符覆盖和工程数字遗漏报告；
- `content.page_script_origin_document`：初始化时实际逐页稿来源路径；
- `content.page_count_at_init`：识别到的页数。

内容审批再次检查页码、每页正文和源稿保真。不能用“核心结论、视觉意图、事实边界”表格替代实际口述内容。

## 其他输入的 adapted 绑定

`narrative-plan`、`execution-plan` 和 `presentation-source` 初始化时必须显式传入 `--page-script-source`。逐页稿采用 `## 第 N 页｜标题` 或 `## PAGE N[/T]｜标题`（也接受 ASCII `|`），包含实际要讲的正文，且不得含渲染标记。

```text
事实源 source.md ──语义复核──> inputs/source.md
人工整理的逐页稿 ────────────> page-script.md
                                  binding_mode: adapted
```

脚本不负责从计划自动摘要出逐页稿。整理时保留事实边界，明确新增、删减和重写，不把派生文案反向当成原始事实。

对于 `page-narration` 的显式改写稿，也必须使用 `--page-script-source`。只要不再与源稿逐字节一致，默认就以一个明确的 identity mismatch 阻断；页码集合不一致仍是独立的机械错误。正文保留率、覆盖率和工程数字遗漏写进差异证据并显示警告，不再为同一次非 identity 状态重复制造多个 blocker。

只有用户明确同意改写时，才可使用 `--allow-substantial-rewrite`。参数名为兼容现有命令保留；它实际表示“允许脱离 identity”，不是只有删改达到某个比例才需要。初始化或 content 审批会把授权绑定到当前源稿 SHA、逐页稿 SHA 和 binding audit；只要这些字节未变，后续重批、gate refresh 后重批或审计 contract 升级后重审都不再重复要求该参数。逐页稿再次变化时必须重新授权。该选项只记录授权，不代表改写质量自动通过。

## 诊断命令

`inspect-input` 用于解释 profile 和自动阻断，不是正常入口的必做步骤：

```bash
run.sh inspect-input \
  --document source.md \
  --profile auto \
  --markdown-output input-preflight.md
```

`validate-input` 用于在项目外单独验证现成的复核文件：

```bash
run.sh validate-input \
  --document source.md \
  --review input-review.json \
  --json-output input-gate.json \
  --markdown-output input-gate.md
```

它们不得与 `init` 机械串联并重复生成同一结论。

已存在项目遇到 input gate `contract_version` 升级、但 `inputs/source.md` 字节未变时，使用显式刷新入口：

```bash
run.sh refresh-input-gate --project PROJECT --input-profile auto
# 非 page-narration 先为 PROJECT/inputs/source.md 生成新版复核，再传入：
run.sh refresh-input-gate --project PROJECT \
  --input-review current-input-review.json
```

该命令只接受当前项目内源稿 SHA 未变的情况。默认 `auto` 重新识别项目内源稿，因此能纠正旧规则写入的错误 profile；确有歧义时才显式覆盖。gate/review 或 profile 证据发生变化时 content 审批失效，但内容字节 fingerprint 不变，因此视觉、旁白和二进制产物不被无意义重建；若刷新结果逐字节不变，content 审批保持 current，命令不会谎报 stale。源稿字节已经变化时不得使用刷新入口，应重新建立内容绑定。

## 失效与返工

- 初始化前输入变化：旧语义复核因 SHA 不匹配失效。
- 初始化后 `inputs/source.md` 变化：源稿绑定失效，重新门禁并明确更新项目。
- input gate 契约版本变化但项目内源稿未变：运行 `refresh-input-gate`，再重新 content 审批。
- `page-script.md` 变化：内容审批及其下游失效；`page-narration` 还要重新检查保真。
- 只修改音色、全局语速、音高或发音词典：不重新运行输入门禁，只使旁白审批和音频下游失效。

门禁失败时只修改被点名的源稿或逐页稿，不生成替代摘要，不提前制作 SVG、PPTX 或音频。自动规则与用户明确指定的输入身份冲突时，先修正规则或显式 profile，而不是改写用户内容迎合检测器。
