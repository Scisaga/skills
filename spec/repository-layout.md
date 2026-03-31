# Repository Layout

当前仓库采用中性的 skill repository 结构：

```text
.
├── skills/
├── template/
├── spec/
├── README.md
└── AGENTS.md
```

## 约定

- `skills/` 下每个一级目录是一个独立 skill
- `template/skill-template/` 是新建 skill 的起点
- `spec/` 放仓库级规范，不放具体业务实现
- 不在仓库根目录直接放业务 skill
- 不默认要求 `.claude-plugin/`、`.codex-plugin/` 或其他平台专属元数据
- 如果后续需要对接某个平台，再在此结构上增补对应发布配置
