# 桌面凭据存储

## 先确认提示来源

VS Code 在 GitHub 浏览器登录成功后提示 OS keyring unavailable，说明 Linux 加密凭据存储不可用，不代表浏览器登录失败，也不代表实际桌面是 GNOME。检查当前 Xfce 会话的 D-Bus、`org.freedesktop.secrets` owner、`gnome-keyring-daemon` 和 libsecret。VS Code SecretStorage 与 Git 的 `credential.helper` 分别配置；安装 libsecret 动态库不会自动提供 Secret Service 或 Git helper。

PRoot 没有 PAM 登录密码时，普通 GNOME Keyring 无法自动从 Android 锁屏取得解锁密码。先明确用户是否接受额外密码。用户拒绝时，不配置空密码密钥环、`password-store=basic`、Git `store`，也不把主密码明文写入启动脚本或文件。

## Android 硬件保护方案

本方案显式选用，不随普通桌面安装自动初始化。适用于 Android 15/API 35 以上，且实际探针确认 Android Keystore 密钥不可导出、security level 为 TEE（1）或 StrongBox（2）。更早版本的 unlocked-device 密钥存在已知平台问题，不自动降级。

`TabletKeyring.java` 经 D8 生成只读 DEX JAR，由现有 Termux UID 下的 `app_process` 一次性运行，无需安装 APK、更新 Termux 或增加常驻服务。随机 GNOME 主密码仅在内存和匿名管道中使用；磁盘只保存 AES-256-GCM 密文。AES 密钥由 Android Keystore 保管，要求设备已解锁。程序不提供输出主密码、导出密钥或删除密钥的动作。

这保护桌面目录被复制时的凭据，不隔离同一 Termux UID 中的程序。密钥环已解锁时，同用户程序仍可能访问凭据；息屏不会自动锁定已打开的 GNOME 密钥环。卸载/清除 Termux 数据、移除系统锁屏或 Keystore 密钥丢失后，复制桌面备份不能保证恢复凭据，需要重新登录。不要删除 `master.sealed`、Android 密钥或 `~/.local/share/keyrings` 来尝试修复普通提示。

## 构建与部署

先在当前 guest 安装依赖。当前终端没有 guest root 时，确认能力缺口后，通过现有原生维护入口执行固定的 `proot-distro login ... --user root` 包安装，不另开 SSH，不改变网络：

```sh
apt-get install --no-install-recommends gnome-keyring libsecret-tools seahorse libsecret-1-dev build-essential
```

在有 JDK 的构建主机、skill 根目录执行：

```sh
python scripts/build_android_keyring.py
```

脚本复用已固定摘要的 Android/D8 工具；缺 JDK 时提示 `host_tools.py --jdk --apply`。保留输出 JAR 的 SHA256。把当前 skill 源码、JAR 和下面的官方 Git helper 源码放进 guest 私有缓存，禁止通过共享目录传输真实令牌或主密码：

```sh
mkdir -p "$HOME/.cache/tablet-keyring"
curl --fail --location https://raw.githubusercontent.com/git/git/v2.47.3/contrib/credential/libsecret/git-credential-libsecret.c -o "$HOME/.cache/tablet-keyring/git-credential-libsecret.c"
```

在当前 Xfce 终端、skill 根目录执行；`JAR_SHA256` 使用构建结果，JAR 预先复制到下面的私有路径：

```sh
python3 scripts/keyring_setup.py --bridge-jar "$HOME/.cache/tablet-keyring/tablet-keyring.jar" --bridge-sha256 "$JAR_SHA256" --credential-source "$HOME/.cache/tablet-keyring/git-credential-libsecret.c"
```

默认预览；旧 Code 包装器缺少下述启动检查时，先安装检查，再加 `--apply` 配置。缺检查时实际安装以非零退出码停止。安装器核对 Android 版本、硬件探针、JAR 摘要和固定 Git 源码摘要，编译 helper，初始化或解锁密钥环，并备份后合并以下配置：

- `~/.vscode/argv.json`：保留 JSONC 注释和其他字段，设置 `password-store=gnome-libsecret`。
- Git global helper：指向用户私有的 `git-credential-libsecret`；已有其他 helper 时停止，不覆盖。
- Xfce autostart：调用一次性解锁程序。
- 用户 D-Bus Secret Service 激活入口：同样调用解锁程序，避免 Git/Code 的早期请求先启动一个锁定的 daemon。

已存在未受本桥接管理的密钥环时停止，不重置或猜测密码。原配置只在设备私有备份目录保存；输出不包含真实凭据。

新版 `desktop_setup.py` 为普通及软件 Code 包装器加入条件检查，仅在存在受保护状态时调用桥接。旧安装通过 guest root 预览/安装相同检查，保留原 GPU 参数：

```sh
python3 scripts/keyring_setup.py --launch-guard --state /home/developer/.local/state/tablet-desktop/keyring-launch-guard.json
```

按实际用户调整状态路径，加 `--apply` 生效。不为该检查重跑整个桌面部署或替换用户主题。已有 Code 需要正常关闭重开，保留保存提示；不要强杀。首次登录此前未能持久化时，可能需要再点一次 GitHub 登录。

## 启动和验收

解锁入口使用文件锁串行化，`status` 先查 owner，不意外激活未运行的服务。D-Bus 激活采用 starter bus 地址和明确 HOME；同一总线使用同一个私有控制目录，避免激活环境与终端环境不同导致双 daemon。JAR 必须只读（0400），否则 Android 会拒绝动态加载。GNOME 只启动 `secrets` 组件，不接管 SSH agent。

用唯一 `.invalid` 主机和随机临时密码验证 Git approve/fill/reject，比较仅在内存中进行。正常停止本次创建且身份已复核的凭据 daemon，分别验证 Xfce 命令和 D-Bus 冷激活可自动解锁，再读取测试条目，最后删除。并发启动不应产生多个 daemon 或密码框。不要用读取真实 GitHub 令牌作为验收。

正常重开日常 Code 后，核对其主进程实际选择 `gnome-libsecret`、加密可用，以及原工作区恢复。Android 整机重启、真实锁屏及长时息屏分别记录；服务重开不能冒充这些测试。

## 回退

`keyring_setup.py --restore <configuration.json>` 默认检查，`--apply` 恢复；后续配置发生变化会拒绝覆盖。Code 启动检查使用单独 `--state`，以 guest root 同样回退。回退保留桥接程序、Android 密钥、密文和已保存的凭据，不删除账户或重置密钥环。需要重新启用时先验证保留状态，再恢复启动入口。

依据：[VS Code 凭据存储排障](https://code.visualstudio.com/docs/configure/settings-sync#_troubleshoot-credentialstore-issues)、[Android Keystore](https://developer.android.com/privacy-and-security/keystore)、[unlocked-device 密钥限制](https://developer.android.com/reference/android/security/keystore/KeyGenParameterSpec.Builder#setUnlockedDeviceRequired(boolean))、[GNOME Keyring 安全边界](https://wiki.gnome.org/Projects/GnomeKeyring/SecurityFAQ)、[Git credential helpers](https://git-scm.com/doc/credential-helpers.html)。
