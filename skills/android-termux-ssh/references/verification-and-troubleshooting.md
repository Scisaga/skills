# 验证与排障

## 分级验收

### 设备内

```bash
bash verify-termux.sh
```

必须确认：

- `sshd -t` 成功。
- `authorized_keys` 非空且权限正确。
- runit 中 sshd 为 `run`。
- Boot 脚本存在且可执行。
- `~/AGENTS.md` 存在并包含最新的设备应用、能力与边界说明。
- `termux:service-wakelock` 已请求。
- 需要共享存储时，`~/storage/downloads` 可读写。
- 需要 API 时，命令存在；相机和 Wi-Fi 分别做最小真实测试。

### 主机侧

```bash
bash scripts/run.sh host-doctor --serial SERIAL
```

然后直接连接设备 IP：

```bash
ssh -o BatchMode=yes -o ConnectTimeout=8 -p 8022 root@PHONE_IP true
```

### 息屏矩阵

依次测试并记录：

1. Termux 前台、屏幕亮。
2. Home 前台、屏幕亮。
3. 图案锁屏但显示仍亮。
4. 物理息屏，至少持续 6 分钟，每 30–60 秒建立一个新的直接 LAN SSH 会话。
5. 重启、用户首次解锁后，等待 Boot 拉起服务，再重复物理息屏测试。

最终移除全部 `adb forward`、停止 ADB server 或断开 USB，然后再连接一次 `PHONE_IP:8022`。这是“不依赖 ADB”的验收证据。

## 症状定位

### Connection refused

检查：

```bash
sv status "$PREFIX/var/service/sshd"
sshd -t
ss -ltn | grep ':8022 '
```

常见原因：服务未启用、配置语法错误、端口被占用、Boot 尚未运行。

### Connection timed out

先区分路由/防火墙和进程冻结。检查手机 IP 是否变化、Wi-Fi 客户端隔离、是否连到访客网络，以及端口是否仍监听。

### Connection timed out during banner exchange

TCP 已建立但 sshd 没有被调度。若物理息屏才发生，检查 wake lock、进程冻结和厂商电池策略。使用 USB forward 只能作为诊断：如果 USB forward 也卡在 banner，问题更可能是 CPU/进程冻结，而不是 Wi-Fi 入站过滤。

### 锁屏可达、物理息屏不可达

不要把黑色截图当作真正息屏。确认：

```bash
adb -s SERIAL shell dumpsys power | grep 'mWakefulness='
```

`Asleep` 才是物理休眠测试。HyperOS 设备继续按 `android-permissions-and-power.md` 检查 Greeze。

### Boot 权限被拒绝或重启后未启动

检查：

- Termux:Boot 是否打开过一次。
- Termux、Boot 是否同签名来源。
- `RECEIVE_BOOT_COMPLETED` 是否授予且 receiver 已注册。
- Boot 脚本路径是否为 `~/.termux/boot/`。
- 用户是否在本次重启后完成过首次解锁。
- 厂商是否禁止自启动或后台活动。

### 存储 Permission denied

运行 `termux-setup-storage` 并授权。若没有弹窗：

1. 检查 `MANAGE_EXTERNAL_STORAGE` AppOp 或系统“所有文件访问”页面。
2. 直接测试 `/storage/emulated/0/Download` 的读写。
3. 权限已生效但 `~/storage` 缺失时，只补建不存在的标准符号链接。

不要把 SSH 的 `root` 标签误认为能绕过 Android 存储权限。

## 清理与交付

- 删除安装时生成的临时 APK、临时公钥副本和测试照片；保留用户明确要求的备份。
- 恢复为了安装临时修改的屏幕超时、保持唤醒和未知来源设置。
- 不关闭用户原有图案/PIN。
- 报告仍存在的限制：重启后首次解锁、动态 IP、相机前台限制、厂商设置可能被系统更新重置。
- 给出连接命令，但不在文档或日志中包含私钥内容。
- 运行 `update-termux-agents`，确认受管区块刷新且已有非受管 AGENTS 内容未丢失。
