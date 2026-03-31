# Skill Format

每个 skill 推荐采用以下结构：

```text
skills/<skill-name>/
├── SKILL.md
├── agents/
├── references/
├── scripts/
└── assets/
```

## 最小要求

- 必须有 `SKILL.md`

## 推荐要求

- `agents/openai.yaml`
- `scripts/`
- `references/`
- `assets/`

## 说明

- `SKILL.md` 负责触发说明与工作流导航
- `references/` 负责细节说明
- `scripts/` 负责可重复执行的稳定逻辑
- `assets/` 负责输出模板、样例或非执行资源
