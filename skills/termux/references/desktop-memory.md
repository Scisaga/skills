# Android 与 Xfce 应用内存

## 先确定统计口径

- 不累加多进程 RSS。native Termux 使用每个可读 PID 的 `/proc/PID/smaps_rollup`，分别汇总 `Pss` 和 `SwapPss`；PRoot 的 `/proc/PID/exe` 可能是 loader，应用身份还须结合 cmdline、父子关系及控制器记录。
- Android 16 的 `Debug.MemoryInfo.getTotalPss()` **已经加上 SwapPss**。该版本 `dumpsys meminfo` 的驻留部分为 `TOTAL PSS - TOTAL SWAP PSS`，逻辑总量就是 `TOTAL PSS`，不能再加一次 swap。其他 Android/OEM 版本先核对实际表格与对应源码；脚本的 `--android-total resident` 用于 TOTAL 原本不含 swap 的格式。
- smaps 的 PSS 包含映射的 `Gfx dev`；只补充 `EGL mtrack`、`GL mtrack` 和 `Other mtrack` 这类非映射统计。Android `App Summary > Graphics` 已含映射部分，是驻留总量的子集，不能整项再加到 PSS。每个 PID 只计一次，不能把同一进程的 Android 与 native 记录重复相加。
- SwapPss 是换出页的逻辑大小，不是这些页实际占用的 RAM。ZRAM 的 `mm_stat` 第三项 `mem_used_total` 包含压缩数据、分配器碎片与元数据。无权读取 sysfs 时使用 `dumpsys meminfo` 的 `ZRAM: ... physical used`，并注明来源。不要把全机压缩率当成单个应用的精确压缩率。
- `MemAvailable`、全机 ZRAM 物理量和应用驻留分别报告；不能再次把 ZRAM、GPU 或 DMA-BUF 全机统计加到应用总和。页面缓存可回收，剩余 free、Android 的 Free RAM 与内核 MemAvailable 不是同一个指标。

