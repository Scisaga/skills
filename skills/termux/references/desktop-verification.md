# 验收、覆盖范围与迁移检查

## 功能覆盖清单

| 场景 | 实现/资源 | 验收重点 |
|---|---|---|
| 原生安装、签名与迁移 | 原有 bootstrap、安装/迁移参考 | 已有数据保留；插件同源；不把 Root 标签当权限 |
| SSH、Boot/runit、Bash、存储 | 原有脚本和 remote-management | 公钥、服务、Downloads、严格指纹；最终脱离 ADB |
| API、蓝牙、本机 Codex | 原有 API/companion/Codex 脚本与参考全部保留 | 按需安装/授权；实际能力与权限边界 |
| Debian/Xfce 桌面 | desktop_setup.py、profile、guest 安装脚本 | 新建/维护范围、普通用户、X11 APK+CLI、无隐式 reset |
| Code/Chromium/Office/VLC | 按 applications 选择的包装器与桌面入口 | 真实启动/文件打开/播放；默认浏览器 helper；不自动卸载其他应用 |
| GPU 渲染 | gpu_backend、GpuResource、tablet-gpu-run、GPU 参考 | 真实渲染器/绘制、应用并发、私有 socket、复用/清理/软件回退；硬解另测 |
| 整窗拖影与边框 | window-probe、present-report、display-input 参考 | 区分客户端装饰、Xserver 重绘与最终呈现；实际运动状态、像素正确性和应用性能分别验证 |
| Android 子进程与后台 | host-doctor、host-permissions、电源参考 | cap 与 monitor 分别核对；Termux/X11 都检查；白名单不代替厂商电池 UI 与最近任务锁定 |
| 清晰度、字号、暗色与标题 | profile、主题资产、display-input 参考 | native 分辨率、缩放协调、标题和字体下拉不裁切 |
| 实体键盘与输入法 | hardware_keyboard 预设、Android 设置流程 | 软件键盘开关、已有 Alphabet、Shift 中英文实测 |
| 触屏/触控板切换 | 同 UID 私有服务 + 四处同步入口 | 双向切换、图标完整、恢复用户模式 |
| 自动隐藏底栏 | profile、repair-panel | 底部触发区位置、呼出/收起、动态尺寸异常定位 |
| 会话、正常/强制结束、CPU | session_manager、退出 UI、guard tests | 单会话复用、保存等待/取消、身份范围、SSH 保留 |
| Android/Xfce 应用内存 | memory-report、memory 参考 | PSS/图形/SwapPss 去重、ZRAM 物理量、同工作负载比较与覆盖缺口 |
| 电池 | native API 缓存 + genmon | 真实读数/充电状态；过期明确不可用 |
| Android 图形管理和全部应用 | APK 源码、构建/部署脚本、activity-alias | 两个正式入口、留白、确认、返回复用会话 |
| 同系列图标与文件夹 | skill/Android SVG、launcher-plan、Android 集成参考 | 深浅背景、实际 UI 分组、全部应用入口与去重 |
| 网络与 VPN | network-doctor、network 参考 | VPN 是否运行、Termux 分应用路由、显式代理与 DNS 分开验证 |
| 功耗、性能、Docker/Root | lifecycle/setup 参考 | 报告测量条件与未验证能力，不承诺性能无损 |

## 仓库内确定性检查

```bash
python -m unittest discover -s skills/termux/tests -v
python -m unittest discover -s tests -p test_manage_skills.py -v
python scripts/manage_skills.py package --sync-manifests --output /path/outside/repo/scisaga.zip
```

测试应覆盖配置渲染及文件保留、拒绝越界写入、安装门禁不产生设备动作、无副作用 plan、当前/更早两个旧名迁移、未知/已修改安装保留、旧名 CLI 兼容和进程身份清理规则。目录符号链接迁移测试在不能创建链接的 Windows 账号会跳过，需另在 Linux/WSL 执行；源目录改名造成的旧资源断链也应能迁移。样例设备的长息屏/重启行为不能由单元测试替代。

构建图形管理器并通过 APK 签名验证；检查两个 launcher entry、非导出的结果回调 receiver，以及默认禁用、仅处理受保护开机广播的 Boot receiver。启用开机恢复后还要做真实重启验收，不能将“所有 receiver 均非导出”作为要求。签名私钥、缓存、编译产物不进入分发包。

