# 0.1.0 升级验收

验收日期：2026-10-23。使用 Windows、Python 3、Codex CLI `0.162.0-alpha.17.2` 和 Claude Code `2.1.308`。原生安装测试的 HOME、CODEX_HOME、CLAUDE_CONFIG_DIR 和安装记录全部指向临时目录。未向真实用户配置安装插件，未推送本仓库或公开发布。

## 仓库与安装

- 九个源码技能名称、目录、SVG 图标、元数据、资源链接和生成清单通过脚本校验；失败会返回非零退出码和输入摘要。
- Codex 与 Claude Code 原生安装、九技能发现、`0.1.0 → 0.1.1` 升级、卸载和同源重装通过。
- 使用本地临时 Git smart HTTP 服务验证两端 Git marketplace：`main` 更新到 `0.1.1`，固定完整提交的安装继续保持 `0.1.0`。Claude 使用不可变本地 catalog 兼容原生克隆不接受 SHA 的限制。
- 独立验收覆盖异源同名冲突、别名共存、跨来源独立更新、`video → speech` 路径映射、配置保留和同名重装。源码未提交修改时停止更新；未知来源副本保持原样。
- 根目录、脚本目录 `.env`、其他本地配置与运行文件在更新、卸载、重装后保留。ZIP 解压可直接作为安装源；不会继承父级 Git 仓库身份。归档不含真实 `.env`、虚拟环境、Git 数据或缓存。
- 含空格的安装路径和仓库外工作目录，独立评估实际执行了 24 条文档/帮助中的安全命令，全部成功。
- Codex 启动参数按原始参数列表传递；原生更新失败时使用已有可用安装。无可用安装时退出。子进程超时会终止进程树，文件生成和提交安装前也检查共享更新预算。

## 语音与兼容

- 真实 Qwen 实例验证短文本、三段长文本，以及 `xiaochen-hd`、`yunyang`、`xiaoxiao` 三种已就绪音色。
- `+8%` 语速与 `+1st` 音高生成成功；核对服务编译与执行记录中的控制值，下载的音频与时间轴通过完整性校验。
- `newscast` 风格不受当前 Qwen 服务支持时，整份转到 Azure；不可达地址也成功回退到 Azure。两端失败时错误同时包含后端原因，旧音频保持原值。
- 回归覆盖长文本中途失败后的整份回退、输出发布失败回滚、无 Azure SDK 的 Qwen/ASR 路径和五层环境变量优先级。
- Slides 项目契约、语音协议固定值及音频/字幕调用保持兼容。三个 SVG 继续作为专业技术 PPT 的可选示例，未扩展为组件库。

## 可重复检查

先按各技能的 requirements 初始化所需测试依赖，再执行：

```bash
python -m unittest discover -s tests -v
python -m unittest discover -s skills/speech/tests -v
python -m unittest discover -s skills/slides/tests -v
python scripts/manage_skills.py check --home-dir tmp/check-home --state-dir tmp/check-state
python scripts/manage_skills.py package --sync-manifests
```

安装管理、Speech、Slides 三组分别为 23、13、72 个测试，共 108 个。真实客户端的发现与更新由隔离 CLI 验证；桌面 GUI、IDE 交互以及所有操作系统上的安装未逐一实测。

本地试听与详细证据位于 `tmp/scisaga-upgrade/`：`audio/audition.html`、`audio/results.json`、`native-final/results.json`、`native-git-smart/results.json`、`forward-test-2/report.json` 和 `forward-docs-final/report.json`。这些运行记录和音频不进入分发包。试听页供人工比较音色和衔接；自动校验不代替听感验收。
