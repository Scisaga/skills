# Chromium ANGLE 与 Skia 提交等待

## 现有 30 毫秒事件实际说明什么

### Takeaway

现有追踪支持“GPU 主线程主要在等待”，而非网页 JavaScript 或该线程的 CPU 运算过重；但还没有定位到某个具体 GL／Mesa／内核调用。需要区分阻塞发生的位置、阻塞等待的对象，以及对象为何迟迟不能完成。

### Cited Findings

- 本机基线追踪共有 156 个 `SkiaOutputSurfaceImplOnGpu::FinishPaintCurrentFrame`。墙钟中位 30.045ms、P95 32.270ms；trace 的线程执行时间 `tdur` 中位仅 0.350ms、P95 1.103ms。最长一次墙钟 33.277ms、线程时间 0.432ms。`FireAnimationFrame` 墙钟中位 2.019ms、线程时间 1.970ms。`GLContextEGL::MakeCurrent` 墙钟中位 0.425ms／P95 11.462ms，线程时间中位 0.081ms／P95 0.188ms。以上是对已有 JSON 的只读计算，并非新一轮设备实测。[本机基线 trace](</C:/Users/scisa/AppData/Local/Temp/y900-web3d-20261118/3-baseline-trace.json>)
- `BeginAccessImages` 在基线中位 0.018ms、P95 0.037ms。进入 FinishPaint 到该子事件开始，中位 0.011ms；子事件结束后到 FinishPaint 结束，中位 30.017ms。因此不能把 30ms 直接称为“获取共享图像耗时”。[同一 trace](</C:/Users/scisa/AppData/Local/Temp/y900-web3d-20261118/3-baseline-trace.json>)
- 精确 Chromium `157.0.8103.50` 的 FinishPaint 在该位置之后还会做 semaphore wait、DDL 绘制、`ScopedPaint::Flush`、条件性的 GL release fence 创建。没有足够的子事件把这些阶段进一步分开。[精确版本源码 467–596 行](https://chromium.googlesource.com/chromium/src/+/refs/tags/157.0.8103.50/components/viz/service/display_embedder/skia_output_surface_impl_on_gpu.cc#467)
- 同版本 `SkiaOutputDevice::Flush` 最终调用 Ganesh `direct_context->flush(sk_surface, flush_info)`；`ScopedPaint::Draw` 则转给 Ganesh 的 DrawDDL。此函数名本身不意味着同步 `glFinish`。[精确版本 SkiaOutputDevice 328–379 行](https://chromium.googlesource.com/chromium/src/+/refs/tags/157.0.8103.50/components/viz/service/display_embedder/skia_output_device.cc#328)
- M157.0.8103.50 的 DEPS 固定 ANGLE `751417514a521b2e92d6928260c62122138824d3`、Skia `ca84ce0a6f1659748188469a89361ccea71e3a64`。这是上游版本的依赖关系；Termux 还会应用其打包补丁，不能把上游源码等同于可复现二进制证明。[精确版本 DEPS](https://chromium.googlesource.com/chromium/src/+/refs/tags/157.0.8103.50/DEPS#333) [Termux 对应版本打包提交](https://github.com/termux/termux-packages/commit/5387caf98dc76ae6cca94f96a0247d2a20ac0549)
- 此 ANGLE GL 后端 `RendererGL::flush` 直接转给下层 GL Flush；`RendererGL::finish` 是另一个明确调用 GL Finish 的路径。下层 Zink／Turnip 的 Flush 仍可能因队列、资源或同步而阻塞，必须通过调用栈／分段事件验证。[匹配 ANGLE 源码](https://chromium.googlesource.com/angle/angle/+/751417514a521b2e92d6928260c62122138824d3/src/libANGLE/renderer/gl/RendererGL.cpp#218)
- 配套 Skia 的 `onSubmitToGpu` 在 CPU 同步要求或不支持 fence 等条件下才进入 `finishOutstandingGpuWork`；正常分支 Flush 并检查完成回调。不能仅从 FinishPaint 名称断言某种同步分支已发生。[匹配 Skia GL 源码 4389–4424 行](https://skia.googlesource.com/skia/+/ca84ce0a6f1659748188469a89361ccea71e3a64/src/gpu/ganesh/gl/GrGLGpu.cpp#4389)
- 整套 ANGLE／Skia Vulkan 的 FinishPaint 中位仅 0.070ms，但 SwapBuffers 墙钟中位 95.602ms、线程时间中位 69.616ms。它没有消灭开销，而是形成了不同且更慢的提交路径。仅 ANGLE Vulkan／GaneshGL 的候选实际为软件合成、WebGL readback，不能作为去除 Zink 后的纯硬件公平对照。[Vulkan trace](</C:/Users/scisa/AppData/Local/Temp/y900-web3d-20261118/2-vulkan-trace.json>) [Vulkan GPU 状态](</C:/Users/scisa/AppData/Local/Temp/y900-web3d-20261118/2-vulkan-compare.json>) [ANGLE Vulkan 回退状态](</C:/Users/scisa/AppData/Local/Temp/y900-web3d-20261118/6-angle-vulkan-compare.json>)

### Inferences

- 基线 FinishPaint 的墙钟与线程时间差很大，最有价值的问题是“等待 fence／缓冲区／队列／调度中的哪一项”，不是先削减 JavaScript 或降低粒子数。当前只能把范围收窄到 BeginAccessImages 之后的未细分提交阶段。
- Flush／Fence 可能等待真实 GPU 工作，也可能等待旧缓冲区、X11 呈现、跨上下文同步或驱动调度；线程 CPU 很低不能独自区分这些原因，更不能证明 GPU 很空闲。
- 打开 Chromium tracing 本身会改变负载。基线 trace 中的 156 次 FinishPaint／约 8 秒不应直接当作无追踪三轮 25～32 rAF/s 的同一吞吐量。

### Gaps

- 尚无 FinishPaint 内 Draw、Flush、Wait、CreateReleaseFence 的分别耗时，没有阻塞时原生调用栈或 GPU 硬件时间；无法把唯一根因定为 Zink、Turnip、Picom 或 Android 调度。
- 未找到一个直接匹配“此本机版本、Adreno 830、相同提交链路、此症状”的已验证上游修复，因此不提供保证有效的启动参数清单。

## 自适应刷新率和 VSync 来源是否可能参与

### Takeaway

有新的可疑证据，足以把刷新率与时钟来源对照放到下一轮首位；但已有数据不支持把问题简单称为“锁在 30Hz”。浏览器的估算 interval 不是 Android 面板的实际 Hz。

### Cited Findings

- 基线 321 个 `Scheduler::BeginFrame` 的 `interval_us` 为 36 个不同值，范围 10751～13932µs，中位 12544µs，首尾为 12057→13559µs；并不是固定 33333µs。`DelayBasedBeginFrameSource::OnTimerTick` 实际事件间隔中位 12.721ms、P95 56.754ms。浏览器在尝试按一个更快、但不稳定的估算节奏调度，同时有较长间断。[基线 trace](</C:/Users/scisa/AppData/Local/Temp/y900-web3d-20261118/3-baseline-trace.json>)
- no-raster trace 的 interval 首尾 10638→12957µs；整套 Vulkan 的 interval 固定 16666µs，后者仍只有约 7 rAF/s，且提交阶段很慢。因此即使浏览器使用 60Hz 的 interval，其他渲染／提交瓶颈仍可造成严重低帧。[no-raster trace](</C:/Users/scisa/AppData/Local/Temp/y900-web3d-20261118/8-no-raster-trace.json>) [Vulkan trace](</C:/Users/scisa/AppData/Local/Temp/y900-web3d-20261118/2-vulkan-trace.json>)
- 精确 M157 的 `SyncControlVSyncProvider` 在 Linux 上，若不能准确取得刷新率，初始假定 60Hz；优先使用 `GetMscRate`，否则计算前后 UST 时间差／MSC 计数差；连续两次估算的相对差小于 5% 才接受新值，允许的范围为 10～400Hz。此算法能接受任意落在范围内的估计值，并不会把结果强制量化成面板显示模式。[精确版本 SyncControlVSyncProvider](https://chromium.googlesource.com/chromium/src/+/refs/tags/157.0.8103.50/ui/gl/sync_control_vsync_provider.cc#47)
- EGL 实现调用 `eglGetSyncValuesCHROMIUM` 取得 UST／MSC／SBC；若有 `EGL_ANGLE_sync_control_rate`，调用 `eglGetMscRateANGLE`。没有该扩展就不能从这里直接取得分子／分母式刷新率。[精确 EGL provider 实现](https://chromium.googlesource.com/chromium/src/+/refs/tags/157.0.8103.50/ui/gl/gl_surface_egl.cc#54)
- 本机基线实际同时广告 `EGL_CHROMIUM_sync_control` 和 `EGL_ANGLE_sync_control_rate`；Vulkan候选两个都不广告。因此“基线缺少扩展所以只能估算”不成立。仍需观察 GetMscRate 的实际成功／失败，以及返回的分子／分母，才能知道本机具体走的是哪条计算分支。[基线 GPU 扩展](</C:/Users/scisa/AppData/Local/Temp/y900-web3d-20261118/3-baseline-compare.json>) [Vulkan GPU 扩展](</C:/Users/scisa/AppData/Local/Temp/y900-web3d-20261118/2-vulkan-compare.json>)
- 基线中 `SyncControlVSyncProvider::GetVSyncParameters` 191 次，总墙钟约 920ms；其单次中位约 4.596ms、P95 13.182ms。查询本身也有等待，不能视为零成本。[基线 trace](</C:/Users/scisa/AppData/Local/Temp/y900-web3d-20261118/3-baseline-trace.json>)

### Inferences

- 若 UST／MSC 来自模拟或间接呈现链路，其计数与物理刷新不一致，浏览器可得到约 11～14ms 的估计，甚至出现“估计变快而实际出帧更慢”。这里存在时钟来源错配的可能；当前不能断言它就是根因。
- Android 的自适应刷新、X11 声明时序、Mesa／ANGLE 估算、Chromium BeginFrame 和最终屏幕出帧是不同层。Xrandr 120Hz 与浏览器 rAF 25～32 都不能单独证明 Android 当时的面板频率。
- 单纯切换自动刷新可能改善、加重或不改变这种等待。需要记录同一运动阶段的 Android 实际 mode，而不能用开始前或结束后的静置快照代替。

### Gaps

- 此 8 秒基线 trace 不含完整同步的 Android 实际活动 mode、SurfaceFlinger actualPresent、原始 UST／MSC／MscRate 值；无法区分面板切换与计数估计错误。
- 下一轮先做可回退的“原自动／固定 60／固定 120”对照；如果固定实际模式后浏览器 interval 仍漂移，应继续调查 EGL／X11 计数来源。如果 interval 稳定而 FinishPaint 仍等约 30ms，就不能把刷新率视作充分解释。

## 哪些版本和修复方向值得验证

### Takeaway

先用少量能区分原因的实验，随后做新旧 Chromium／驱动隔离比较。已有失败候选应保留为排除证据，不继续重复整套 Vulkan或关闭 GPU 栅格化。

### Cited Findings

- Termux 官方当前 Chromium 打包源码已为 157.0.8103.78；M157.0.8103.50 对应官方打包提交可以精确回溯。设备仍在 .50，因此有一个同主版本更新可作隔离比较，但还需核实当前仓库是否实际有匹配架构二进制及依赖。[当前官方打包定义](https://raw.githubusercontent.com/termux/termux-packages/master/x11-packages/chromium/build.sh) [旧版本提交](https://github.com/termux/termux-packages/commit/5387caf98dc76ae6cca94f96a0247d2a20ac0549)
- .78 的 DEPS 已更新 ANGLE 和 Skia；本次取得的两个版本 `skia_output_surface_impl_on_gpu.cc` 内容完全一致。因此更新不是已确认能改掉 FinishPaint 的修复。[M157.0.8103.78 DEPS](https://chromium.googlesource.com/chromium/src/+/refs/tags/157.0.8103.78/DEPS#333) [新版 Viz 文件](https://chromium.googlesource.com/chromium/src/+/refs/tags/157.0.8103.78/components/viz/service/display_embedder/skia_output_surface_impl_on_gpu.cc)
- 两个 ANGLE revision 之间四个提交分别涉及 Vulkan deferred clear、Vulkan attrib buffer 状态和两个 D3D11 修复；没有找到基线 GLES-on-Zink 性能修复说明。[精确 ANGLE 范围日志](https://chromium.googlesource.com/angle/angle/+log/751417514a521b2e92d6928260c62122138824d3..c56e2a4a9b8cb0040920c995a268be559ba53f1c)
- 新 Skia 含一个 Ganesh flush token 修复：确保即使没有 draw，flush 末尾的 token 也推进，避免后续 flush 错把工作看作仍 pending。这是正确性修复说明，不能从文字中的 pending 推断会消除本机 30ms fence 等待。[Skia 提交与差异](https://skia.googlesource.com/skia/+/f311246998aa0faec7e6c85be242d9332d45cbc8)
- Chromium 官方 GPU 调试文档提供 `--enable-gpu-service-tracing`，用来为 command-buffer 下的 GL API 发出事件；文档同时提醒跨进程系统中用“操作加 glFinish 的总时间”不能提供有意义的性能归因。它未承诺该开关覆盖 Skia 直接 GL 调用。[官方调试文档](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/docs/gpu/debugging_gpu_related_code.md#tracing-opengl-calls)
- ANGLE 官方说明 apitrace 会与 ANGLE 导出的 GL 符号发生冲突，正确抓取需要特定链接方式；因此不能直接套用桌面 Linux 的 LD_PRELOAD 抓取方式到日常 Termux Chromium。其详细 GLES／EGL trace 还涉及编译选项。[匹配 ANGLE 的调试说明](https://chromium.googlesource.com/angle/angle/+/751417514a521b2e92d6928260c62122138824d3/doc/DebuggingTips.md#running-angle-under-apitrace-on-linux)

### Inferences

建议实验优先级如下，全部维持同一 URL、高画质、canvas1920×1152、DPR2、固定动画阶段、原分辨率和既有稳定 compositor／mailbox。

| 优先级 | 单独改变或补齐什么 | 如何判断 | 回退／拒绝条件 |
|---|---|---|---|
| P0 | 自动刷新、固定实际60、固定实际120；记录运动中的实际 mode | 对照 BeginFrame interval、查询耗时、FinishPaint wall／tdur 和 rAF；每项预热后重复至少3轮10秒，顺序交替 | 恢复原自动策略；不能把仅 Xrandr 改值当成物理模式已固定 |
| P0 | 在现有 GL 路径补齐 CPU 阻塞栈或 FinishPaint 子阶段 | 优先区分 Draw、Flush、Wait、release fence；同时查看 UST／MSC 的来源和变化 | 普通 GPU service trace 仍无这些子调用就明确不足；不靠反复增加无关 flags |
| P1 | 用异步 GPU timestamp／disjoint query 测模拟和绘制 | GPU时间接近整帧预算：考虑驱动执行／队列；GPU时间明显较短但 CPU长等：优先WSI／同步／调度 | 不在每帧插 glFinish 或同步 readPixels，因为它们会改变被测流水线 |
| P1 | 隔离比较 Chromium .50 与官方 .78，Mesa和其他条件完全一致 | 比较实际GPU功能状态、renderer、rAF、wall／tdur，以及外部画面 | 新版无收益便保留原版；不能从版本号或commit标题保证提速 |
| P2 | 根据已定位的阻塞函数再比较匹配驱动构建或提交修复 | 明确native26.2.7与guest27.0是不同栈，不能把guest新驱动回归直接套到native | 逐个固定版本、独立目录，不覆盖现有Mesa；保持原profile、输入及稳定性配置 |

若能复现稳定提升，最终仍要验证日常 Chromium 的高画质实际画面、地址栏输入／加载、滚动与窗口拖动；出现白屏、readback回退、闪动或上下文丢失即拒绝。目标是接近同机原生 Chrome 的体验，不能用更高内部计数代替真实画面。

### Gaps

- 尚未执行上述新增对照。本轮仅为资料与已有追踪分析，没有连接、修改或测试平板。
- 没有足够证据宣布某个 ANGLE 功能开关、VSync选项或升级已解决问题；刷新率假设优先验证，驱动／fence／GPU执行／调度仍需按结果分辨。
