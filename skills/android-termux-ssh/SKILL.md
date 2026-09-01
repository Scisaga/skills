---
name: android-termux-ssh
description: 在 Android 设备上安装、迁移、配置和验证可独立运行的 Termux SSH、Termux:Boot、Termux:API、共享存储、蓝牙 companion 与 Bash 环境。适用于通过 ADB 完成一次性部署后，要求设备通过局域网 SSH 自启动、息屏可达并支持相机、Wi-Fi 或蓝牙只读管理的场景。
---

# Android Termux SSH

## 概述

把 Android 设备交付成不依赖 ADB 日常运行的 Termux 管理节点。ADB 可以用于首次安装、授权和诊断，但最终验收必须直接访问设备自身的 IP 与 SSH 端口。

这个 skill 默认采用原生 Termux，不安装 `proot` Ubuntu。SSH 中提供的 `root` 用户名只是显示/连接别名；Termux OpenSSH 会把客户端用户名映射到当前 Android 应用 UID，它不会让未 Root 的设备获得 UID 0。

## 工作流

1. 先盘点设备和现有 Termux：Android 版本、厂商 ROM、CPU ABI、已安装的 `com.termux*` 包、安装来源、数据是否需要保留、主机公钥和目标 SSH 端口。
2. 需要换安装来源或卸载旧版时，先读 [references/installation-and-migration.md](references/installation-and-migration.md)。有数据的设备先备份并验证；新装空环境可在用户明确确认后跳过备份。
3. Termux、Termux:API、Termux:Boot 必须来自同一签名来源。需要插件时优先选择整套 F-Droid 包，不混装 F-Droid、GitHub 和 Google Play 版本。
4. 安装后分别打开 Termux 与 Termux:Boot 一次。Android 权限和厂商后台策略按 [references/android-permissions-and-power.md](references/android-permissions-and-power.md) 配置。
5. 把本 skill 的 `scripts/bootstrap.sh` 与 `scripts/update-agents-md.sh` 放到 Termux 的同一目录，使用公钥文件或标准输入执行。bootstrap 会在登录根目录生成/更新 `~/AGENTS.md`，保留其中非受管内容。不要把私钥复制到设备，也不要把真实公钥、IP 或序列号写回 skill。
6. 需要相机、Wi-Fi、共享存储或 Ubuntu 风格 Bash 时，读 [references/remote-management.md](references/remote-management.md)。需要蓝牙状态、已配对列表或 BLE 扫描时，额外读 [references/bluetooth-companion.md](references/bluetooth-companion.md)。相机测试结束后删除测试照片并验证不存在残留。
7. 运行设备内和主机侧检查，按 [references/verification-and-troubleshooting.md](references/verification-and-troubleshooting.md) 完成亮屏、锁屏、物理息屏、重启后首次解锁和纯局域网验收。
8. 最终清空 ADB forward，并停止或断开主机 ADB 后再次 SSH。不要把 ADB forward、USB 常连或自动点亮屏幕当作交付方案。

## 命令模式

```bash
# 查看入口
bash skills/android-termux-ssh/scripts/run.sh help

# 主机侧只读检查
bash skills/android-termux-ssh/scripts/run.sh host-doctor --serial SERIAL

# 预览 Android 权限变更；加 --apply 才真正执行
bash skills/android-termux-ssh/scripts/run.sh host-permissions \
  --serial SERIAL --storage --api --background

# 在 Termux 内执行：从文件导入主机公钥
bash bootstrap.sh --authorized-key-file ~/host_key.pub

# 或避免公钥落盘
cat /path/to/host_key.pub | bash bootstrap.sh --authorized-key-stdin

# Termux 内只读验收
bash verify-termux.sh

# 应用、端口或能力改变后刷新设备上下文
update-termux-agents --greeze-status enabled

# 主机侧构建及一次性部署独立蓝牙 companion
bash skills/android-termux-ssh/scripts/run.sh build-bluetooth \
  --adb /path/to/adb.exe --output /tmp/termux-bluetooth-bridge.apk
bash skills/android-termux-ssh/scripts/run.sh deploy-bluetooth \
  --apk /tmp/termux-bluetooth-bridge.apk --serial SERIAL \
  --ssh-host root@PHONE_IP
```

`bootstrap.sh` 默认使用端口 `8022`、连接标签 `root`、提示符主机名 `android`。非 Root Android 进程不能监听 22 等特权端口；除非已验证真实 Root 和相应能力，否则不要改成 22。

## 资源使用

- 安装来源、签名一致性、备份、卸载和恢复：读 `references/installation-and-migration.md`。
- Android 权限、Boot、Doze、HyperOS/MIUI Greeze、重启首次解锁：读 `references/android-permissions-and-power.md`。
- SSH、公钥、相机、Wi-Fi、存储和 Bash 使用方式：读 `references/remote-management.md`。
- 独立蓝牙 companion 的权限、构建、部署、安全边界和排障：读 `references/bluetooth-companion.md`。
- 出现拒绝连接、banner 超时、息屏冻结或 Boot 不启动：读 `references/verification-and-troubleshooting.md`。
- `scripts/host-android-permissions.sh` 会修改设备权限或设置，只有用户已授权相应变更时才加 `--apply`。

## 输出规则

- 先报告当前状态、假设和将要修改的范围，再执行安装或权限变更。
- 区分“Android 系统 Root”和“SSH 用户名显示为 root”，不要声称后者提供系统 Root。
- 区分“重启后未首次解锁”和“普通锁屏/息屏”；凭据加密存储在首次解锁前不可用。
- 所有破坏性卸载、清除数据、移除锁屏或全局禁用省电策略都需要单独的明确授权。
- 验收报告至少包含 IP/端口、密钥指纹、服务状态、息屏持续时间、是否绕过 ADB、存储/API 测试结果和剩余限制。
- 交付前确认 `~/AGENTS.md` 已反映实际应用、能力和限制；后续重大变更后重新生成其受管区块。