口径依据：[Android 16 Debug.java](https://android.googlesource.com/platform/frameworks/base/+/refs/heads/android16-release/core/java/android/os/Debug.java)、[Android dumpsys](https://developer.android.com/tools/dumpsys#meminfo)、[Linux ZRAM 统计](https://docs.kernel.org/admin-guide/blockdev/zram.html#stats)。

## 可重复快照

`memory_report.py` 仅使用标准库和既有 OpenSSH；`--android` 额外使用连接文件中配置的 ADB。不安装常驻采样器、不启动 GUI、不发信号、不写设备配置，也不加载 `.env`。主机缺少 Python/ADB/OpenSSH 时，沿用 `host-tools` 与 [验收入口](desktop-verification.md) 的安装方式。

```bash
# 相同的原有 Code、Codex、终端、浏览器标签与前台状态；先让它们静置
python scripts/memory_report.py snapshot --connection /private/device.json \
  --state /private/before.json --workload 'same-tabs-code-terminal-idle' \
  --samples 3 --interval 3 --android

# 执行有依据、可回退的单项应用级优化，然后恢复相同前台与静置条件
python scripts/memory_report.py snapshot --connection /private/device.json \
  --state /private/after.json --workload 'same-tabs-code-terminal-idle' \
  --samples 3 --interval 3 --android
python scripts/memory_report.py compare --before /private/before.json \
  --after /private/after.json --state /private/comparison.json
```

Windows 从仓库根目录调用时在脚本路径前加 `skills/termux/`；`run.sh memory-report` 是同一入口。连接文件格式见 [桌面验收](desktop-verification.md#可重复执行的验收入口)。输出含输入摘要、连接摘要、boot/session、PID 创建 ticks、实际 Code GPU 参数、注册身份、覆盖缺口和分组中位数。文件留在仓库外私有目录。原始参数、代理环境、浏览历史、认证文件不采集。

采集使用 `dumpsys --local -a -S`，避免逐一调用应用的远程详细转储及其超时/额外活动。GPU 进程的非映射图形内存单独读取，前后复核 PID 身份。时序采样并非原子快照；短时变化、应用自主重启和厂商缓存调度须保留在结果中。中位数各列独立统计，可能有少量不相加误差。

Android 应用归属以 ActivityManager 的实际 packageList 与同名 PID 对应，兼容 `:push` 和 `.unstable` 这类进程命名；共享包无法唯一归属时保留 shared 标记。应用在枚举和取数之间退出会触发最多两次重采，并记录原因；仍不完整就失败。僵尸进程没有地址空间，不计入应用内存；其他可读范围内的覆盖缺口保持 pending。

比较会拒绝输入条件、boot、桌面会话或应用根进程身份不一致；标签内容与实际负载仍由操作者核对，文本 workload 名称本身不能证明相同负载。timeout、缺失格式、缺少 ZRAM 物理证据不能算通过；GPU 缺测保留 unknown，不能按 0 计算。快照/比较通过退出 0，失败退出 1，参数错误退出 2，覆盖不足退出 3。只用 LAN SSH 时无法完整计入非映射 GPU 内存，须如实标注。

## 优化顺序与回退

1. 读取 native/guest 的 AGENTS，记录当前工作、标签、消息推送、VPN 和会话。核对存储入口与**正在运行**的 GPU 参数，尤其是一次性试验可能与默认入口不同。内存任务不自动重启 Code 或恢复被拒绝的图形方案。
2. 从浏览器的正式 Performance 设置检查 Memory Saver 和 Preload pages。优先开启均衡的内存节省、关闭确有开启的预加载；已经设置好的项不重复修改。保留标签及其会话，通过浏览器自己的活动媒体、表单、下载、通知等保护规则决定休眠，不按 renderer 内存大小杀进程。网页休眠会在重访时重新加载，不能承诺所有页面瞬时状态都不变。
3. 记录原设置、设置截图和当前应用身份；通过运行中浏览器 UI 应用并回读设置，不直接覆盖正在运行的 Preferences/Local State。回退使用同一 UI 恢复 Memory Saver 开关/级别和 Preload pages 原值，无需清数据。完整私有配置备份仅供取证，不直接覆盖用户之后的配置。
4. Android 缓存应用先核对当前 PID、启动时间、应用级 proc state、前台服务及可见任务。历史名单不是当前清理依据。确实未使用的 cached 进程可使用 Android 的 `am kill --user current PACKAGE`，由系统决定是否可安全回收；不使用 force-stop、禁用包或清数据替代。应用会自行重新缓存，不能将一次回收宣称为永久收益。消息/VPN/Termux/X11/Codex 保留。
5. 残留进程只按 [生命周期身份规则](desktop-lifecycle.md#防止遗留进程占满-cpu) 处理；PPID=1 不代表残留，仍有当前 PRoot tracer 的 Code/zygote 不清理。没有身份合格的目标就不杀进程。
6. 不调整全局省电、phantom 监控、分辨率、缩放、字体、ZRAM 大小或 swappiness，不使用 drop_caches/swapoff 制造“空闲内存”。固定工作负载比较，保留零收益或回退结果。

Memory Saver 的保护规则与重载行为见 [Chrome 官方说明](https://support.google.com/chrome/answer/12929150)。Termux native Chromium 是桌面构建，不按 Android Chrome 的设置能力推断。

## 验收

恢复相同应用前台、标签与终端状态后比较至少三个样本；同时报告应用驻留和换出变化，不能仅凭 MemAvailable 一项归因。恢复/切换已有窗口，检查 Code/Codex 可响应、原终端正常、native/guest DNS/TLS/HTTP 与原 VPN 正常；只看到进程或 UI 时不能宣称已完成真实 Codex 请求或消息推送验收。

清理自己创建的设置/诊断标签，不关闭用户标签。没有长期驻留采样器或额外 Code 测试实例；所有诊断连接退出。使用过 ADB 时清理本任务转发，停止/断开 ADB，再用独立 LAN SSH 做最终复查。长息屏、重启、推送到达、主观手感未测的项目单独列明。
