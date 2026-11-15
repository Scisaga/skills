# Scisaga 工具箱

简体中文 | [English](README.en.md)

面向 Codex 与 Claude Code 的九个实用技能，覆盖 Android 工作站、演示与配音、文档与视频处理，以及服务、域名和开发协作。

## Skills

点击技能名称查看工作流、命令与配置说明。

| 图标 | 技能 | 能做什么 |
|:---:|---|---|
| <img src="skills/termux/assets/logo.svg" alt="Termux 终端平板图标" width="64" height="64"> | [`termux`](skills/termux/)<br>Android 工作站 | **原生环境**：安装、迁移 Termux，配置 SSH、开机服务、共享存储、API、蓝牙与本机 Codex。<br>**桌面与应用**：按需部署 X11、Debian/Xfce，以及 VS Code、Chromium、LibreOffice、VLC，提供 Android 图形管理与应用入口。<br>**设备适配**：排查显示、触控、键鼠、GPU、VPN/DNS、后台进程与耗电，验证实际功能及性能。<br>[查看小米平板 7 实机演示 ↓](#termux-实机演示) |
| <img src="skills/slides/assets/logo.svg" alt="Slides 演示板图标" width="64" height="64"> | [`slides`](skills/slides/)<br>演示与逐页配音 | **从文稿到演示**：保真绑定逐页讲稿，结合计划或 Markdown 材料制作技术图示、架构流程与路线图，支持模板复用、动画和单页 SVG 改稿。<br>**自然旁白**：编排语速、停顿与术语读法，支持音色试听、更换声音；优先自托管 Qwen3，不可用时整套回退 Azure。<br>**多种交付**：逐页 MP3、静态／动画／旁白 PPTX，或由 Windows PowerPoint 导出 MP4；按真实音频时长换页，支持增量重建与分级验收。 |
| <img src="skills/dev-ops/assets/logo.svg" alt="Dev Ops 服务器图标" width="64" height="64"> | [`dev-ops`](skills/dev-ops/)<br>服务部署 | 管理 Compose 栈、配置模板、环境变量与远程发布；覆盖 GitLab、数据库、对象存储、代理、WireGuard、DDNS、DNS 与证书同步，提供统一服务入口和硬编码审计。 |
| <img src="skills/domain-manager/assets/logo.svg" alt="Domain Manager 域名地球图标" width="64" height="64"> | [`domain-manager`](skills/domain-manager/)<br>域名与解析 | 查询与管理 Gandi、Dynadot 的域名资产、DNS 记录、域名服务器、DNSSEC、联系人、续费及转移；支持沙箱，写操作先预览计划、确认后执行并回读结果。 |
| <img src="skills/gitlab-issue/assets/logo.svg" alt="GitLab Issue 任务单图标" width="64" height="64"> | [`gitlab-issue`](skills/gitlab-issue/)<br>议题协作 | 在当前自托管 GitLab 仓库中检索、创建和更新议题，管理标签、描述与评论，支持关闭、重开和删除；发送令牌前校验仓库与受信任实例一致。 |
| <img src="skills/pdf/assets/logo.svg" alt="PDF 文档图标" width="64" height="64"> | [`pdf`](skills/pdf/)<br>文档处理 | 本地合并、拆分、抽取、替换、删除、重排和旋转页面；添加保留文本层的水印、烧录水印或骑缝章，支持目录批处理及 PDF／图片互转。 |
| <img src="skills/speech/assets/logo.svg" alt="Speech 麦克风图标" width="64" height="64"> | [`speech`](skills/speech/)<br>语音合成与转写 | 将短文本或长稿合成为 MP3，支持音色查询及后端可用的风格、语速、音高控制；优先 Qwen3、整份回退 Azure，并记录实际后端与音色。通过自托管 Qwen3 ASR 转写会议、访谈等音频。 |
| <img src="skills/subtitle-matcher/assets/logo.svg" alt="Subtitle Matcher 字幕气泡图标" width="64" height="64"> | [`subtitle-matcher`](skills/subtitle-matcher/)<br>批量匹配字幕 | 扫描电影、剧集目录，按片源版本从 ASSRT、SubHD 等来源查找中文字幕；评分筛选、下载校验，并用内嵌字幕时间轴辅助比对。规范 VLC 自动加载命名，生成带复查项与播放入口的 HTML 报告。 |
| <img src="skills/video/assets/logo.svg" alt="Video 场记板图标" width="64" height="64"> | [`video`](skills/video/)<br>视频工具 | 提取关键帧与音频，检索现成字幕或通过 ASR 生成 SRT，封装字幕并检查同步；支持跨平台 FFmpeg 安装，以及联网整理影片简介和评价。 |

### Termux 实机演示

小米平板 7 实机快览：YouTube（3Blue1Brown）→ GitHub → VLC 视频播放 → 全屏 VS Code，右侧 Codex 为贪吃蛇添加最高分，再从底部终端启动游戏。保留左侧文件栏，展示真实 AI 改码与运行结果。片段经过剪辑，9 秒循环，GIF 约 2 MB。

<img src="assets/demos/termux-pad7.gif" alt="小米平板 7 的 Xfce 桌面快速切换 YouTube、GitHub、VLC，以及带左侧文件栏、右侧 Codex 改码结果和底部终端的全屏 VS Code，启动 Python 贪吃蛇" width="1120">

[贪吃蛇示例源码](skills/termux/assets/demo/snake.py) · 在 Debian/Xfce 中运行 `python3 snake.py`；缺少 Tk 时安装 `python3-tk`。方向键或 WASD 移动，空格暂停，R 重开。

VLC 演示片段取自 [MDN 的 flower 示例视频](https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4)。

## 安装与更新

插件名为 `scisaga`，marketplace 名为 `scisaga-skills`。例如，`slides` 在插件中以 `scisaga:slides` 调用，独立安装默认为 `ss-slides`；版本统一维护在根目录 `plugin.json`。

先安装 [Codex](https://developers.openai.com/codex/cli/) 或 [Claude Code](https://code.claude.com/docs/en/setup)，并准备 Python 3、Git：

```bash
python -m pip install -r requirements-tools.txt
python scripts/manage_skills.py install --agent codex --mode plugin
python scripts/manage_skills.py install --agent claude-code --mode plugin
```

上面跟踪 GitHub `Scisaga/skills` 的 `main`；**本地尚未发布的修改使用 `--source .`**。固定版本或提交用 `--ref <tag-or-commit>`。插件通过客户端原生命令安装。Codex 中使用 `$scisaga:slides`，Claude Code 中使用 `/scisaga:slides`。

兼容 Codex IDE 等独立技能场景：

```bash
python scripts/manage_skills.py install --agent codex --mode standalone --skill slides --source .
python scripts/manage_skills.py install --agent codex --mode standalone --skill video --alias speech=my-speech --source .
```

默认名称均带 `ss-`；同名冲突用 `--alias slides=my-slides` 共存。`video` 自动带入 `speech`，并按安装映射调用。后续更新保留别名和本地配置。

```bash
python scripts/manage_skills.py check --agent codex --mode plugin --remote
python scripts/manage_skills.py update --agent codex --mode plugin
python scripts/manage_skills.py launch codex --
```

`launch codex` 在启动前限时 60 秒更新，失败且已有可用安装时继续启动；直接运行 `codex` 不保证经过此更新流程。Claude Code 需在 `/plugin` → Marketplaces → `scisaga-skills` 开启第三方 marketplace 自动更新，更新在重新加载或下次会话生效。完整安装、冲突处理、隔离测试、迁移和卸载见 [安装与更新规范](spec/installation-and-updates.md)。

安装技能、初始化 Python/系统依赖和配置外部服务是三个步骤。Speech/Slides 配音默认优先 Qwen，失败时整份尝试 Azure；从项目 `.env` 或外部 `--env-file` 读取配置。仅使用 Qwen 不要求 Azure Key/SDK，详见 [Speech 运行说明](skills/speech/references/usage.md)。

## 目录结构

```text
.
├── skills/
│   ├── termux/
│   ├── slides/
│   ├── dev-ops/
│   ├── domain-manager/
│   ├── gitlab-issue/
│   ├── pdf/
│   ├── speech/
│   ├── subtitle-matcher/
│   └── video/
├── template/
│   └── skill-template/
├── assets/demos/
├── spec/
├── scripts/manage_skills.py
├── plugin.json
├── .codex-plugin/
├── .claude-plugin/
├── .agents/plugins/marketplace.json
├── .env.example
├── AGENTS.md
├── README.md
└── README.en.md
```

## 说明

- `skills/`：真实可用的 skill
- `template/`：新建 skill 时可复制的基础模板
- `assets/demos/`：README 使用的实机演示素材
- `spec/`：仓库级结构约定与编写规范

## 分发原则

- `skills/` 是唯一源码；插件内使用短名称，独立安装生成带前缀或别名的视图。
- 根目录 `plugin.json` 是插件身份与版本的唯一来源；兼容清单由 `package --sync-manifests` 生成并校验。
- `package` 按允许列表打包真实文件，不包含真实 `.env`、虚拟环境、缓存或生成产物。

## 常用入口

```bash
bash skills/termux/scripts/run.sh help
bash skills/slides/scripts/run.sh help
bash skills/domain-manager/scripts/run.sh help
bash skills/gitlab-issue/scripts/run.sh help
bash skills/pdf/scripts/run.sh help
bash skills/speech/scripts/run.sh help
bash skills/subtitle-matcher/scripts/run.sh help
bash skills/video/scripts/run.sh help
bash skills/dev-ops/scripts/run.sh help
```

## 环境变量

仓库级示例配置见 [.env.example](.env.example)。建议放在当前项目 `.env`；共享配置通过 `--env-file` 引用插件缓存外的文件。Speech/Slides 按进程变量 → 显式文件 → 当前目录 → 技能目录 → 脚本目录补充缺失配置。从其他项目调用时不会自动读取源码仓库根目录 `.env`。不要提交密钥或含凭据的代理地址。

## 维护原则

- 根目录只放仓库级文档和规范，不直接放具体 skill
- 每个 skill 自包含，至少包含 `SKILL.md`
- 详细说明放 `references/`
- 稳定可复用流程放 `scripts/`
- 输出资源或模板放 `assets/`

更细规则见 `AGENTS.md` 和 `spec/`。
