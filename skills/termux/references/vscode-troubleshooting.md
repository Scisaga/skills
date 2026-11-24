# VS Code 与 Codex 排查

适用于 Termux:X11 与 Debian PRoot 的独立 VS Code，包含 Y900「无限工作台」与小米平板 7 HyperOS 的实测案例。先确认当前使用 Dock 还是 Widget，以及问题发生在 Android 任务、X11 窗口、Debian 编辑器还是 Codex 子进程。
完整的系统日志、进程列表和编辑器状态留在设备或私有工作目录，记录本次判断所需的行。

## 窗口显示 Not connected 或点图标开了新窗口

主屏 VSCode 图标调用启动器，最近任务卡片可以直接恢复旧的 Android 界面。对照同一次操作的任务标签、会话锁、显示号和 X11 窗口 PID。

```bash
# 主机，沿用当前 ADB 连接。把 SERIAL 换成已确认的设备
adb -s SERIAL shell dumpsys activity recents | rg "dat=vscode(-[0-9]+)?"
adb -s SERIAL shell dumpsys activity exit-info com.termux
adb -s SERIAL shell logcat -b system -d -s ActivityManager:I ActivityTaskManager:I "*:S"

# 原生 Termux，从 skill 源码所在仓库运行
bash skills/termux/scripts/run.sh standalone-code inspect

# 同一 X11 显示。也可在共享 X11 套接字的 Debian guest 执行
# DISPLAY_NUMBER、WINDOW_ID 取自现场
DISPLAY=:DISPLAY_NUMBER xprop -root _NET_CLIENT_LIST
DISPLAY=:DISPLAY_NUMBER xprop -id WINDOW_ID _NET_WM_PID _NET_WM_NAME
```

