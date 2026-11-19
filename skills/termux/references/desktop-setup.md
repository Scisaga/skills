# 可选 Linux 桌面与应用

## 选择范围与能力边界

原生 Termux、SSH/Boot/API 与 X11/PRoot 桌面是可分别选择的模块。只需要 SSH 时沿用 `bootstrap`，不安装 rootfs；只需要本机桌面可直接走本页。用户可选择最小 Xfce 或 VS Code、Chromium、LibreOffice、VLC 组合。

本实现以 Debian 13、原生架构和 Xfce 为可重复安装路径。PRoot 与 Android 共用内核，guest 的 root 是用户态映射；它不授予 Android Root。CPU 架构相同也存在 PRoot 系统调用转换、软件图形渲染与内存开销，不能承诺利用全部硬件性能。GPU/视频解码须另测。Docker 不属于本次已实现能力；有需求时分别评估设备内核/容器支持或远程 Docker 引擎，不把安装 Docker CLI 或拉取 OCI rootfs 当成 Docker daemon 已运行。

## 安装前

1. 读取设备上下文，确认是否已有桌面、未保存编辑或后台任务。已有 rootfs 与用户目录优先维护，不执行 reset/remove 或整套覆盖。
   恢复定制桌面时，从本机的 [配置基线](desktop-verification.md#桌面配置基线) 选用 `profile.json`。核对 `desktop-plan` 展开的默认值，以及主题素材、应用入口和用户设置的恢复来源。
2. 完成 Termux 与必要插件安装。Termux、Boot、API、Widget 同源签名；安装共享 UID 插件可能中断 Termux 与桌面，安排在保存并结束桌面之后。复查 Downloads 存储权限。
3. 安装官方 Termux:X11 APK，并打开一次；native `termux-x11-nightly` 是另一个必要组件。两者来源见 [Termux:X11 官方说明](https://github.com/termux/termux-x11)。本安装器安装 native 包，不代替 Android APK 安装。
4. 将整个 skill 的 `scripts/` 和 `assets/` 保持相对位置复制到 native Termux。脚本使用 Python 3.10+ 标准库：`pkg install python`。不把设备上的 SSH 私钥、Cookie、订阅或主机 APK 签名密钥带入技能。

```bash
bash skills/termux/scripts/run.sh desktop-plan
bash skills/termux/scripts/run.sh desktop-plan --apps code,chromium
```

plan 不改设备，输出模块和配置摘要。新建自己的 profile.json 可从 `assets/desktop/tablet.json` 复制。未列出的应用不会被安装，已有其他应用也不会被自动卸载。

## 配置

| 配置 | 含义 |
|---|---|
| container / image / user | 独立容器名、Debian 13 OCI 引用、guest 普通用户；image 可加 sha256 digest |
| display | X11 display，例如 `:1`；不指定设备物理分辨率 |
| scale / dpi | GTK 整数窗口缩放与逻辑字体 DPI，分别设置；预设为 2 与 96 |
| font / monospace_font / font_size | 实际已安装的字体及基础字号；预设不捆绑 Consolas |
| theme / icons / titlebar_theme | 深色主题、图标与触屏标题栏，可按设备修改 |
| window_compositing / window_vblank_mode / window_shadows | 默认 false / auto / true，保留兼容路径；vblank 可选 auto、off、xpresent、glx。按设备比较可见输出、窗口重绘及浏览器性能；开启整桌面合成时不启动手动重定向底栏的辅助程序 |
| software_rendering | 已验证的 GTK/Electron 兼容路径；适合需要禁用 GPU 的设备，不代表所有设备只能软件渲染 |
| gpu_backend | software、virgl-android 或 freedreno-kgsl；分别为兼容软件、native VirGL 服务、隔离的 glibc 直接 KGSL 驱动。后两者须在设备验证；见 [GPU 验收](desktop-gpu.md) |
| browser_backend / native_browser_icd | 默认 guest；验证后可选择 termux-zink，让桌面 Chromium 在 native Termux 中运行。ICD 是已安装的 Vulkan JSON 文件名；当前验证路径为 Adreno/Turnip，详见 GPU 参考 |
| office_backend | guest 或 native-gtk3；后者使用官方 native LibreOffice，复制原用户配置至独立 profile，经控制器在 PRoot 外运行 |
| media_backend | guest 或 termux-va；后者要求 freedreno-kgsl，安装固定校验和的视频桥接和隔离 VLC，按需启动硬件解码服务 |
| cursor_theme / cursor_size | 非空指针主题与尺寸；GTK、GPU 包装器和 native 应用保持一致，默认 Adwaita / 48 |
| touch_mode | 默认 preserve，也可选择 direct（原生触屏）、touch（兼容模拟触屏）、trackpad |
| x11_mitshm | 默认 true，保留既有 X11 行为；仅在实际 MIT-SHM 共享内存错误时设 false，正常结束并重新进入后生效，DRI3/Present 另验 |
| touch_long_press / touch_long_press_ms / touch_long_press_move_px | 默认关闭；按需为 Xfdesktop/Thunar 补长按右键，同时适配 Xfce 壳层点击。默认 700ms/24 个物理像素，可按设备调整；不改浏览器/Code 原生触摸，见显示与输入参考 |
| media_hardware_policy | all 保留既有设备行为；h264-baseline 只让通过本地元数据检查的 Baseline/无 B 帧/8 位/最高 1080p30 文件走硬解，其余使用 GPU 显示的兼容解码 |
| hardware_keyboard | 实体键盘预设：隐藏 X11 附加键栏；Android 输入法显示仍需系统设置 |
| dock_autohide / dock_output | 底栏是否自动隐藏、绑定的 X11 输出名；先用 xrandr 确认 |
| dock_hide_indicator | 隐藏底栏触发横线并通过 X11 事件修正位置；保留边缘输入区，见显示与输入参考 |
| applications / code_autostart | 应用组合与 Xfce 登录时是否打开 VS Code，默认 `false` |
| code_version | stable 或明确的 x.y.z；已有 Code 不因重复安装而重新下载/更换版本 |
| android_folder | Android 桌面分组建议名称，默认 Termux；不直接修改启动器数据库 |

新脚本只读取 CLI/JSON，以及正常进程环境；不自动读取 `.env`。旧 SSH/Codex 网络环境文件与兼容路径保持原规则。

`software_rendering` 兼容开关不代替 GPU 后端选择。GPU 请求按 [GPU 渲染](desktop-gpu.md) 安装真实通路，并用日常应用验证；保持 GTK 兼容环境仍可启用浏览器/Code GPU。

## 执行

```bash
# native Termux；确保 Android X11 APK 已安装
bash skills/termux/scripts/run.sh desktop-install --profile /path/to/profile.json --apply
# 有既有、未登记的 Xfce 布局时，先审阅再明确采用本预设
bash skills/termux/scripts/run.sh desktop-install --profile /path/to/profile.json --adopt-existing --apply
```

安装器拒绝覆盖活动或未完全退出的桌面；用正常结束入口保存并退出后重试。它为修改文件生成备份，保留未知配置，使用普通 guest 用户运行桌面。当前 fresh-install 路径要求支持 OCI `--name` 的 proot-distro 5.x；旧 rootfs 目录可识别。参见 [proot-distro 官方命令](https://github.com/termux/proot-distro)。不对既有容器执行隐式升级/reset。

安装包括：native X11/PulseAudio/控制服务；guest Xfce/中文字体/主题/SVG loader/诊断工具；所选应用；桌面/菜单/面板入口；电量桥接；正常退出与输入切换；原生及 guest AGENTS 区块。不自动开启桌面。

```bash
desktop start
desktop status --json
bash skills/termux/scripts/run.sh desktop-doctor --profile /path/to/profile.json
```

## 应用

- VS Code 使用 [微软官方 Linux 下载](https://code.visualstudio.com/docs/setup/linux)，按 guest 架构选择包，使用普通用户和 PRoot 兼容启动参数。版本需要与主机一致时设置明确版本并核对。扩展、账户与登录信息保持用户控制。
- Chromium 是桌面预设的浏览器。MIME、Xfce helper 和启动包装器应一致指向兼容入口，避免菜单调用未安装浏览器或直接运行缺少 PRoot 参数的系统入口。已有 Firefox 不因选择 Chromium 而卸载。
- WebGL 动画性能不足时先实测；已加速的 VirGL 仍可能受传输和呈现限制。可选 `browser_backend=termux-zink` 使用官方 native Chromium/Mesa，保留现有图标并增加菜单内的兼容版入口。它通过私有控制器在 PRoot 外启动，不能只在 guest 中直接执行 bionic 二进制就宣称消除了 PRoot。配置和迁移步骤见 GPU 参考。
- LibreOffice 提供 Writer/Calc/Impress；使用 GTK3、CJK 字体与协调缩放。`native-gtk3` 减少 PRoot 调用开销，不宣称获得 Skia GPU 加速；原 guest 版保留在 `libreoffice-tablet-guest`。菜单裁切先排查 DPI、主题与自定义 CSS，不用全局放大所有 GTK 控件来补救标题栏。
- VLC 的兼容预设使用软件解码；`termux-va` 是另行验证的硬解选项，保留 `vlc-tablet-guest`。播放成功不能证明硬件解码或高码率性能，需用授权短样本核对实际解码器、显示/丢失帧及音频。详见 GPU 参考。

浏览器/Code 在 PRoot 中使用 `--no-sandbox` 的兼容性与隔离限制需要向用户说明，不扩展为其他原生工具的通用参数。PulseAudio 只监听有 Cookie 认证的环回地址，不开放无认证 LAN 音频服务。

## 维护

维护前记录当前 profile、应用版本、输入模式、窗口与配置备份。桌面脚本只管理该容器和自有入口。Code settings 支持 JSON/JSONC，合并时保留注释、无关键与已有值；不合法或含重复顶层键的配置会报错并保留原文件。

原生安装显式对齐 `libexpat` 和 `libc++`。已有 Termux 部分更新后，旧库可能无法满足新 Python XML 模块或 Chromium/FFmpeg 依赖；先按缺失符号定位并升级相应库，再恢复未完成的包配置。保留包签名校验，不以移除后安装脚本或无差别重装规避链接错误。

主机缺 JDK/ADB 时可下载到用户目录：

```bash
python skills/termux/scripts/host_tools.py --adb --jdk --apply
```

支持 Windows/Linux/macOS，输出可用路径。Android 管理器、同系列图标和文件夹分组见 [Android 集成](android-desktop-integration.md)。