## 设备上最小回归

按本次改动选择相关检查，不为了文档改名重装整套环境或结束用户桌面。保留当前未保存编辑；需要关闭/重启时先正常结束并处理保存提示。

1. 启动一次再重复返回，核对同一 session UUID、一个配置容器的桌面核心；启动终端可关闭。
2. 查看 Code、Chromium 和实际网页/文件；浏览器网络失败按网络分层定位。未播放视频不能宣称硬解可用。
3. X11 根窗口尺寸与 Android 当前视口对应，字体清楚；标题、LibreOffice 字体菜单、Code 滚动条、SVG 图标可见。
4. 输入模式双向切换，检查桌面/菜单/底栏/顶栏标签并恢复原模式；实体键盘中英文由用户实际输入确认。
5. 自动隐藏栏可呼出/收起，触发条处在当前底部；电池数值来自 API，过期状态明确。
6. 管理器的启动/返回、状态与记录可用；全部应用有两个入口；文件夹分组按实际界面检查。
7. 正常结束先测试取消；用专门创建的未保存测试窗口验证阻塞/取消，再由用户处理后正常退出。强制结束至少测试确认取消，未经授权不对真实工作执行强制结束。
8. 检查退出后本次桌面/X11 cohort 结束、SSH 保留；再启动得到新会话；没有循环启动或持续异常 CPU。

## 电源与网络验收

亮屏、切回 Android、普通锁屏、真正息屏及重启后首次解锁分别记录。长息屏按原生 verification-and-troubleshooting 的矩阵进行；本次未做的明确写未验证。USB 常亮不是息屏验收。

使用 ADB 后清空 forward 并停止/断开 ADB，再直接设备 LAN SSH。网络代理测试不能只看环境变量、进程或端口存在；保留实际 HTTP/TLS 结果与模式，不保存订阅/密码。

## 可重复执行的验收入口

`scripts/desktop_verify.py` 在主机运行，只依赖 Python 标准库及当前检查所需的 ADB/OpenSSH。`run.sh desktop-verify` 调用同一入口；Windows 可直接执行 Python，不要求 WSL。连接参数与检查点保存在仓库外的私有目录：

```json
{
  "adb": "/path/to/adb",
  "serial": "SERIAL",
  "ssh_target": "termux@PHONE_IP",
  "ssh_port": 8022,
  "identity": "/private/host-key"
}
```

重叠 VPN 路由可加 `ssh_bind` 指定主机 LAN 地址；`ssh_config` 和 `kex_algorithms` 为可选连接选项。保持严格主机指纹校验。传输使用参数数组和标准输入，避免 Windows/SSH 多层 shell 引号损坏；不接受密码、订阅或任意代理凭据字段。

```bash
# 128 仅为已选择上限的示例，按本次设备/负载确定，不能全局套用
python scripts/desktop_verify.py policy --connection /private/device.json \
  --state /private/policy.json --min-cap 128 --monitor enabled

# 正常保存并结束桌面、修复前置检查后才进行已授权的真实重启
python scripts/desktop_verify.py boot-baseline --connection /private/device.json \
  --state /private/boot.json --min-cap 128
# 外部工作流安排重启及用户首次 PIN/图案解锁；脚本不自动打开应用
python scripts/desktop_verify.py boot-check --connection /private/device.json \
  --state /private/boot.json --min-cap 128 --no-manual-app-start
# 使用独立管理器恢复入口时，另加 --require-boot-helper

# 正常进入桌面后进行真正息屏；不需要电量插件时可省略 --require-battery
python scripts/desktop_verify.py sleep --connection /private/device.json \
  --state /private/sleep.json --min-cap 128 --require-battery \
  --duration 360 --interval 45 --apply --wake-at-end

# 移除本任务转发并停用/断开 ADB 后；此命令只新建 SSH，绝不调用 ADB
python scripts/desktop_verify.py final-check --connection /private/device.json \
  --state /private/final.json
```

