# 安装、更新与迁移

## 两种安装方式

插件标识为 `scisaga`，显示名称为 Scisaga 工具箱，marketplace 为 `scisaga-skills`。插件包含全部九个技能，身份例如 `scisaga:slides`、`scisaga:speech`。独立安装默认使用 `ss-slides`、`ss-speech` 等名称，并可指定别名；适用于 Codex IDE 扩展或按需选择技能。

先安装 Python 3.10+、Git 和管理工具依赖：

```bash
git clone https://github.com/Scisaga/skills.git
cd skills
python -m pip install -r requirements-tools.txt
```

以下命令中的 `--agent` 为 `codex` 或 `claude-code`，默认 `codex`；`--mode` 为 `plugin` 或 `standalone`，默认 `plugin`。安装范围为当前用户。管理工具不安装客户端本身；Codex 与 Claude Code 的安装分别参考 [Codex CLI](https://developers.openai.com/codex/cli/) 和 [Claude Code](https://code.claude.com/docs/en/setup)。

## 插件安装

```bash
python scripts/manage_skills.py install --agent codex --mode plugin
python scripts/manage_skills.py install --agent claude-code --mode plugin
```

发布后的默认源为 `https://github.com/Scisaga/skills.git`，跟踪 `main`。用 `--ref TAG_OR_FULL_COMMIT` 固定版本；提交请使用完整 SHA，固定提交不会跟随新提交更新。Claude Code 的原生 Git marketplace 仅直接支持分支/标签；固定提交时，管理工具先取出该提交，生成不可变的干净本地 marketplace，再通过原生命令安装，来源记录仍保存原始 Git URL 与 SHA。首次发布前或开发未提交改动时，显式使用 `--source .` 从当前工作树测试，工具会先生成不含本地配置、虚拟环境和缓存的干净插件副本，再交给客户端安装。

安装调用客户端原生的 marketplace 和 plugin 命令，不直接修改客户端缓存。Codex 中可显式选择 `$scisaga:slides`，Claude Code 中使用 `/scisaga:slides`。自然语言仍按技能的触发描述选择能力。

## 独立安装与别名

```bash
python scripts/manage_skills.py install --mode standalone --skill slides
python scripts/manage_skills.py install --mode standalone --skill video --alias speech=my-speech
```

不传 `--skill` 安装全部技能；参数可重复。默认名称为 `ss-<技能名>`，例如 `$ss-slides`。安装 `video` 自动带入 `speech`，自定义的 `my-speech` 路径会写进依赖映射。插件模式不接受单技能选择或独立别名。

安装前检查目标路径和当前用户、项目可见范围中的注册名称。遇到另一来源的同名技能时，用 `--alias slides=another-slides` 等显式名称共存，不覆盖原安装。别名保存到安装记录，更新持续沿用；改名需卸载后按新别名重新安装。

同一状态目录中有多个来源时，用 `update --mode standalone --name another-slides` 或 `uninstall --mode standalone --name another-slides` 精确选择安装；`--name` 可重复。更新指定 `video` 安装会带入其同源的 `speech` 依赖，其他来源保持不变。省略名称则按客户端与模式批量处理。

独立安装生成包含正确 `name` 和默认提示的安装视图，支持链接的资源优先链接，其他资源复制；可用 `--copy` 强制复制。元数据发生变更后运行 `update`，不能只改文件夹名，也不能把安装视图当成源码仓库。

已安装技能的脚本以该 `SKILL.md` 所在目录为根。源码示例的 `skills/<name>/scripts/...` 用于仓库根目录；独立安装视图会改写为实际安装路径并适配依赖别名。插件中的示例从插件根目录解析；从其他项目调用时，使用该技能目录中的脚本绝对路径，保持当前工作目录为实际项目目录。路径含空格时为路径加引号。

## 更新与生效时机

```bash
python scripts/manage_skills.py check --remote
python scripts/manage_skills.py update --agent codex --mode plugin
python scripts/manage_skills.py update --mode standalone
python scripts/manage_skills.py launch codex -- --model MODEL_NAME
```

`launch codex` 每次启动前更新已登记的 Codex 安装，再原样转发 `--` 后的参数；更新最多等待 60 秒。更新失败且存在可用旧版时，打印原因后启动旧版；没有可用安装则退出。直接启动 `codex` 或 IDE 扩展不会自动经过此入口。桌面端使用手动更新后重新加载/重启。

Claude Code 的第三方 marketplace 默认不自动更新。在 `/plugin` 的 Marketplaces 页面选择 `scisaga-skills`，开启 **Enable auto-update**。启动会话时客户端会后台同步；当前会话继续使用已加载版本，使用 `/reload-plugins` 或新会话应用更新。手动更新：

```bash
claude plugin marketplace update scisaga-skills
claude plugin update scisaga@scisaga-skills
```

仅刷新 Claude marketplace 的列表不等于更新已安装插件。具体规则见 [Claude Code 更新说明](https://code.claude.com/docs/en/discover-plugins#keep-plugins-updated)；Codex 原生刷新见 [插件打包与管理](https://developers.openai.com/plugins/build/plugins)。本地目录开发源需要先修改本地文件或自行同步 Git，再执行管理工具的 `update`。

Codex 的 `marketplace upgrade` 面向 Git marketplace；本地目录源通过原生 `marketplace add` 重新读取目录，再由 `plugin add` 刷新安装。两条路径均核对实际启用版本与源码摘要。

Git 源使用按提交隔离的工作树，使旧安装可继续引用旧版本。发现源码或已安装文件有未提交/本地修改时，停止覆盖并报告。管理工具不会执行强制 reset，也不会更新正在运行的会话。

## 运行依赖与环境配置

技能安装完成后，再按实际能力运行对应技能的 bootstrap 和 doctor；Python 包、FFmpeg、Windows PowerPoint、自托管服务均属于运行环境。插件安装不会部署 Qwen 服务或提供这些软件。

推荐将配置放在实际项目的 `.env`；跨项目共享配置使用 `--env-file /absolute/path/settings.env`。Speech 与 Slides 按以下顺序逐层补充缺失值，先前的值不被覆盖：

1. 已有进程环境变量。
2. 显式 `--env-file`。
3. 当前工作目录 `.env`。
4. 当前技能根目录 `.env`。
5. 当前脚本目录 `.env`。

从其他项目调用技能时，不会自动读取此源码仓库根目录的 `.env`。避免把长期配置写进插件缓存；更新不会搬运缓存中的凭据。根目录 `.env.example` 是公开变量的统一示例，只包含安全默认值。

Speech 与 Slides 共用 `QWEN_TTS_API_BASE`、`QWEN_TTS_API_KEY`、`QWEN_TTS_VOICE_ID`、`QWEN_TTS_TIMEOUT_SECONDS`、`QWEN_TTS_POLL_INTERVAL_SECONDS`。实际实例地址与已注册音色只写入本地配置。Azure 回退使用 `AZURE_SPEECH_KEY` 和资源对应的 `AZURE_SPEECH_REGION`。仅使用 Qwen 无需 Azure Key/SDK。

从其他目录检查服务也可直接指定配置：Speech 使用 `doctor --mode synthesize --check-service --env-file PATH`，Slides 使用 `doctor --stage audio --check-service --env-file PATH`。

## 检查、卸载和隔离测试

```bash
python scripts/manage_skills.py check
python scripts/manage_skills.py doctor --agent codex --mode plugin
python scripts/manage_skills.py uninstall --mode standalone --skill slides
python scripts/manage_skills.py uninstall --agent claude-code --mode plugin
```

管理工具只卸载自己登记且内容未修改的安装；保留额外的本地配置和运行文件，包括技能和脚本目录 `.env`。卸载后保留归属标记，允许同源同名重装沿用配置。仍被其他技能依赖的技能不能单独卸载。插件卸载不移除整个 marketplace，也不影响其他插件。

Windows 状态默认位于 `%LOCALAPPDATA%/Scisaga/skills`，其他平台位于 `$XDG_STATE_HOME/scisaga` 或 `~/.local/state/scisaga`。记录保存来源、提交、内容摘要、安装路径和别名，不保存凭据。通过 `--state-dir PATH --home-dir PATH` 可将记录、目标路径和原生客户端配置隔离到临时目录；适用于测试，不需要修改真实用户配置。

## 旧安装迁移

`build-narrated-presentation` 对应 `slides`，`android-termux-ssh` 对应 `termux-ssh`。旧名称的无来源副本不会被按名称自动删除。能确定同源、旧内容未修改的已登记安装可以迁移；未知来源或已修改副本保持原样并报告，确认后手动移除旧安装，再使用新名称安装。

Termux 远端设备的 `~/.config/android-termux-ssh`、SSH 配置文件及托管标记属于既有部署协议，改名时继续兼容；Slides 项目 schema、Qwen 的 `compatibility` 固定值和 provider ID 也保持原值。

## 打包与版本

```bash
python scripts/manage_skills.py package --sync-manifests
python scripts/manage_skills.py package --bump patch
```

根目录 `plugin.json` 是身份和版本来源；兼容清单与两端 marketplace 由它生成。内容变更正式发布时递增版本，客户端才能可靠识别更新。默认包为 `dist/scisaga.zip`，只有一个顶层 `scisaga/`，包含真实技能文件、兼容清单、marketplace 与安装工具/说明，可解压作为安装源；排除凭据、Git 数据、测试缓存、虚拟环境和生成产物。

检查失败返回非零退出码，输出输入内容 SHA256；输出包附带文件数与归档 SHA256。打包不提交 Git、不推送、不上传账号或公开目录。
