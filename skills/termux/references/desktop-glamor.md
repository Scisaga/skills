# Glamor 原桌面修复

用于已有应用GPU加速，但整桌面合成与缓冲交接仍使Web3D低帧的维护。`x11_glamor` 默认false；开启前必须核对APK支持和设备验证结果。它与浏览器ANGLE后端、Mesa选择、Picom后端分别控制。

## 阶段结果与当前回归

2026-11-19后续用户操作暴露了新问题：Chromium标签拖出成为独立窗口、再拖回合并时，左上角出现白块。仅GPU屏障方案及随后两种局部同步方案仍在重复录屏中出现偶发错误，不能视作最终修复。后续还发生所有Xfce窗口触屏拖动延迟与黑色角点残留，实验已撤回。仅关闭Glamor不能证明二进制恢复，也不能证明其他合成配置已撤回。

恢复使用未经修改的官方X11后，原Picom局部重绘仍有角点残留。关闭局部重绘仅通过一次纯色像素检查，Chromium拖窗的自动触屏检查仍失败。随后撤回Picom，恢复Xfwm自身合成。120Hz触屏手势拖动Xfce窗口，松手后约25ms停止，约644万个背景像素未检出黑色残留。用户实际复验Xfce和Chromium拖窗及切换窗口，反馈“显示和拖动都正常”。验收时的core事件模式已保存到Xfwm进程专用启动项并回读，完整桌面冷启动待验。Web3D提帧目标仍未完成，以下帧率记录属于此前实验版本。

2026-11-18在Adreno830设备的原`:1`桌面验证，保留Xfwm、Picom12.5/xrender/vsync/use-damage、原日常Chromium配置与Code。3840×2560桌面、scale2；Tendrils高画质1024粒子根数、1920×1152画布。网页约44.62次rAF/秒，后续六秒录屏双帧号解码约41.30个新WebGL画面/秒；两项不是同一采样窗口。旧链路曾约30个新画面/秒，不能将独立无WM窗口的45帧结果当作原桌面结果。未达到Android原生Chrome约60rAF/s，也不保证所有网页。

Code十轮覆盖切换、缩放与重新最大化后，标题区像素一致，屏幕与客户端所检区域一致；Android应用切走再返回后四个静态区域像素一致，截图无之前的条纹。长期功耗、Android重启恢复及完整IME手感未重新验收。

## 源码与补丁

- [Termux:X11 PR1153](https://github.com/termux/termux-x11/pull/1153)，固定merge `e35f1c4a01a5bc572fb3968c2440207ca6aa17cd`，Xserver子模块`65d790bd208ec380b196eb98f144abb0b32e334d`。
- GLES精度、上传与VBO修正参考并适配自[PietroCav501固定版本补丁](https://github.com/PietroCav501/termux_on_dex/blob/191b9319b2332c24a5cb5bea749c665469872ecc/x11/patch/xserver-glamor.patch)，保留原许可与作者信息。
- 补丁及摘要位于 [assets/desktop/patches](../assets/desktop/patches/source-manifest.json)：native侧兼容raw-FD DRI3并避免GPU根缓冲CPU重锁；Xserver侧处理BGRA读回查询、GLES高精度、上传步长、VBO、FBO切换与纹理屏障。逐次CPU读回虽可消除残影，但原桌面降至约31帧；异步PBO读回仍有错误，未采用。
- 此前版本在取源纹理前切换目标FBO，使用texture-fetch/texture-update/framebuffer GPU memory barrier；GLES不使用shim空实现的NV texture barrier。该组合通过基本重绘检查，但后续标签拆合测试仍失败。仓库所附补丁保留为这一阶段的可复现源码，不能作为已消除闪动的最终版本分发。

在固定基线及完整子模块上执行；下列命令仅适用于独立源码目录：

```bash
git apply --check /path/to/termux-x11-glamor-native.patch
git apply /path/to/termux-x11-glamor-native.patch
git -C lorie/src/main/cpp/xserver apply --check /path/to/xserver-gles-adreno.patch
git -C lorie/src/main/cpp/xserver apply /path/to/xserver-gles-adreno.patch
```

Termux:X11的CMake还会应用自己的`xserver.patch`；不要把构建后的整棵Xserver差异误当成本补丁。Windows通过WSL构建时，源码放在Linux区分大小写的持久目录，避免NTFS的`Xlocale.h/xlocale.h`冲突与`/tmp`重启丢失。此版本使用NDK29.0.14206865、android-24、arm64-v8a、RelWithDebInfo；按上游CMake构建Xlorie。APK仅替换arm64库，保持16KB对齐并核验签名。需要保留原可安装APK和源码清单，不把签名密钥放入仓库或设备。

## 部署与验收

1. 备份原APK、native配置和控制器。正常结束桌面，确认服务及浏览器退出，拒绝丢弃未保存编辑。
2. 仅在签名确实匹配时更新原包并保留应用数据。设备profile显式设`x11_glamor=true`，控制器增加`-glamor`；通用模板仍false。普通旧APK、未修复的PR构建不等同于上述组合。
3. 先显示原X11 Activity，再启动桌面和恢复浏览器。提前启动服务可能使应用初始尺寸为1280×1024，网页自动选择低画质；必须读回实际画布和粒子数。日常`desktop start`已有显示优先顺序。
4. 核对原profile、标签、工作区、compositor owner、实际进程与几何。日常实例不加CDP或automation。使用同画质、同画布的DOM/WebGL双帧号和SurfaceFlinger区分回调、呈现与真正新像素。
5. 覆盖/暴露、拖动缩放、输入菜单、Android切走再返回，并查看实际截图。必须重复标签拖出和拖回合并，记录实际窗口数量与几何；鼠标与手指拖标题栏分别验证，确认松手后停止，不能以鼠标通过替代触屏通过。静态ROI应配合人工检查，区域统计不能发现所有位置的预存残影。测试后刷新原网页移除观察器，关闭自有维护窗口，保留用户应用。
6. 回滚先正常结束桌面，恢复配置、控制器及需要撤回的合成器，再恢复签名匹配且能通过系统验证的APK，保留原浏览器profile。若原备份被Play Protect拒绝，记录失败并核对当前实际安装包；不要关闭保护、绕过拦截或把被拒绝文件重新打包。可核验官方发布的摘要与签名后正常更新，安装后必须回读实际APK，不能以安装前文件或命令后续输出代替成功证明。不要只关闭glamor开关却声称二进制也已恢复。

本机固定60/120Hz与修正重复MSC没有可部署性能收益；刷新率原值恢复。Glamor补丁不要求全局升级Mesa、关闭浏览器GPU或降低网页画质。
