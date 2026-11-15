# Android 权限与息屏保活

## 权限分层

Termux 内的 Unix 文件权限不能替代 Android 运行时权限。分别处理：

- `com.termux`：共享存储、前台服务、唤醒锁。
- `com.termux.x11`：桌面场景分别检查 X11 的后台与电池策略；它不要求与 Termux 共用 UID。
- `com.termux.api`：相机、位置、附近 Wi-Fi 所需权限、通知；远程拉起相机时某些 ROM 还需要悬浮窗/后台启动能力。
- `com.termux.boot`：开机广播与后台启动；安装后必须手动打开一次。

主机侧脚本默认只预览：

```bash
bash scripts/run.sh host-permissions --serial SERIAL \
  --storage --api-battery --background
```

用户明确授权后才加：

```bash
bash scripts/run.sh host-permissions --serial SERIAL \
  --storage --api-battery --background --apply
```

权限名称和 Android 行为会随版本变化。脚本会尽力设置已声明的权限，但最终要用真实功能验证，而不是只看 `pm grant` 返回值。

按能力选择 `--camera`、`--location`、`--notifications`、`--overlay`；`--api-battery` 只检查 API 安装状态，不授予相机或定位权限。旧 `--api`/`--all-standard` 保留兼容但会提示其广泛授权范围，新流程避免直接使用。沿用本次用户已授权的范围执行 `--apply`，不因脚本分步而重复请求相同授权。

官方 Termux:API 当前未声明一套可用的蓝牙扫描/连接 CLI，因此基础权限脚本不会虚构或强授予 `BLUETOOTH_SCAN`/`BLUETOOTH_CONNECT`。蓝牙扩展边界见 `remote-management.md`。

## Boot 与加密边界

Termux:Boot 官方流程要求：安装后打开一次，在 `~/.termux/boot/` 放可执行脚本；需要持续运行时可先调用 `termux-wake-lock`。官方说明：<https://github.com/termux/termux-boot#how-to-use>

设置了图案、PIN 或密码的现代 Android 通常使用凭据加密存储。重启后、用户首次解锁前，普通 Termux 的 `$HOME` 不可用；首次本地解锁后，之后再次锁屏和息屏不应影响 SSH。Android Direct Boot 说明：<https://developer.android.com/privacy-and-security/direct-boot>

不要把“重启后尚未首次解锁”误诊为 Boot 配置失败。若业务要求无人值守重启后立即 SSH，需要 Direct-Boot-aware 的独立应用、设备管理方案或真实 Root；原生 Termux 配置无法绕过凭据加密。

## 标准后台设置

对实际安装的 Termux、API、Boot 执行并验证；桌面场景还包括 Termux:X11。脚本跳过未安装的可选包：

- 电池策略设为“不限制/无限制”。
- 允许自启动、后台活动、前台服务和通知。
- 加入 Android DeviceIdle 用户白名单。
- Termux 中运行 `termux-wake-lock`，并保持 Termux 前台服务通知存在。

不要为了一个应用全局关闭 Doze、缓存应用冻结或 PowerKeeper。优先做包级豁免，保留设备其余省电策略。

桌面场景另外在 ROM 电池管理中分别检查 Termux 与 Termux:X11 的“不限制/允许后台高耗电”，并在最近任务页面按实际方式锁定两者。DeviceIdle 白名单、AppOps、厂商电池页面与最近任务锁定是不同层，某项通过不能代替其他项。最近任务锁定也不能避免所有内存压力终止；真实息屏后再新建 SSH 和返回 Xfce 验收。USB 常亮不替代息屏测试。

HyperOS 的“自启动管理”需要单独验证。可先解析 `miui.intent.action.OP_AUTO_START`，再通过实际系统界面只允许本次需要的 Termux、API、Boot、X11 和 VPN。部分版本会以 `MIUIOP(10008): ignore` 及开机时的 rejectTime 记录拦截；该数值只作当前 ROM 的诊断证据，不跨机型盲写私有操作。重启首次解锁后应等待服务自行恢复，不能先手动打开 Termux 或 VPN 再宣称自启动通过；修改权限后需要重新重启复验。

