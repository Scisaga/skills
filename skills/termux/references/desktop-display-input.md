# 显示、输入、主题与字体

## 分辨率与清晰度

先区分 X11 渲染分辨率、Android 窗口尺寸、GTK 窗口缩放、逻辑字体 DPI，以及应用自身缩放。优先 native 自适应渲染，再选择合适字号；不要将低分辨率画面整体拉伸来放大界面。

```bash
# native Termux，先查看实际键名和值
termux-x11-preference list
termux-x11-preference displayResolutionMode:native
# guest，先加载当前会话环境
. /data/data/com.termux/files/home/.local/state/tablet-desktop/session.env
xrandr --current
xfconf-query -c xsettings -lv
```

高密度平板预设为 GTK scale=2、逻辑 DPI=96、CJK 基础字号 11、编辑器字号 14、光标 48。它是本次设备上有效的组合，其他屏幕应重新确认。不要把 DPI 与窗口缩放同时翻倍。验证文字、细线与截图原始像素；缩小后的截图本身会模糊。

鼠标模式下指针过小，先检查 `/Gtk/CursorThemeName` 是否为空，而非只加大 size。设置 `Adwaita` 与 `CursorThemeSize=48`，核对根窗口 `RESOURCE_MANAGER` 的 `Xcursor.theme/size`。native 应用也必须能找到主题：本实现使用 guest 图标目录，并在 native `~/.icons/Adwaita` 创建指向 guest 主题的链接；应用包装器使用同一配置。实际 XFixes 游标尺寸优于设置值作为验收依据；先调用 QueryVersion，再 GetCursorImage。Electron 可能缓存启动环境，改尺寸后需正常重开 Code，保留工作区和保存提示。本次用户认为 64 偏大，最终浏览器与 Code 都实测 48×48；不要将临时 64 固化为设备偏好。

灰色边框/黑边也可能来自固定宽高比、Android 非全屏/分屏、系统栏或窗口比例。检查实际根窗口与可用视口后再判断。

## 鼠标移动与实际刷新率

先区分指针在整个 Xfce 中不顺、特定应用重绘慢，以及 Android 系统中也不顺；记录连接类型和当前输入模式。保留用户的 Trackpad/Direct touch、指针速度与加速度，不靠一起改动这些选项来猜原因。

`xrandr` 的模式频率不代表 Android 面板当时的实际刷新率。先查该 ROM 的 `cmd display help`，再读取活动模式和系统策略；Android 17 的一次实测中，Xrandr 显示约 120Hz，实际面板却为 30～60Hz。

