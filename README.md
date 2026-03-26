# Skill Collection Template

这是一个适合作为 Codex skill 集合仓库的最小模板。

## 推荐结构

```text
.
├── example-writing-assistant/
│   ├── SKILL.md
│   ├── agents/
│   │   └── openai.yaml
│   ├── scripts/
│   ├── references/
│   └── assets/
├── pdf-ocr/
├── speech/
└── video-caption-editor/
```

## 结构原则

- 每个项目根目录下的一级子目录都可以是一个独立 skill。
- 每个 skill 必须自包含，至少有 `SKILL.md`，不要依赖仓库里其他 skill 的隐式上下文。
- `pdf/`、`speech/`、`video/` 这类目录如果最终作为 skill 存在，建议直接整理成符合 skill 规范的一级目录，而不是再套一层聚合目录。

## 建议命名

- skill 目录使用小写短横线命名，例如 `pdf-ocr`、`speech`、`video-caption-editor`。
- 一个 skill 做一件完整的事，不要把多个弱相关能力塞进一个目录。
- 只有包含 `SKILL.md` 的一级目录才视为一个有效 skill。
