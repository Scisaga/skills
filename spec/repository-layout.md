# Repository Layout

当前仓库维护一份技能源码，同时提供插件与独立技能分发：

```text
.
├── skills/
├── template/
├── spec/
├── scripts/
├── plugin.json
├── .codex-plugin/
├── .claude-plugin/
├── .agents/plugins/
├── README.md
└── AGENTS.md
```

## 约定

- `skills/` 下每个一级目录是一个独立 skill
- `template/skill-template/` 是新建 skill 的起点
- `spec/` 放仓库级规范，不放具体业务实现
- 不在仓库根目录直接放业务 skill
- `plugin.json` 是 `scisaga` 插件身份和版本的唯一来源，兼容清单由管理工具生成
- `.agents/plugins/marketplace.json` 和 `.claude-plugin/marketplace.json` 的 marketplace 均为 `scisaga-skills`
- `scripts/manage_skills.py` 负责安装视图、别名、显式依赖、更新与允许列表打包
- 版本、配置和迁移规则见 [installation-and-updates.md](installation-and-updates.md)
