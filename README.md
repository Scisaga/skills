# Skill Repository

这是一个中性的 skill 仓库模板与实例集合。

## 目录结构

```text
.
├── skills/
│   ├── dev-ops/
│   ├── pdf/
│   ├── speech/
│   └── video/
├── template/
│   └── skill-template/
├── spec/
├── AGENTS.md
└── README.md
```

## 说明

- `skills/`：真实可用的 skill
- `template/`：新建 skill 时可复制的基础模板
- `spec/`：仓库级结构约定与编写规范

## 中性原则

- 当前仓库默认只维护 skill 本体、模板和规范
- 不默认绑定 `.claude-plugin/`、`.codex-plugin/` 或其他平台专属 marketplace 元数据
- 只有在明确要发布到某个平台时，才在仓库根目录追加对应平台的元数据目录和发布配置

## 当前 Skills

- `skills/dev-ops/`
- `skills/pdf/`
- `skills/speech/`
- `skills/video/`

## 常用入口

```bash
bash skills/pdf/scripts/run.sh help
bash skills/speech/scripts/run.sh help
bash skills/video/scripts/run.sh help
bash skills/dev-ops/scripts/run.sh help
```

## 维护原则

- 根目录只放仓库级文档和规范，不直接放具体 skill
- 每个 skill 自包含，至少包含 `SKILL.md`
- 详细说明放 `references/`
- 稳定可复用流程放 `scripts/`
- 输出资源或模板放 `assets/`

更细规则见 `AGENTS.md` 和 `spec/`。
