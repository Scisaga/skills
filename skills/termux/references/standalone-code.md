# Android 主屏独立 VS Code

## 安装主屏入口

复用现有 Debian 用户和官方 Linux VS Code。需要匹配的官方 Termux:X11 APK 与 native CLI，两端都须支持多窗口 `-tag`。Termux:Widget 与 Termux 使用同一签名来源。 [桌面安装](desktop-setup.md) · [Termux:X11 多窗口](https://github.com/termux/termux-x11/blob/c5d0920/README.md#running-multiple-displays-as-separate-windows) · [Termux:Widget 安装](https://github.com/termux/termux-widget#setup-instructions)

在原生 Termux 中从仓库根目录运行。先查看预览，再使用 `--apply` 写入 Widget 任务与图标。默认使用 `:2`，需要其他显示号时两次命令均传入同一个空闲的 `--display`。

```bash
bash skills/termux/scripts/run.sh standalone-code launcher
bash skills/termux/scripts/run.sh standalone-code launcher --apply
```

在 Android 主屏的小组件/快捷方式中找到 **Termux shortcut**，进入 **tasks** 选择 **VS Code**，确认添加后点击图标。任务文件在原生 Termux 的 `~/.shortcuts/tasks/VS Code`，图标取自已安装的 Code。Xfce 继续用原来的 **Linux 桌面** 图标或 `desktop start` 按需启动。新建桌面配置时，将 `code_autostart` 设为 `false` 可在手动启动 Xfce 时保持 VS Code 按需打开。

小米平板 7 的 HyperOS 若拒绝固定图标，在 Termux:Widget 的「其他权限」中临时允许「桌面快捷方式」。完成固定后可恢复该权限并再点一次图标验证。点击后若编辑器已启动但设备仍停在主屏，检查 `ActivityTaskManager` 的后台启动记录。小米平板 7 上要让 Termux 从后台显示 X11 窗口，需在 Termux 的应用权限中允许「后台弹出界面」和「显示在其他应用上层」。若 HyperOS 以小窗打开编辑器，可下拉小窗底部横条切到全屏。

独立入口启动带 `vscode` 标签的 X11、最小 Xfwm 和 Code 图形进程。重复点击只返回现有窗口。Code 用户设置、扩展和 XDG 目录在 guest 的 `~/.local/share/tablet-vscode`，项目仍用同一 Debian 用户访问。在 Code 文件选择器中可打开 `~/Desktop/skills`，也可访问已授予 Termux 存储权限的 `/sdcard/Download` 和 `/sdcard/Documents`。如需启用已有 Android 保护的 GNOME Keyring，按 [桌面凭据配置](desktop-credentials.md) 验证解锁。登录或同步由当前用户在隔离配置中完成。 [VS Code 配置隔离](https://code.visualstudio.com/docs/configure/command-line#_isolating-vs-code-instances)

## 安装所需扩展

在原生 Termux 查询独立实例的扩展，再选择需要的组合。多个 ID 可放在一次命令中。省略 `--apply` 可预览。

```bash
bash skills/termux/scripts/run.sh standalone-code extensions
bash skills/termux/scripts/run.sh standalone-code extensions openai.chatgpt --apply
bash skills/termux/scripts/run.sh standalone-code extensions \
  yzhang.markdown-all-in-one shd101wyy.markdown-preview-enhanced \
  mechatroner.rainbow-csv mathematic.vscode-pdf --apply
bash skills/termux/scripts/run.sh standalone-code extensions cweijan.vscode-office --apply
bash skills/termux/scripts/run.sh standalone-code extensions peakchen90.open-html-in-browser --apply
```

- **Codex** 使用 `openai.chatgpt`。该扩展可能随安装带入 `openai.codex-audio`，也可单独检查语音扩展。Y900 上 `26.1111.21308` 的语音扩展 Linux 原生组件只有 x86-64，ARM64 即使装好也没有语音输入。重新排查时先检查所装 VSIX 的架构、扩展输出与 guest 的录音源，再检查按钮和实际录音。
- **Markdown、表格文本与 PDF** 分别使用 Markdown All in One / Markdown Preview Enhanced、Rainbow CSV 和 `mathematic.vscode-pdf`。验证 Markdown 预览命令、CSV/TSV 的普通编辑以及 PDF 查看器。
- **Office Viewer** 默认只关联 `.docx`、`.dotx`、`.xls`、`.xlsx`、`.xlsm`、`.ods`、`.pptx`、`.pptm`。首次安装选用已验证的 `4.2.3`，安装前写入 `workbench.editorAssociations`，约束它声明的其他默认文件关联。Markdown、CSV/TSV、压缩包等继续用原有明确选择或内置编辑器。已有 `mathematic.vscode-pdf` 时为 PDF 保留 `pdf.view`。已装 Office Viewer 或升级后重跑同一条无版本号命令，按实际安装的扩展清单校正关联。若工作区覆盖用户设置，验收时用 **Reopen Editor With…** 查看该文件实际的默认编辑器。 [Office Viewer 扩展说明](https://marketplace.visualstudio.com/items?itemName=cweijan.vscode-office)

Marketplace 不可达时，可在 Debian 中安装已核对发布者、版本和目标架构的官方本地 `.vsix`。已有缓存文件缺少后缀时，在私有临时目录建立带 `.vsix` 后缀的链接并在安装后清理。Office Viewer 优先使用上面的默认安装入口。离线安装 Office Viewer 前先关掉独立窗口，安装后执行同一入口写入文件关联，再打开 Code。

```bash
code_root="$HOME/.local/share/tablet-vscode"
code --no-sandbox --user-data-dir "$code_root/code" --extensions-dir "$code_root/extensions" \
  --install-extension /path/to/extension.vsix
```

## 在 Android Chrome 预览 HTML

安装 **Open In Default Browser** 后可选配独立实例的 HTTP 路由。先确认 Android Chrome 已安装，且隔离配置已有可用的 Linux HTTP 浏览器。脚本保留这个处理程序，供普通 HTTP URL 使用。Debian 中缺少浏览器路由工具时安装 `libglib2.0-bin`、`xdg-utils` 和 `python3`。

```bash
bash skills/termux/scripts/run.sh standalone-code android-chrome
bash skills/termux/scripts/run.sh standalone-code android-chrome --apply
```

在独立 Code 中打开包含测试 HTML 的文件夹，确认 `openInDefaultBrowser.run.openWithLocalHttpServer` 为 `true`（扩展默认值），从 HTML 编辑器运行 **Open In Default Browser**。扩展产生的 `http://localhost:端口/...` 经 Termux Intent 交给 Android `com.android.chrome`。首次出现 ROM 的关联启动提示时，按当前用户选择允许这对应用。需要预览 Debian 私有文件时通过这个工作区服务器访问。HTML 需在已打开的工作区内，单独打开文件可能得到 Linux 文件路径。

该扩展的内置 HTTP 服务没有指定监听地址。用无敏感内容的工作区测试，完成后关闭对应预览窗口并确认测试端口释放。 [Open In Default Browser 说明](https://marketplace.visualstudio.com/items?itemName=peakchen90.open-html-in-browser) · [服务实现](https://github.com/peakchen90/vscode-open-in-default-browser/blob/master/src/local-server/LocalServer.ts)

## 验收与回退

1. 正常结束 Xfce 后从主屏冷启动，再点一次图标。检查只有一个 `vscode` 标签的 X11 和同一个独立 Code 实例，且 `desktop status --json` 仍报告 `stopped`。小米平板 7 已通过这项冷启动检查。再打开任意正常项目文件夹（例如 `~/Desktop/skills`），确认窗口与 X11 实例仍在。
2. 复核 Office 文件进入 Office Viewer，Markdown、CSV/TSV、PDF 仍用对应编辑器。验证 HTML 命令实际在 Android Chrome 加载页面，普通网站链接仍交给已有 Linux 处理程序。
3. 保存文件并正常关闭独立 Code。检查它占用的显示号释放、Xfce 仍可按原入口启动；再次打开主屏快捷方式，确认可重启。检查原生 Termux 的 `~/.local/state/tablet-desktop/vscode-standalone/last.log` 定位启动错误或已有 X11 显示冲突。

打开文件夹时若 VS Code 消失或返回 Xfce，先检查启动器是否仍在等待 `code --wait`。VS Code 切换工作区时可结束 CLI 的等待，后台任务随后会误结束 X11。当前脚本直接持有图形进程，直至窗口正常退出。 [VS Code 1.146.0 工作区载入与等待处理](https://github.com/microsoft/vscode/blob/1.146.0/src/vs/platform/windows/electron-main/windowsMainService.ts)

恢复时按安装结果的 `changed` 与 `backup` 找到此前版本。移除主屏入口可在启动器删除图标、恢复或移除本次创建的任务。要回退 Chrome 预览，可恢复或移除本次创建的隔离配置 `config/mimeapps.list` 中的 HTTP 默认项，再检查 `xdg-mime query default x-scheme-handler/http`。在 Code 中撤销 Office 配置时先备份当前用户设置，再恢复相应 `workbench.editorAssociations`。保留项目文件和其他配置，结束临时窗口、连接与测试文件。
