# 桌面网络、VPN 与代理排障

## 定位顺序

PRoot 中的程序保留 Termux 的真实 Android UID。Android 分应用 VPN 应将 Termux 纳入代理范围，不能只选择 Termux:X11 或桌面管理器。guest 的用户名和 root 标签不改变这一点。

1. 检查系统是否确有活动 VPN、目标 VPN 应用的服务是否运行；“已安装”或主界面打开不等于隧道已连接。
2. 检查分应用规则是否包含 Termux。白名单/排除名单含义相反，按实际 UI 核对。
3. 区分 VPN 模式与仅本地代理模式；前者接管所选应用的网络，后者需要应用显式使用代理。
4. 分别在 native Termux 与 guest 测试 DNS/TLS/HTTP，比较国内与目标站点结果；不要把连通性问题归因于 Chromium 安装失败。
5. 如果代理可连接但浏览器仍失败，检查 Chromium 的显式代理、已有进程参数、DNS、IPv4/IPv6、系统时间/证书与上游节点。

```bash
# 主机只读查看 VPN 类型与应用状态
python skills/termux/scripts/network_doctor.py --adb /path/to/adb --serial SERIAL
# native / guest 分别执行；不输出代理环境变量中的凭据
python /path/to/skills/termux/scripts/network_doctor.py --check-network
```

本工具只检查候选本地端口与连接状态，不读取订阅、节点密钥、登录缓存或代理密码。默认端口是探测候选，不是已确认配置；不要未经检查固定为 10809。

## VPN 模式

Chromium 没有 `--proxy-server` 不代表它绕过系统 VPN。先用 Android VPN 状态和应用路由判断；终端 curl 的 `--noproxy '*'` 仅禁用应用层代理，也仍可能走系统 VPN。

本次排障案例为 v2rayNG 安装但未运行、无活动系统 VPN、候选代理端口未监听；native 与 guest 访问百度正常，Google 超时。这是已观察到的案例，不能写成每次 Google 不通的固定原因。

参见 [Android 分应用 VPN](https://developer.android.com/develop/connectivity/vpn#per-app)、[v2rayNG 模式说明](https://github.com/2dust/v2rayNG/wiki/Mode)。不要未经用户意图切换节点、导入订阅或重写整个 VPN 策略。

## 仅代理模式

确认实际监听地址/端口和协议，再测试，例如：

```bash
curl --proxy socks5h://127.0.0.1:PORT --connect-timeout 4 --max-time 10 -I https://www.google.com
```

socks5h 让代理侧解析域名，可用于区分本地 DNS 问题。明确需要 Chromium 显式代理时再修改其自有包装器或专用配置，并处理已有浏览器进程继续复用旧参数的情况；保留原标签页，不随意杀进程。

环境代理不是所有应用都会自动读取的统一设置；不要以 export 成功代替应用真实验证。NO_PROXY 应包含 localhost、127.0.0.1、::1，保护原生 API/其他本地服务的环回访问。

## DNS 与 SSH 路由

检查当前 guest `/etc/resolv.conf` 和 native 的解析结果；固定公共 DNS 可能被当地网络阻断。优先定位解析与连接的具体阶段，再决定是否使用 VPN DNS、代理端解析或本地可信解析器；不覆盖未知用户 DNS 配置。

重叠 VPN/LAN 路由可能让主机 SSH 走错网卡。必要时使用主机 `ssh -b SOURCE_IP`，保持严格主机指纹校验；不要用 ADB forward 代替最终 LAN 可达性。VPN 地址的息屏测试继续遵守原生参考文档的首次入站与 keepalive 验证流程。
