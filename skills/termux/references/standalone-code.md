# Android 主屏独立 VS Code

## 安装主屏入口

通用主屏快捷方式使用 Termux:Widget。Y900 需要 Dock 原生图标和独立窗口时，使用下文的 [Android 宿主](#y900-的-dock-图标和独立窗口)。

复用现有 Debian 用户和官方 Linux VS Code。需要匹配的官方 Termux:X11 APK 与 native CLI，两端都须支持多窗口 `-tag`。Termux:Widget 与 Termux 使用同一签名来源。 [桌面安装](desktop-setup.md) · [Termux:X11 多窗口](https://github.com/termux/termux-x11/blob/c5d0920/README.md#running-multiple-displays-as-separate-windows) · [Termux:Widget 安装](https://github.com/termux/termux-widget#setup-instructions)

在原生 Termux 中从仓库根目录运行。先查看预览，再使用 `--apply` 写入 Widget 任务与图标。默认使用 `:2`，需要其他显示号时两次命令均传入同一个空闲的 `--display`。

```bash
bash skills/termux/scripts/run.sh standalone-code launcher
bash skills/termux/scripts/run.sh standalone-code launcher --apply
```

在 Android 主屏的小组件/快捷方式中找到 **Termux shortcut**，进入 **tasks** 选择 **VS Code**，确认添加后点击图标。任务文件在原生 Termux 的 `~/.shortcuts/tasks/VS Code`，图标取自已安装的 Code。可通过 **Linux 桌面** 图标或 `desktop start` 按需启动 Xfce。桌面预设默认 `code_autostart=false`，需要随 Xfce 打开 VS Code 时可显式设为 `true`。

小米平板 7 的 HyperOS 若拒绝固定图标，在 Termux:Widget 的「其他权限」中临时允许「桌面快捷方式」。完成固定后可恢复该权限并再点一次图标验证。点击后若编辑器已启动但设备仍停在主屏，检查 `ActivityTaskManager` 的后台启动记录。小米平板 7 上要让 Termux 从后台显示 X11 窗口，需在 Termux 的应用权限中允许「后台弹出界面」和「显示在其他应用上层」。若 HyperOS 以小窗打开编辑器，可下拉小窗底部横条切到全屏。

独立入口启动带 `vscode` 标签的 X11、最小 Xfwm 和 Code 图形进程。重复点击只返回现有窗口。Code 用户设置、扩展和 XDG 目录在 guest 的 `~/.local/share/tablet-vscode`，项目仍用同一 Debian 用户访问。在 Code 文件选择器中可打开 `~/Desktop/skills`，也可访问已授予 Termux 存储权限的 `/sdcard/Download` 和 `/sdcard/Documents`。如需启用已有 Android 保护的 GNOME Keyring，按 [桌面凭据配置](desktop-credentials.md) 验证解锁。登录或同步由当前用户在隔离配置中完成。 [VS Code 配置隔离](https://code.visualstudio.com/docs/configure/command-line#_isolating-vs-code-instances)

## Y900 的 Dock 图标和独立窗口

### 主屏入口和窗口切换

从应用抽屉长按 **VSCode**（`com.scisaga.tabletvscode`）并选择**添加到桌面**。可从同一菜单固定到「无限工作台」Dock。**文件 → 新建窗口**和 **Ctrl+Shift+N** 启动各自的 X11 会话与 Android 任务。ZUI 将同包任务归到一个 Dock 图标，点击可选窗口缩略图，长按后可从 **VSCode 窗口**按项目名切换。 [Termux:X11 多窗口](https://github.com/termux/termux-x11/blob/c5d0920/README.md#running-multiple-displays-as-separate-windows)

点主屏图标时，单窗口直接回到原窗口，多个窗口显示项目列表。Y900 旧版宿主调用 `AppTask.moveToFront()` 后曾停在桌面。从宿主 1.3 起，使用原 `vscode-N` 标签启动 `MainActivityTagged`，按 `documentLaunchMode="intoExisting"` 匹配已有任务。复验时核对切换前后的任务 ID 与 Linux 编辑器 PID。 [Android 文档任务](https://developer.android.com/guide/components/activities/recents.html)

Dock 与缩略图复用白底蓝色应用图标。应用名为 **VSCode**。宿主读取 X11 的 `_NET_WM_NAME`，去掉 Linux 标题末尾重复的产品名，再由 ZUI 显示应用名与编辑器标题。按工作区启动时可先提供项目名，恢复会话时可先用保存的标题。若 `_NET_WM_NAME` 已更新而卡片仍显示旧字样，核对 ZUI 的卡片缓存。重新挂接同一标签后查看卡片，并验证 Linux 编辑器 PID 延续。项目列表显示单独维护的项目名，长标题可能被 ZUI 省略。

### 关联启动提示

弹窗出现时先查看屏幕上的发起应用和目标应用，再在同一次操作的系统日志中查 `ZuiSecurityService`、`ZuiAutoRunManager` 与 `ActivityTaskManager`。本例的旧 Widget 和旧版新建窗口命令会由 Termux 跨应用启动 VSCode。Y900 上曾在宿主升级后重新询问。旧 Widget 即使获准关联启动，也曾被“读取已安装应用列表”策略静默拦下。Y900 的日常入口直接使用应用抽屉里的 **VSCode**，取代旧的 Widget 图标。 [Lenovo ZUI 权限诊断](android-permissions-and-power.md#lenovo-zui-的自启动与关联启动)

宿主 1.4.1 在当前窗口接管 **Ctrl+Shift+N**，通过 Termux 的 `RUN_COMMAND` 启动 X11。Termux 回报就绪后，宿主自行创建 Android 任务并回送接收确认。Android 14 及以上的现行 TermuxAm 广播在发送后立即返回，启动脚本应等待这次请求的确认再继续打开 Code。若任务短暂出现后关闭，从原生 Termux 检查该槽位的 `last.log` 和就绪确认，复测时同时看 Activity 发起包、实际出现的编辑器及 ZUI 屏幕。升级宿主和 launcher 后，旧编辑器会话里的快捷键立即走新版路径，菜单命令在该会话下次正常启动时加载新版扩展。 [Termux RUN_COMMAND](https://github.com/termux/termux-app/wiki/RUN_COMMAND-Intent) · [TermuxAm 广播实现](https://github.com/termux/TermuxAm/blob/master/app/src/main/java/com/termux/termuxam/Am.java)

### 构建与更新

在构建主机安装标准 JDK 21 和 Android SDK 的 `platforms;android-34`、`build-tools;36.0.0`。从已安装的 Linux Code 取得 `/usr/share/code/resources/app/resources/linux/code.png`。包含中文上屏修复的版本先在 Linux 或 WSL 安装 Android NDK `29.0.14206865`、CMake 3.22 及以上、Ninja、Bison 和 M4，构建 ARM64 原生库。打包时传入生成的库，并把 `native-manifest.json` 放在库的同一目录。`--upstream-apk` 仍可用于重建使用官方库的 1.4.1 版本。宿主和 loader 用同一组独立签名，构建产物和签名目录保存在仓库外。 [Android SDK 工具](https://developer.android.com/tools/sdkmanager)

```bash
python skills/termux/scripts/build_vscode_host.py native --android-ndk /path/to/ndk \
  --output /private/vscode-native
python skills/termux/scripts/build_vscode_host.py --android-sdk /path/to/sdk \
  --java-home /path/to/jdk --native-library /private/vscode-native/libXlorie.so \
  --code-icon /path/to/code.png --output /private/vscode-host
adb -s SERIAL install -r /private/vscode-host/vscode-host.apk
```

通过现有设备通道将同一次构建的 `vscode-loader.apk` 放到 Termux 可以读取的位置。用构建产物 `manifest.json` 核对 APK 摘要与签名，保留同一宿主签名用于覆盖安装。首次使用宿主时，按用户授权配置 Termux 的 `allow-external-apps`，并在 Android 权限界面授予该宿主 `RUN_COMMAND`。launcher 更新会校验会话锁，按安装器提示先保存并正常退出仍在运行的独立编辑器。 [Termux RUN_COMMAND 设置](https://github.com/termux/termux-app/wiki/RUN_COMMAND-Intent)

```bash
bash skills/termux/scripts/run.sh standalone-code launcher --dock-loader /path/to/vscode-loader.apk
bash skills/termux/scripts/run.sh standalone-code launcher --dock-loader /path/to/vscode-loader.apk --apply
```

主窗口沿用隔离配置的 `code/`。额外窗口首次创建时复制主窗口的设置和快捷键，并将各自的编辑器状态与登录存到 `windows/<编号>/code/`。同一 Debian 用户和已安装的扩展目录供这些窗口使用。仅覆盖安装 Android 宿主时，先记录现有标签、Linux PID 与窗口标题，再把失联的 Android 界面挂回原 X11 会话，核对原项目与编辑状态。

原生库升级后，现有 X11 进程会继续使用已加载的库。保存编辑内容和未发送的草稿，再正常关闭并重开需要验证的窗口。在临时编辑标签和新的 Codex 输入框分别提交整词「更新项目」，多次输入包含不同汉字的长句，对照候选、实际文字和字符顺序。X11 动态键映射更新后需要让客户端读取新映射，后续键盘事件通过同一队列派发。 [Termux:X11 问题 #1124](https://github.com/termux/termux-x11/issues/1124) · [上游修复提案 #1125](https://github.com/termux/termux-x11/pull/1125)

Y900 上的 1.4.2 已实测。模拟蓝牙键盘经 Gboard 提交的 6 次拼音，以及直接送入 X11 的 8 段长文本，在 Codex 输入框逐字回读共 218 个字符，内容和顺序一致。

#### 整段上屏试验

1.4.3 试验将普通 Gboard 候选串通过宿主与 X11 已建立的 Binder 连接送到 GTK。GTK 在准备接收时记录输入焦点，在提交前再次核对焦点，再把文本一次交给 VSCode。每个窗口有独立的本机套接字。旧宿主、未启用 GTK 模块和已按旧方式处理的合成文本继续走 1.4.2 的键盘事件路径。 [Android 文本提交接口](https://developer.android.com/reference/android/view/inputmethod/InputConnection#commitText(java.lang.CharSequence,int)) · [GTK 文本提交接口](https://docs.gtk.org/gtk3/signal.IMContext.commit.html)

在 VSCode 所在的 Linux guest 中，从包含 Termux skill 源码的目录构建 GTK 模块。缺依赖时执行 `sudo apt install gcc pkg-config libgtk-3-dev`，按 guest 的权限方式执行安装。

```bash
python3 skills/termux/scripts/build_vscode_ime.py --output /private/im-tablet-vscode.so
```

Android 宿主沿用前面的构建命令，额外传入 `--ime-bridge`。用 `--ime-test` 生成独立包 `com.scisaga.tabletvscode.imetest`。为隔离包启动匹配的 loader，分配专属 X11 标签、显示号和临时 VSCode 配置，再把该标签挂接到测试 Activity。载入前把测试 loader 设为只读（例如权限 `0400`）。Y900 的 Android 17 会拒绝加载可写的 DEX。正式宿主与 GTK 模块通过同一个 launcher 配置显式启用。

```bash
bash skills/termux/scripts/run.sh standalone-code launcher --dock-loader /path/to/vscode-loader.apk \
  --ime-gtk-module /private/im-tablet-vscode.so --apply
```

先用实际蓝牙键盘或模拟蓝牙 HID 核对 Gboard 候选，再回读普通编辑区和 Codex 临时草稿中的实际内容。模拟 HID 注册后等输入法就绪再发首键。验收覆盖整词「更新项目」、连续上屏、长句与中英文和 emoji 混合输入。用对应 X11 进程的 `TabletIme` 日志确认整段路径，日志只记录成功提交的字节数。上屏文字完整时仍需核对这条日志，以区分直接提交与键盘事件回退。

多窗口复测时保留尚未选中的候选词，切换到另一 Android 窗口后按确认键，回读两个窗口各自的内容。随后在两边分别提交新词，并检查编辑器焦点、重连旧服务和常用快捷键。去掉 `--ime-gtk-module` 并正常重开窗口可恢复键盘事件路径。

常见回退点在 Android 与 GTK 之间。先确认当前编辑框有焦点且对应套接字可读取就绪响应。`LocalSocket` 要先连接再设置读取超时，否则返回 `socket not created` 并走键盘事件路径。测试日志记录提交结果和字节数，实际内容从输入框回读。

Y900 的 1.4.3 隔离包已实测。模拟蓝牙键盘经 Gboard 向右侧 Codex 输入框提交 6 次「更新项目」，回读 24 字均完整，宿主日志记录 6 次直接提交。「保存位置」处于候选状态时切换到另一个 Android 窗口并按空格，另一窗口只收到空格，Codex 草稿仍是原来的 24 字。随后两个窗口都能独立提交「保存位置」。

本机 Electron 43.8.6 对照已验证普通文本框、富文本输入、长文本和焦点失效。该版本对应 VS Code 1.146.0。 [VS Code 构建版本](https://github.com/microsoft/vscode/blob/1.146.0/package.json#L5-L11)

以下命令用于重新挂接已确认仍在运行的会话，将 `vscode-N` 换成原标签。

```bash
adb -s SERIAL shell am start -W \
  -n com.scisaga.tabletvscode/com.termux.x11.MainActivity -d vscode-N
```

### 多窗口验收与恢复

先按 [子进程限制](android-permissions-and-power.md#phantom-process-killer--子进程限制) 回读有效上限和当前进程情况。将 Android 最近任务与原生 Termux 已占用的 `dock/<编号>/session.lock` 对照，并用 X11 窗口的 `_NET_WM_PID` 验证实际会话。关掉 ZUI 的缩略图可能只移除 Android 任务，独立 X11 和编辑器仍在运行。接近上限时，可先用已有会话检查切换，把新建测试安排在有余量时。

```bash
# 主机，使用当前已连接的设备
bash skills/termux/scripts/run.sh host-doctor --serial SERIAL
adb -s SERIAL shell dumpsys activity recents | rg 'dat=vscode-[0-9]+'
# 在提供 PhantomProcessRecord 的设备上查看当时的记录数
adb -s SERIAL shell dumpsys activity processes | rg -c 'PhantomProcessRecord \{'

# 原生 Termux，查看仍被会话持有的锁
for lease in "$HOME/.local/state/tablet-desktop/vscode-standalone/dock/"*/session.lock; do
  [[ -f "$lease" ]] || continue
  if ! flock -n "$lease" true; then
    printf '%s\n' "$lease"
  fi
done
```

从主屏实测单窗口返回，再按本次改动复测 **Ctrl+Shift+N**、**文件 → 新建窗口**和项目列表切换。核对每个 Android 任务的标签、实际出现的 Linux 窗口，以及 Dock 上的图标与标题。通过 Code 的正常退出关闭本次测试窗口，然后核对它的 X11 已结束、会话锁已释放、Android 任务已移除，以及原会话仍可操作。记录每条已测入口与未测项。

若新建时窗口或 SSH 同时消失，查看同一时段 `ActivityManager` 的 `Trimming phantom processes` 日志，逐个确认回收的 PID。正常结束本次测试窗口后，用原 profile 和原槽位恢复保存的工作区。可在该 profile 的 `User/globalStorage/storage.json` 查 `windowsState.lastActiveWindow`。主屏入口可能先返回其他存活会话，按实际工作区确认恢复目标。

如旧 X11 锁或 socket 阻止复用显示号，先在 native 环境核对会话锁已释放、记录的 Xserver 已退出、socket 已无监听，再备份移走这两个已确认的遗留记录。SSH 同时被回收时，可沿已有 USB/ADB 打开临时 Termux 终端，由已部署的 runit 恢复服务，再通过 `sv status "$PREFIX/var/service/sshd"` 和原通道复核。分别记录重新打开的工作区和仍待确认的未保存编辑。

#### 运行日志与残留进程

每个窗口每次启动写一份 `last.log`，最多保留 4 MiB。达到上限后写入截断提示，并继续排空管道。

排查旧日志时用 `df` 和 `du` 核对可用空间与实际占用，再用文件设备号、inode 和 `/proc/PID/fd` 确认写入者。处理前保留少量有代表性的报错，记录 PID、原 tracer 和所属会话，只清理用户授权的文件。旧描述符继续写入时可能形成稀疏文件，清理结果以实际分配空间和分区可用量为准。Y900 此前两个窗口的日志合计占用约 181 GiB。

Y900 的隔离复现中，单独结束 VSCode 主进程时 zygote 正常退出。让 PRoot 跟踪进程突然退出时，两个 zygote 留在系统里并高频报错。PRoot 的 seccomp 过滤器会将 `recvmsg()` 交给 tracer。tracer 消失后，Linux 返回 `ENOSYS`。Chromium 对这个错误记录日志并回到轮询。历史故障中终止 PRoot 的事件没有留存。 [PRoot 5.1.107.102 的过滤表](https://github.com/termux/proot/blob/v5.1.107.102/src/syscall/seccomp.c#L306-L330) · [Linux seccomp 文档](https://docs.kernel.org/userspace-api/seccomp_filter.html#return-values) · [Chromium zygote 的读取处理](https://github.com/chromium/chromium/blob/150.0.7871.250/content/zygote/zygote_linux.cc#L212-L228)

独立窗口的启动器在已有的 `--no-sandbox` 参数旁加上 `--no-zygote`，让 Electron 直接创建子进程。启动器还为每个窗口单独启用 Linux 子进程收养。PRoot 退出后，只回收被此窗口接管的子进程，例如 D-Bus、GVfs 和 Xfce 配置服务。新启动的窗口使用这两项设置。 [Chromium 启动参数](https://github.com/chromium/chromium/blob/150.0.7871.250/content/public/common/content_switches.cc)

故障注入使用限量日志和临时配置，分别对照正常退出、主进程退出和 PRoot 突然退出。逐项复核该会话的子进程、显示号和日志，确认日常窗口仍能使用。Y900 使用独立 VSCode 的原 GPU 参数完成了编辑、保存、Codex 扩展激活和正常退出的复测。强制终止隔离 PRoot 后，启动器约 0.12 秒退出，该会话的进程已回收，日志中没有出现上述循环报错。

需要回到官方 X11 入口时，先正常结束窗口，再执行不带 `--dock-loader` 的 `launcher --apply`。

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
- **Office Viewer** 默认只关联 `.docx`、`.dotx`、`.xls`、`.xlsx`、`.xlsm`、`.ods`、`.pptx`、`.pptm`。首次安装选用已验证的 `4.2.3`，安装前写入 `workbench.editorAssociations`，约束它声明的其他默认文件关联。Markdown、CSV/TSV、压缩包等使用已选编辑器或内置编辑器。安装顺序任意，两个扩展都在时会把 PDF 的内置默认值更新为 `pdf.view`，并尊重已选的其他 PDF 查看器。已装 Office Viewer 或升级后重跑同一条无版本号命令，按实际安装的扩展清单校正关联。若工作区覆盖用户设置，验收时用 **Reopen Editor With…** 查看该文件实际的默认编辑器。 [Office Viewer 扩展说明](https://marketplace.visualstudio.com/items?itemName=cweijan.vscode-office)

Marketplace 不可达时，可在 Debian 中安装已核对发布者、版本和目标架构的官方本地 `.vsix`。已有缓存文件缺少后缀时，在私有临时目录建立带 `.vsix` 后缀的链接并在安装后清理。Office Viewer 优先使用上面的默认安装入口。离线安装 Office Viewer 前先关掉独立窗口，安装后执行同一入口写入文件关联，再打开 Code。

```bash
code_root="$HOME/.local/share/tablet-vscode"
code --no-sandbox --user-data-dir "$code_root/code" --extensions-dir "$code_root/extensions" \
  --install-extension /path/to/extension.vsix
```

## 在 Android Chrome 预览 HTML

安装 **Open In Default Browser** 后可选配独立实例的 HTTP 路由。先确认 Android Chrome 已安装，且隔离配置已有可用的 Linux HTTP 浏览器。脚本保留这个处理程序，供普通 HTTP URL 使用。Debian 中缺少浏览器路由工具时安装 `libglib2.0-bin`、`xdg-utils` 和 `python3`。

安装过程中若 HTTP 默认项校验失败，已有的 MIME 配置、启动脚本和 `.desktop` 文件会恢复到安装前的状态。

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
