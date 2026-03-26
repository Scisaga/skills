# Skills 仓库

这个仓库用于集中维护一组可被 Codex 调用的本地 skill。  
当前内容不是“空模板”，而是已经包含多个可直接使用或继续演进的 skill。

如果你是：

- 想了解这个仓库里现在有哪些 skill
- 想知道每个 skill 大概负责什么
- 想按当前约定新增或改造 skill
- 想快速找到各 skill 的入口文件

先读本文件；真正执行某个 skill 相关任务时，再进入对应目录阅读它自己的 [`SKILL.md`](/mnt/c/Users/scisa/Desktop/skills/dev-ops/SKILL.md) 或脚本说明。

## 当前 Skill 列表

### [`dev-ops/`](/mnt/c/Users/scisa/Desktop/skills/dev-ops)

运维资产与部署脚本集合，覆盖：

- Docker Compose 服务端栈
- 主机级安装脚本
- DNS / DDNS / 证书续签
- 代理、VPN、远程发布等场景

它本身也是一个 skill，入口说明见：

- [`dev-ops/SKILL.md`](/mnt/c/Users/scisa/Desktop/skills/dev-ops/SKILL.md)

内部已经按服务拆成多个子目录，例如：

- `data-platform/`
- `ddns/`
- `gitlab/`
- `hysteria/`
- `keycloak/`
- `letsencrypt/`
- `minio/`
- `mysql/`
- `proxy/`
- `redis/`
- `unbound/`
- `wireguard/`

### [`pdf/`](/mnt/c/Users/scisa/Desktop/skills/pdf)

面向本地 PDF 的确定性处理 skill，当前已经覆盖：

- 替换指定页面
- 普通水印
- 栅格化并烧录水印
- 骑缝章
- 抽页 / 删页 / 重排 / 旋转
- 批量处理目录
- PDF 和图片互转

主要入口：

- [`pdf/SKILL.md`](/mnt/c/Users/scisa/Desktop/skills/pdf/SKILL.md)
- [`pdf/bootstrap.sh`](/mnt/c/Users/scisa/Desktop/skills/pdf/bootstrap.sh)
- [`pdf/scripts/run.sh`](/mnt/c/Users/scisa/Desktop/skills/pdf/scripts/run.sh)

### [`speech/`](/mnt/c/Users/scisa/Desktop/skills/speech)

语音相关 skill，覆盖：

- 文本转语音
- 音频转文本

当前默认组合是：

- TTS 使用 Azure Speech
- ASR 使用 OpenAI 兼容接口的 Qwen3-ASR 服务

主要入口：

- [`speech/SKILL.md`](/mnt/c/Users/scisa/Desktop/skills/speech/SKILL.md)
- [`speech/scripts/bootstrap.sh`](/mnt/c/Users/scisa/Desktop/skills/speech/scripts/bootstrap.sh)
- [`speech/scripts/run.sh`](/mnt/c/Users/scisa/Desktop/skills/speech/scripts/run.sh)

### [`video/`](/mnt/c/Users/scisa/Desktop/skills/video)

视频处理 skill，负责：

- 关键帧抽取
- 音频抽取
- 字幕生成
- 视频与字幕封装
- 字幕同步检查
- 结合联网搜索完成现成字幕和影片信息检索

主要入口：

- [`video/SKILL.md`](/mnt/c/Users/scisa/Desktop/skills/video/SKILL.md)
- [`video/scripts/bootstrap.sh`](/mnt/c/Users/scisa/Desktop/skills/video/scripts/bootstrap.sh)
- [`video/scripts/run.sh`](/mnt/c/Users/scisa/Desktop/skills/video/scripts/run.sh)

## 仓库结构约定

每个一级目录都可以是一个独立 skill，但要满足最小结构要求：

- 至少包含 `SKILL.md`
- 推荐提供：
  - `agents/openai.yaml`
  - `scripts/`
  - `references/`
  - `assets/`

当前仓库已经基本遵循这种结构。例如：

```text
.
├── dev-ops/
│   ├── SKILL.md
│   ├── agents/
│   └── references/
├── pdf/
│   ├── SKILL.md
│   ├── agents/
│   ├── references/
│   └── scripts/
├── speech/
│   ├── SKILL.md
│   ├── agents/
│   ├── references/
│   └── scripts/
└── video/
    ├── SKILL.md
    ├── agents/
    ├── references/
    └── scripts/
```

更具体的编辑规范见：

- [`AGENTS.md`](/mnt/c/Users/scisa/Desktop/skills/AGENTS.md)

