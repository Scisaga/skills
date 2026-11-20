---
name: termux
description: 在 Android 上安装、迁移和维护 Termux 原生 SSH/API/Boot 环境，以及按需部署 Termux:X11、PRoot Linux 桌面与开发办公应用。用于平板工作站、设备远程管理、独立 VS Code 主屏与 Dock 多窗口，以及显示、输入、网络、功耗和遗留进程排障。
---

# Termux

## 概述

按任务选择原生环境或可选 Linux 桌面。原生功能保留旧 `termux-ssh` 的 SSH、公钥、Boot/runit、共享存储、API、蓝牙 companion、Bash 和本机 Codex。桌面模块提供 X11、Debian/Xfce、VS Code、Chromium、LibreOffice、VLC，以及显示输入适配和会话管理。

SSH 用户名、提示符或 PRoot 中显示的 `root` 都不赋予 Android UID 0。无需把 Root 作为安装桌面的前置条件。Docker 与硬件加速另行评估，见 [能力与部署边界](references/desktop-setup.md)。

## 执行环境与连接

- 先按问题所属环境选择操作位置：Xfce 菜单、Thunar、桌面设置及 guest 应用，直接在当前 Xfce 界面或其终端处理；原生 Termux 服务才使用 native 环境；Android 系统设置使用已有 ADB/系统界面。不要把技能名称、旧脚本或 ADB shell 的权限限制当作跳到 Termux 的理由。
- 沿用用户指定且已确认的设备和通道。USB/ADB 已连接时，不额外尝试 LAN SSH、校验/登记主机密钥或改网络。只有任务明确涉及 SSH，或现场证据证明当前通道无法完成必要步骤时，才处理相应连接需求；不得先换通道再找理由。
- 仅问“是否应该”且不依赖现场状态时直接给建议，不自行展开设备诊断；用户要求“调整”“看看菜单”时，实际查看目标界面、完成修改并在原界面复核，不停在建议。
- 用户纠正执行环境或连接方式后立即按纠正路径继续任务，不再尝试已拒绝的路径。具体位置、权限与终端选择见 [执行位置与现有通道](references/execution-context.md)。

## 工作流

1. 核对当前设备、问题所属环境及已有连接，只盘点本次任务需要的状态。维护现有环境时读取目标环境的 `~/AGENTS.md`；Xfce 任务先读 guest 指引，涉及 native 操作时再读原生指引。保留当前输入模式、文档和窗口，不为读取无关上下文切换终端或建立新连接。
2. 选择本次需要的模块。仅远程管理走原生流程；仅本机桌面可直接使用桌面安装流程，不强制启用 SSH。桌面应用、外设、Android 文件夹整理按需求选择。
   把用户已知故障列为本次验收条件；记录必需检查及用户明确跳过的项目。配置、真实功能与性能分别验收，未执行不能计为通过。