结果包含输入摘要/散列及 passed、failed、pending、skipped 状态；退出码分别为 0、1、3、4，参数错误为 2。未首次解锁时保留原 boot ID，解锁后重复 `boot-check` 即可，不需要再重启；解锁后的自动服务采用有界等待，失败先诊断对应阶段。`--no-manual-app-start` 表示操作者确认取证前未打开相关应用，脚本不能替代这一现场条件。息屏每次先建立全新主机到设备的 SSH，比较 boot ID、配置散列、会话、真实 Asleep、唤醒锁及新增冻结事件；中断或失败的记录不能算完整通过。USB/AC 充电条件不证明续航。

## 窗口状态与重绘对照

`window_probe.py` 默认 `inspect`，通过现有严格 LAN SSH 临时执行只读诊断；不调用 ADB、不打开测试窗口、不暂停辅助、不更改配置。主机仅需 Python/OpenSSH，guest 需要现有 Xfce、Python、`python3-xlib`、`python3-gi` 和 `gir1.2-glib-2.0`；缺失时给出安装命令。它也集成在 `desktop_verify.py window-report` 中。native `desktop-doctor` 仅在已有桌面运行时附带这项检查，不为诊断启动桌面。

```bash
python scripts/window_probe.py inspect --connection /private/device.json \
  --state /private/window-state.json
python scripts/desktop_verify.py window-report --connection /private/device.json \
  --state /private/window-report.json

# 不带 --apply 只返回 skipped，且不联系设备
python scripts/window_probe.py compare --connection /private/device.json \
  --state /private/window-compare.json
# 显式进行临时窗口与辅助暂停/恢复对照，默认每组 3 轮
python scripts/window_probe.py compare --apply --connection /private/device.json \
  --state /private/window-compare.json --trials 3 --steps 120 --step-ms 20
```

输出区分 `non_composited`、`composited`、`possible_redirect_conflict`、`unverified_helper_state` 和 `compositor_state_mismatch`。正常无合成检查可以通过，这只是取证成功；可疑冲突仍须结合当前日志确认，不能自动判定根因。旧状态文件、失效窗口或未知 helper 身份不能作为活动重定向的证明。

`compare --apply` 只支持已核对身份、处于同一 managed PRoot tracer cohort 的底栏辅助，且实际合成关闭。辅助 PID、启动 ticks、UID、executable、命令和 tracer 在发信号前再次核对；guest 映射 UID 与 Android 实际 UID 分别记录。窗口尺寸和轨迹按当前工作区计算并在本轮固定，验证实际位置变化与窗口可见性；工作区、桌面或活动合成器改变时中止，最终再回读实际 Xfwm 设置。绘制/事件与同步状态查询使用独立 X11 连接，位置来自真实 ConfigureNotify 事件，避免在绘制连接中穿插同步查询。只读检查不限 640×480，创建对照窗口至少需要该工作区尺寸。

三阶段分别为辅助运行、正常停止、恢复；不改 autostart、主题、GPU、输入和合成设置。恢复经现有 Thunar D-Bus Execute，在桌面 cohort 内启动；不让长期辅助挂在诊断 SSH 的 PRoot 下。结果含输入/源码/负载散列、实际轨迹、各轮 Expose 事件数和重绘完成数。次数不是 FPS，不设置“必须零重绘”的通用门禁；`passed` 仅表示对照完成、恢复及清理成功。单轮可用于调试，不能代替重复取样的结论。

暂停前记录原生私有 `~/.local/state/tablet-desktop/probes/window-*/recovery.json` 检查点，包含当前阶段、诊断进程与原辅助/窗口管理器身份。Xfconf 查询和辅助恢复使用有 3 秒超时的标准 Gio D-Bus 调用；退出时显式关闭诊断连接。普通异常、SIGINT/SIGTERM/SIGHUP 及 I/O 总时限进入恢复与清理；恢复失败也继续清理自建窗口，并返回失败。原生监督在 55 秒 I/O 超时后依据唯一检查点、实际 Android UID、PID/启动 ticks/executable/tracer/请求再次核对，仅向自己的诊断 Python 发 SIGTERM，并留出 8 秒恢复；超时样本始终标失败。无法核对身份或仍未恢复时返回非零并保留检查点，不以终止整个桌面代替清理。硬终止或设备断电不能保证执行恢复：先核对原会话和身份，再通过该会话启动原辅助；不添加无条件重启循环或自动开启合成。测试后还要检查屏幕可见输出；本脚本不替代真实手指验收、浏览器 GPU 跑分或续航测试。

