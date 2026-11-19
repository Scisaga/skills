# Y900 Web3D 渲染 性能 修复 研究

**桌面显示与触屏拖窗已通过用户实机复验。Web3D提帧目标仍未完成。** 当前使用未经修改的官方Termux:X11、原控制器与配置，以及Xfwm自身合成。Glamor和外置Picom已撤回。此前约41～42个新WebGL画面/秒来自出现白块及拖窗延迟的候选版本。固定60/120Hz及修正MSC的对照也未改善实际出帧。

## 标签拆合与触屏拖窗回归（2026-11-19）

用户明确是把标签拖成独立窗口，再拖回合并。加入新建FBO首次采样与外部存储采样同步的版本，高画质实测约42.49个新画面/秒，但三轮拆合中的第三轮合并仍捕到一帧条纹。随后补上桌面根缓冲的写入互斥及完成等待，六轮拆合中仍出现一次左上白块，不能认定问题已消失。

根缓冲交接解析的后续候选未通过验收。用户报告手指拖窗口标题栏有严重延迟，停止拖动后窗口还在移动；随后包括普通Xfce窗口都卡顿，并出现黑色阶梯状角点残留。仅关闭Glamor、恢复控制器和配置，仍然能复现残留，不能称为完整回退。

已将修改版X11替换为未经修改的官方Nightly Release 20261115，同包名更新保留应用数据；GitHub资产摘要、签名证书及安装后回读摘要一致。官方APK SHA256为`77c1791d6dccb4853a0b9e5e5fd85dc27872968fefe9122a8c6e45abd342f618`。原备份APK被Play Protect拒绝安装，未绕过、未关闭保护；没有将被拒绝的文件重新打包安装。[官方发布](https://github.com/termux/termux-x11/releases/tag/nightly)

官方X11配合Picom原局部重绘仍能观察到黑色角点。关闭局部重绘后，纯色检查的6,377,572个像素未检出黑色残留，Chromium触屏拖窗的自动检查仍失败。进一步撤回Picom及其自启动，恢复Xfwm自身合成。重启面板后，隐藏底栏触发区回到原生坐标`y=2554`。在该配置下，120Hz触屏手势首次移动Xfce窗口约159ms，松手后约25ms停止，6,439,396个预期纯色背景像素未检出黑色残留。窗口框架和客户端都可能发出配置事件，因此单独用像素计数评估画面更新。

随后用户实际拖动Xfce和Chromium窗口并切换窗口，反馈“显示和拖动都正常”。已将验收时的`GDK_CORE_DEVICE_EVENTS=1`保存在Xfce的Xfwm启动项，并回读核对。该设置仅作用于Xfwm，仍待下一次正常桌面冷启动复核。原始自动测试与实际触屏反馈分别保留。

## 官方 X11 下的 Xfwm 同步对照（2026-11-19）

使用同一官方APK的独立标签显示，保留原桌面会话，启动独立Xfwm和干净的Chromium配置。保持同一Tendrils高画质1024粒子根数、1920×1152画布、DPR2、音频暂停在80秒，三阶段面板均约60Hz。Xfwm始终开启合成，仅切换`xpresent → off → xpresent`。对照重复两轮，降低录屏尺寸并选定实际持续提交的Android图层后得到以下结果。

| 测量 | XPresent | 关闭垂直同步 | 恢复 XPresent |
|---|---:|---:|---:|
| 网页动画回调/秒 | 29.25 | 33.87 | 27.12 |
| 未录屏时图层呈现/秒 | 28.63 | 32.24 | 26.75 |
| 录屏中的新WebGL画面/秒 | 27.97 | 32.58 | 26.15 |

第一次关闭垂直同步测得42.87次网页回调/秒，录屏只测到29.20个新画面/秒。低开销复测中的呈现与像素证实有限的增益，仍达不到此前隔离路径的约45个新画面/秒。原桌面保留已验收的XPresent配置。隔离浏览器、显示及ADB转发已退出，原Xserver、浏览器与窗口管理器进程继续运行。

## 此前原桌面阶段结果（2026-11-18）

原3840×2560桌面、scale2、Tendrils高画质`rootNum=1024`（1,048,576粒子）及1920×1152画布未变。原日常实例约44.62 rAF/s；随后约六秒录屏的DOM/WebGL双帧编号均解码到约41.30个新画面/秒，7个重复编码帧、1次大跳变、0无法解码帧。SurfaceFlinger两个阶段约40.67/42.31呈现/秒。与此前约30个新画面/秒相比已有改善，但不是稳定60fps或所有网页性能承诺。

原Code经过十轮覆盖切换、缩放和重新最大化后，欢迎页标题区像素一致；外部屏幕与客户端所检区域一致。Android应用切走再返回后，菜单、标题、侧栏、活动栏所检像素一致，实际截图无此前条纹。原四个标签和工作区保留，网页观察器已通过原标签刷新移除，日常无调试端口。

原包`com.termux.x11`同签名更新，APK SHA256=`4fc6ade80a5030cf5e4b73670073956c718d89aa2095543961513971f98bcd07`，native库SHA256=`db096c68fb915d75d5f2d4dcdd1af5cc0a010fcbc73559f1642e28d51f5b9ad2`。新增设备级`x11_glamor=true`，原Picom12.5/xrender/vsync/use-damage和MIT-SHM选择保留，Mesa未全局更新。补丁及归属、构建基线和验收方法见[技能参考](../skills/termux/references/desktop-glamor.md)。

逐次CPU读回消除了当时的残影却使原桌面仅约31个新画面/秒；异步PBO仍有局部错误。当时组合先绑定目标FBO再取源纹理，并使用显式GPU纹理/帧缓冲内存屏障，通过性能及基本像素检查，随后被标签拆合回归否定。长期功耗、Android重启恢复和完整IME手感也未重新验收。

## 自适应刷新与时钟异常的区别

Android 的刷新率选择同时受到显示策略、活跃图层、内容检测、触摸和静置计时器影响。`min_refresh_rate`、`peak_refresh_rate` 是策略输入；应用请求和系统约束仍会参与，写入 60 并不等于运行中的面板已经稳定在 60Hz。Xrandr 报告的时序、Chromium 的同步估计和 SurfaceFlinger 的实际呈现，也不是同一项测量。([AOSP 刷新率机制](https://source.android.com/docs/core/graphics/multiple-refresh-rate)、[Android 帧率请求与实际显示变化](https://developer.android.com/media/optimize/performance/frame-rate))

在对应的完整提交 `488dbbd559acd24f62da0add3182b9c953782cfe` 中，`LorieView.sendWindowChange()` 在布局或尺寸更新时读取 Android 的 `Display.getRefreshRate()` 并传给 native。现场确实出现过面板 60Hz、X11 仍报告约 120Hz 的差异；后续布局更新让 X11 报告变为 60Hz，桌面 Chromium 仍只有约 25～30 rAF/s。**刷新率声明过期是一个问题，但修正这一声明不足以解决当前卡顿。** ([LorieView](https://raw.githubusercontent.com/termux/termux-x11/488dbbd559acd24f62da0add3182b9c953782cfe/lorie/src/main/java/com/termux/x11/LorieView.java)、[MainActivity](https://raw.githubusercontent.com/termux/termux-x11/488dbbd559acd24f62da0add3182b9c953782cfe/lorie/src/main/java/com/termux/x11/MainActivity.java))

本机 `3-baseline-trace.json` 中，321 个 `Scheduler::BeginFrame` 的预期间隔有 36 种，范围 **10.751～13.932ms，中位 12.544ms**；实际 Timer 事件间隔的 P95 达 56.754ms。它没有呈现固定 33.3ms 的简单上限，也不能据此称面板在以约 80Hz 工作。精确 M157 源码显示，Chromium 优先读取 MscRate；失败才用 UST 时间与 MSC 计数差估算。本机同时广告两个相关 EGL 扩展，所以也不能先假定“缺扩展导致估算错误”；应采集调用是否成功及其返回值。([M157 同步算法](https://chromium.googlesource.com/chromium/src/+/refs/tags/157.0.8103.50/ui/gl/sync_control_vsync_provider.cc#47)、[EGL 查询实现](https://chromium.googlesource.com/chromium/src/+/refs/tags/157.0.8103.50/ui/gl/gl_surface_egl.cc#54))

“自动→固定实际 60Hz→恢复自动”和“自动→固定实际 120Hz→恢复自动”均已完成，活动模式由 SurfaceFlinger 连续确认。固定 60Hz 的三轮为 21.4、27.1、34.2 rAF/s；固定 120Hz 为 23.3、20.8、28.1 rAF/s，SurfaceFlinger 呈现仍约 22 次/秒。恢复自动后的结果也未形成固定高刷可重复改善的证据，因此没有保留强制刷新率设置。

## Present MSC 随画面更新被重复推进

2026 年 11 月 18 日，在面板与 X11 均为 60Hz 时，通过自有未映射窗口读取 XPresent NotifyMSC，分别采样约三秒。物理活动模式持续为 60Hz，得到：

| 场景 | 面板 Hz | MSC 每秒增长 | 同期画面更新每秒 |
| --- | --- | --- | --- |
| 静态页 | 60 | 61.10 | 1.01 |
| 简单 CSS 动画 | 60 | 85.79 | 25.80 |
| Tendrils 高画质 | 60 | 84.51 | 24.72 |

MSC 的增长率几乎等于“60＋画面更新次数”。对应源码在 `lorieRedraw()` 的 Choreographer 路径推进 MSC，在 `loriePresentAfterFlip()` 又根据完成的 Present 推进同一个计数；从当前 APK 提取的 native 库也核对到了这一更新位置。这定位了一项实际的重复计数问题。它可以污染依赖 UST/MSC 的节拍估计，与旧追踪约 12.5ms 的漂移相符；但 Chromium 的 MscRate 查询返回值以及该错误对低帧的独立贡献，仍需补丁对照确认。([固定版本显示与 Present 实现](https://github.com/termux/termux-x11/blob/488dbbd559acd24f62da0add3182b9c953782cfe/lorie/src/main/cpp/lorie/InitOutput.c#L568))

USB 恢复后，最小诊断副本已完成原版／单时钟／原版 A/B/A：MSC 增长约 80.83→60.20→79.88 次/秒，SurfaceFlinger 呈现约 21.90→21.10→21.80 次/秒。计数异常被修正，但没有性能收益，故未部署。固定几何的 full-damage 和延后完成通知副本也只用于隔离验证，均未形成可采用的改善；不能将其作为卡顿唯一根因已获证实。

## 约 30 毫秒主要发生在等待阶段

此前同机 [Tendrils](https://epok.tech/work/tendrils/) 对照保持高画质 `rootNum=1024`、约 105 万粒子、1920×1152 画布、DPR 2、音频暂停于 80 秒而模拟继续。三轮各 10 秒采样，Android Chrome 约 60 rAF/s，桌面 Chromium 约 25～32。相同画布控制了网页主要离屏负载，但浏览器构建、驱动、整窗合成和呈现机制仍有差别，不能把倍率全部归给某一驱动。

| 链路 | 已核对的路径 | 仍需区分的成本 |
| --- | --- | --- |
| Android 网页渲染 | ANGLE／高通原生 GLES／Adreno 830 | 原生应用的提交与显示节拍 |
| 桌面网页渲染 | ANGLE GLES／Zink／Vulkan／Turnip | GL 转译、上下文和同步等待 |
| 桌面最终呈现 | Chromium 提交／X11 与合成／Android 呈现 | 缓冲交接、拷贝、合成与调度 |

Zink 本身是在 Vulkan 上实现 OpenGL 的驱动，因此当前桌面路径确有额外转译层；但架构差异不等于已经测出该层占用了多少时间。([Mesa Zink 设计](https://docs.mesa3d.org/drivers/zink.html))

本机基线追踪中，`FinishPaintCurrentFrame` 的**墙钟中位为 30.045ms，线程 CPU 时间中位仅 0.350ms**；其中 `BeginAccessImages` 约 0.018ms，网页动画回调约 2ms。需要修正先前可能的理解：30ms 主要是等待，不能称为该线程计算了 30ms，也不能归为获取共享图像耗时。线程少用 CPU 仍可能是在等真实 GPU 工作、缓冲区、队列或调度，不能反推 GPU 很空闲。

精确 M157 源码在图像访问之后仍有绘制、信号量等待、Skia flush 与条件性 release fence 创建；`Flush` 不等于一定调用同步 `glFinish`。本轮用异步 GPU 查询，每八帧取一帧，得到基线整个网页渲染约 17ms、粒子 step 约 3ms、draw 约 12ms，而回调 CPU 提交约 2ms。查询没有 disjoint 或 GL error；读取像素与录屏放在性能采样之后。它把 GPU 工作与提交等待分开了，但还没有把 FinishPaint 内每个等待函数逐一打点。([M157 FinishPaint](https://chromium.googlesource.com/chromium/src/+/refs/tags/157.0.8103.50/components/viz/service/display_embedder/skia_output_surface_impl_on_gpu.cc#467)、[SkiaOutputDevice](https://chromium.googlesource.com/chromium/src/+/refs/tags/157.0.8103.50/components/viz/service/display_embedder/skia_output_device.cc#328)、[Chromium GPU 调试说明](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/docs/gpu/debugging_gpu_related_code.md#tracing-opengl-calls))

已有失败实验不值得重复：整套 Vulkan 仅约 6.5～7.8 rAF/s，等待转移到 SwapBuffers；仅 ANGLE Vulkan 的候选出现软件合成和 WebGL readback；关闭 GPU 栅格化也没有收益。它们都没有形成可采用的修复。追踪本身有开销，不能把带 tracing 的回调数量混进无追踪的 25～32 帧基准。

## 已完成的实机对照

早期对照使用原桌面的 3840×2560。后续隔离显示保留原桌面进程，因 Android 临时窗口标题栏占用 98 像素，隔离 X11 根窗口为 3840×2462；同组 A/B/A 保持这一尺寸。网页均为高画质 `rootNum=1024`、1920×1152 画布、DPR 2、音频暂停于 80 秒而模拟继续。独立 profile 不复制账号或标签；真实窗口管理器复测仅复制外观偏好和显示、字体环境。每次实验后精确恢复刷新率原键与原值。

下表 rAF/s 是网页回调，SurfaceFlinger actualPresent 是呈现事件；两者都可能高于真正更新的画面数。后续在 DOM 和同一个 WebGL framebuffer 内分别写入 12 位帧编号，性能采样结束后录屏六秒并解码，单独统计新编号、重复帧和异常跳变。同步检查三色块、WebGL 上下文与 GL error。录屏会带来观察开销，其帧编号结果不冒充先前三轮各十秒采样的同一时间窗口。

| 单变量对照 | 观测 | 结果 |
| --- | --- | --- |
| 固定实际 60Hz、120Hz | 仍约 21～34 rAF/s；SurfaceFlinger 呈现约 22 次/秒 | 未解决，恢复自动 |
| 同版本 KGSL、Zink 27；再拆分 Mesa 与 Turnip | 原生 KGSL 约 35～42 rAF/s；只换 Turnip 也到约 35～39，但后者同期SurfaceFlinger 呈现约 20.9 次/秒 | 有 GPU 提速，未形成可采用的显示改善 |
| Turnip 强制 sysmem、gmem | GPU 与回调差异很小 | 不采用 |
| 关闭 Gallium 线程 | 约 23～28 rAF/s | 无收益，不采用 |
| Picom 开启→关闭→恢复 | 回调约 26～34→35～42→25～26；SurfaceFlinger 呈现约 24.4→27.2→23.6 次/秒 | 合成有成本，仍远低于 Android Chrome；此对照未在各阶段重置模拟，不能单独量化其全部贡献 |
| Picom GLX 配合隔离 KGSL | 实际整屏黑画面，三色块检测失败 | 立即恢复 xrender |
| 仅关闭 Picom 垂直同步 | 回调约 26～29，无实质改善 | 恢复原值 |
| Picom 保持同一二进制和配置，脱离 PRoot | 已确认 TracerPid=0、图像正确，回调却约 20 | 恢复原执行路径 |
| native Chromium 经 VirGL 调用 Android GLES | 图像正确、硬件路径存在，约 8 rAF/s | 不采用 |
| 关闭 Chromium GPU 同步、解除帧率限制 | 前者无收益；后者 WebGL 上下文已丢失 | 丢失上下文后的几百次回调作废 |

呈现记录必须覆盖同一单调时钟的完整运动窗口。SurfaceFlinger 短历史需要滚动采集、去重并去掉未完成时间戳，不能用尾部一秒替代全程；Termux:X11 使用 SurfaceView，也不能把缺少某条 FrameTimeline 轨道当作“没有呈现”的证明。高频 dumpsys 和录屏编码会增加负载，观察方法应一致。([Perfetto FrameTimeline](https://perfetto.dev/docs/data-sources/frametimeline))

原生线程采样进一步显示，当前 Zink 场景下 Xserver 工作线程在约 7 秒窗口中消耗约 89.8% 的一核 CPU，LorieRenderer 另约 23.7%；GPU 进程主线程则常在 futex、poll 或 Adreno 等待中。**浏览器的提交等待与 Xserver 的 CPU 压力可以同时存在。** 这些状态还不足以把每毫秒精确归给拷贝、合成或某个 fence 函数，后续需在 Xserver 内部分段取证。native Chromium 本体已在 PRoot 外；实际单独移出 Picom 的对照也没有改善，不能笼统归因 PRoot。([Perfetto CPU 调度](https://perfetto.dev/docs/data-sources/cpu-scheduling)、[Termux:X11 官方慢速说明](https://github.com/termux/termux-x11#avoiding-slowdowns))

## 浏览器与驱动候选需要独立验证

官方 Termux 打包源码已有 Chromium 157.0.8103.78，可在确认对应架构包和依赖后做同路径 A/B。不过 .78 与 .50 所核对的 Viz 提交文件内容相同，ANGLE／Skia 依赖更新也没有直接证明能消除本机等待。它是一个改动范围较小的候选，不是已确认的性能补丁。([官方 Chromium 配方](https://raw.githubusercontent.com/termux/termux-packages/master/x11-packages/chromium/build.sh)、[.78 DEPS](https://chromium.googlesource.com/chromium/src/+/refs/tags/157.0.8103.78/DEPS#333)、[新版 Viz](https://chromium.googlesource.com/chromium/src/+/refs/tags/157.0.8103.78/components/viz/service/display_embedder/skia_output_surface_impl_on_gpu.cc))

**native bionic Chromium＋隔离 bionic KGSL Mesa 已完成实测。** 维护者 r2 包经过摘要核验，只解包到私有目录，分别验证 KGSL、同版本 Zink，以及仅替换 Turnip、仅替换 Gallium 的组合，没有覆盖全局 Mesa。KGSL 的 GPU 渲染可降至约 10～14ms，但较高 rAF 没有同步转化为最终显示更新。早期一次暗画面未稳定复现；后来在读取像素前也看到了正常图像，因此没有把那一次暗画面直接确认为驱动根因。所有候选仍保留默认完成 fence。([官方 Mesa 配方](https://raw.githubusercontent.com/termux/termux-packages/master/packages/mesa/build.sh)、[native KGSL 固定发布](https://github.com/lfdevs/termux-packages/releases/tag/freedreno-27.0.0-devel-20261025-r2)、[维护者 PR25](https://github.com/lfdevs/termux-packages/pull/25)) 在已避免旧画面重复的隔离 front-buffer 配置下，stock、仅 Turnip27、KGSL27 的可见新 WebGL 画面分别约 30.57、30.63、30.78 次/秒；仅 Turnip27 虽达到约 57～60 rAF/s，屏幕新画面并未相应增加。没有采用驱动升级。

搜索命中的 Adreno 830 大幅回退案例值得参考，但发生于定制 KGSL 的 Wayland 路径；后续已有区分 Wayland 与 X11 的修复，r1/r2 也包含相关热修。不能把它直接认作当前官方 native Mesa 26.2.7 的根因，更不能据此全局升降级。原厂 Vulkan wrapper 仍可能保留 Zink，原厂 EGL 桥接虽更接近 Android 驱动，Chromium 共享图像和合成兼容性证据不足，均排在后面。([KGSL Present fence PR96](https://github.com/lfdevs/mesa-for-android-container/pull/96)、[Adreno 830 问题111](https://github.com/lfdevs/mesa-for-android-container/issues/111)、[Wayland 修复112](https://github.com/lfdevs/mesa-for-android-container/pull/112)、[EGL 桥接项目](https://github.com/tareksander/termux-gfx-wrapper))

呈现层的实验也有明确边界：Picom 的 unredirect 实际影响整个 screen，窗口规则只是触发条件；`TERMUX_X11_FORCE_FLIP` 属于 Xserver 启动环境，会越过源码中针对导入 buffer 的 Turnip 保护，并非可热加给 Chromium 的普通提速项。应先确认本机版本、buffer 类型与 copy/flip 路径，再考虑隔离显示诊断，保留当前日常合成及禁用 MIT-SHM 的选择。([Picom 12.5 手册](https://raw.githubusercontent.com/yshui/picom/v12.5/man/picom.1.adoc)、[固定版本 DDX](https://raw.githubusercontent.com/termux/termux-x11/488dbbd559acd24f62da0add3182b9c953782cfe/lorie/src/main/cpp/lorie/InitOutput.c))

最终采用条件仍是**原桌面中的网页真实运动更流畅，同时静态区域、输入、加载、滚动和拖窗保持正确**。本轮没有更换日常 GPU、合成配置或安装包，也没有把诊断二进制用于日常入口。窗口管理器复测排除了直接采用 legacy-drawing＋关闭 Picom vsync；全屏自动 unredirect 试验也出现约 10 rAF/s 的回退。下一步应围绕明确的 buffer 类型、copy/flip 和合成器交接继续取证；只修正时钟或提高内部计数不算解决。

## 约 45 帧的独立窗口与原桌面的区别

两者都运行 Termux native Chromium，并非改用 Android Chrome。原桌面路径经过 Chromium、Xfwm／Picom、Termux:X11 和 Android；独立诊断路径使用另一个 X11 显示和临时 Chromium profile，取消桌面合成，窗口铺满隔离显示，并允许导入 FD buffer 直接 flip。它不能直接共享正在运行的日常 profile，也不能仅凭此测试承诺原标签、登录、输入和窗口管理体验已全部验证。

| 已完成的隔离对照 | 可见新 WebGL 画面/秒 | 解释与结论 |
| --- | ---: | --- |
| 无窗口管理器、无合成器、铺满根窗口、允许直接 flip | 44.99 | DOM 与同 framebuffer 编号均约 44.99，269 个编码帧中 268 个独立 WebGL 编号；确有真实画面提升，但不是原桌面交付 |
| 无 WM、legacy-drawing；Picom vsync true→false→true | 13.73→30.56→13.55 | 关闭该 Picom Present 翻页路径可消除这一 legacy 条件的旧帧重复，不代表原日常配置从 14 提升到 30 |
| 真实 guest Xfwm／guest 启动 Picom；原配置→legacy＋vsync=false→原配置 | 30.01→28.37→27.80 | 三组分别重置场景；候选没有重复得出性能提升，不采用 |
| 真实 WM、全屏和自动 unredirect；先不强制 flip，再允许 flip | 约 10 | 两种条件 rAF 均约 10；全屏方案回退。后续 UI 自动检查因前台窗口焦点字段读取失败而中止，恢复轮未执行，不能声称完整 A/B/A 或输入验收通过 |

Picom v12.5 的 xrender 在启用 vsync 时通过 PresentPixmap 等待完成、交替使用缓冲；关闭时直接绘制到目标 front buffer。这解释了为何两种配置能有相似的呈现事件计数，却显示不同数量的新像素。它只是已测现象的机制线索，真实 guest WM 复测未通过，所以没有据此改日常设置。([Picom v12.5 xrender 实现](https://raw.githubusercontent.com/yshui/picom/v12.5/src/backend/xrender/xrender.c))

Termux:X11 的导入 FD 直接 flip 有明确的 Turnip 保护；`TERMUX_X11_FORCE_FLIP=1` 越过该保护，属于 Xserver 启动环境。已有无合成器的短样本不能证明它在原桌面、多个窗口、菜单和切换全屏时都可靠。([已核对版本的 flip 条件](https://raw.githubusercontent.com/termux/termux-x11/488dbbd559acd24f62da0add3182b9c953782cfe/lorie/src/main/cpp/lorie/InitOutput.c))

## 后续源码方向与交付边界（早期研究阶段）

以下记录形成于Glamor试验之前。当前部署、后续回归与回退状态以本文开头2026-11-19记录为准。

上游另有尚未合并的 glamor GPU 2D 加速分支，可减少桌面 2D 合成的 CPU 路径；但其 DRI3 导入代码拒绝 raw FD，只接受相应 AHardwareBuffer 通路。当前安装不含 `-glamor`，不能加一个参数就启用，也未在本机测试这一分支。若继续此方向，应先验证客户端 buffer 格式与协议兼容，再在私有显示构建和测试，不能直接替换日常 APK。([上游 PR1153](https://github.com/termux/termux-x11/pull/1153)、[该分支的 DRI3 导入实现](https://raw.githubusercontent.com/termux/termux-x11/f84cb04/lorie/src/main/cpp/lorie/InitOutput.c))

用户已确认日常滚动、地址栏中英文输入与拖窗“明显顺畅，未见闪动”，该结论继续有效；同网址 Web3D 性能仍未达到目标。独立显示的 45 帧证明这一设备和当前 Chromium 不只有 30 帧能力，但不代表 Android 原生约 60 rAF/s 与桌面之间的全部成本已被定位。日常浏览器、Code、原标签和登录继续保留，所有实验都未降低画质。
