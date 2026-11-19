# Termux X11 呈现与自适应刷新率

## 自适应刷新率能否解释当前低帧

### Takeaway

这是应当优先排查的可验证假设，但现有资料不足以认定它是根因。尤其不能由旧的静置30Hz快照推定当前Web3D运行时仍为30Hz，也不能由Xrandr约120Hz或Chromium的估算节拍反推物理屏幕刷新率。

### Cited Findings

- Android由DisplayManager设定策略范围，SurfaceFlinger再按活跃图层、内容检测以及touch/idle等定时器选模式；min/peak是策略输入，应用mode请求、节电等条件仍参与决策。官方还提供“Show refresh rate”显示当前刷新率。——[AOSP Multiple refresh rate，2026-10-09更新](https://source.android.com/docs/core/graphics/multiple-refresh-rate)
- Surface的目标帧率请求不是实效保证；系统可能采用其整数倍，或因更高优先级Surface、节电等不切到请求速率；应监听实际显示变化。——[Android Frame rate](https://developer.android.com/media/optimize/performance/frame-rate)
- 固定commit `488dbbd559acd24f62da0add3182b9c953782cfe` 的Java端 `LorieView.sendWindowChange()` 读取 `getDisplay().getRefreshRate()`、取整后发往native，display缺失时用30。在直接下载的该文件中，唯一普通Java调用点是布局/尺寸更新后的 `if (!dimensionsFrozen) sendWindowChange()`。——[固定commit LorieView.java](https://raw.githubusercontent.com/termux/termux-x11/488dbbd559acd24f62da0add3182b9c953782cfe/lorie/src/main/java/com/termux/x11/LorieView.java)
- 同commit的 `MainActivity.java` 与 `LorieView.java` 未发现 `DisplayListener`、`onDisplayChanged` 或 `registerRefreshRate` 注册。native收到配置后更新root报告的framerate；Present MSC又由redraw路径推进。它们都不是SurfaceFlinger实际呈现计数。——[MainActivity.java](https://raw.githubusercontent.com/termux/termux-x11/488dbbd559acd24f62da0add3182b9c953782cfe/lorie/src/main/java/com/termux/x11/MainActivity.java)、[InitOutput.c](https://raw.githubusercontent.com/termux/termux-x11/488dbbd559acd24f62da0add3182b9c953782cfe/lorie/src/main/cpp/lorie/InitOutput.c)
- 本轮baseline trace的320个 `DelayBasedBeginFrameSource::OnTimerTick` 报告interval为10.751–13.932ms，中位12.608ms；实际事件间距中位12.721ms、P95 56.754ms、最长79.467ms。同期156次 `FireAnimationFrame` 覆盖约7.975秒。**这个追踪不呈现一个简单的固定33.3ms BeginFrame上限，且不是屏幕“79Hz”的证据**。追踪开销也不能混进此前无追踪的25–32rAF基准。——[现场baseline原始追踪](C:/Users/scisa/AppData/Local/Temp/y900-web3d-20261118/3-baseline-trace.json)
- 现场先前只有另一轮任务中的静置30Hz、运动结束60Hz与Xrandr约120Hz快照；这不是此次Web3D期间的同步记录。——[设备兼容记录](../../skills/termux/references/desktop-compatibility.md)

### Inferences

- 若Android只切刷新模式、不改窗口尺寸且未触发上述Java调用，X11可能保留旧的reported refresh值；当前源码足以支持“可能脱节”，还不能证明本机已经走到此状态。需要同时观察物理mode、X11 Present节拍与Chromium计时，不能只读取任意一层。
- 当前应把“自适应造成低档/节拍失配”和“图形提交阻塞导致来不及生产”并列。12.6ms的估计interval与长间隙、较少rAF并存，也符合后者，尚不能据此排除前者。
- **第一优先实验：自动A → 临时实际60Hz B → 恢复自动A。先不测120Hz。** 60Hz已经足以判别相对Android Chrome约60的差距，120会增加呈现需求、调度和功耗变量；只有实际60条件下已接近60，再研究120才有价值。
- 实验前保存 `Settings.System` 中 `min_refresh_rate`、`peak_refresh_rate` 的**存在状态和原始字符串**，同时记录当前ROM界面的自动/固定选项；若原键不存在，恢复应删除该键，不能写入字符串 `null`。先准备恢复步骤，再用短时测试和 `finally` 精确恢复，退出后回读核对。连接中断则先停止采样，重连后的第一步恢复设置，不能留下永久锁定。
- B阶段只用系统已有的正式设置或已授权ADB通道临时设60；保持3840×2560、原画质rootNum1024、画布1920×1152、DPR2、同一动画阶段、原GPU及Picom/mailbox。**必须验证实际active mode保持60且分辨率未变**。若系统/ROM按应用策略继续30或120，仅settings回显60不算有效B阶段；不要据无效实验否定刷新率假设，也不为实验改ROM数据库、关闭全局节电或授予新系统权限。
- 每阶段4秒预热、至少10秒采样、重复三轮；使用相同观察开销。把同一单调时钟窗口内的以下证据对齐：①Android active mode/当前vsync周期与可用的显示策略votes，②精确Termux:X11 Surface图层的有效actualPresent时间戳，③Xrandr报告值和Chromium BeginFrame interval/rAF间隔，④网页实际像素运动及静态区域异常。SurfaceFlinger短历史须滚动采集、去重、裁剪到完整窗口，排除0与未完成时间戳，不能再拿最后一秒尾样本充当全程。
- 如果固定实际60使rAF及实际运动同时稳定接近60、恢复自动又重复掉到原水平，则自适应/按应用策略是强因果线索，可进一步修复应用帧率hint或采用用户可选的按应用60策略。若实际60始终成立而仍25–32，排除“仅物理屏幕30Hz上限”这个单因解释，继续查提交/拷贝/同步。若只有rAF升而外部画面不动、白屏、闪动、撕裂或context loss，则拒绝该候选。

### Gaps

- 尚无本次Web3D同窗、完整时段的actual mode与actualPresent联合记录；现阶段不能回答“就是自适应刷新率造成的”。
- ZUI本机按应用策略的优先级与min/peak实效没有取证。AOSP描述平台通用机制，不足以证明该ROM允许仅靠两键锁定。
- Perfetto FrameTimeline官方文档仍提示SurfaceView支持限制；Termux:X11正使用SurfaceView，因此不能依赖缺失的应用FrameTimeline track作负面证据。应同时用可用的SurfaceFlinger图层呈现数据与外部图像。——[Perfetto FrameTimeline](https://perfetto.dev/docs/data-sources/frametimeline)

## X11 合成和缓冲交接还可能损失在哪里

### Takeaway

应用WebGL硬件化不等于整个桌面的每次合成均在GPU完成。当前最有价值的呈现诊断是确认buffer类型、copy/flip及合成参与程度，再做隔离对照；不应直接开启全局unredirect或越过Turnip保护分支。

### Cited Findings

- 固定commit的DDX同时注册DRI3/Present和EXA；普通Solid/Copy/Composite准备回调拒绝加速。`loriePresentFlip()`要求root同尺寸，且默认拒绝已导入FD buffer，注释明确关联Turnip异常；`TERMUX_X11_FORCE_FLIP=1`仅越过该保护条件。——[InitOutput.c](https://raw.githubusercontent.com/termux/termux-x11/488dbbd559acd24f62da0add3182b9c953782cfe/lorie/src/main/cpp/lorie/InitOutput.c)
- DDX缓冲可经CPU访问，AHardwareBuffer类型的lock/unlock会调用Android缓冲接口；可采样AHB使用EGLImage，而FD内存路径需要纹理上传。——[buffer.c](https://raw.githubusercontent.com/termux/termux-x11/488dbbd559acd24f62da0add3182b9c953782cfe/lorie/src/main/cpp/lorie/buffer.c)
- renderer在root锁保护下绘制，并等待GPU fence后归还Xserver；交换后还做小绘制与fence等待准备下一buffer。其新实现也包含legacy模式按损坏行上传；这并不证明本机开启了legacy。——[renderer.cpp](https://raw.githubusercontent.com/termux/termux-x11/488dbbd559acd24f62da0add3182b9c953782cfe/lorie/src/main/cpp/lorie/renderer.cpp)
- Picom12.5手册明确：xrender经XRender渲染；关闭damage会重画全屏；unredirect会取消**整个screen**的重定向，规则只是决定哪个窗口触发，切换有闪动风险。——[Picom12.5手册](https://raw.githubusercontent.com/yshui/picom/v12.5/man/picom.1.adoc)
- Android fence用于跨生产者/消费者表达缓冲依赖，CPU等待、GPU等待和buffer释放不是同一种事件。长墙钟阶段不能自动等同GPU执行了同样时长。——[AOSP synchronization framework](https://source.android.com/docs/core/graphics/sync)

### Inferences

- Picom xrender仍可能承担像素合成/读写成本；CPU访问或交接又可能反压Chromium。反过来，Chromium中30ms的FinishPaint不能单凭名称归因Picom，尤其同帧已打点的BeginAccessImages很短；需要跨线程/跨进程时间证据。
- 画布相同只控制网页offscreen负载，不完全控制最终物理窗口、整窗图层面积与桌面拷贝。下一轮可保持网页canvas不变，仅改变**自建诊断窗口**物理面积；若成本随窗口面积变化而非粒子数变化，支持呈现/合成带宽因素。这是诊断，不将降低日常分辨率当修复。
- 第二优先：在独立测试显示/独立窗口，固定同一renderer和相同窗口尺寸，对照Picom xrender参与与不参与，观察rAF、Xserver/Picom线程CPU和实际画面。不得把“单个窗口匹配的unredir规则”描述成“只关闭这一个窗口合成”；它实际影响screen。原桌面的 `unredir-if-possible=false` 保持。
- `TERMUX_X11_FORCE_FLIP` 属于**Xserver进程的环境**，不是Chromium flag，也不能靠给新Chromium子进程加变量来热改现有server。通常须另起server或重启server，当前用户桌面不能因此中断。先在不改全局配置的隔离显示收集 `TERMUX_X11_DEBUG` buffer导入类型、Present copy/flip路径和fence时序，确认是否命中保护条件，再决定是否有必要研究它。若已安装APK/native支持官方tagged多显示，可研究自有`:2`及独立tag；必须先核对版本、空闲display、资源所有权与关闭方法，不能直接照抄命令启动。——[Termux:X11多显示文档](https://github.com/termux/termux-x11#running-multiple-displays-as-separate-windows)
- 强制flip是越过已知异常保护的实验，源码注释没有说明具体坏因，不能声称它必然安全或必然解决帧率。若试验发生破图、颜色/方向错误、撕裂、闪动、丢上下文、buffer复用异常或只有内部计数提升，立即拒绝、正常关闭自有显示并核对原桌面仍正常。
- 已失败的GLX白屏、EGL黑屏不能因为更高内部计数重新采纳；不启用导致过xfdesktop BadAccess的MIT-SHM，也不把关闭damage当提速默认方案。

### Gaps

- 缺本机当前帧实际导入buffer类型、Present完成mode、CPU读写/fence耗时与最终SF层时序。源码中有FD拒绝分支不等于已经证明Chromium命中它。
- 未定位一个已验证适用于这台设备、可直接采用的Xserver合成修复补丁；当前commit本身是heartbeat修复，不是WebGL提速证明。——[488dbbd提交](https://github.com/termux/termux-x11/commit/488dbbd559acd24f62da0add3182b9c953782cfe)

## Android 调度与版本对应应如何排除

### Takeaway

Termux与Termux:X11不同UID确有平台级调度差异的可能，但现有“允许0–7核”或CPU总量不能决定结论。优先采集可运行等待、CPU频率和同步阻塞；共享UID迁移作为后续独立方案，不能替代证据或直接覆盖现有安装。

### Cited Findings

- Termux:X11官方明确指出独立Termux在X11前台时可能受后台CPU调度影响；sharedUid APK只配GitHub签名Termux，不能与F-Droid/Play签名混用；APK与native配套包都须安装。——[Termux:X11官方README](https://github.com/termux/termux-x11#avoiding-slowdowns)
- Perfetto调度数据可区分何时在核上运行、为何被移走、何时已可运行但还没得到CPU；`sched_switch`与` sched_waking`联合用于定位调度等待。——[Perfetto CPU scheduling](https://perfetto.dev/docs/data-sources/cpu-scheduling)
- CPU频率的ftrace只记录变化，短样本可能没有初始频率；官方建议结合sysfs周期采样，避免将空轨迹解释为低频或不变频。——[Perfetto CPU frequency](https://perfetto.dev/docs/data-sources/cpu-freq)
- Android正式System Tracing及Perfetto可用于系统性能记录，不要求先更换应用签名。——[Android系统追踪](https://developer.android.com/topic/performance/tracing/on-device)

### Inferences

- 第三优先：同一固定60Hz/画质/尺寸条件，采集Chromium GPU与renderer、Xserver主线程、LorieRenderer、Picom的scheduler状态、CPU频率和图形等待；保持观察方法一致，避免录屏编码负载与高频dumpsys成为新的瓶颈。大量runnable而不能上核支持调度因素；大量sleep/fence等待则优先图形同步；两者可共存。
- 不以taskset绑大核、全局关闭后台策略或修改优先级作为第一步，它们改变功耗与调度而不能区分瓶颈。若ZUI提供已有正式按应用设置，可在记录原值后作单变量对照；没有事实证据前不改。
- 不把sharedUid APK覆盖现有F-Droid安装。若调度证据明确后考虑迁移，须另做备份、Termux/API/Boot/Widget签名一致性与会话恢复规划；它是较大迁移，不是浏览器修复flag。
- 本轮只研究，没有连接/操作平板、改变刷新率、安装驱动或新增测试实例。以上实验是待执行的判别方案，不是验证通过结果。

### Gaps

- `488dbbd...` 来自已有维护记录所定位的源码。本轮可核对该上游commit及内容，却未取得现场APK、native CLI/库摘要、构建标识、运行映射与该commit完整闭环，因此**不把它称为已安装二进制的可复现构建证明**。在应用任何版本相关修复前先做此核对；不要只按nightly名字或短hash匹配。
- 同一固定raw URL的web提取曾给出与主机直接下载不同的文件行数，关键机制一致但精确行号不可靠。本轮将主机直接下载的四个固定commit文件与SHA256清单保存于私有证据 `C:/Users/scisa/AppData/Local/Temp/y900-web3d-20261118/termux-x11-research-source/`，便于复核；这些源文件摘要也不是安装包摘要。
- 缺本机本轮scheduler/frequency完整记录。当前已测硬件renderer与 `TracerPid=0` 排除了Chromium本体受PRoot系统调用转换的解释，却不能排除同UID其他后台调度、Xserver或驱动交接开销。——[现场对照摘要](C:/Users/scisa/AppData/Local/Temp/y900-web3d-20261118/comparison-summary.json)
