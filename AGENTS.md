# AGENTS Guide

本文件用于指导在当前仓库中创建、编辑和维护 skill。

## 仓库约定

- 所有真实 skill 统一放在 `skills/` 目录下，例如 `skills/speech/`、`skills/pdf/`。
- 仓库根目录只保留仓库级文档、模板和规范，不直接放 skill。
- 推荐同时维护：
  - `template/skill-template/`
  - `spec/`
- 平台专属元数据不是默认结构；只有明确要接入某个平台 marketplace 或插件系统时，才增加对应目录。
- 一个 skill 至少包含 `SKILL.md`。
- 推荐为每个 skill 提供：
  - `agents/openai.yaml`
  - `scripts/`
  - `references/`
  - `assets/`

## 创建或编辑 Skill 的基本原则

- 优先保持 skill 自包含，不依赖其他 skill 的隐式上下文。
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

适用于像 `skills/speech/` 这类依赖脚本执行的 skill。新建类似 skill 时，默认沿用同样模式。

### `.env` 读取规则

- 优先读当前工作目录的 `.env`
- 再读 skill 根目录的 `.env`
- 再读脚本同目录 `.env`

以当前 `skills/speech/` 为例，实际顺序是：

- 当前工作目录 `.env`
- `skills/speech/.env`
- `skills/speech/scripts/.env`

### 依赖检查

- 脚本启动时应自动检测缺失依赖。
- 如果缺少依赖，必须直接提示安装命令，不要静默失败。
- 如果发现 `.env` 文件存在，但缺少 `python-dotenv`，应明确提示无法自动加载 `.env`。
- 如果 skill 依赖外部可执行文件，不要只写“请自行安装”。
- 这类 skill 应提供可执行文件的下载或安装脚本，并按操作系统区分。

### 统一入口

脚本型 skill 推荐提供：

- `scripts/bootstrap.sh`
- `scripts/run.sh`
- 可选 `scripts/doctor.py`

推荐形态：

```text
skills/skill-name/
├── SKILL.md
├── requirements.txt
├── agents/openai.yaml
├── references/
├── assets/
└── scripts/
    ├── bootstrap.sh
    ├── run.sh
    ├── doctor.py
    └── ...
```

## 编辑已有 Skill 时

- 先读 `SKILL.md`，再按需读 `references/` 和 `scripts/`。
- 不要新增无关文档，例如 skill 目录内的 `README.md`、`CHANGELOG.md`、`INSTALLATION_GUIDE.md`。
- 如果只是补充参数说明或排障，不要把大段内容塞回 `SKILL.md`，优先更新 `references/`。

## 提交前检查

- 目录结构符合 `skills/<name>/` 约定
- `SKILL.md` 与目录职责一致
- 命令示例可运行
- 缺依赖时提示明确
- `.env` 加载顺序明确
