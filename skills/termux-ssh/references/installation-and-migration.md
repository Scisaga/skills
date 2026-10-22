# 安装来源与迁移

## 不变量

Termux 主应用和插件使用共享 UID，必须来自同一签名来源。不要混装：

- F-Droid Termux + GitHub Termux:API
- Google Play Termux + F-Droid Termux:Boot
- 任何来历不明的重签名 APK

官方说明：<https://github.com/termux/termux-app#installation>

需要 Termux:API 与 Termux:Boot 时，默认选择以下同源 F-Droid 包：

- `com.termux`
- `com.termux.api`
- `com.termux.boot`

F-Droid 客户端不是必须条件，也可以从 F-Droid 网站下载同源 APK；关键是整套来源和签名一致。

## 盘点

主机侧优先运行：

```bash
bash scripts/run.sh host-doctor --serial SERIAL
```

手工检查：

```bash
adb -s SERIAL shell getprop ro.product.manufacturer
adb -s SERIAL shell getprop ro.build.version.release
adb -s SERIAL shell getprop ro.product.cpu.abi
adb -s SERIAL shell pm list packages | grep -E '^package:com\.termux($|\.)'
adb -s SERIAL shell dumpsys package com.termux | grep -E 'versionName=|userId='
```

Android 能让共享 UID 包共存，本身已经说明其签名兼容；需要审计 APK 证书时，再用 Android Build Tools 的 `apksigner verify --print-certs` 检查每个 APK，不要只比较文件名或版本号。

## 备份决策

- 已有脚本、密钥、软件包或用户数据：先备份并验证归档能读取。
- 用户明确说明是全新空环境：可以跳过备份，但仍需在卸载前复述将删除哪些包和数据。
- 不要把 `authorized_keys` 当作私钥备份；主机私钥始终留在主机。

在旧 Termux 内可创建数据归档：

```bash
termux-backup ~/storage/downloads/termux-backup.tar.gz
```

若当前版本没有 `termux-backup`，按官方备份说明选择 `tar` 方案，并在换源前把归档复制到 Termux 私有目录之外：<https://github.com/termux/termux-app/wiki/Backing-up-Termux>

至少验证：

```bash
tar -tzf ~/storage/downloads/termux-backup.tar.gz >/dev/null
```

## 换源与安装

只有在用户明确授权后才能卸载。换源时必须卸载主应用和所有插件，否则常见结果是 `INSTALL_FAILED_SHARED_USER_INCOMPATIBLE` 或签名不匹配。

建议顺序：

1. 验证备份或确认空环境。
2. 记录当前 `com.termux*` 包清单。
3. 卸载旧的 Termux 主应用及所有插件。
4. 从同一个来源安装 Termux、Termux:API、Termux:Boot。
5. 打开 Termux，等待 bootstrap 初始化完成。
6. 打开 Termux:Boot 一次，使其具备接收开机事件的条件。
7. 恢复数据或运行本 skill 的 bootstrap。

不要把某一版本号写死在自动化中。安装完成后记录实际版本、来源和 ABI。

仅在安装期间为 F-Droid 或当前安装器授予“安装未知应用”，完成后恢复原状态。小米“增强防护”等提示可能扩大系统级安全变更；除非用户明确要求，不要为了安装 Termux 永久关闭整机防护，优先取消该额外变更并只授予必要的包级权限。

## 恢复边界

恢复旧数据后重新检查：

- `$PREFIX` 与 `$HOME` 文件属主仍是当前 Termux Android UID。
- `~/.ssh` 为 700，`authorized_keys` 为 600。
- 没有把其他设备生成的 SSH host 私钥错误覆盖到新设备，除非用户明确需要保持同一主机身份。
- `sshd -t` 成功，软件包数据库没有半配置状态。

不同设备由 Android 分配的 `u0_aNNN` UID 可能不同。不要把 UID、设备序列号、IP 或 `/data/user/0` 中的临时路径写入可复用配置。
