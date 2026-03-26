# AGENTS Guide

本文件用于指导在当前仓库中创建、编辑和维护 skill。

## 仓库约定

- 每个 skill 直接放在项目根目录下，例如 `speech/`、`pdf/`、`example-writing-assistant/`。
- 一个 skill 至少包含 `SKILL.md`。
- 推荐为每个 skill 提供：
  - `agents/openai.yaml`
  - `scripts/`
  - `references/`
  - `assets/`

## 创建或编辑 Skill 的基本原则

- 优先保持 skill 自包含，不依赖仓库中其他 skill 的隐式上下文。
- `SKILL.md` 只写触发条件、工作流、关键命令和资源导航，不堆长篇背景说明。
- 详细参数、排障、接口细节放到 `references/`。
- 需要重复执行、需要确定性、或容易出错的操作，落成 `scripts/`。
- `agents/openai.yaml` 应与 `SKILL.md` 保持一致，尤其是名称、用途和默认提示。

## SKILL.md 规则

- frontmatter 只保留：
  - `name`
  - `description`
- `name` 使用小写短横线或现有目录名风格，并与目录语义一致。
- `description` 必须同时说明：
  - 这个 skill 做什么
  - 在什么场景下应触发
- 正文优先使用中文，除非 skill 本身明显要求英文。
- 正文结构优先包含：
  - 概述
  - 工作流
  - 命令模式
  - 资源使用
  - 输出规则

## 脚本型 Skill 运行约定

适用于像 `speech/` 这类依赖脚本执行的 skill。新建类似 skill 时，默认沿用同样模式。

### `.env` 读取规则

- 优先读当前工作目录的 `.env`
- 再读 skill 根目录的 `.env`
- 再读脚本同目录 `.env`

以当前 `speech/` 为例，实际顺序是：

- 当前工作目录 `.env`
- `speech/.env`
- `speech/scripts/.env`

### 依赖检查

- 脚本启动时应自动检测缺失依赖。
- 如果缺少依赖，必须直接提示安装命令，不要静默失败。
- 如果发现 `.env` 文件存在，但缺少 `python-dotenv`，应明确提示无法自动加载 `.env`。
- 如果 skill 依赖外部可执行文件，不要只写“请自行安装”。
- 这类 skill 应提供可执行文件的下载或安装脚本，并按操作系统区分。
- 至少考虑：
  - Linux
  - macOS
  - Windows
- 推荐放置方式：
  - `scripts/install-linux.sh`
  - `scripts/install-macos.sh`
  - `scripts/install-windows.ps1`
- 如果无法完全自动安装，也应提供最小可执行的下载脚本或占位脚本，明确：
  - 下载地址
  - 版本
  - 目标路径
  - 安装后的校验方式

### 统一入口

脚本型 skill 应提供以下入口：

- `bootstrap.sh`
  - 用于一条命令完成依赖安装和环境检查
- `run.sh`
  - 用于统一分发常用子命令
- 可选 `doctor.py`
  - 用于只做环境检查，不执行业务逻辑

以 `speech/` 为参考，推荐形式：

```text
skill-name/
├── SKILL.md
├── requirements.txt
├── agents/openai.yaml
├── references/
└── scripts/
    ├── bootstrap.sh
    ├── run.sh
    ├── doctor.py
    ├── common.py
    ├── <main-command>.py
    └── <secondary-command>.py
```

### 命令设计

- `bootstrap.sh` 负责：
  - 安装 `requirements.txt`
  - 检查环境变量
  - 检查外部服务可达性
  - 如有外部可执行依赖，提示或调用对应系统的安装脚本
- `run.sh` 负责：
  - 提供统一子命令入口
  - 屏蔽底层脚本路径差异
- Python 脚本负责：
  - 参数解析
  - 实际业务逻辑
  - 明确错误输出

## 编辑已有 Skill 时

- 先读 `SKILL.md`，再按需读 `references/` 和 `scripts/`。
- 不要新增无关文档，例如 skill 目录内的 `README.md`、`CHANGELOG.md`、`INSTALLATION_GUIDE.md`。
- 如果只是补充参数说明或排障，不要把大段内容塞回 `SKILL.md`，优先更新 `references/`。
- 如果新增了脚本入口，必须同步更新：
  - `SKILL.md`
  - `references/`
  - `agents/openai.yaml`（如有必要）
- 改造或新建 skill 时，注意对文档、默认值、脚本示例中的敏感地址做脱敏处理。
  - 不要直接写内网 IP、私有域名、真实服务地址，除非用户明确要求保留。
  - 优先改为 `127.0.0.1`、`example.com`、`<host>` 这类安全占位值，或通过环境变量传入。
  - 如果仓库里已有敏感地址，更新相关 skill 时应顺手替换为脱敏版本，并同步修改 `SKILL.md`、`references/`、脚本默认值。

## 提交前检查

- 目录结构符合 skill 约定
- `SKILL.md` 与目录职责一致
- 命令示例可运行
- 缺依赖时提示明确
- `.env` 加载顺序明确