## 窗口呈现时间戳与短时移动取证

整窗搬移、网页内部动画、Code 边栏调整分别取样。先确认现有窗口身份和几何；能直接读取的 GPU 页面、系统状态由操作者获取，保留用户标签页、原焦点与未保存内容。先做不改设置的短样本，再根据证据选择刷新或合成的单变量对照，不把主题、驱动、输入和全局刷新同时改动。

SurfaceFlinger 取证选择真正承载 X11 桌面的 SurfaceView/BLAST 图层，记录同一 boot、完整图层名和设备端时钟。`--list` 在部分 ROM 返回带包装的 debug 名，须与 `--latency` 接受的精确名字核对；只有首行不能证明图层匹配。

下面是主机 Bash 示例；PowerShell 传递远端命令时可用 `Device.shell_script` 的标准输入，避免多层引号丢失。所有原始输出按 UTF-8 保存。

```bash
adb -s SERIAL shell dumpsys SurfaceFlinger --list
# 保持远端 shell 引号；含空格、括号的图层名不要丢失引号
adb -s SERIAL shell 'dumpsys SurfaceFlinger --latency "EXACT_SURFACE_LAYER"'
```

先保存 UTF-8 的 latency 基线和 native CPU 起点，再用单一持久 X11 连接、固定窗口大小短时平移约 2 秒，记录实际 ConfigureNotify 和运动起止的设备端 monotonic 纳秒。结束后立即取 CPU 终点及 latency 末样，随后恢复几何并回读。若恢复帧已混入，按原运动时间范围严格裁剪；主机时钟、墙钟或不同来源的 uptime 不可直接充当该范围。EWMH 重定位应标明“无真实鼠标输入”，它不能验收输入延迟或替代真实拖动体验。不要每步启动 wmctrl/SSH 或做 XSync 往返；需要像素取证时另做短观察，避免全屏 GetImage/录屏改变本次时序。

