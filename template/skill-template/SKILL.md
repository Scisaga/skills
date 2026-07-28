---
name: skill-template
description: 用于创建新 skill 的基础模板。适用于需要快速初始化一个包含 SKILL.md、agents、references、scripts 和 assets 的标准 skill 目录时使用。
---

# Skill Template

## 概述

把这个目录复制到 `skills/<your-skill-name>/`，然后替换名称、描述和具体实现。

## 工作流

1. 修改 frontmatter 中的 `name` 和 `description`
2. 替换 `assets/logo.svg`，并同步 `agents/openai.yaml` 的图标和品牌色
3. 把稳定流程写进 `scripts/`
4. 把细节说明写进 `references/`
5. 把模板或资源放进 `assets/`