自动策略下分别记录静置、症状发生期间和结束后的活动模式、最终 DisplayInfo 与 SurfaceFlinger 调度；一次 60Hz 快照不能写成持续固定 60Hz。`dumpsys display` 的原始 `mOverrideDisplayInfo` 对象也不能直接归给某个应用：先核对最终有效字段、UID 覆盖与实际呈现。AOSP 的 [WM override 合并字段](https://android.googlesource.com/platform/frameworks/base/+/refs/heads/main/services/core/java/com/android/server/wm/utils/DisplayInfoOverrides.java) 不包含 modeId、renderFrameRate 或 refreshRateOverride；厂商分支须另核实，不凭对象中残留的 30 推断应用被锁定 30 FPS。声明模式、物理活动模式和实际新帧间隔分别报告，呈现取证见 [验收参考](desktop-verification.md#窗口呈现时间戳与短时移动取证)。

```bash
# 主机 ADB；部分 ROM 不支持 get-active-mode，须明确记录不可用
adb -s SERIAL shell cmd display get-active-mode 0
adb -s SERIAL shell settings get system min_refresh_rate
adb -s SERIAL shell settings get system peak_refresh_rate
```

临时提高最低刷新率之前保存原值、设置有期限的自动恢复，并回读活动模式证明生效；`set-user-preferred-display-mode` 请求成功也可能仍为 60Hz。若原值是 `null`，恢复应删除该键，而非写入字符串 `null`。测试中保持应用负载和输入路径不变，分别验证指针与应用拖动。最低刷新率属于全局屏幕策略，用户选择保留后再持久化，不把它写成所有设备的安装默认值；提高刷新率不算续航验收。测试结束清理恢复任务，再断开 ADB。

若 Android 顺畅但 Xfce 仍顿，先检查指定鼠标的 EventHub 移动包间隔，再查 X11 转发与光标呈现；停手或切换窗口也会产生长间隔，不能直接计为无线丢包。需要记录时只保留该鼠标 REL_X/REL_Y 包的时间统计，不采集键盘或保存输入坐标。

可单独试 Termux:X11 标准 `pointerCapture:true`，比较鼠标绝对坐标与相对移动路径，保持触屏模式及其他速度参数。配置保存后须在 X11 中点击以激活，并从 Android `dumpsys input` 确认 `Pointer Capture: RELATIVE` 及目标 X11 窗口；仅保存首选项不算路径已切换。验证移动、左右键、滚轮、窗口拖动和切回 Android；原先为 false 且无收益时恢复 false。采用限时恢复和明确的用户反馈，不修改输入处理源码或叠加事件注入。

“移动顿”还可能实际指向微操和加速。[已核对版本的 Termux:X11 捕获实现](https://github.com/termux/termux-x11/blob/488dbbd559acd24f62da0add3182b9c953782cfe/lorie/src/main/java/com/termux/x11/input/TouchInputHandler.java) 会将相对移动乘以 `capturedPointerSpeedFactor / 100 × display density`，再交给 X11；同时读取 `xinput get-feedbacks 'Lorie mouse'`。Y900 的 density=2.5，捕获倍率 100 对应 2.5 倍固定增益；旧 X11 反馈值为 2∶1，但设置值本身不能证明实测又放大一次，更不能直接归因。应比较 XInput2 原始与处理后位移。不要仅提高刷新率就宣布精细定位已修复，也不要把捕获开关保存成功视为微操验收。

需要线性参照时，可按实测 density 计算捕获倍率，并仅对对应的 X11 鼠标设置 1∶1 反馈，保留原阈值；例如该设备的 40% 抵消 2.5 倍密度放大。这个数是校准参照，不能作为其他设备默认值或用户最终速度。验收窄分隔条命中、文字选区、慢速定位与跨屏移动距离；“拖不动”先区分按键拖拽失效和整体移动过慢。若只嫌整体速度慢，调整一次线性倍率，不重新叠加加速曲线。确认保留后，可使用 [Xfce 标准设备设置](https://github.com/xfce-mirror/xfce4-settings/blob/xfce4-settings-4.20.1/xfsettingsd/pointers.c) 的 `/Lorie_mouse/Acceleration` 持久化 `double 1.0`，并回读实际 feedback；设备名按本机转换，不能依赖固定 ID。原属性不存在时记录这一点，回退只删除新增属性并恢复原 feedback，不覆盖整个 pointers 通道。触控板也可能使用同一虚拟鼠标，须一并复验。

若增速仍慢且低速定位变粗，停止继续调倍率。确认实际操作设备、Android 相对输入节点、屏幕状态和当前捕获窗口；蓝牙断开或节点换号时重新识别，零样本不能算丢事件。固定配置，只统计指定鼠标的相对位移和时间，对照 EventHub 与 XInput2 增量；非零报告间隔不是硬件轮询率或呈现 FPS。完整累计位移能对应、报告数减少时，先查历史事件合批，不能把条目减少直接报成丢包。

采样必须记录设备端读取器的 PID、UID、启动 ticks、可执行文件与精确参数，并在正常结束、断连和异常时于设备端回收。仅终止主机 `adb` 客户端或外层 `timeout` 可能留下孤儿 `getevent`；设备节点移除后还可能空转占用 CPU。检查零残留和 CPU 状态后再交付；带有这些观测负载的时间数据不得作为无负载性能基准。回收只针对身份与本轮启动记录匹配的诊断进程，不能按进程名批量杀进程。

Android 原生鼠标路径通过 `pointerCapture=false` 转发系统绝对位置，绕过捕获分支的固定密度倍率。需要验证时只切这一项，保留其余设置并比较慢速定位和正常移动。该路径按上游实现不发送 XI_RawMotion；需要额外取证时可只订阅 XRecord 的 MotionNotify，将绝对位置在内存中换成相对增量，不记录键盘、按钮值或屏幕内容。没有后置有效样本时，只报告用户确认的操作改善，不声称事件频率、最小像素步长或 GPU 帧率提高。

## GTK 与应用兼容

已验证的保守兼容参数：`GDK_GL=disable LIBGL_ALWAYS_INDIRECT=1 NO_AT_BRIDGE=1`。部分设备在缺少这些参数时连 GTK 命令行控制入口也可能卡住；从 SSH 运行 `xfce4-panel --restart` 等命令时同样注意环境。保留故障证据后仅终止自己启动的卡住诊断进程，不清空全部 PRoot。

Greybird-dark + Papirus-Dark 提供一致深色界面；安装 `librsvg2-common` 后再判断 SVG 图标是否失效。`assets/desktop/theme/xfwm4` 保存触屏标题栏主题；标题按钮有独立尺寸，不通过大范围 GTK CSS 修改全局字体。首次部署后检查完整标题、关闭/最大化按钮、LibreOffice 字体下拉菜单。

自定义 CSS 限定菜单与面板按钮。避免对所有 menu/button/combobox 设置巨大最小高度，否则 LibreOffice 的字体列表等控件可能裁切。

### 窗口边框、拖动重绘与合成

先读取窗口 `_NET_FRAME_EXTENTS`、`_GTK_FRAME_EXTENTS`、深度、实际 compositor selection owner、主题素材尺寸和 `use_compositing`。前者为 WM 框架范围，GTK 属性描述客户端装饰区域；四边 10 不等于可见描边厚 10 像素，也不证明透明阴影正在绘制。无合成时 Chromium 可主动选择实色客户端装饰，不能一律称为“透明阴影变黑”。Chrome/Code 的客户端装饰与 Xfwm 框架分别判断；Xfwm 原生窗口需要细边框时可先试发行版自带 Greybird，高密度屏幕检查标题裁切，`Greybird-dark-accessibility` 是已安装时可选的较大标题栏变体。保留标题栏按钮、调整大小和原有字体。

Chromium 浮动窗口有多层粗边框时，先查看 `chrome://settings/appearance` 的 Theme。若当前是 GTK，可通过官方 **Use Classic** 与原主题做单变量对照，保留一体式标签栏；不修改 GPU、Xfce 主题或窗口协议属性。Chromium 157 的 `extensions.theme.system_theme` 为 Default/Classic=0、GTK=1、Qt=2；仅用于回读，已有实例通过实际 UI 切换，不直接改运行中的 Preferences。[对应版本设置源码](https://chromium.googlesource.com/chromium/src/+/refs/tags/157.0.8103.50/chrome/browser/resources/settings/appearance_page/appearance_page.ts)。Classic 可消除 GTK 的分层粗框，但默认绘制仍有标准边缘/缩放区域和细描边，不承诺浮动窗口零边框；见 [默认框架绘制](https://chromium.googlesource.com/chromium/src/+/refs/tags/157.0.8103.50/ui/views/window/frame_view_utils_linux.cc)。比较同一尺寸的浮动窗口与最大化效果，由用户选择保留；不把单台设备的主题选择变成安装默认。

只放大 Xfwm 左上角菜单和右上角按钮时，使用[上游支持的用户主题目录](https://wiki.xfce.org/howto/xfwm4_theme)，从当前主题派生 `~/.themes/<name>/xfwm4`，保留发行版原文件。小米平板 7 按用户要求将按钮由 22×22 增至 35×35（约 +60%），派生主题为 `Greybird-dark-buttons160`；各按钮的全部状态同步调整，标题素材由 34 增至 47 像素以容纳按钮，侧边和底边仍为 3 像素，字体保持原值。通过 `xfconf-query` 切换主题并同步设备 profile 的 `titlebar_theme`，核对实际按钮子窗口的点击区域和标题是否裁切。热切换后若顶端窗口被面板遮住，只将受影响窗口移回可用区域；不增加常驻布局修补。该设备偏好不作为其他设备的默认值。

Chromium 标签栏空白处右键的 **Use system title bar and borders** 会增加一行独立系统标题栏；用户需要标签页与窗口按钮同一行时，不能用它规避客户端厚边缘。[对应版本实现](https://chromium.googlesource.com/chromium/src/+/refs/tags/157.0.8103.50/chrome/browser/ui/views/frame/browser_native_widget_aura_linux.cc) 中，`browser.custom_chrome_frame=true` 使用浏览器自身装饰，`false` 使用窗口管理器装饰。它与 GTK/Classic 主题是两项独立选择。小米平板 7 曾否决系统标题栏方案；该设备与后续 Y900 的外观结果分别见兼容记录。未找到独立且受支持的零边框选项时保留限制，不新增注入、伪造合成支持或修改窗口协议属性来隐藏问题。

外观选项通过实际菜单切换，核对 profile 保存值、屏幕和窗口行为；已有运行实例不要直接改 Preferences 文件，避免被浏览器内存状态覆盖。运行中切换后 `_GTK_FRAME_EXTENTS` 可能暂留旧值，不能只看该属性判失败，应结合 `_NET_FRAME_EXTENTS` 与屏幕。不把设备的外观选择固化为全局默认，也不把最大化后的效果视为浮动窗口边缘已修复。

应用 GPU 和窗口合成是不同路径。未合成的 X11 在移动前景窗口时会向露出的背景窗口发送 Expose，造成重绘；用自建窗口、相同轨迹和尺寸比较重绘次数、native CPU 与呈现时间戳，再单独复测浏览器固定 WebGL 负载。主题变薄不等于消除重绘。

先用 `window_probe.py inspect` 或 `desktop_verify.py window-report` 检查运行态：实际 Xfwm 设置、`_NET_WM_CM_S<n>` owner、底栏辅助的 selection、进程身份、状态文件与触发窗实际位置。仅存在两个进程不证明冲突；辅助已让出手动重定向时不能报为接管冲突。状态文件只是证据之一，需排除陈旧 PID 和失效窗口。安装时禁用自启动也不代表旧实例已退出。

需要验证辅助是否引起重绘时，显式运行 [受控窗口对照](desktop-verification.md#窗口状态与重绘对照)：保持合成、驱动、主题、输入和窗口轨迹不变，依次测量辅助运行、停止、恢复，每组重复采集。Expose 事件数与最后一个 Expose 后的重绘完成次数分开计数；它们都不是 FPS。对照不支持某个因果时停止沿该假设修改；不能把本机结果扩展为所有应用或其他设备的性能结论。

启用整桌面合成前，先正常停止身份已核对的 `tablet-panel-edge` 并禁用其自启动，释放它的手动 Composite 重定向。仅在合成器启动后等待辅助程序让出资源存在竞争，实机出现过 `Composite BadAccess` 导致 Xfwm 退出。安装器在 `window_compositing=true` 时禁用此辅助；透明底栏 CSS 保留。回退为无合成时恢复原自启动和底栏位置。不要用窗口管理器重启循环掩盖错误。

“有背景重绘”与“接管冲突”分别取证。前者在正常未合成 X11 中也会发生；后者需结合活动合成器、尚未释放的手动重定向及对应错误日志判断。`MIT-SHM BadAccess` 是另一条共享内存故障路径，不能因错误名相同归入 Composite 冲突。

Xfwm 的 `xpresent`/`glx` 是呈现与同步选择，不能仅凭 GLX 名称宣称全部合成都由 GPU 完成；[其实现](https://raw.githubusercontent.com/xfce-mirror/xfwm4/xfwm4-4.20.0/src/compositor.c) 仍调用 XRender 绘制。测试其他发行版合成器时也要验证可见画面、窗口管理器重入及应用性能：黑屏样本即使有高频呈现时间戳也不计为成功。无有效收益或出现回归时撤回测试，不继续增加事件或预加载注入。

VLC 的 Qt 界面单独按 profile 的 `scale` 设置 `QT_SCALE_FACTOR`，同时关闭 Qt 自动倍率，避免高分辨率屏幕上控件过小或重复缩放。软件兼容入口使用 `--avcodec-hw=none --vout=xcb_x11`，不让视频输出依赖尚未配置的 OpenGL/Vulkan 驱动；调整后应正常退出已有 VLC，再实测画面和播放进度。

## VS Code 与主机字体一致

先读取主机 VS Code 的 editor.fontFamily/fontSize/fontLigatures 等实际设置，再在 guest 用 `fc-match` 确认字体存在。只复制用户有权使用的字体到 guest `~/.local/share/fonts/`，执行 `fc-cache -f`；不把主机字体文件打包进技能。随后合并相关设置，保留其他 Code 配置和账户。

本次偏好为 Consolas 14 与 editor 水平/垂直 scrollbarSize=6 逻辑像素。技能预设使用可安装的 DejaVu Sans Mono；用户要求匹配主机时再切换。

滚动条先确认属于编辑区、终端、扩展 Webview 还是 GTK 应用，分别定位；不要未经验证就修改扩展源码/CSS。缩放过大与滚动条宽度是独立问题。

## 实体键盘与输入法

- 有实体键盘时可隐藏 Termux extra-keys、X11 附加键栏，并在 Android 中关闭“连接实体键盘时显示屏幕键盘”。只改 Xfce 设置无法控制 Android 输入法弹出。
- 先确认键盘真能输入，再检查 Gboard 当前语言。中文拼音可能已包含 Alphabet，无需再重复添加英语布局。
- Gboard 的单独 Shift 切换中英文在本次设备验证有效；Ctrl+Space、Shift+Space 未必在不同输入法版本/物理键盘模式中可用。按实际 Gboard“Shift 切换中英文”设置核对，不盲目在 Xfce 抢占同名快捷键。
- 软件键盘、系统输入法与 X11 键盘转发是三层；先记录症状属于哪层再改设置。

ZUI 若在蓝牙键盘打字时自动进入“无限工作台”，先记录相关设置及手动入口状态。当前 ROM 的自动进入项是 `settings get system keyboard_enter_desktop_mode`，仅将该项设为 `0`。同属 system 的 `zui_ov_desktop_mode` 是工作台状态；将其一起清零会影响手动进入，不作为禁用自动切换的通用步骤。不同 ROM 先查实际键名及命名空间；global/secure 读到 null 不等于设置已丢失。验收必须包含真实键盘输入不再切换、手动按钮仍可进入；本次两项均经用户确认。

## 触屏模式与入口

X11 提供三种输入模式：Direct touch（原生触屏）、Simulated touchscreen（模拟鼠标的兼容触屏）和 Trackpad（触控板）。需要单指拖动内容滚动时先验证 Direct touch，它把真实触摸事件交给应用。Chromium 和 GTK ScrolledWindow 已实测单指滚动，Xfwm 标题栏仍能单指拖动；不保证所有桌面应用都支持同样的触控手势。

桌面、应用菜单、底部栏、顶部栏的主按钮在原生触屏和触控板之间切换，四份标签/图标同步。模拟触屏仍可通过 X11 设置或 `tablet-touch-toggle touch` 选择；支持 Desktop Actions 的启动器也会显示三个固定模式动作。不要假定所有 Xfce 面板版本都把 Desktop Actions 显示在右键菜单中。

```bash
# guest；请求通过私有 Unix socket 交给 native 服务
tablet-touch-toggle status --quiet
tablet-touch-toggle toggle
tablet-touch-toggle direct    # Direct touch，真实触摸事件
tablet-touch-toggle touch     # 保留旧接口：Simulated touchscreen
tablet-touch-toggle trackpad
```

服务只允许 status/toggle/direct/touch/trackpad 与枚举的生命周期动作。启动时默认保留已有模式，不能每次强制重置。用隔离测试页记录 pointerType、touchmove 与 scrollY，并用真实 Android touchscreen 事件验证；鼠标滚轮或脚本 scrollTo 不算单指滚动验证。

### Xfce 桌面和文件管理器的长按右键

Direct touch 不自动提供鼠标右键；[上游说明](https://github.com/termux/termux-x11/issues/670) 将触摸处理交给应用。不要为此全局改成模拟触屏，或全局设置 `GDK_CORE_DEVICE_EVENTS=1` 而损失应用的原生滚动。

有此需求时可启用 `touch_long_press=true`，调节 `touch_long_press_ms`（400–3000，默认 700）和 `touch_long_press_move_px`（4–80，默认 24 个物理像素）。小米平板 7 本次选择 500ms。安装器按需安装 gcc、libc6-dev、libx11-dev、libxi-dev、libxtst-dev 并从随附源码编译；不分发主机架构二进制。

`tablet-touch-longpress` 只观察 XInput2 原始触摸，不抓取键盘，不抢占触摸事件。单指静止达到阈值，松手后在 Xfdesktop/Thunar 中发出一次右键；移动、多指、窗口切换或旋转取消。Chromium/Code 等窗口不补偿，保持应用自身的触摸处理。显示内 selection 保证单实例，无触摸时阻塞等待，不高频轮询。

Xfce 桌面/面板的单击、双击还需单独验收。启用该适配时，受管启动项通过 `tablet-xfce-pointer` 启动，只对这两个组件设置 GTK 标准的 `GDK_CORE_DEVICE_EVENTS=1`；应用和 GPU 包装器清除此变量，保留应用原生触摸。此路径无需预加载输入库。不要同时再合成左键，否则会把单击误识别成双击。自定义 Xfce 启动项不能按固定编号覆盖，安装器从已有配置/发行版默认项识别组件；未知会话先检查。已有保存会话也应核对实际启动命令。

验收同时覆盖：菜单打开和菜单项、单击仅选中、双击打开、图标/窗口拖动、空白与文件右键、多指取消、浏览器单指滚动、切换触控板后鼠标点击，以及再次进入会话。仅看到右键菜单不能宣布输入修复完成。热重启壳层后可用一次 `xrefresh` 确认重绘，不将高频刷新当作修复。

GTK 下拉框必须包含带 Motion 更新的真实点按。`adb input tap` 的瞬时按下/抬起可能通过，而 80–650ms 的静止 `swipe` 和实机手指会使菜单立刻收回。检查选择值、控件回显及桌面重绘，不能只看菜单可选。用户允许暂缓时，将该项保留为未解决；不以事件注入掩盖失败。黑桌面先查桌面进程和 X11 错误，`MIT-SHM BadAccess` 的处理见 GPU 参考。

## 自动隐藏底栏的横线

自动隐藏面板会保留触发边缘。若灰色细横线出现在页面中部，用 `xwininfo -root -tree`、`xprop -id WINDOW WM_CLASS _NET_WM_WINDOW_TYPE` 确认归属；可能是错位的 xfce4-panel 小高度 dock 窗口，而非浏览器内容。

X11 自适应尺寸变化后，检查触发区是否仍停在旧坐标；不要仅凭外观断言 GPU 故障。先核对 xrandr 输出名，再将自有 panel-2 绑定该输出并刷新面板：

```bash
bash skills/termux/scripts/run.sh repair-panel --profile /path/to/profile.json
```

绑定输出并刷新只能修复当次位置，分辨率变化后仍可能复发。`dock_hide_indicator=true` 时，XDG autostart 启动 `tablet-panel-edge`：监听 X11 窗口/屏幕事件，把自有薄 dock 触发窗放回当前底边，并仅重定向该触发窗的绘制，使它不可见、输入区域仍保留。它不轮询、不重启面板，也不开启整桌面合成。依赖 `python3-xlib` 由 guest 安装脚本安装；缺失时明确给出 apt 命令。

当前平板布局只有一个自动隐藏底栏。辅助程序同时核对 WM_CLASS、dock 类型、薄窗口尺寸、所属进程和父窗口；多个新候选不明确时不接管。移动必须通过 WM 客户端的 ConfigureRequest，直接移动 WM frame 会造成双方坐标缓存不一致，甚至反复触发配置事件。

单例使用显示内 selection；状态位于 `$XDG_RUNTIME_DIR/tablet-panel-edge.json`。Xfce 会话持有该进程，结束桌面后随会话回收；断开连接自动释放它自己的重定向。只有透明 CSS、但未开启合成时可能出现黑条，不能只凭 CSS 已写入就判定成功。可选回退为 `dock_hide_indicator=false`，正常退出后重新应用 profile。

保持 autohide-behavior=2；验证白底无横线、鼠标/手指底边呼出、移开后收起、模拟错位后自动纠正及空闲 CPU。面板可能有较慢的收起延迟，给它约两秒再判断。刷新面板不需要重启应用；不要用高频轮询反复刷新面板。

实现依据：[Xfce 官方面板主题](https://docs.xfce.org/xfce/xfce4-panel/theming)、[X11 Composite 协议](https://www.x.org/releases/X11R7.7/doc/compositeproto/compositeproto.txt)、[Termux:X11 官方输入模式](https://github.com/termux/termux-x11/blob/master/lorie/src/main/res/values/arrays.xml)。