## 如何使用这个仓库

### 1. 查看某个 skill 是否适合当前任务

先看目标目录下的 `SKILL.md` frontmatter 和正文结构，例如：

- [`pdf/SKILL.md`](/mnt/c/Users/scisa/Desktop/skills/pdf/SKILL.md)
- [`speech/SKILL.md`](/mnt/c/Users/scisa/Desktop/skills/speech/SKILL.md)
- [`video/SKILL.md`](/mnt/c/Users/scisa/Desktop/skills/video/SKILL.md)
- [`dev-ops/SKILL.md`](/mnt/c/Users/scisa/Desktop/skills/dev-ops/SKILL.md)

### 2. 首次使用脚本型 skill 时先做环境准备

典型例子：

```bash
bash pdf/bootstrap.sh
bash speech/scripts/bootstrap.sh
bash video/scripts/bootstrap.sh
```

### 3. 日常优先走统一入口

例如：

```bash
bash pdf/scripts/run.sh --help
bash speech/scripts/run.sh --help
bash video/scripts/run.sh --help
```

`dev-ops/` 因为内部是多服务集合，不存在一个统一总入口；应进入具体服务目录再执行对应脚本。

## 维护已有 Skill

### 编辑顺序

推荐顺序：

1. 先读目标 skill 的 `SKILL.md`
2. 再按需读 `references/`
3. 最后再看 `scripts/`

不要反过来一上来就从脚本细节开始，除非你已经明确知道入口。

### 什么时候改 `SKILL.md`

需要改 `SKILL.md` 的典型情况：

- 入口脚本变化了
- 工作流变化了
- 触发条件变化了
- 新增了必须让 Codex 知道的资源导航

不适合塞进 `SKILL.md` 的内容：

- 冗长背景说明
- 大段排障细节
- 低频参数说明
- 大段 API / schema 细节

这些内容应放进 `references/`。

### 什么时候改 `agents/openai.yaml`

如果 skill 的名称、用途、默认提示已经和 `SKILL.md` 不一致，就应该一起更新。  
不要只改一边。

### 什么时候改 `scripts/`

适用于以下情况：

- 同类操作会重复出现
- 需要确定性
- 手工命令容易出错
- 需要把复杂流程收敛成固定入口

## 敏感信息约定

这个仓库明确要求避免把真实敏感信息写进版本控制。

基本原则：

- 不提交 `.env`
- 不提交 `.env.local`
- 不提交运行时生成的 token、证书、私钥
- 示例域名统一用 `example.com`
- 示例地址优先用 `127.0.0.1` 或安全占位值

当某个 skill 需要真实参数时：

- 通用非敏感默认值写在 `.env.example`
- 真正的密钥、密码、访问令牌写在本地 `.env.local`
- 如有本地维护文件，也放未纳入版本控制的位置

例如：

- `dev-ops/unbound/local-records.conf`
- `dev-ops/unbound/forward-zones.conf`

## 新建或改造 Skill 的建议

新增 skill 时，尽量保持：

- 一目录一能力域
- `SKILL.md` 精简
- 详细内容进入 `references/`
- 稳定操作进入 `scripts/`
- UI 元数据与 `SKILL.md` 保持一致

如果只是补充说明，不要随手在 skill 目录里新增 `README.md`、`CHANGELOG.md`、`INSTALLATION_GUIDE.md` 之类文档。  
这个约束见：

- [`AGENTS.md`](/mnt/c/Users/scisa/Desktop/skills/AGENTS.md)

根目录这个 [`README.md`](/mnt/c/Users/scisa/Desktop/skills/README.md) 负责仓库级说明；skill 内部则优先依赖 `SKILL.md + references/ + scripts/`。

## 校验建议

修改某个 skill 后，至少做以下检查：

- 目录结构仍符合约定
- `SKILL.md` 与实际入口一致
- 脚本帮助信息仍能说明真实用法
- 没有把敏感信息写回仓库

当前仓库中，`dev-ops/` 已接入 skill 结构校验，可使用：

```bash
python3 /home/scisaga/.codex/skills/.system/skill-creator/scripts/quick_validate.py dev-ops
```

脚本修改后，通常还应补一轮：

```bash
bash -n <script>
```

## 备注

- 根目录当前可能存在本地开发用 `.env`，不要把它当成 skill 规范的一部分。
- `pdf/.venv/`、`video/.venv/` 等本地运行痕迹不是 skill 结构要求。
- 真正决定某个 skill 如何被 Codex 触发和使用的，仍然是各自目录下的 `SKILL.md`。
