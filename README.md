# Skill Repository

日常工具

## 当前 Skills

| Logo | 技能名称 | 描述 |
|---|---|---|
| <img src="skills/build-narrated-presentation/assets/logo.svg" alt="Build Narrated Presentation logo" width="44"> | [`build-narrated-presentation`](skills/build-narrated-presentation/) | 验证 Markdown 输入质量，生成 SVG/PPTX/视频；支持跨页连续旁白、只改音频和分级验收。 |
| <img src="skills/dev-ops/assets/logo.svg" alt="Dev Ops logo" width="44"> | [`dev-ops`](skills/dev-ops/) | 维护部署脚本、服务资产、Compose、远程发布和主机级安装流程。 |
| <img src="skills/pdf/assets/logo.svg" alt="PDF logo" width="44"> | [`pdf`](skills/pdf/) | 本地处理 PDF 水印、骑缝章、页面重排、批量操作以及 PDF/图片转换。 |
| <img src="skills/speech/assets/logo.svg" alt="Speech I/O logo" width="44"> | [`speech`](skills/speech/) | 使用 Azure Speech 合成语音，并通过 Qwen3-ASR 兼容接口转写音频。 |
| <img src="skills/subtitle-matcher/assets/logo.svg" alt="Subtitle Matcher logo" width="44"> | [`subtitle-matcher`](skills/subtitle-matcher/) | 批量查找、下载、评分、校验并规范化中文字幕，生成可交互报告。 |
| <img src="skills/video/assets/logo.svg" alt="Video Toolkit logo" width="44"> | [`video`](skills/video/) | 抽帧、抽音频、检索或生成字幕、封装字幕、校验同步并整理影片信息。 |

## 目录结构

```text
.
├── skills/
│   ├── build-narrated-presentation/
│   ├── dev-ops/
│   ├── pdf/
│   ├── speech/
│   ├── subtitle-matcher/
│   └── video/
├── template/
│   └── skill-template/
├── spec/
├── .env.example
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

## 常用入口

```bash
bash skills/build-narrated-presentation/scripts/run.sh help
bash skills/pdf/scripts/run.sh help
bash skills/speech/scripts/run.sh help
bash skills/subtitle-matcher/scripts/run.sh help
bash skills/video/scripts/run.sh help
bash skills/dev-ops/scripts/run.sh help
```

## 环境变量

仓库级示例配置见 `.env.example`。需要本地配置时复制为 `.env` 并填写实际值；`.env` 已被 Git 忽略，不要把密钥或含凭据的代理地址提交到仓库。

## 维护原则

- 根目录只放仓库级文档和规范，不直接放具体 skill
- 每个 skill 自包含，至少包含 `SKILL.md`
- 详细说明放 `references/`
- 稳定可复用流程放 `scripts/`
- 输出资源或模板放 `assets/`

更细规则见 `AGENTS.md` 和 `spec/`。