1. 锁仍被持有且原显示能读到预期编辑器时，可用原标签挂回界面。复核标签、编辑器 PID 与创建 ticks、项目和可见编辑状态。 [重挂原标签](standalone-code.md#y900-的-dock-图标和独立窗口)
2. 如果锁已释放、编辑器身份失效且显示无人监听，保留旧槽位和用户数据，从真实的主屏 **VSCode** 图标启动。必要时按原文检查残留的 X11 套接字和锁文件。 [多窗口验收与恢复](standalone-code.md#多窗口验收与恢复)
3. 新窗口可能选到另一个槽位。主槽的配置在 guest `~/.local/share/tablet-vscode/code/`，额外槽位在 `windows/N/code/`。需要复原项目时先保留原槽的 `User/globalStorage/storage.json` 和 `Backups/`，按原项目路径或 **File → Open Recent** 打开。项目重新打开后还要核对未保存内容与 Codex 草稿。

Y900 现场出现过 `REMOVE TASK` 与 `zui-desktopmode-kill-associated-process`，随后 `startActivityFromRecents` 恢复了旧任务卡片。此时原 Termux 进程、X11 和编辑器已经结束，界面显示 `Not connected`。主屏启动器随后打开了可用窗口。按发生时间核对日志，出现 `Trimming phantom processes` 时另查当时的子进程上限。 [子进程限制](android-permissions-and-power.md#phantom-process-killer--子进程限制)

## 退出 VS Code 后仍有 Codex 进程

先只读对照 Android 任务、X11 会话和父进程。VS Code 扩展通过 stdio 与它启动的 `app-server` 通信，关闭连接后子进程会清理并退出。终端启动的 Codex 和单独运行的守护进程有各自的会话。 [OpenAI 的 VS Code 集成说明](https://openai.com/index/unlocking-the-codex-harness/) · [App Server 文档](https://developers.openai.com/codex/app-server/)

| 现场证据 | 会话状态与处理 |
| --- | --- |
| Android 卡片已关闭，Code 父进程、PRoot tracer 和会话锁仍在 | Linux 会话仍存活。Codex 可能休眠且 CPU 采样为 0%，依然随该会话处理 |
| Code 或 PRoot 已结束，旧 PID 的会话身份可核对，且连续高 CPU、无 tracer | 复核旧槽位、启动时间和活动窗口，再按进程退出流程处理 |
| 进程状态为 `Z` | 进程已退出，等待其父进程回收。复查对应会话的收尾结果 |

需要结束会话时先保存编辑内容和 Codex 草稿。从对应窗口用 **File → Exit** 正常退出。触屏或输入法吞掉退出操作时，在同一 X11 会话用 `_NET_CLIENT_LIST` 和 `_NET_WM_PID` 核对窗口，再用 `DISPLAY=:DISPLAY_NUMBER wmctrl -i -c WINDOW_ID` 向该窗口发送关闭请求。回看可能出现的保存对话框。

如果 Android 任务已被移除，且 `app-server` 的父进程和 PRoot tracer 仍在，继续核对 Linux 编辑器是否收到关闭请求。Y900 宿主 1.4.2 曾在系统记录 `USER REQUESTED / REMOVE TASK` 后仍有整套 Linux 会话。1.4.4 使用对应任务和会话标识传递正常关闭请求，可在 `logcat -s VSCodeTaskClose` 和该槽位的 `last.log` 对照请求与结果。 [宿主更新与验收](standalone-code.md#多窗口验收与恢复)

小米平板 7 的官方 Termux:X11 在上划后曾记录 `OTHER KILLS BY SYSTEM / SwipeUpClean`。专用宿主也可能被 HyperOS 标为 `FORCE STOP`。用 `dumpsys package` 核对宿主是否为 `stopped=true`，并查看是否收到关闭请求。宿主 1.4.6 在 Termux 侧处理停止后的单会话正常退出。 [更新原 Widget 入口](standalone-code.md#安装主屏入口)

```bash
# 主机。PACKAGE 取设备当前 X11 界面的包名
adb -s SERIAL shell dumpsys activity exit-info PACKAGE
adb -s SERIAL shell dumpsys package PACKAGE | rg 'versionName=|stopped='
adb -s SERIAL shell logcat -d -s VSCodeTaskClose
```

- **普通切换**。从原入口打开测试用编辑器并确认 Codex 启动。返回主屏或切换应用后核对原 PID 及会话锁。
- **关闭卡片**。用同一种手势复现，按时序对照 Android 退出记录、Termux 的关闭请求和该槽位的 `last.log`。核对扩展宿主正常退出、原 X11/Code/Codex 进程消失、显示号与会话锁释放。
- **并发窗口**。设备支持多窗口时，关闭一个窗口后回读另一个的 PID 和实际界面。HyperOS 的宿主强停恢复以一个独立会话为前提，多会话由各窗口正常结束。 [Y900 与小米平板 7 的实机回读](standalone-code.md#多窗口验收与恢复)

```bash
# 原生 Termux。先查看进程列表
ps -A -o UID,PID,PPID,STIME,S,CMD
# 原生 Termux。PID_A、PID_B 换成从现场确认的 PID
bash skills/termux/scripts/run.sh standalone-code inspect --pid PID_A --pid PID_B
top -b -n 3 -d 2 -p PID_A,PID_B -o PID,S,%CPU,TIME+,CMD -s 3
```

- `inspect` 输出当前 boot ID、原生 UID、窗口租约和指定 PID 的创建 ticks、父进程、tracer、CPU ticks 与会话环境。可重复采样。`unavailable` 表示读取未完成，需用 `ps` 和 `/proc` 复查。`editor_identity_matches` 只核对 PID 与创建 ticks，窗口是否仍可用由 X11 回读确认。
- `PPID=1` 或进程名相同只能提供线索。结合 `DISPLAY`、`TABLET_VSCODE_DOCK_TAG`、`VSCODE_STANDALONE_DATA`、旧租约和当前编辑器 PID 验证归属。PRoot 里的进程在原生 `/proc/PID/exe` 中可能指向 loader。`/proc/PID/task/PID/children` 不可读时，用完整进程列表的 `PPID` 复核。Android Python 缺少 `pidfd_open` 时，仍可用 UID、boot ID 和 start ticks 核对同一进程。
- 归属明确且与活动会话无关后，按 [退出与强停边界](desktop-lifecycle.md#正常结束) 逐个处理。正常退出失败后，`TERM` 前后均核对身份。仍需强停时取得针对当前 PID 的授权，再核对 UID 与 start ticks。最后复查旧 PID、CPU 和仍在用的 VS Code/Codex。避免按名字批量结束进程或强停 Termux。

Y900 上两条高 CPU 的 Codex 来自旧槽位，原租约已释放，采样中为 `PPID=1`、`TracerPid=0`，单个 PID 接近占满一核。定向 `TERM` 后仍存活，经用户授权定向 `KILL` 后退出，其他窗口继续可用。最先结束旧 PRoot 的事件没有得到证实。PRoot 跟踪器突然退出后，相关 seccomp 调用可能返回 `ENOSYS`。该机制曾在 Chromium zygote 的隔离复现中确认，旧 Codex 的具体循环调用没有取证。 [隔离复现与上游源码](standalone-code.md#运行日志与残留进程)

独立入口的监督器会在编辑器退出后回收它接管的会话子进程。检查对应 `session.py` 进程的 `editor_exit_guard` 或 launcher 调用处。需要更新时用 `standalone-code supervise --entry dock --apply`，Widget 设备把 `dock` 换成 `widget`。新会话启用新监督器，旧孤儿按上面的身份流程处理。验收覆盖正常退出、临时会话中 PRoot 异常退出和一份同时运行的其他会话。 [监督器入口](standalone-code.md#运行日志与残留进程)

## Termux user 与最近的异常掉电

```bash
# 主机。ANDROID_USER 取第一条结果，APP_UID 取第二条中 package:com.termux 的 uid
adb -s SERIAL shell am get-current-user
adb -s SERIAL shell cmd package list packages -U --user ANDROID_USER com.termux
adb -s SERIAL shell id -nu APP_UID
adb -s SERIAL shell dumpsys batterystats --usage
adb -s SERIAL shell dumpsys batterystats --history
adb -s SERIAL shell dumpsys cpuinfo
```

`Termux user` 是 Android 电量界面按应用 UID 汇总的归因。同 UID 的 Termux 组件和原生、PRoot 进程可以共同计入。对照实际运行的 Android 用户和包 UID。X11 界面或 VSCode Android 宿主可以有自己的 UID。

从 history 里定位近期 `status=discharging`、`plug=none` 的实际放电区间，按 `+screen`/`-screen` 对照亮屏、息屏和 Doze。记录时长、电量百分点及同一来源的电荷计数差。交叉核对 `batterystats` 与 `dumpsys battery` 时先确认 mAh 和 µAh 的单位。`batterystats --usage` 有亮屏、息屏/Doze 和插电等累计区段。保留原统计窗口，用相近亮度和负载对比退出旧高 CPU 进程前后的电量变化与 CPU 样本。

一次 Y900 样本在约 23 分钟内由 42% 降到 37%，放电主要出现在连续亮屏时段，两个旧 Codex 在多次采样中持续占用 CPU。系统 UID 的累计占比与单 PID 的 CPU 百分比只能说明归因和负载，样本没有给出每个 Codex 进程的实际电量。 [息屏与功耗](desktop-lifecycle.md#息屏与功耗)

## Update 点完消失但版本未变

先在 **Help → About** 和同一 Debian guest 的 `dpkg-query -W -f='${Version}\t${Architecture}\n' code` 核对版本。Linux 1.146.0 的更新动作打开外部下载链接并复位按钮状态。由 Microsoft APT 仓库管理的 Debian `code` 包走包管理器更新。 [VS Code 1.146.0 源码](https://github.com/microsoft/vscode/blob/1.146.0/src/vs/platform/update/electron-main/updateService.linux.ts#L67-L75) · [Linux 更新文档](https://code.visualstudio.com/docs/setup/linux#updates)

```bash
# 原生 Termux，默认只读已安装版本、源、密钥环与缓存候选
bash skills/termux/scripts/run.sh standalone-code update
# 刷新 Microsoft 签名源，模拟并下载 code。可在编辑器正常运行时准备
bash skills/termux/scripts/run.sh standalone-code update --prepare
# 保存工作并正常退出同一个 Debian 环境的 VS Code
# DEBIAN_PACKAGE_VERSION 换成上一步输出的完整 target
bash skills/termux/scripts/run.sh standalone-code update --apply --version DEBIAN_PACKAGE_VERSION
```

- 遇到 `Missing key`、`NO_PUBKEY` 或证书错误，先检查 guest 中 `vscode.sources` 或 `vscode.list` 的官方地址、架构、`Signed-By` 指向和文件大小。Y900 实际遇到的是 `/usr/share/keyrings/microsoft.gpg` 为 0 字节。准备步骤只修复这个缺失或为空的默认密钥环，下载官方 `microsoft.asc`，核对完整指纹 `BC528686B50D79E339D3721CEB3E94ADBE1229CF` 后再原子写入。若是其他密钥路径、非空密钥或密钥轮换，按当前 Microsoft 文档核实并修复配置。始终保留 TLS、APT 签名与包校验。 [Microsoft 官方签名密钥](https://learn.microsoft.com/en-us/linux/packages#how-to-use-the-gpg-repository-signing-key)
- 缺少更新源时，按官方 Debian/Ubuntu 步骤在所用 guest 配置带 `Signed-By` 的仓库。索引未发布 UI 提示的版本时等仓库同步，再准备更新。缓存里的目标版本已清理时可重跑 `--prepare --version DEBIAN_PACKAGE_VERSION`。 [官方 APT 安装与更新](https://code.visualstudio.com/docs/setup/linux#updates)
- 准备步骤留下签名验证过的索引和下载缓存。更新遵守桌面 `code_version` 与 APT hold，模拟若涉及其他包就停止并显示原因。安装阶段持有 Widget/Dock 会话锁，用确切版本与现有缓存执行升级。Xfce 的常规窗口也需要正常退出。
- 以 `dpkg-query` 回读及原入口重开的 **Help → About** 验收版本，再核对原项目、设置、扩展和 Codex。若重开分配到其他槽位，走上面的项目和数据恢复流程。本次 Y900 以该流程从 `1.146.0` 更新到 `1.147.0`，并在重开后恢复原项目。
