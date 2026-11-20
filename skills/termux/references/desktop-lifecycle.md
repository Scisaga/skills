# 会话生命周期、进程治理与电量

## 原生控制服务

native runit 服务 `tablet-touch` 同时处理输入切换与桌面生命周期。它通过同 UID 校验的 Unix socket 提供固定动作，文件权限 0600，不提供任意命令执行或额外 TCP 管理端口。

核心文件：native `~/.local/lib/tablet-desktop/`、`~/.config/tablet-desktop/config.json` 与 `~/.local/state/tablet-desktop/`；guest `/usr/local/lib/tablet-desktop/ipc.py` 和 `/usr/local/bin/tablet-*`。名称沿用已部署接口。

```bash
desktop start
desktop status --json
desktop events --json
desktop manage
desktop manage --terminal
```

启动请求在健康桌面存在时直接返回该会话。控制器持有长生命周期 PRoot，不依赖启动终端；guest 使用 `dbus-run-session -- xfce4-session`，通过 XDG autostart 注册当前 DISPLAY/D-Bus 环境。桌面正常结束后不自动复活；下次 start 才重启。

服务重启应复用持久化身份记录，只接管所配置容器中的桌面会话，不将短诊断 shell 或其他容器纳入管理。升级 runtime 前正常退出桌面；不要用重启整套 Termux 代替日常退出。

可选 native Chromium/LibreOffice 由固定控制动作在 PRoot 外启动，只有已记录且身份匹配的 native root/后代加入本桌面，正常结束仍等待其窗口保存提示。Termux:VA 解码桥接按需启动，单独记录服务及 socket 身份，结束桌面时在应用之后回收。诊断用 PRoot 不应长期持有日常 GUI：需要 guest GUI 时从既有 Xfce 会话启动；Thunar D-Bus Execute 的 files 参数是文件列表，不能把命令行开关塞进去当 argv。

## 正常结束

入口在 Xfce 桌面、菜单与顶部栏，Android 管理器也提供“正常结束”。流程：

主菜单只显示标准 `xfce4-session-logout.desktop`，同样调用受管的 `tablet-desktop-end`。兼容 ID `tablet-desktop-end.desktop` 保留但设 `NoDisplay=true`，避免两个同名菜单项；桌面快捷方式和面板按钮保持可见。现场调整先在 Xfce 中打开菜单，再从该桌面终端检查用户级 desktop 文件，不为此切到原生 Termux。

1. 用户确认；取消立即返回当前桌面。
2. 按窗口顺序发送普通 WM_DELETE 请求；应用自己的保存提示由用户处理。
3. 未关闭的窗口继续阻塞退出，可随时取消。不能自动选择“不保存”。
4. 窗口结束后请求真实 xfce4-session logout。
5. 控制器清理已记录且身份仍匹配的本次桌面进程、X11 和自己持有且无其他客户端的音频服务。保留 SSH 和原有 SSH wake-lock。

正常退出会结束本次桌面的后台任务，首次使用时应说明。退出包装器只接管 logout，不随意重写其他电源操作。guest 的系统休眠/关机不能当成 Android 电源控制。

强制结束位于 Android 管理器中，需用户明确确认并携带当前会话 UUID。CLI 有 `force-stop --confirmed --session UUID --json` 诊断路径；不能由自动恢复逻辑冒充确认。

独立 VS Code 使用自己的 X11 会话。ZUI 移除窗口缩略图可只结束 Android 界面，Linux 应用继续运行。要结束该会话，在编辑器内正常退出并处理保存提示，再检查 X11 已结束且会话锁已释放。要返回仍在运行的会话，按原标签重新挂接 Android 窗口。 [独立 VS Code 多窗口验收与恢复](standalone-code.md#多窗口验收与恢复)

## 防止遗留进程占满 CPU

本次会话发现过早期脱离 PRoot 的进程持续占满单核；未唯一证明最初触发原因。预防方案是受控会话与身份记录，不是定时全局 pkill。

记录包含 Android UID、PID、内核创建 ticks、可执行文件、session UUID、所属 PRoot tracer/root 和 boot ID。PID 被复用、另一个 UID、另一个会话或仍被 tracer 管理时，都不能自动终止。

自动采样间隔 60 秒。自动清理仅覆盖已记录的 Code zygote / D-Bus 辅助进程，并同时满足原 tracer 与桌面核心已结束、当前无 tracer、连续两次高 CPU。TERM 后再次核验身份，必要时才 KILL。其他高负载只记录，活动应用、renderer、编译任务不因 CPU 高而被自动清理。

`manager-events.jsonl` 有大小轮换；采样历史在明确的会话切换时清空。诊断时先看事件和 PID 身份；不要按进程名或 PPID=1 大范围清理。

## 息屏与功耗

切回 Android、关闭启动终端或息屏，不会主动触发桌面 logout。Android/厂商仍可能回收后台进程；物理息屏、普通锁屏和重启后首次解锁必须分开测试。

沿用原生 SSH 的 Boot/runit、wake-lock 和设备电源策略。只有用户要求时配置 USB/充电常亮，记录旧值与新值；常亮会增加屏幕功耗，它不是后台存活方案。不要全局禁用系统省电或设置无限 phantom process 上限。

PRoot 调用转换、软件渲染和视频解码会产生开销。看进程 CPU/PSS、idle 活动、刷新率、温度和实际任务时长；亮屏尺寸/亮度通常也影响整机功耗。一次 CPU/PSS 快照不是续航结论，不承诺平板全部性能无损。

Android/Xfce 的多进程内存快照、SwapPss/图形去重、实际 ZRAM 占用与可回退的应用级优化见 [应用内存诊断](desktop-memory.md)。

## Android 电池桥接

native 控制器在桌面活动时每 60 秒调用一次 `termux-battery-status`；guest genmon 只读取缓存，不高频唤起 API。缓存包含真实百分比、充电/插电状态、温度和更新时间。过期 180 秒显示不可用，不伪造 guest sysfs/UPower 电池。

Termux:API APK 与 native `termux-api` 包都需要。此功能只请求电量能力；缺少可选 API 时桌面与输入服务继续工作，状态显示未知。
