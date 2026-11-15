# Android 图形管理、入口、图标与分组

## 图形管理器

`assets/desktop/android/` 保存可构建源码、manifest、两个同系列图标及 PNG 资源。包名 `com.scisaga.tabletdesktop`，独立 UID，无 Internet 权限；管理器使用正式 Termux RUN_COMMAND 接口及权限，不共享 Termux 签名密钥。

管理界面采用独立标题/状态、留白与直接按钮，包含启动/返回、正常结束、检查记录、强制结束确认和关闭管理。电量来自 native 缓存。终端数字菜单保留为 `desktop manage --terminal` 诊断入口，不作为日常主界面。

接口只传固定 desktop 命令。结果通过显式一次性 PendingIntent 与非导出 receiver 返回；force-stop 携带当前会话 UUID。`allow-external-apps=true` 配合 RUN_COMMAND 权限使用，不等于授权所有 Android 应用执行 Termux 命令。

“开机恢复后台服务”默认关闭；需要开机保活时，在管理器中启用，并按设备实际 ROM 允许“桌面管理”自启动。它在首次解锁后的 BOOT_COMPLETED 通过同一 RUN_COMMAND 授权执行固定的 `tablet-boot-services`：取得 Termux 唤醒锁、恢复现有 runit 服务和桌面控制器，不启动图形桌面，不自动安装或启用 SSH。它可作为共享 UID 插件自启动权限无法持久保存时的独立入口；保留官方 Termux:Boot，两条路径均复用 runit，避免重复守护进程。关闭开关会禁用该 receiver。完成结果只保留退出码及状态，不保存命令输出。

不要用手工打开管理器或 Termux 代替开机验收：实际重启、用户首次解锁后，在未打开相关应用前验证后台连接和 `~/.local/state/tablet-desktop/boot-services.json` 的本次 boot ID，再从 Linux 桌面入口启动图形会话。仅本地桌面部署不需要启用此选项。

冷启动须重试 `sv up`，直到监督进程实际响应；不能仅凭 `supervise/ok` FIFO 存在判断就绪，该文件会跨重启残留。恢复脚本采用有界等待，诊断输出只写入私有 `~/.local/state/tablet-desktop/boot-services.log`。

## 两个正式启动入口

- `ManagerActivity`：桌面管理，打开控制界面。
- `DesktopEntry` activity-alias：Linux 桌面，点击直接启动或返回 Xfce。

两个入口都声明 MAIN/LAUNCHER，因此可以出现在 Android“全部应用”中，并可拖到主屏幕或同一个文件夹。复用相同桌面会话。仅创建 Termux:Widget 固定快捷方式不能保证它出现在全部应用中。

新部署优先使用这两个正式入口；已有 Widget 快捷方式可保留兼容。不要为了一致图标卸载 Termux:Widget、API 或 Boot。启动器可能给 Widget 图标加来源角标，正式 activity-alias 不依赖该角标。

## 构建与部署

```bash
python skills/termux/scripts/host_tools.py --jdk --adb --apply
python skills/termux/scripts/build_desktop_manager.py --java-home /path/to/jdk \
  --output /path/outside/repo/desktop-manager.apk --key-dir /private/host/termux-signing

python skills/termux/scripts/deploy_desktop_manager.py \
  --apk /path/outside/repo/desktop-manager.apk --adb /path/to/adb --serial SERIAL \
  --ssh-target termux@PHONE_IP --ssh-port 8022 --identity /private/host/key --apply
```

构建器支持 Windows、x86_64 Linux 和 macOS，下载并校验固定版本构建依赖，使用 JDK 编译、D8、AAPT2 与 APK 签名验证。旧版 android.jar 在此仅用于该应用所需的编译符号/资源；它不决定运行时 Android 版本。所有缓存、APK 和签名材料放主机外部目录。

更新已部署包时沿用原签名目录（包含 desktop-manager.p12 与 signing-password）。签名不匹配时停止并检查，不自动卸载。部署脚本仅更新独立管理器包，授予其 RUN_COMMAND，并通过已信任的 SSH 修改 allow-external-apps 后重载设置；不会重新安装共享 UID 插件。

Windows 可直接执行 Python 脚本，不要求 WSL。缺少依赖时使用输出的 host-tools 安装命令。已有蓝牙 companion 的构建脚本及其 WSL/Windows JDK 路径保持兼容。

首次点击时 Android/厂商可能提示关联启动 Termux:X11，按当前用户授权处理；不要全局绕过后台安全策略。只在需要由后台 Termux 拉起界面且用户授权时，调整 Termux 对应的后台/悬浮窗权限。

## 图标

技能图标 `assets/logo.svg` 使用蓝色平板与终端符号。Android“Linux 桌面”和“桌面管理”分别使用同系列显示器+播放、显示器+齿轮图标。保留 SVG 源码和构建所用 PNG；修改时检查浅色/深色背景、实际启动器图标尺寸与文字完整性。

## Android 桌面文件夹管理

用户要求集中管理时，建议文件夹名称 `Termux`，按实际可用入口纳入：Termux、Termux:X11、Linux 桌面、桌面管理，以及有可见启动图标的 Boot/API/Widget。插件无 launcher activity 时无需伪造图标。

```bash
python skills/termux/scripts/launcher_plan.py --adb /path/to/adb --serial SERIAL --folder Termux
```

这是只读盘点与整理计划；Android 没有适用于所有启动器的公共“创建文件夹并摆放图标”接口。实际整理通过设备当前启动器 UI 完成：

1. 查看新截图/界面树，识别当前主页、已有 Termux 文件夹、原图标和重复快捷方式。不能沿用另一页或另一设备的坐标。
2. 用启动器支持的拖放创建/复用文件夹并命名，再逐个放入相关入口。保留用户原有其他图标顺序。
3. 部分厂商启动器的长按需要真实触屏手势；单点 swipe 或鼠标事件可能只点击。检查长按菜单与拖动反馈后继续，不能以命令成功代替 UI 成功。
4. 全部应用中的 Linux 桌面与桌面管理必须仍可找到。旧 Widget 重复入口只在新入口验证成功后移除自有快捷方式，不卸载应用或删除用户文件。
5. 重新打开文件夹，检查名称、完整图标、启动/返回与管理两条路径。报告实际分组结果；UI 暂不可操作时保留具体计划，不声称已完成摆放。

不修改启动器私有数据库、不复制其 token、不依靠已过时的 INSTALL_SHORTCUT 广播强行写入。桌面文件夹、全部应用列表与 Xfce 桌面是三个不同位置，验收分别检查。