3. 首装或迁移先读 [安装与迁移](references/installation-and-migration.md)。Termux/Boot/API/Widget 使用同一签名来源；X11 同时需要 Android APK 与 native CLI。插件安装/更新可能中断 Termux 进程，应在保存并结束桌面后安排，随后复查存储权限。
4. 原生部署使用 `bootstrap`，权限与后台问题按 [Android 权限与电源](references/android-permissions-and-power.md) 和 [远程管理](references/remote-management.md)。需要蓝牙或本机 Codex 时分别读取对应参考，不自动启用其他模块。
5. 桌面部署先 `desktop-plan`，再按 [桌面安装](references/desktop-setup.md) 执行。配置采用 JSON；示例 [tablet.json](assets/desktop/tablet.json) 是可调整的平板预设，不能把分辨率、字体和应用偏好固化为所有设备的要求。
   维护或重装有定制的桌面时，先核对 [配置基线](references/desktop-verification.md#桌面配置基线)。改动后用 `desktop-baseline` 比对实机回读，复验日常入口和受影响的基础操作，再更新已验收的基线。
6. 显示、键盘、触屏和主题按 [显示与输入](references/desktop-display-input.md)；GPU 与应用性能按 [GPU 渲染与验收](references/desktop-gpu.md)，分别验证 VirGL、直接 KGSL、native Chromium/Zink、原生办公或视频硬解，不以启动参数代替实际绘制/出帧；会话、退出、电量和 CPU 问题按 [生命周期](references/desktop-lifecycle.md)；VPN/代理/DNS 按 [网络排障](references/desktop-network.md)。
   已知低帧率要在本次 GPU 配置内固定负载复测，并验证日常入口。输入修复同时检查单击、双击、拖动、长按与滚动；不要只验证新增手势。鼠标先区分速度、精细定位与事件节拍，固定配置取证后再做单变量对照。
   窗口问题分开验证应用 GPU、Xserver 重绘、整桌面合成与 Android 最终呈现；在症状发生时核对实际刷新率，不用 Xrandr 或静置快照代替。先只读取证，固定条件做单变量对照；Expose、动画回调、呈现时间戳与像素正确性分别报告。外框先区分客户端装饰和 Xfwm 框架，再试应用自带外观选项，见显示与输入参考。
   能直接读取的窗口、GPU 页面和系统状态主动获取，保留原标签页及几何；用户主要验收真实输入、手感和偏好。快捷键按 Android 转发与 Xfce 绑定分别验证，裸 Win 还须验证再次收起菜单；主题检查按钮全部状态及 PNG/XPM 覆盖尺寸。见显示与输入参考中的可回退脚本。源码结论须对应实际安装版本，设备案例不作为全局默认。
   优先使用上游支持的配置；出现控件回显或桌面回归时先撤回实验并查日志。用户允许暂缓的兼容问题如实保留，不继续叠加事件拦截或预加载注入。
   内存任务按 [应用内存诊断](references/desktop-memory.md) 区分驻留 PSS、非映射图形、SwapPss 与 ZRAM 物理量；保留工作与网络，固定负载比较，优先浏览器正式设置及身份合格的缓存/残留进程。
7. 需要 Android 图形管理、双应用入口、同系列图标或桌面文件夹时，读取 [Android 集成与图标分组](references/android-desktop-integration.md)。管理器从随附源码构建；签名私钥留在主机外部目录。仅整理当前启动器的实际图标，不直接改其数据库。
   Android 主屏独立 VS Code、Dock 图标与标题、快捷键新建窗口和 ZUI 关联启动提示按 [独立 VS Code 与扩展配置](references/standalone-code.md) 处理。实测多窗口前对照 Android 任务与仍在运行的 X11 会话，并检查子进程余量。选择 Office Viewer 时默认仅关联 Office 格式。
8. 按 [桌面验收](references/desktop-verification.md) 与 [原生验收](references/verification-and-troubleshooting.md) 完成本次相关检查，仅更新涉及的 AGENTS 受管区块。清理本任务的临时文件、进程和转发，沿本次已有通道复核结果；只有任务包含独立 SSH 交付时才做脱离 ADB 的 LAN SSH 验收。保留未通过及未执行的测试。
   重启前先收齐依赖、有效子进程上限、权限与服务就绪检查。重启后使用原检查点，首次解锁后先取证自动恢复与实际上限，再打开图形桌面；不以手动启动代替自启动证明。检查失败先定位并修复对应阶段，减少重复重启与解锁。

## 命令模式

```bash
bash skills/termux/scripts/run.sh help

# 主机只读盘点；权限脚本默认预览
bash skills/termux/scripts/run.sh host-doctor --serial SERIAL
bash skills/termux/scripts/run.sh host-permissions --serial SERIAL --storage --api-battery --background

# 原生 Termux：SSH/Boot/API/Bash，沿用现有选项
bash skills/termux/scripts/run.sh bootstrap --authorized-key-file /path/to/host.pub
bash skills/termux/scripts/run.sh verify
bash skills/termux/scripts/run.sh update-agents --greeze-status unknown

# 可选桌面；plan 可在主机运行，install 在 native Termux 运行
bash skills/termux/scripts/run.sh desktop-plan --apps code,chromium,office,vlc
bash skills/termux/scripts/run.sh desktop-install --profile /path/to/profile.json --apply
bash skills/termux/scripts/run.sh desktop-doctor --profile /path/to/profile.json
# 主屏独立 VS Code，默认预览
bash skills/termux/scripts/run.sh standalone-code launcher
# 主机验收；连接文件和检查点置于仓库外的私有目录
python skills/termux/scripts/desktop_verify.py policy --connection /private/device.json \
  --state /private/policy.json --min-cap 128 --monitor enabled
python skills/termux/scripts/window_probe.py inspect --connection /private/device.json \
  --state /private/window-state.json
# 已取得的同一图层前后快照；NS 为设备端同一时钟下的运动起止纳秒
python skills/termux/scripts/presentation_timing.py --before /private/before.txt \
  --after /private/after.txt --layer 'EXACT_SURFACE_LAYER' \
  --start-ns START_NS --end-ns END_NS --state /private/present.json

# 安装后 native 入口：桌面由服务持有，启动终端可以关闭
desktop start
desktop status --json
desktop stop                   # 打开正常结束界面，保存选择由用户处理
desktop manage                 # Android 图形管理器；--terminal 为诊断菜单

# 主机构建管理器并盘点图标；Windows 可直接运行相应 Python 脚本
bash skills/termux/scripts/run.sh build-manager --java-home /path/to/jdk --output /path/outside/repo/desktop-manager.apk
bash skills/termux/scripts/run.sh launcher-plan --adb /path/to/adb --serial SERIAL --folder Termux
```

其余命令包括 `configure-codex`、`build-bluetooth`、`deploy-bluetooth`、`desktop-context`、`repair-panel`、`deploy-manager`、`network-doctor`、`host-tools`。先看相应 `--help` 与参考文档。缺少 Python/JDK/ADB 时使用明确的安装命令或随附下载脚本。新桌面脚本使用 CLI/JSON 配置，不自动加载 `.env`；旧原生脚本与私有网络配置保持原有行为。

## 资源使用

- 操作前先确定位置与通道：[execution-context.md](references/execution-context.md)。
- 原生安装/签名/备份：[installation-and-migration.md](references/installation-and-migration.md)。
- 权限/Boot/Doze/Greeze：[android-permissions-and-power.md](references/android-permissions-and-power.md)。
- SSH、存储、Bash、API、设备上下文：[remote-management.md](references/remote-management.md)。
- 可选蓝牙：[bluetooth-companion.md](references/bluetooth-companion.md)；本机 Codex：[codex-on-termux.md](references/codex-on-termux.md)。
- 桌面预设、安装、应用与边界：[desktop-setup.md](references/desktop-setup.md)。
- Thunar 缩略图、SMB 文件打开与 Xfce 启动器排障见 [desktop-file-access.md](references/desktop-file-access.md)。
- VS Code/Git 凭据、GNOME Keyring 与无额外密码解锁：[desktop-credentials.md](references/desktop-credentials.md)。
- Android 主屏独立 VS Code、Office Viewer 文件关联及 Chrome 预览：[standalone-code.md](references/standalone-code.md)。
- 显示/触控/实体键盘/字体/主题：[desktop-display-input.md](references/desktop-display-input.md)。
- 服务、退出、CPU 和电池：[desktop-lifecycle.md](references/desktop-lifecycle.md)。
- Android/Xfce 多进程内存、应用级优化与回退：[desktop-memory.md](references/desktop-memory.md)。
- GPU 后端、并发应用、真实绘制与回退：[desktop-gpu.md](references/desktop-gpu.md)。
- 设备兼容记录与测量边界：[desktop-compatibility.md](references/desktop-compatibility.md)，只用于选择待验证路径，不替代当前设备实测。
- VPN、代理、DNS：[desktop-network.md](references/desktop-network.md)。
- Android 管理器、全部应用入口、图标与分组：[android-desktop-integration.md](references/android-desktop-integration.md)。
- 验收与能力覆盖：[desktop-verification.md](references/desktop-verification.md)。

## 输出规则

- 报告实际变更、入口、备份位置、验证结果和限制。不要把高分辨率、Root 标签或应用已安装等同于完整性能/功能已验证。受管记录从 UTF-8 文件生成，更新时备份并回读；乱码依据原始证据修复，不猜测丢失内容。
- 在用户需求内安装所选模块；主题、字体、浏览器及触控偏好依任务确定。
- 正常退出保留应用保存提示；强制退出须有明确授权并绑定当前会话。自动清理只针对记录且身份复核通过的异常辅助进程，不按高 CPU 杀活动应用。
- 不在技能中保存真实 IP、序列号、UID、订阅、代理凭据或私钥；参数示例使用占位符。保留旧设备目录及 `android-termux-ssh` 受管标记兼容。
- 破坏性卸载、清数据、移除锁屏或全局关闭省电策略需单独明确授权；首次解锁、普通锁屏、真正息屏分别记录。
