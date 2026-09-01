# 远程管理功能

## SSH 连接模型

Termux OpenSSH 默认监听 8022。Android 下的 Termux OpenSSH 是单用户模型，会忽略客户端提供的用户名并映射到当前 Termux UID，因此可以写：

```bash
ssh -p 8022 root@PHONE_IP
```

但远端 `whoami` 仍会是 `u0_aNNN`，不是 UID 0。官方补丁可见：<https://github.com/termux/termux-packages/blob/master/packages/openssh/auth.c.patch>

非 Root Android 应用不能监听 1–1024 的特权端口。默认保留 8022；不要用端口转发伪装成“设备已监听 22”。

公钥要求：

```bash
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys
ssh-keygen -lf ~/.ssh/authorized_keys
```

主机私钥不进入 Android。部署完公钥后关闭密码和键盘交互认证，并用第二个 SSH 会话验证成功，再结束当前维护会话。

## 服务管理

设备内：

```bash
export SVDIR="$PREFIX/var/service"
sv status sshd
sv up sshd
sv restart sshd
sv-enable sshd
```

Boot 脚本通过 `termux-wake-lock`、`start-services.sh` 和 runit 拉起 SSH。不要同时维护另一个循环执行 `sshd` 的守护脚本，以免重复监听或掩盖 runit 状态。

## 共享存储

Android 公共下载目录：

```text
/storage/emulated/0/Download
```

Termux 标准快捷路径：

```text
~/storage/downloads
```

先运行 `termux-setup-storage` 并完成 Android 授权。如果特殊权限已生效但广播没有创建快捷链接，只有在确认目标目录可读写后，才补建安全的符号链接；不要删除已有 `~/storage` 内容。

`wget` 和 `curl` 默认写当前目录。需要直接进入公共下载目录时：

```bash
cd ~/storage/downloads
```

## Termux:API

必须同时满足：

1. Android 安装了同签名的 Termux:API 应用。
2. Termux 内安装了 `termux-api` 命令包。
3. Android 权限和系统开关已启用。

列出 Wi-Fi 热点：

```bash
termux-wifi-scaninfo
```

Wi-Fi 扫描通常需要位置权限，并要求系统“位置信息”开关开启。不要记录或上传扫描结果，除非用户明确要求。

### 蓝牙

当前官方 Termux:API 应用和 CLI 没有稳定发布的蓝牙扫描、配对或连接命令；官方仓库中的蓝牙扫描实现仍是未合并变更：<https://github.com/termux/termux-api/pull/686>

基础部署提供打开系统设置的 helper：

```bash
remote-bluetooth-settings
```

它尝试打开 Android 蓝牙设置页。若用户明确要求从 SSH 读取蓝牙状态、已配对设备或执行限时 BLE 扫描，可部署本 skill 自带的独立、可审计 companion，详见 [bluetooth-companion.md](bluetooth-companion.md)。部署后使用：

```bash
termux-bluetooth status
termux-bluetooth bonded
termux-bluetooth scan 8
```

不要默认安装第三方修改版 Termux:API：它可能使用不同签名、与 F-Droid 主应用冲突，并扩大蓝牙权限。companion 不是 F-Droid/Termux 官方组件，不提供通用配对或连接动作，也不能静默开关蓝牙。

远程拍照：

```bash
remote-camera-photo ~/storage/downloads/photo.jpg 0
```

新 Android 可能禁止后台进程直接使用相机。本 skill 的 helper 会先尝试把 Termux Activity 带到前台，再调用 `termux-camera-photo`。锁屏、厂商后台启动限制或相机正在被占用时仍可能失败。

每次相机测试后：

1. 记录实际输出路径。
2. 在用户要求或测试任务完成时删除测试照片。
3. 用 `find` 或精确路径再次确认不存在残留。

不要使用宽泛通配符删除相册。

## Ubuntu 风格 Bash

`bootstrap.sh` 安装 Bash completion、command-not-found、常用 GNU 工具以及 `nano`、`vim`、`htop`、`tree`，并加载独立的用户配置片段。它不会安装 Ubuntu rootfs。

默认提示符：

```text
root@android:~#
```

其中 `root` 是显示标签。配置还提供：

- `ll`、`la`、`l`、`..`、`...`
- 彩色 `ls`、`grep`、`diff`
- Tab 补全
- 上下键按已输入前缀搜索历史
- 每条命令及时追加历史
- `SVDIR=$PREFIX/var/service`

已有 `.bashrc`、`.bash_profile` 和 `.inputrc` 不会被整体覆盖；脚本只追加加载本 skill 管理片段的语句。

## 登录根目录 AGENTS.md

bootstrap 会安装 `update-termux-agents`，并在 `~/AGENTS.md` 中维护设备上下文区块。它记录实际应用包、Termux/native package 版本、SSH 与 Root 边界、Boot/息屏配置、共享存储、API 命令能力和蓝牙限制。

若目标设备已有 `~/AGENTS.md`，受管区块之外的内容保持不变；更新前会备份旧文件。应用、端口、权限或能力改变后运行：

```bash
update-termux-agents --greeze-status enabled
```

只有通过主机侧日志和设置确认 HyperOS 豁免已生效时才写 `enabled`，否则保留 `unknown`。
