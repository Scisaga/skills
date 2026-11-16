# GPU 渲染与验收

设备结果按 [兼容记录](desktop-compatibility.md) 分开。可复用探针和失败退出的性能门禁见 [验收入口](desktop-verification.md#gpu-探针与性能门禁)；真实 renderer、有效绘制、同负载性能和日常入口分别取证。

## 分层证据与版本对应

| 层次 | 要读取的证据 | 不能据此推断 |
|---|---|---|
| 应用内部绘制 | 日常实例的 Graphics Feature Status、GL_VENDOR/GL_RENDERER/GL_VERSION，必要时真实 shader/pixel | 有 GPU 进程、参数或设备 FD 就代表所有功能硬件化 |
| Xserver 普通 2D 与缓冲交接 | 对应 DDX 的 Copy/Composite、DRI3/Present 路径；运动时 native CPU/线程与同步证据 | 应用 GPU 开启就保证整窗移动、背景露出重绘流畅 |
| Xfwm 整桌面合成 | 实际 selection owner、重定向与 XRender/输出实现；与底栏局部重定向分开 | `glx`/`xpresent` 名称就代表所有窗口混合都在 GPU 上 |
| X11 声明模式 | root 尺寸与 Xrandr 时序 | Android 此刻按同样频率呈现 |
| Android 最终呈现 | 症状期间活动模式、SurfaceFlinger 有效 actualPresent 时间戳及画面 | 均匀提交就代表每帧内容完整，或短尾样本证明全程无丢帧 |

同一日常 Chromium 的功能状态与真实 Adreno/ANGLE/Zink/Turnip renderer 相互印证，比启动参数更有力。页面的 Vulkan Disabled 描述浏览器内部功能，不否定 Zink 下层使用 Vulkan；Video Decode 软件也不等于 UI 软件合成。`MESA_VK_WSI_PRESENT_MODE=mailbox` 选择呈现方式，Code 的 `terminal.integrated.gpuAcceleration=off` 只改变终端渲染，均须按各自范围报告。某应用 `--status` 返回 0 但无 GPUFeatureStatus 时保留未知，不能用退出码或驱动映射补成完整硬件验收；进程 environ 已清空时，也不能从空输出断言没有设置相关变量。

Termux:X11 完整提交 `488dbbd559acd24f62da0add3182b9c953782cfe` 的 [EXA PrepareSolid/Copy/Composite](https://github.com/termux/termux-x11/blob/488dbbd559acd24f62da0add3182b9c953782cfe/lorie/src/main/cpp/lorie/InitOutput.c) 返回 false；进入这些普通请求的操作有软件回退路径，同时可与 DRI3 应用 GPU、最后 GLES 输出并存。不能扩展成“整个桌面全在 CPU”，也不能从源码推定本机拖窗已受 CPU 限制。Xfwm 普通混合使用 XRender，开启合成前须评估该 DDX 的实际路径，按显示参考先释放底栏 helper 重定向，再对照拖影和同负载浏览器性能。

查上游时先记录实际 APK/native CLI 版本、安装包摘要及运行映射，再用完整 commit/tag 核对源码。短 ref 缓存若与版本不符应排除；二进制特征吻合只支持实现一致性，不等于可复现构建校验。相似标题的 issue 不是根因或修复证明；确认相关提交是否已是安装版本的祖先、参数是否仍生效。独立光标 surface 的更新只针对纯指针移动时，不能承诺整窗拖动也改善。研究结论与现场事实、假设、已解决及未验证项分别记录。

## 后端与安装

先读取包装器、运行参数与实际渲染器。`--disable-gpu` 关闭 Chromium/Electron 硬件加速；只移除它可能退回 llvmpipe，不能当作成功。GPU 渲染不要求 Android Root，但不同 GPU/ROM 需要分别验证。

profile 的 `gpu_backend` 支持 `software`（通用兼容预设）、`virgl-android`（native GPU 服务）和 `freedreno-kgsl`（glibc 应用直接访问 Adreno KGSL）。VirGL 通过 guest Mesa virpipe 和私有 Unix socket 调用 Android GLES 驱动。直接 KGSL 路径见后文；两者均须先独立测试，再用于日常应用。

在已有 profile 中增加 `"gpu_backend": "virgl-android"`；仍可保留 `software_rendering: true` 以兼容 GTK。GPU 包装器会覆盖相关传输变量。不要仅把该布尔值改为 false 就宣称 GPU 已启用。

```bash
bash skills/termux/scripts/run.sh desktop-plan --profile /path/to/profile.json
# 保存并正常结束现有桌面后，安装器才允许变更运行文件
bash skills/termux/scripts/run.sh desktop-install --profile /path/to/profile.json --apply
desktop start
desktop status --json
```

安装器增加官方 native 包 `virglrenderer-android`、`~/.config/tablet-desktop/gpu.json` 和应用包装器。已有活动桌面的专门维护先备份，保留文档，正常重启需要换参数的应用；不为验证配置而强制结束整个桌面。

## 通路与兼容环境

```text
Chromium / VS Code → ANGLE → Debian Mesa virpipe
→ native VirGL server → Android GLES 驱动 → 设备 GPU
```

`tablet-gpu-run` 设置 `GALLIUM_DRIVER=virpipe`、`LIBGL_DRI3_DISABLE=1`、`LIBGL_ALWAYS_SOFTWARE=1`、`VTEST_SOCKET_NAME=/tmp/.tablet-desktop-gpu`，并清除继承的 `LIBGL_ALWAYS_INDIRECT`。此处 Mesa 的 software winsys 用于传输，实际渲染由 native 服务完成；须结合真实渲染器判断。`LIBGL_ALWAYS_SOFTWARE=1` 单独使用可能只是 CPU 渲染。

保留 `GDK_GL=disable` 和关闭 Xfwm 合成可规避某些设备的 GTK 故障，不妨碍应用自己通过 ANGLE 加速。Xfwm 合成开关不是所有应用的 GPU 开关。

服务使用 `--no-fork --multi-clients`，支持浏览器、编辑器及多个 GL 上下文同时工作，避免额外失管的 fork 子进程。必须验证并发应用。不要伪造 `MESA_GL_VERSION_OVERRIDE`/GLES 版本；先让 Chromium 自动选择 ANGLE 后端。实测强制 `--use-angle=gl` 反而可能回退软件。

## 服务与回退

原生 X11 与 PRoot 的 System V IPC 机制可能不一致；[Termux 上游问题](https://github.com/termux/proot/issues/271) 说明了 MIT-SHM 对两端共享内存机制的要求。若日志实际出现 `MIT-SHM BadAccess` 并导致 GTK/xfdesktop 退出，可在该设备 profile 设置 `x11_mitshm=false`，保存并正常结束桌面后重新启动，使 X11 使用标准 `-extension MIT-SHM`。默认保持原选择；不全局套用于已验证正常的设备。此选项不关闭 DRI3、Present 或应用 GPU 驱动，仍须回读扩展、重复壁纸重绘和实测 GPU 性能。不要用重启绘制进程的循环掩盖崩溃。

- 桌面控制器持有 GPU 服务，启动前检查依赖和 socket；重复返回复用实例。状态的 `gpu_server_alive` 只证明进程身份，硬件渲染另验。
- socket 为 0600，无新增 GPU TCP 监听。未知进程占用相同 socket 时报告错误，不抢占、不按进程名终止。
- 正常退出在 guest/X11 结束后回收已记录的服务；复核 UID/PID/创建 ticks/可执行文件。PID 复用不授权终止进程。控制器重启保留桌面和 GPU 身份记录。
- 软件回退入口为 `chromium-tablet-software`、`code-tablet-software`。先正常关闭同一应用，否则新请求可能交给旧实例。永久回退修改 profile 为 `software`，正常结束后重新应用。
- 异常先看 `~/.local/state/tablet-desktop/gpu.log`、状态和事件。确认后用 `desktop start` 恢复服务，再正常重开受影响应用。不全局 pkill，也不静默丢弃编辑。

## 验收

1. 独立配置启动测试应用，保留账户和默认 profile。临时调试端口只用于隔离测试进程，用完正常关闭并确认监听结束。
2. 主动读取日常实例 `chrome://gpu` 的 Canvas、Compositing、Rasterization、WebGL 和 GL_RENDERER 附近 vendor/version；可用普通查找/滚动时不让用户代查。保留原标签页、焦点和窗口几何，不为读页面给日常实例加调试端口。渲染器应含真实 GPU，例如 `virgl (Adreno …)`；llvmpipe、softpipe、SwiftShader 表示软件路径。实体键盘、输入法和主观手感仍需实机/用户验证。
3. 建立 WebGL 2 上下文，实际绘制并读取像素，检查 native 服务打开 GPU 设备。开关和图标本身不足以验收。
4. Chromium 与 VS Code 同时运行，分别核对渲染与窗口响应；测试窗口关闭后日常应用仍可绘制。桌面、菜单和面板入口都走相同包装器。
   已知低帧率必须在本次 GPU 配置中处理并复测，不能仅凭真实 renderer 宣告完成。对比固定画布、视口、缩放和画质，排除预热后采样至少 10 秒并重复；记录回调帧率及帧间隔，不能把空白页、失去上下文或隐藏页面的数据算作提升。若 PRoot 路径仍慢，验证 native Chromium 后再统一日常入口；保留兼容版与原 profile。
5. 重复返回不新增服务；正常结束回收自有资源。可先用独立 socket/状态验证资源清理，避免中断用户桌面；真实整桌面退出未执行时明确记录。
6. 从 native `/proc/PID/stat` 采样 CPU 增量，区分启动、静置、症状期间与持续空转；必要时分开 Xserver 主线程和 renderer 线程，线程已计入进程，不重复相加。100% 表示一核，短样本低 CPU 不能排除带宽、锁或 fence 等待。PRoot 静态 `/proc/stat` 会让 guest 工具失真，VS Code `--status` 也可能因此除零，不能据此判断 GPU 失败。整窗搬移的呈现取证见 [短时移动流程](desktop-verification.md#窗口呈现时间戳与短时移动取证)。

某些 VirGL/X11 组合的 `glxinfo -B` 会因 X_GetImage BadMatch 失败；用实际窗口/WebGL 绘制交叉确认，不靠伪造版本号消除错误。

## 性能边界

GPU 渲染不等于零损耗：PRoot 系统调用转换、VirGL 命令传输/拷贝、原生分辨率和 Android 调度仍有开销。原生架构、全部核心可见也不证明持续频率或满带宽。

### 可选原生桌面 Chromium

帧率低时确认具体页面、当前画质、画布尺寸、实际 renderer 与 native CPU 增量。网页自己的高画质可能成倍增加粒子数量；降低网页动画负载和降低整个 X11 分辨率是不同选择。`requestAnimationFrame` 采样表示页面动画节奏，不等于 SurfaceFlinger 的实际呈现帧数。

官方 Termux 图形仓库提供 `chromium`，可执行入口为 `chromium-browser`。在支持的 Adreno 设备上，先使用独立 profile 验证 native Mesa/Turnip/Zink，再配置：

```json
{
  "schema": 1,
  "browser_backend": "termux-zink",
  "native_browser_icd": "freedreno_icd.aarch64.json"
}
```

将这些字段合并进既有 profile；不要用这个片段替换设备全部设置。安装器增加 native `chromium mesa mesa-vulkan-icd-freedreno`；ICD 文件须实际存在。当前实现使用 `--use-gl=angle --use-angle=gles` 和 `GALLIUM_DRIVER=zink`，清除 VirGL 的 software/indirect/DRI3-disable 环境，native 进程的 `TracerPid` 应为 0。不伪造 GL 版本，也不把开启 Vulkan 开关当成性能提升。

现有 Chromium 桌面/面板/MIME 包装器改为 `tablet-native-browser`。它只通过原有 0600、同 UID Unix socket 发起固定的 `browser.open` 请求，校验当前会话与 URL/文件参数；不接收任意程序或 shell。控制器记录 native Chromium 的 PID、创建 ticks、UID、可执行文件及后代，纳入原有正常退出与精确清理。关闭桌面仍先等待窗口保存提示；高 CPU 不授权终止活动浏览器。

native profile 位于 `~/.config/chromium-native`，与原 guest profile 分开。迁移已有数据时先正常关闭 Chromium，确认相关进程退出，再在应用私有目录复制用户授权的数据，排除 Singleton 锁和 GPU/磁盘缓存，修正下载目录；保留原 profile，已有 native profile 不覆盖。账户/密码是否可用另验，不把标签页恢复等同于账户迁移成功。`chromium-tablet-guest` 和应用菜单的“Chromium（兼容版）”保留原 guest 路径；Code 可继续使用 VirGL。

### 输入或加载时闪烁

先记录具体表现，区分整窗闪黑、局部缺块、键盘弹收和窗口尺寸变化。保留用户输入法及现有驱动；分别核对真实屏幕键盘显示状态、X11 分辨率和 Chromium 实际 GPU 功能。XTest 输入绕过 Android IME，不能单独作为输入法通过或失败的证据。

等待目标网址的 `document.readyState=complete`，并确认该网站的异步控件已就绪，再做不导航的稳定画面对照；`Page.navigate` 刚返回时读到的 complete 可能仍属于前一个文档。加载中的 SVG/图标、建议菜单遮挡和菜单关闭的过渡帧不能计为漏画。必要时用无动画静态页，以及浏览器内部截图、X11 GetImage、Android 录屏交叉定位。截图读取本身可能改变同步时序，应结合重复录屏和相同条件的对照，不能凭一对截图就断言某个驱动函数有错。

若软件对照稳定、原 native Zink/Turnip 路径出现局部缺块，可先在隔离 Chromium 中验证标准 WSI 提交方式，而非叠加输入事件模块或关闭所有 GPU 功能。已验证设备可在既有 JSON profile 中合并：

```json
{
  "native_browser_present_mode": "mailbox"
}
```

此字段仅在 native Chromium 包装器中设置 `MESA_VK_WSI_PRESENT_MODE=mailbox`，保留 ANGLE GLES、Zink/Turnip、GPU 合成、栅格化与 WebGL。默认 `default` 沿用原有环境和 Mesa 选择，不覆盖其他设备；恢复 `default` 后正常重开浏览器即可撤回。配置不修改输入法、Xfwm 合成或 X11 的启动参数。已经运行的 Chromium 不会因新启动请求而切换环境，必须正常关闭旧实例，再由原入口重开，核对新进程的环境和实际绘制。

提交方式的作用与设备有关。[驱动维护者的 Adreno 830 案例](https://github.com/lfdevs/mesa-for-android-container/issues/56) 也区分了即时提交、mailbox 与软件 WSI 的稳定性和代价；该案例不代替本机验收。候选配置须同时通过真实输入、加载/滚动、稳定画面及同负载 GPU 性能检查。录屏编码帧、页面 rAF 和屏幕实际呈现帧率分别报告。`-legacy-drawing`、关闭 GPU 栅格化或切换 ANGLE 后端未改善时应撤除，不保留无效开关。

### VS Code 直接 KGSL 与原生办公

支持的 Adreno 可独立测试 [mesa-for-android-container 上游](https://github.com/lfdevs/mesa-for-android-container) 的 glibc KGSL 驱动。`desktop_gpu_bundle.py` 固定 Debian 13 ARM64、版本 `27.0.0-devel-20261025-r2`、下载 URL 和 SHA256；校验、拒绝越界路径/链接后仅安装到 guest `/opt/tablet-mesa-*`，保留发行版 Mesa。已有目录必须有匹配清单才可复用，不隐式覆盖。开发版本不视为全部 GPU 通用驱动。

`gpu_backend=freedreno-kgsl` 的 `tablet-gpu-run` 使用隔离的 library/dri/GLVND/Vulkan 路径，设置 `MESA_LOADER_DRIVER_OVERRIDE=kgsl`，清除 VirGL software/indirect/DRI3-disable 变量，不启动 VirGL daemon。`gpu_driver_ready` 检查依赖文件，仍须实测渲染。已正常退出的旧自有 VirGL 服务按身份回收，不能为换路径全局杀进程。

维护旧安装时，doctor 读取实际 `gpu.json` 选中的隔离目录，并检查 bundle 版本、校验清单和驱动文件。旧目录别名不同但内容匹配时无需搬移驱动；缺少清单或校验不匹配仍判失败，不因应用曾经打开就放宽检查。

Code 的真实 GPU 绘制通过后，仍须测试边栏调整、编辑器滚动和终端布局；WebGL 跑分不能代替编辑器交互。若边栏拖动很慢，在相同缩放、窗口尺寸和内容的独立 Code profile 中比较，两个实例都关闭扩展，以排除扩展差异。必要时用标准 DevTools 性能记录区分 Layout/Script 与 GPU 的 `SkiaOutputSurfaceImplOnGpu::FinishPaintCurrentFrame` 等等待，结合可见录屏复核。

已验证设备可设置 `"code_angle_backend": "gles"`，由原 `code-tablet` 入口向微软 VS Code 加入 `--use-gl=angle --use-angle=gles`；它要求已选硬件 `gpu_backend`，继续使用同一受管驱动。默认 `default` 保留原来的 ANGLE 选择，不推广为所有设备的开关。软件兼容入口移除这些强制后端参数，仍是明确的软件回退。正常重开日常 Code 后核对实际参数、GPU 驱动及原扩展/工作区中的操作；不改扩展打包代码、不把隔离测试的调试端口带入日常实例。

小米后续隔离测试中的 ANGLE/Skia Vulkan 虽缩短交换等待、提高了边栏更新，但日常实例出现用户可见闪动，未通过画面稳定性验收，已恢复 GLES。该实验未加入可安装 profile 的枚举。真实 shader/像素、吞吐量与画面稳定性须分别验证，不能凭更快的计数推广路径，见[兼容记录](desktop-compatibility.md#小米-vs-code-与-codex-面板)。

2026-11-15 此前在 Adreno 830 上，微软 VS Code 保留原版本、扩展、工作区与字体；隔离实例实测 ANGLE/freedreno Adreno 830v1、OpenGL 4.6、加速 Compositing/Raster/WebGL，WebGL2 绘制读取像素成功。随后同条件边栏对照确认 GLES 更快，日常入口已按设备选择 GLES，详见兼容记录。日常 Code 的 GPU 子进程也加载隔离驱动并打开 `/dev/kgsl-3d0`。真实 GPU 路径证明与编辑器响应测试分别记录，不宣称获得浏览器同样倍率的提升。

若独立 Code 已顺畅，日常工作区仍慢，保持后端与窗口条件，分别收起终端和扩展侧栏做对照。Y900 的一次实测中，主要剩余开销来自可见终端；官方设置 `"terminal.integrated.gpuAcceleration": "off"` 切换终端 DOM 渲染后，保留终端及原扩展也显著改善了边栏拖动，编辑器仍用 GLES 加速。这是该终端负载的选择，不能推广为终端都应禁用 WebGL；[官方文档](https://code.visualstudio.com/docs/terminal/appearance#_gpu-acceleration) 说明 DOM 与 WebGL 的取舍。标准用户设置会由安装器保留，无需增加全局 GPU 开关或修改打包代码。记录备份、原值、真实终端绘制和用户操作结果；无收益时恢复原值。

GPU 开启不等于应用空闲。Code 中可启用 `workbench.reduceMotion=on`；不用的动画 Webview/登录侧栏先收起，保留扩展功能，再从 native `/proc/PID/stat` 比较稳定后的 CPU 增量。不修改扩展打包代码、不因活动动画 CPU 高而杀进程；功能使用时的绘制负载另计。

`office_backend=native-gtk3` 使用官方 Termux LibreOffice，固定 `office.open` 请求仅接受 writer/calc/impress 和校验后的文件/URL。native `~/.config/libreoffice-native` 初次复制 guest `~/.config/libreoffice/4`，保留原目录，已有 native profile 不覆盖。字体桥接包含 guest 系统字体和用户字体；主题、缩放与指针保持一致。原生 oosplash/soffice 后代加入桌面保存等待和身份清理。菜单、桌面及常用 MIME desktop ID 走同一包装器；高级 CLI/批量转换可显式用兼容入口。

该 native 构建没有 Skia，不能称为办公 GPU 全面加速。相同自建中文文档转换的有效样本：guest 1.48 秒、native 0.85 秒，均输出存在且中文保留；只代表这个样本。未生成输出的“快速退出”样本无效。Writer/Calc/Impress 窗口已实际打开，原 guest 程序和设置仍保留。

### VLC 的 Android 硬解桥接

`media_backend=termux-va` 需要直接 KGSL 驱动。`desktop_video_bundle.py` 固定 [Termux:VA](https://github.com/lfdevs/termux-va) 0.1.0 和 [匹配 VLC 上游构建](https://github.com/lfdevs/vlc/releases/tag/release%2Ftermux-va) 3.0.24-90 的 SHA256。全部匹配 VLC 核心、可执行文件和插件放入 `/opt/tablet-vlc-va-3.0.24-90`；只替换两个插件配发行版核心可能失败，不能据此验收。发行版 VLC 留作回退。

guest `tablet-video-run` 请求固定 `video.ensure`，再设置 termuxva VAAPI 驱动、KGSL/DRI3 bridge 与隔离 VLC 路径。控制器按需直接启动 `termux-va`，运行 `tva-probe` 实际解码健康检查，记录 PID/UID/start/exe 和 socket inode。目录 0700、socket 0600，不增加 TCP 监听；不调用包内使用宽泛 pkill 的 start/stop 脚本。服务可在桌面会话中复用，随正常/强制结束精确回收；控制器重启保留身份，未知监听者不接管。

Adreno 830 实测：健康探针解码 5 帧；VLC 日志实际选择 Mesa/Adreno termux-va 硬件解码，1080p H.264 短样本显示 146 帧、统计丢失 0，PulseAudio 已通过 Cookie 认证连接。该样本无音轨，声音与其他 codec/profile、高码率/4K 另测；VLC 内部 decoded 统计不直接当成呈现 FPS。native FFmpeg MediaCodec/NDK 测试虽创建了解码器但未完成出帧，不算成功，也未设为日常默认。VLC 硬解成功不改变 Chromium 的 Video Decode 状态。

部分设备的 H.264 High/B 帧会出现桥接同步失败，需按同一文件复测并保留失败记录。`media_hardware_policy=h264-baseline` 是保守的按文件策略：guest FFprobe 只检查本地文件，限已验证的 8 位、无 B 帧 Baseline、最高 1080p30 使用硬解；其他文件、流媒体、空白播放器以及探测失败均使用软件解码和 KGSL GPU 显示。它不预取远程媒体，不影响 `all` 策略已有设备的行为。界面内再打开文件会沿用该 VLC 实例的解码路径；需按文件重新选择时先正常退出播放器。硬解与 GPU 显示必须分别报告，不能把兼容路径宣称为硬解通过。

2026-11-14 在 Adreno 830 上的 Tendrils 页面，6 秒动画采样：

| 路径 | 高画质 | 普通画质 | 画布 |
|---|---:|---:|---|
| Debian Chromium / VirGL | 约 10 FPS | 约 13 FPS | 1920×1092 |
| native Chromium / Zink GLES | 约 30 FPS | 约 38 FPS | 1920×1152 |
| Android Chrome | 约 58 FPS | 约 60 FPS | 1536×889 |

X11 保持原生 3840×2560，native Chromium 与 Code 并发；实际 WebGL2 绘制/像素读取及单指滚动另测通过。Android 画布较小，不能把该表当成严格同尺寸跑分或所有网站的性能承诺。native ANGLE/Vulkan 在此测试中反而更慢；VirGL/ANGLE Vulkan 的上下文丢失使动画没有初始化，其空白页帧率无效。这个 native Chromium 的 Video Decode 状态为软件，视频硬解没有通过。

系统调度也需区分：检查实际 cpuset/允许核心，不能从“后台”标签直接断言被锁在小核。[Termux:X11 官方说明](https://github.com/termux/termux-x11#avoiding-slowdowns) 的 sharedUid 变体要求 GitHub 签名的 Termux，不能直接覆盖 F-Droid 环境；迁移涉及另一项备份/签名任务，不作为当前优化的隐式操作。

Video Decode 状态不证明某段视频实际硬解；需核对 codec/profile 与 `chrome://media-internals` 的实际 decoder。VLC 软件解码预设保留。WebGPU、计算任务和 Vulkan 另测：native Turnip 成功不等于 PRoot 中 Chromium 使用 Vulkan，也不代表 CUDA/OpenCL/NPU 可用。

来源：[Termux 官方包](https://github.com/termux/termux-packages/blob/master/packages/virglrenderer-android/build.sh)、[VirGL 服务源码](https://gitlab.freedesktop.org/virgl/virglrenderer/-/blob/virglrenderer-1.3.0/vtest/vtest_server.c)、[Chromium 视频验收](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/gpu/vaapi.md)。