个别 HyperOS 实测出现共享 UID 插件的自启动开关在重启后回退，而主应用保持允许。此时先记录实际包级状态与广播拦截，不反复盲开开关；确需后台开机恢复时，可使用 [独立管理器的可选恢复入口](android-desktop-integration.md)，保留官方 Boot 与既有服务。仅本机桌面不强制启用 SSH。配置值、当前有效值和重启后的值通过 [统一验收入口](desktop-verification.md#可重复执行的验收入口) 分阶段记录，首次解锁等待可续用检查点，不要求每次重新重启。

## Phantom Process Killer / 子进程限制

PRoot、Xfce 和浏览器会创建多个子进程。先用 `host-doctor` 分别记录存储配置、当前有效上限和监控标志：

```bash
adb -s SERIAL shell device_config get activity_manager max_phantom_processes
adb -s SERIAL shell dumpsys activity settings
adb -s SERIAL shell settings get global settings_enable_monitor_phantom_procs
adb -s SERIAL shell getprop persist.sys.fflag.override.settings_enable_monitor_phantom_procs
```

提高 cap 与禁用监控是两种策略。实际 cap=128 不表示 Phantom 监控已停用；null/空标志也不能证明已关闭。signal 9 还可能来自 LMKD/内存压力、厂商后台策略或手动终止，须结合相同时段 ActivityManager/lmkd 日志确定原因。

若用户选择提高上限，先保存原值，采用适度上限并回读 `dumpsys activity settings`，不默认写入最大整数。例如已授权时：

```bash
adb -s SERIAL shell device_config put activity_manager max_phantom_processes 128
adb -s SERIAL shell dumpsys activity settings
# 回退：原值为 null 时删除覆盖；否则 put 回原值
adb -s SERIAL shell device_config delete activity_manager max_phantom_processes
```

若重启后普通 `put` 被服务端配置还原，先检查 `device_config help` 是否提供按单个参数的 `override`。支持时可只固定这个上限，并用 `put` 触发 ActivityManager 的即时更新：

```bash
adb -s SERIAL shell device_config override activity_manager max_phantom_processes 128
adb -s SERIAL shell device_config put activity_manager max_phantom_processes 128
adb -s SERIAL shell device_config list_local_overrides
adb -s SERIAL shell dumpsys activity settings
```

只看到 `get` 返回 128 仍不够：部分版本在 `override` 后，ActivityManager 的有效值仍可能是 32，需完成第二条命令并回读有效值。记录原有该项覆盖、普通值和监控状态；重启后再核对有效上限。按项覆盖保留其余配置同步，无需全局关闭 DeviceConfig 同步。回退时仅 `clear_override activity_manager max_phantom_processes`，再恢复该项原值；保留其他参数的已有覆盖。

用户明确选择解除限制时，Android 14+ 部分 ROM 开发者选项提供“停用子进程限制 / Disable child process restrictions”；开启后重新核对 monitor 标志及实际行为。该选择影响系统监控，不仅针对 Termux，不能隐含在普通包级保活中。关闭开发者选项、OTA 或 ROM 策略可能重置它；记录改动前值与回退方式，不同时改变不相关的 Doze/freezer 开关。

参见 [Termux 官方 Android 限制说明](https://github.com/termux/termux-app#android-12) 与 [Termux 维护者 Phantom 机制说明](https://github.com/agnostic-apollo/Android-Docs/blob/master/en/docs/apps/processes/phantom-cached-and-empty-processes.md)。

## HyperOS/MIUI Greeze

### 何时进入这条分支

典型现象：

- `sshd` 进程仍在、8022 仍监听。
- 物理息屏后 SSH 在 banner 阶段超时。
- 锁屏但屏幕仍亮时可以连接。
- `dumpsys power` 中 `termux:service-wakelock` 显示 `DISABLED`。
- logcat 明确出现 `reason: greeze`，或 `dumpsys greezer` 记录 Termux UID 被 `FZ`。

诊断示例：

```bash
adb -s SERIAL shell dumpsys power | \
  grep -E 'mWakefulness=|termux:service-wakelock'

adb -s SERIAL shell logcat -d -v threadtime | \
  grep -Ei 'termux:service-wakelock|reason: greeze|PowerManagerServiceImpl'

adb -s SERIAL shell dumpsys greezer | \
  grep -E 'com.termux|FZ uid|THAW uid|SCREEN (ON|OFF)'
```

Termux、API、Boot 共用 UID，但 Greeze 可能把 UID 归到任一包名。只豁免 `com.termux` 可能仍被冻结。因此确认日志后，把以下三个包都加入 `Settings.System.MILLET_NO_RESTRICT_APP`，并保留原有列表：

```text
com.termux
com.termux.api
com.termux.boot
```

若安装了本 skill 的蓝牙 companion，也加入：

```text
io.github.scisaga.termuxbluetoothbridge
```

使用：

```bash
bash scripts/run.sh host-permissions --serial SERIAL \
  --hyperos-greeze --apply
```

若 SSH 地址依赖设备上的 VPN，还要把实际 VPN 包加入相同的后台策略。例如设备使用官方 WireGuard：

```bash
bash scripts/run.sh host-permissions --serial SERIAL \
  --background --hyperos-greeze \
  --keep-package com.wireguard.android --apply
```

先用 `dumpsys connectivity`、`ip addr` 和包状态确认 VPN 实现，不要仅凭接口名猜包名。

`MILLET_NO_RESTRICT_APP` 是 PowerKeeper 从其用户配置表中所有 `bgControl=noRestrict` 项生成的派生列表。脚本直接合并该值可以立即修复和验证，但 PowerKeeper 可能在重启或用户修改其他应用电池策略时重新生成它。要做持久交付，还必须在小米自己的应用耗电策略页面中，把实际安装的 Termux、Termux:API、Termux:Boot 和蓝牙 companion 分别设为“不限制”；之后重新读取该列表并重启验证。

在当前 HyperOS 能解析标准 intent 的情况下，可逐包打开对应页面：

```bash
adb -s SERIAL shell am start -W \
  -a android.settings.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS \
  -d package:com.termux.api
```

不要用 ADB 绕过图案/PIN。若页面被锁屏层遮挡，让用户正常解锁后再继续。遇到复发先重新读取设置和 `dumpsys greezer`，不要直接反复重启服务。关于该私有列表与 Greeze 的代码和实机研究：<https://github.com/dingwen07/hyperos-fcm-fix/blob/main/docs/xiaomi-hyperos-gms-fcm-greezer-investigation.md>

验收必须同时满足：

- `mWakefulness=Asleep`；
- `termux:service-wakelock` 不含 `DISABLED`；
- 静置超过设备的冻结窗口后，新建 SSH 会话成功；
- `dumpsys greezer` 没有新增 Termux UID 的 `FZ` 事件；
- 重启并首次解锁后重复上述检查。

厂商私有实现可能改变。只有日志证据吻合时才使用这条分支，不要把 `MILLET_NO_RESTRICT_APP` 当作所有 Android 的通用设置。

## Lenovo ZUI 的自启动与关联启动

DeviceIdle 白名单、AppOps allow、standby bucket=5 不代表 ZUI 已允许自启动。实测重启后系统已解锁，`com.termux.boot` 的 BOOT_COMPLETED 广播仍可因 `startProcessLocked failed` 失败；system log 中 `ZuiAutoRunManager` 明确记录 `isAllowStart not allow start`。同一策略也可能拦截 Termux 启动 Termux:API，导致电量缓存过期。

先分清用途：本机 Linux 桌面不依赖 SSH。若用户只要求本机桌面，不把 SSH 开机自启设为桌面验收的前提；使用正式 Linux 桌面入口按需启动服务。需要无人值守 SSH 时，另验证 Termux:Boot 自启动；需要电量插件自动冷启动时，另验证 Termux → Termux:API 的关联启动。

诊断仅筛选相关包的 system log 和 `dumpsys activity broadcasts`，不要保存无关系统日志。通过 ZUI 自身设置管理实际包级开关，不改全局省电策略。安全中心首次启动若要求接受隐私政策并允许联网，这是一个额外用户选择，不能把配置自启动当作已经同意该条款。只做了手动打开 Termux/API 的恢复时，要明确报告，不能计为开机自动恢复通过。

## Wi-Fi 锁限制

新 Android 已弃用传统高性能 Wi-Fi 锁，并可能转换为低延迟锁；低延迟锁的有效条件包括屏幕开启和应用在前台。不要只凭 Wi-Fi lock 状态判断息屏 SSH 是否可靠。以真实局域网连接和 CPU wake lock 为准。Android API 说明：<https://developer.android.com/reference/android/net/wifi/WifiManager>
