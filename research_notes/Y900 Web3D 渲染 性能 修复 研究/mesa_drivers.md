# Mesa Zink Turnip 与原生 KGSL 修复路径

## 当前性能差距能够证明什么

### Takeaway

相同粒子数和画布下，Android 原生 Chrome 的约 60 rAF/s 与桌面 native Chromium 的约 25～32 rAF/s，证明桌面整条图形通路有额外成本；尚不能把这些成本全部归给 Zink、Turnip，或某一个共享图像等待。当前应先做可逆的固定刷新率 A/B，再做同一 native Chromium 路径的版本对照，驱动替换放在后面。

### Cited Findings

- 本次本机对照保持 Tendrils 高画质 rootNum=1024、1920×1152、DPR2、音频80秒暂停且模拟继续。Android Qualcomm GLES 约60，native Termux GLES/Zink/Turnip 约25～32。旧 Vulkan/Skia、纯 ANGLE Vulkan、关闭 GPU raster 实验均没有产生可采用的提升。原始数据属于本机实验，不来自外部网页。[本机比较摘要](C:/Users/scisa/AppData/Local/Temp/y900-web3d-20261118/comparison-summary.json)
- Zink 的设计是以 Vulkan 调用实现 Gallium/OpenGL，而非直接面向 GPU 指令集。因此当前通路中，ANGLE GLES 后面还有 Zink→Vulkan→Turnip；切换成原厂 Vulkan wrapper 只能替换 Turnip，未必去掉 Zink。[Mesa Zink 设计说明](https://docs.mesa3d.org/drivers/zink.html)
- 官方 Termux 当前 Mesa 构建配方与安装版一致为26.2.7，启用的 Gallium 驱动只有 llvmpipe、softpipe、virgl、zink，未包含 Freedreno Gallium/KGSL。不能在现有安装上仅把 `MESA_LOADER_DRIVER_OVERRIDE` 改成 `kgsl` 就当成已经切换到真实硬件 KGSL。[Termux Mesa26.2.7 构建配方](https://raw.githubusercontent.com/termux/termux-packages/master/packages/mesa/build.sh)
- Chromium 研究线进一步读取本机长耗时事件：最长约32～33ms的 FinishPaintCurrentFrame 内，BeginAccessImages 仅约0.015～0.033ms；整套 Vulkan 把等待移到 SwapBuffers，不能由函数名直接断言“获取共享图像耗时30ms”。[本机 baseline trace](C:/Users/scisa/AppData/Local/Temp/y900-web3d-20261118/3-baseline-trace.json)、[本机 Vulkan trace](C:/Users/scisa/AppData/Local/Temp/y900-web3d-20261118/2-vulkan-trace.json)

### Inferences

- 图形提交事件的墙钟时间可能包含 GPU 未完成工作、驱动 flush/fence、线程调度或呈现节奏的等待。需结合实际 Android 活动刷新率、CPU 栈/调度和 GPU 时间继续区分。固定刷新率实验的成本和回退范围均小于替换 Mesa，所以优先。
- 正常 Android Chrome 使用不同的驱动、WSI 和构建配置；其60帧不能单独证明把桌面 Mesa换新版就能达到60。

### Gaps

- 尚无当前 Y900 同场景的 GPU 命令执行时间或 native 线程采样栈，无法分摊25～32帧背后的 GPU 工作、CPU等待和显示节拍。
- 尚未找到一手源码明确证明“Android自适应30/60Hz与X11声明120Hz的差异”必然导致当前约30ms等待；这只能作为待检验假设，不是既定根因。

## 上游同步修复与版本适用性

### Takeaway

发现了与“修正闪动后性能下降”高度相关的 KGSL Present wait-fence 上游历史，但它属于 lfdevs 的定制 KGSL 分支，不能直接套用于当前官方 native Mesa26.2.7。另一方面，部分检索到的 Zink 同步修复已包含在26.2.7所继承的26.2.5/26.2.6中，重复建议升级这些旧修复没有依据。

### Cited Findings

- Mesa26.2.5发布记录已列出 Zink 的重排序同步修复、unthreaded batch 按screen序列化、unbind后强制同步等改动。Mesa26.2.6又包含 dma-buf fence 在batch结束时等待、区分读写消费者等修复；两者均早于本机26.2.7。[26.2.5发布说明](https://docs.mesa3d.org/relnotes/26.2.5.html)、[26.2.6发布说明](https://docs.mesa3d.org/relnotes/26.2.6.html)
- 官方26.2.7为2026-11-11的bugfix release；26.3.0于2026-11-09发布，官方仍建议重视稳定性的用户保留前一版或等26.3.1。26.3.0“版本更新”并不自动意味着本机25～32帧问题已修好。[26.2.7发布说明](https://docs.mesa3d.org/relnotes/26.2.7.html)、[26.3.0发布说明](https://docs.mesa3d.org/relnotes/26.3.0.html)
- lfdevs #96 给 KGSL导出图像增加 Present wait-fence，作者还发现 outgoing back buffer 被重复flush，第二次在KGSL落入CPU同步等待。该PR中的 `011eb29` 改动用于避免已成功导出fence后的重复flush。这里的修复目标是定制KGSL DRI路径，不是所有Mesa或所有Vulkan路径。[KGSL Present wait-fence PR96](https://github.com/lfdevs/mesa-for-android-container/pull/96)
- #111原始报告称 Adreno830 上 26.3.0-devel-20260824→27.0.0-devel-20261025 在原生 Wayland 中 glmark2 分数从4454降至797，约5.6倍退化。作者/维护者随后区分了 Wayland 与 Termux:X11：#112于2026-10-29合入，原生Wayland默认关闭该等待，X11/XWayland保留。不得把这个 Wayland 报告当成本机 X11 必然退化的证据。[问题111](https://github.com/lfdevs/mesa-for-android-container/issues/111)、[Wayland热修112](https://github.com/lfdevs/mesa-for-android-container/pull/112)
- 27.0.0-devel-20261025-r1发布说明已包含#112/#113；r2于11月8日发布，后续变化主要是更多发行版构建与Termux:VA启用条件。因此“10月25日”版本字符串不代表r2缺少10月29日热修。X11/XWayland默认保留Present wait-fence，提供 `MESA_DRI3_DISABLE_PRESENT_WAIT_FENCE=1` 退出项，并说明会影响峰值性能。[r1发布说明](https://github.com/lfdevs/mesa-for-android-container/releases/tag/mesa-27.0.0-devel-20261025-r1)、[r2发布说明](https://github.com/lfdevs/mesa-for-android-container/releases/tag/mesa-27.0.0-devel-20261025-r2)

### Inferences

- 现有guest KGSL bundle的稳定性/性能，应核对到r2源码和实际库摘要；不能只看到27.0就宣称已修或一定更快。
- 若将来测试 native bionic KGSL，先保持默认fence保证正确性；仅在隔离窗口中将退出项作为“同步等待贡献”的诊断变量。去掉正确的完成fence可能使消费者读到未完成图像，重现闪动，不能只按内部rAF选择。
- 上述Present fence语义是缓冲区内容完成/消费者就绪，与Android屏幕自适应刷新率不是同一层。两者可能叠加等待，但本研究没有直接证明这一交互。

### Gaps

- 没有找到特定上游commit明确宣称修复“Termux native Chromium157 + Mesa26.2.7 + Adreno830 + Tendrils”这一组合。
- 未证明官方26.3.0相较26.2.7还缺哪些恰好作用于当前等待位置的改动。不能据变更标题就要求全局升级。

## 原生 KGSL 与原厂驱动桥接有哪些可行路径

### Takeaway

后续较值得验证的是“同一 native bionic Chromium + 隔离 bionic KGSL Mesa”，因为它同时避免PRoot与Zink→Vulkan翻译；这并不是已经测过的guest KGSL方案。原厂Vulkan和原厂EGL桥接确有上游实现，但兼容性证据弱于前者，应作为更后面的实验，不直接装进全局prefix。

### Cited Findings

- lfdevs已经提供native Termux bionic构建 `freedreno-27.0.0-devel-20261025-r2`，发布的mesa包SHA256为 `5ee95d32b6030227d3cda52fa14cfa4628a7b3ff5d991f7221fba7cd4fb4b378`；其源配方commit `3ee2f3a` 固定Mesa源码commit `b84f02a4514983ea9b2d96971cde72720c377320`。这是维护者分支，不是Termux官方稳定仓库已合入的KGSL包。[native r2 release](https://github.com/lfdevs/termux-packages/releases/tag/freedreno-27.0.0-devel-20261025-r2)、[固定配方](https://raw.githubusercontent.com/lfdevs/termux-packages/3ee2f3a/packages/mesa/build.sh)
- 维护者PR25要求 `MESA_LOADER_DRIVER_OVERRIDE=kgsl`，并说明其代码来自Lucas Fryzek/xMeM；PR同时提醒在全局安装构建产物前关闭桌面合成。这个全局安装方式不适合作为本机直接执行的首选路径，因为Picom是已验收的配置。[native KGSL PR25](https://github.com/lfdevs/termux-packages/pull/25)
- xMeM的 `vulkan-wrapper-android` 25.0.0-2配方固定wrapper源码commit `e65c7eb6ee2f9903c3256f2677beb1d98464103f`，只构建Vulkan wrapper、不构建OpenGL/Gallium；它依赖generic Vulkan loader和X11/Wayland等库。[wrapper维护者配方](https://raw.githubusercontent.com/xMeM/termux-packages/dev/wrapper/packages/vulkan-wrapper-android/build.sh)
- Termux官方issue25397有Adreno740/750/830使用原厂Vulkan wrapper＋Zink时在glmark2特定场景创建图形pipeline失败的第一手报告。该报告不能证明所有新版本都会失败，但足以阻止把wrapper当成通用稳定替代品。[Termux issue25397](https://github.com/termux/termux-packages/issues/25397)
- `tareksander/termux-gfx-wrapper` 项目明确包装Android原生 `libEGL.so` 并提供X11 GLES；README将Vulkan写为未来工作。构建安装注册优先级10的GLVND vendor JSON，库名为 `libegl-android.so`。这条EGL路线在架构上可以去掉Zink与Turnip，但默认注册会影响同prefix的其他EGL应用。[EGL wrapper README](https://raw.githubusercontent.com/tareksander/termux-gfx-wrapper/main/README.md)、[构建与安装规则](https://raw.githubusercontent.com/tareksander/termux-gfx-wrapper/main/CMakeLists.txt)、[vendor JSON](https://raw.githubusercontent.com/tareksander/termux-gfx-wrapper/main/10_android_wrapper.json)

### Inferences

- native bionic KGSL隔离方案：先校验release摘要，把deb解包到新建私有目录，检查ELF依赖与当前bionic依赖是否兼容；使用该进程自己的 `LD_LIBRARY_PATH`、`LIBGL_DRIVERS_PATH`、`MESA_LOADER_DRIVER_OVERRIDE=kgsl` 及指向私有绝对路径的GLVND vendor JSON。不能加载guest glibc `.so`进native bionic Chromium，也不应执行release文档中的全局 `pkg reinstall ./mesa*.deb`。
- 此隔离方案是需要验证的实施设计，不是已在Y900运行成功的命令。必须核对driver映射，确保没有由于硬编码lib路径而混装旧Mesa；缺依赖或回退软件即拒绝，不趁机全局升级。
- native KGSL仍然使用开源Freedreno，并非“Android原厂GLES”。原厂Vulkan wrapper＋Zink去掉的是Turnip，仍保留OpenGL→Vulkan翻译；原厂EGL wrapper才更接近Android Chrome驱动，但Chromium的EGLImage、共享纹理、compositor兼容性还需验证。
- wrapper实验要保持独立GLVND JSON与进程环境，不向全局 `egl_vendor.d` 安装优先级10文件。所有路线都必须检查 `gpu_compositing=enabled`、`webgl=enabled`，不能把 `enabled_readback`、SwiftShader或软件合成的结果称作纯硬件后端对照。

### Gaps

- 尚无同一Y900/同一Tendrils负载上native bionic KGSL的成绩；此前guest KGSL固定shader约34 vs native Zink约41不是当前负载，也同时混入了PRoot/浏览器构建差别。[既有本机GPU记录](C:/Users/scisa/Desktop/skills/skills/termux/references/desktop-gpu.md)
- 未确认wrapper包已经合入Termux官方稳定仓库；本机driver inventory只发现freedreno ICD。PR22500网页本轮多次获取超时，不能据历史评论断言其今天仍open或已经merge。
- 没有找到EGL wrapper在Chromium157上通过GPU合成、WebGL共享图像和日常输入无闪动验收的主来源。

## 哪些低风险实验应该先做

### Takeaway

优先顺序应为固定刷新率、同native浏览器版本对照、再定位GPU/CPU等待，最后才是native KGSL。每一项只改一个变量，保持高画质和所有已接受的界面配置；拒绝用一组环境变量同时改动后只看rAF。

### Cited Findings

- Turnip官方文档支持 `TU_AUTOTUNE_ALGO=bandwidth/profiled/profiled_imm/prefer_sysmem/prefer_gmem`。本轮另从官方26.2.7源码归档下载并核对SHA256 `04294f75d22e9f61cd1e050206bc48b3d39366e788f1803a3368e3d5a872ce18`，确认 `tu_autotune.cc` 确有这些选项；不是仅从latest文档推定老版支持。[Turnip autotune文档](https://docs.mesa3d.org/drivers/freedreno.html#autotune)、[26.2.7源码归档](https://archive.mesa3d.org/mesa-26.2.7.tar.xz)
- 26.2.7源码中，`zink_screen.c`通过 `GALLIUM_THREAD` 选择线程化，并提供 `ZINK_DESCRIPTORS`；官方文档仅在高CPU负载场景建议尝试descriptor manager。`ZINK_DEBUG=sync`、`flushsync` 会增加/强制同步，`noreorder`关闭重排序优化，它们不是通用提速开关。[Zink调试与性能文档](https://docs.mesa3d.org/drivers/zink.html)、[已核验源码观察](C:/Users/scisa/AppData/Local/Temp/y900-web3d-20261118/research-upstream/source-observations.json)
- 维护者同Adreno830的旧Turnip案例指出 `immediate` 可严重撕裂，mailbox能维持较好的正确性；`immediate`叠加软件WSI虽能避免撕裂，却明显降帧。这支持保留本机已接受的mailbox，而不是为了计数解除同步。[维护者issue56](https://github.com/lfdevs/mesa-for-android-container/issues/56)

### Inferences

| 顺序 | 只修改的变量 | 要记录什么 | 如何判断和恢复 |
|---|---|---|---|
| 1 | Android自适应→临时固定60，然后固定120；每轮恢复原策略做交替对照 | 动画期间实际active mode、rAF分布、外部呈现、同一图形提交事件 | 若固定策略明显缩短等待，先修显示节拍一致性；不能只看设置值或Xrandr120。结束恢复原自适应策略 |
| 2 | 同一native Chromium安装路径的patch/build版本 | 完整版本、ANGLE/Skia构建信息、相同Mesa/同DPR/同backend及GPU状态 | 仅独立实例A/B；不改日常profile，未出现稳定提升即撤回；没有对应版本时先不声称升级有效 |
| 3 | 保持现有路径，只补CPU调度/等待与GPU执行时间证据 | 长FinishPaint等待期间究竟在哪个native函数阻塞、GPU是否繁忙 | 这决定应优化提交同步、GPU pass还是调度，避免把墙钟事件误当GPU shader时间 |
| 4 | 仅native Chromium加载隔离bionic KGSL Mesa | 驱动映射/真实renderer、shader像素、context loss、GPU合成是否仍启用、固定Tendrils、外部画面 | 先默认fence；按相同顺序至少三轮。任意白屏、闪动、readback/软件回退、输入回归即拒绝。关闭诊断实例并移除本进程env即可回退 |

- 若第3项确认GPU render pass耗时高，再在原Mesa上分别比较 `TU_AUTOTUNE_ALGO=prefer_sysmem` 与 `prefer_gmem`，每次只有一个变量；若CPU提交线程占用高，再选 `ZINK_DESCRIPTORS=lazy` 或 `GALLIUM_THREAD=0` 之一诊断。它们是依据profile选择的后备实验，不是下一轮应一口气尝试的flags清单。
- 所有性能候选都必须同时通过真实图像和稳定性。不可通过关掉必要fence换取数字上涨，也不接受固定刷新率提高但长时出现闪动的方案。

### Gaps

- 本轮为只读研究；未连接或更改设备、未运行新的性能对照。表中为可执行研究设计，任何候选尚未构成本机修复。
- 原厂GLES桥接与原厂Vulkan wrapper的依赖/兼容风险较高，且本轮没有新的Chromium稳定性主来源，因此不应在上述低风险实验之前安装。
