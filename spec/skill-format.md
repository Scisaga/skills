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
- frontmatter 仅含 `name` 和 `description`；源码 `name` 与目录名相同，使用短名称。插件以 `scisaga:<name>` 调用，独立安装视图默认为 `ss-<name>`，不得直接在源码改前缀。
- 必须有 `assets/logo.svg`；`agents/openai.yaml` 配置两个图标路径及有效品牌色。

## 图标维护

当前九个图标参考 [Keek](https://icons8.com/icons/all--style-keek) 的圆润造型、柔和双色和表情设计，使用原创 SVG 路径与透明背景；以终端、演示板、服务器等不同轮廓区分技能。矢量绘制源统一维护在 [generate_skill_logos.py](../scripts/generate_skill_logos.py)，不依赖外部图片或字体。

修改配色或路径后，执行 `python scripts/generate_skill_logos.py` 更新技能资源；使用 `python scripts/generate_skill_logos.py --check` 检查资源与绘制源是否一致。设计调整后同时预览浅色、深色背景，以及 README 使用的 64px 和较小的 44px、24px 尺寸。

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
- 插件版本来自根目录 `plugin.json`；兼容清单使用管理工具生成。安装、别名、配置及更新约定见 [installation-and-updates.md](installation-and-updates.md)。
