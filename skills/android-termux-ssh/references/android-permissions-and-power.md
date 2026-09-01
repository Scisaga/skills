# Android 权限与息屏保活

## 权限分层

Termux 内的 Unix 文件权限不能替代 Android 运行时权限。分别处理：

- `com.termux`：共享存储、前台服务、唤醒锁。
- `com.termux.api`：相机、位置、附近 Wi-Fi 所需权限、通知；远程拉起相机时某些 ROM 还需要悬浮窗/后台启动能力。
- `com.termux.boot`：开机广播与后台启动；安装后必须手动打开一次。

主机侧脚本默认只预览：

```bash
bash scripts/run.sh host-permissions --serial SERIAL \
  --storage --api --background
```

用户明确授权后才加：

```bash
bash scripts/run.sh host-permissions --serial SERIAL \
  --storage --api --background --apply
```

权限名称和 Android 行为会随版本变化。脚本会尽力设置已声明的权限，但最终要用真实功能验证，而不是只看 `pm grant` 返回值。

官方 Termux:API 当前未声明一套可用的蓝牙扫描/连接 CLI，因此基础权限脚本不会虚构或强授予 `BLUETOOTH_SCAN`/`BLUETOOTH_CONNECT`。蓝牙扩展边界见 `remote-management.md`。

## Boot 与加密边界

Termux:Boot 官方流程要求：安装后打开一次，在 `~/.termux/boot/` 放可执行脚本；需要持续运行时可先调用 `termux-wake-lock`。官方说明：<https://github.com/termux/termux-boot#how-to-use>

设置了图案、PIN 或密码的现代 Android 通常使用凭据加密存储。重启后、用户首次解锁前，普通 Termux 的 `$HOME` 不可用；首次本地解锁后，之后再次锁屏和息屏不应影响 SSH。Android Direct Boot 说明：<https://developer.android.com/privacy-and-security/direct-boot>

不要把“重启后尚未首次解锁”误诊为 Boot 配置失败。若业务要求无人值守重启后立即 SSH，需要 Direct-Boot-aware 的独立应用、设备管理方案或真实 Root；原生 Termux 配置无法绕过凭据加密。

## 标准后台设置

对三个包执行并验证：

- 电池策略设为“不限制/无限制”。
- 允许自启动、后台活动、前台服务和通知。
- 加入 Android DeviceIdle 用户白名单。
- Termux 中运行 `termux-wake-lock`，并保持 Termux 前台服务通知存在。

不要为了一个应用全局关闭 Doze、缓存应用冻结或 PowerKeeper。优先做包级豁免，保留设备其余省电策略。

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

使用：

```bash
bash scripts/run.sh host-permissions --serial SERIAL \
  --hyperos-greeze --apply
```

该设置可能被 PowerKeeper 在用户修改其他应用电池策略时重新生成。遇到复发先重新读取设置，不要直接反复重启服务。关于该私有列表与 Greeze 的代码和实机研究：<https://github.com/dingwen07/hyperos-fcm-fix/blob/main/docs/xiaomi-hyperos-gms-fcm-greezer-investigation.md>

厂商私有实现可能改变。只有日志证据吻合时才使用这条分支，不要把 `MILLET_NO_RESTRICT_APP` 当作所有 Android 的通用设置。

## Wi-Fi 锁限制

新 Android 已弃用传统高性能 Wi-Fi 锁，并可能转换为低延迟锁；低延迟锁的有效条件包括屏幕开启和应用在前台。不要只凭 Wi-Fi lock 状态判断息屏 SSH 是否可靠。以真实局域网连接和 CPU wake lock 为准。Android API 说明：<https://developer.android.com/reference/android/net/wifi/WifiManager>