[FrameTracker 源码](https://android.googlesource.com/platform/frameworks/native/+/refs/heads/main/services/surfaceflinger/FrameTracker.cpp) 三列依次为 desired、actual、ready；只分析新增有效的第 2 列，排除非正数、INT64_MAX、重复值和基线旧记录。首行是调度刷新周期，不能当作目标图层的实测 FPS。环形历史有限，仅保留下来的最后一秒不能证明整段没有丢帧；自动刷新可能在过程中切换，不能拿末样首行周期计算全程掉帧数。零数据/旧数据表示本轮没有足够证据，不报告为 0 FPS。

`presentation_timing.py` 仅离线分析已保存的两份原始快照，不连接设备、清全局统计或改变显示策略：

```bash
python scripts/presentation_timing.py --before /private/before.txt \
  --after /private/after.txt --layer 'EXACT_SURFACE_LAYER' \
  --start-ns START_NS --end-ns END_NS --state /private/present.json
# 等价统一入口：bash scripts/run.sh present-report <同样参数>
```

`START_NS`/`END_NS` 替换为本次设备时钟下的实际整数。输出记录原文件和脚本摘要、输入摘要、两份首行周期、过滤计数、选中数量/跨度与间隔 min/p50/p95/max。原始文本不含图层或 boot 身份，`--layer` 是操作者提供的元数据，仍须现场核实；脚本不验证画面或判定修复。至少两个有效新时间戳才返回 `collected=0`，不足返回 `pending=3` 且间隔为空；坏数据或 I/O 错误为 `failed=1`，参数错误为 2。不输出推算 FPS，不将 collected 当作性能验收通过。结果不得覆盖输入快照，私有证据放在仓库外。

CPU 使用 native `/proc/PID/stat` 或对应 task/TID 的 utime+stime 差值，100% 为一核。线程包含在进程总量中，不重复加总；Xserver 主线程和 LorieRenderer 应分别看。对比静置与运动期的相同负载，短时低 CPU 不排除复制、带宽、锁和 fence 等待。采样器须有设备端期限与身份记录，结束确认退出；不复用缺少设备端回收的 getevent 临时脚本。

均匀 actualPresent 只能说明该段呈现节奏。像素残影、背景露出重绘与输入手感另验：Expose/DAMAGE 次数不证明画面正确；观察到 DAMAGE 合并时按协议 subtract，不能拿事件数当绘制完成数。后续若测试合成，先按显示参考释放底栏辅助重定向，在同一设备同时评价拖影和固定浏览器负载，结束恢复原设置；案例中的性能代价不跨设备套用。

## 受管记录的 UTF-8 更新

`managed_context.py`（`run.sh context-block`）从 UTF-8 文件替换一个指定区块；不把中文嵌入 PowerShell 到 Python/SSH 的多层命令字符串。根据原始 JSON/日志修复已有乱码，不能凭问号猜回内容。文件名、块名和摘要都通过结构化参数传入；传到设备时用文件复制或明确编码的标准输入。

```bash
python scripts/managed_context.py --file /private/AGENTS.md \
  --block-file /private/reviewed-block.md --name 'device maintenance' \
  --expected-sha256 REVIEWED_FILE_SHA256
# 审阅预览后，同样参数加 --apply --backup-dir /private/backups
```

替换文件须含匹配的 BEGIN/END 标记；缺块只有显式 `--append` 才允许新增。拒绝重复/倒置标记、已变化的原文件、替换文本中的损坏字符和连续问号。应用时备份原始字节、同目录原子替换并回读校验，保留区块外的原始字节；失败退出非零。native 与 guest 的文档分别更新并验证，不能用整份旧备份覆盖其后来新增的用户记录。退出码沿用 passed=0、failed=1、skipped=4。

## GPU 探针与性能门禁

`gpu_probe.py` 只连接明确指定的隔离 Chromium 调试实例，不给日常浏览器开放调试端口。独立新 profile 必须位于应用私有的 `.local/state/tablet-desktop/probes/<name>`，启动时含 `--enable-automation`、`--user-data-dir=...`、仅环回的 `--remote-debugging-port`，以及与日常路径一致的 GPU 参数。不要迁入账户数据。依赖缺失时脚本给出 `python -m pip install websocket-client==1.9.2`，推荐装在仓库外的主机 venv。

```bash
python scripts/gpu_probe.py --connection /private/device.json --owned-probe \
  --remote-port 9226 --expected-profile /data/data/com.termux/files/home/.local/state/tablet-desktop/probes/UNIQUE_NAME \
  --trials 3 --output /private/native-gpu.json

python scripts/desktop_verify.py gpu-report --candidate /private/native-gpu.json \
  --baseline /private/guest-gpu.json --state /private/gpu-result.json \
  --min-fps 60 --min-speedup 2
```

阈值按用户已知故障与实际目标指定，不把示例 60/2 作为所有设备标准。探针先核对调试实例实际 `user-data-dir`，不匹配则不创建测试页、不关闭未知浏览器；确认后才建立自有页面，固定 WebGL2 shader、画布、视口和缩放，4 秒预热、10 秒测量。多路径对比可用 `--trials 1` 交替采集三组，再按相同 workload hash 合并 samples；单样本仅标 collected，不等于性能通过。结束正常关闭已验证的自有实例，确认端点终止并移除临时 SSH 隧道。

门禁拒绝软件 renderer、绘制像素错误、上下文丢失、测量期间页面隐藏、负载不一致、预热/测量不足、样本少于三组及未达到指定性能目标；保留 median 和回调帧间隔，不称为 SurfaceFlinger 实际呈现帧数。隔离探针通过后，日常菜单/面板/MIME 入口仍需实测。

C 手势策略回归可在安装了触屏构建依赖的 Debian guest 执行 `python3 tests/test_touch_policy.py`；它编译并调用实际识别器，以假时间/窗口元数据检查短按、长按、拖动取消、多指取消、应用范围和禁止重复合成左键，不连接显示服务器。主机无 gcc/X11 开发头文件时会明确跳过，须在 guest 补跑。

## 旧名称与部署兼容

源码只保留 `skills/termux/`。安装器将 termux-ssh 和 android-termux-ssh 都映射到 termux，标准独立安装名为 ss-termux；用户自定义别名保持不变。未知来源或修改过的旧副本不会按名称删除；同一来源登记多个历史安装时停止并报告，避免选择性覆盖。

设备既有 `~/.config/android-termux-ssh`、SSH 配置片段、AGENTS 托管标记和 native 桌面接口继续兼容。技能改名不是迁移 Android 用户数据的理由。
