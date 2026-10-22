# Scisaga 工具箱

九个演示、语音、文档、视频与运维技能。插件名 `scisaga`，marketplace 名 `scisaga-skills`，当前版本由根目录 `plugin.json` 统一维护。源码短名称、插件身份和独立安装名称分别为 `slides`、`scisaga:slides` 和 `ss-slides`。

## 安装与更新

先安装 [Codex](https://developers.openai.com/codex/cli/) 或 [Claude Code](https://code.claude.com/docs/en/setup)，并准备 Python 3、Git：

```bash
python -m pip install -r requirements-tools.txt
python scripts/manage_skills.py install --agent codex --mode plugin
python scripts/manage_skills.py install --agent claude-code --mode plugin
```

上面跟踪 GitHub `Scisaga/skills` 的 `main`；**本地尚未发布的修改使用 `--source .`**。固定版本或提交用 `--ref <tag-or-commit>`。插件通过客户端原生命令安装。Codex 中使用 `$scisaga:slides`，Claude Code 中使用 `/scisaga:slides`。

兼容 Codex IDE 等独立技能场景：

```bash
python scripts/manage_skills.py install --agent codex --mode standalone --skill slides --source .
python scripts/manage_skills.py install --agent codex --mode standalone --skill video --alias speech=my-speech --source .
```

默认名称均带 `ss-`；同名冲突用 `--alias slides=my-slides` 共存。`video` 自动带入 `speech`，并按安装映射调用。后续更新保留别名和本地配置。

```bash
python scripts/manage_skills.py check --agent codex --mode plugin --remote
python scripts/manage_skills.py update --agent codex --mode plugin
python scripts/manage_skills.py launch codex --
```

`launch codex` 在启动前限时 60 秒更新，失败且已有可用安装时继续启动；直接运行 `codex` 不保证经过此更新流程。Claude Code 需在 `/plugin` → Marketplaces → `scisaga-skills` 开启第三方 marketplace 自动更新，更新在重新加载或下次会话生效。完整安装、冲突处理、隔离测试、迁移和卸载见 [安装与更新规范](spec/installation-and-updates.md)。

安装技能、初始化 Python/系统依赖和配置外部服务是三个步骤。Speech/Slides 配音默认优先 Qwen，失败时整份尝试 Azure；从项目 `.env` 或外部 `--env-file` 读取配置。仅使用 Qwen 不要求 Azure Key/SDK，详见 [Speech 运行说明](skills/speech/references/usage.md)。

## 当前 Skills

| Logo | 技能名称 | 描述 |
|---|---|---|
| <img src="skills/termux-ssh/assets/logo.svg" alt="Android Termux SSH logo" width="44"> | [`termux-ssh`](skills/termux-ssh/) | 在 Android 上部署同源 Termux、SSH 公钥登录、Boot/runit 自启动、息屏保活、Termux:API、可选本地蓝牙 companion 与 Codex CLI、设备能力清单、共享存储、登录根目录 AGENTS.md 和 Ubuntu 风格 Bash，并完成不依赖 ADB 的局域网验收。 |
| <img src="skills/slides/assets/logo.svg" alt="Slides logo" width="44"> | [`slides`](skills/slides/) | 保真绑定逐页演讲稿并编排语速、音高和停顿，优先 Qwen3 自托管配音、不可用时回退 Azure；生成每页 MP3、静态/动画/旁白 PPTX 或视频，支持专业技术图示参考、真实音频边界切页、模板复用、增量重建和分级验收。 |
| <img src="skills/dev-ops/assets/logo.svg" alt="Dev Ops logo" width="44"> | [`dev-ops`](skills/dev-ops/) | 维护部署脚本、服务资产、Compose、远程发布和主机级安装流程。 |
| <img src="skills/domain-manager/assets/logo.svg" alt="Domain Manager logo" width="44"> | [`domain-manager`](skills/domain-manager/) | 通过计划确认门禁安全管理 Gandi 与 Dynadot 的域名、DNS、nameserver、DNSSEC、续费与转移。 |
| <img src="skills/gitlab-issue/assets/logo.svg" alt="GitLab Issue logo" width="44"> | [`gitlab-issue`](skills/gitlab-issue/) | 通过统一入口管理当前自托管 GitLab 仓库的 issue，并强制校验 origin 与实例一致。 |
| <img src="skills/pdf/assets/logo.svg" alt="PDF logo" width="44"> | [`pdf`](skills/pdf/) | 本地处理 PDF 水印、骑缝章、页面重排、批量操作以及 PDF/图片转换。 |
| <img src="skills/speech/assets/logo.svg" alt="Speech I/O logo" width="44"> | [`speech`](skills/speech/) | 自托管 Qwen TTS 优先、Azure 回退，生成 MP3 与实际后端记录；通过自托管 Qwen ASR 转写音频。 |
| <img src="skills/subtitle-matcher/assets/logo.svg" alt="Subtitle Matcher logo" width="44"> | [`subtitle-matcher`](skills/subtitle-matcher/) | 批量查找、下载、评分、校验并规范化中文字幕，生成可交互报告。 |
| <img src="skills/video/assets/logo.svg" alt="Video Toolkit logo" width="44"> | [`video`](skills/video/) | 抽帧、抽音频、检索或生成字幕、封装字幕、校验同步并整理影片信息。 |

## 目录结构

```text
.
├── skills/
│   ├── termux-ssh/
│   ├── slides/
│   ├── dev-ops/
│   ├── domain-manager/
│   ├── gitlab-issue/
│   ├── pdf/
│   ├── speech/
│   ├── subtitle-matcher/
│   └── video/
├── template/
│   └── skill-template/
├── spec/
├── scripts/manage_skills.py
├── plugin.json
├── .codex-plugin/
├── .claude-plugin/
├── .agents/plugins/marketplace.json
├── .env.example
├── AGENTS.md
└── README.md
```

## 说明

- `skills/`：真实可用的 skill
- `template/`：新建 skill 时可复制的基础模板
- `spec/`：仓库级结构约定与编写规范

## 分发原则

- `skills/` 是唯一源码；插件内使用短名称，独立安装生成带前缀或别名的视图。
- 根目录 `plugin.json` 是插件身份与版本的唯一来源；兼容清单由 `package --sync-manifests` 生成并校验。
- `package` 按允许列表打包真实文件，不包含真实 `.env`、虚拟环境、缓存或生成产物。

## 常用入口

```bash
bash skills/termux-ssh/scripts/run.sh help
bash skills/slides/scripts/run.sh help
bash skills/domain-manager/scripts/run.sh help
bash skills/gitlab-issue/scripts/run.sh help
bash skills/pdf/scripts/run.sh help
bash skills/speech/scripts/run.sh help
bash skills/subtitle-matcher/scripts/run.sh help
bash skills/video/scripts/run.sh help
bash skills/dev-ops/scripts/run.sh help
```

## 环境变量

仓库级示例配置见 [.env.example](.env.example)。建议放在当前项目 `.env`；共享配置通过 `--env-file` 引用插件缓存外的文件。Speech/Slides 按进程变量 → 显式文件 → 当前目录 → 技能目录 → 脚本目录补充缺失配置。从其他项目调用时不会自动读取源码仓库根目录 `.env`。不要提交密钥或含凭据的代理地址。

## 维护原则

- 根目录只放仓库级文档和规范，不直接放具体 skill
- 每个 skill 自包含，至少包含 `SKILL.md`
- 详细说明放 `references/`
- 稳定可复用流程放 `scripts/`
- 输出资源或模板放 `assets/`

更细规则见 `AGENTS.md` 和 `spec/`。
