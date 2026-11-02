# DDNS 工作流

阿里云 DDNS 同步与 `acme.sh` 证书获取入口位于 `scripts/services/ddns/`，配置模板和 systemd 单元位于 `assets/services/ddns/`。

## 地址来源与凭据

- `DDNS_TARGETS='example.com|AAAA|home'`：只同步指定域名、记录类型与 RR；多组用分号分隔，同组多个 RR 用逗号分隔。
- `DDNS_INTERFACE=eth0`：直接读取 Linux 网卡的稳定公网地址。AAAA 排除链路本地、ULA、临时、失效、tentative 与 DAD 失败的地址；多于一个合格地址时停止写入。A 不接受网卡的内网 IPv4，不能把局域网地址发布为公网记录。
- `DDNS_IPV4_SOURCE=auto|interface|public`：默认保持上面的行为；NAT 场景显式选择 `public`，通过 `DDNS_INTERFACE` 直连查询出口 IPv4。该请求固定禁用代理、忽略 `.curlrc`、强制 IPv4；AAAA 继续读取网卡地址。
- 公网查询使用 `DDNS_IPV4_LOOKUP_URL` / `DDNS_IPV6_LOOKUP_URL`；默认 IPv4 服务为 `https://ip.3322.net`，返回纯 IP。可用独立来源核对出口地址与归属地，例如 `https://myip.ipip.net`，但带地区文字的响应不能直接作为纯 IP 查询地址。
- `DDNS_LOOKUP_DNS_SERVER` 可选指定直连 DNS（例如局域网网关），用于解析查询服务。脚本通过 `dig` 动态获取地址，再传给 curl 的 `--resolve`，保持原域名的 TLS 校验；无需修改系统 DNS。查询失败时停止写入，不会退回使用代理获取公网 IP。
- DNS API 调用与公网 IP 探测分别处理代理：API 可沿用主机代理，公网 IP 探测始终绕过代理。
- `ALIYUN_ACCESS_KEY_ID`、`ALIYUN_ACCESS_KEY_SECRET` 同时提供时，默认通过 Python 标准库直接调用 HTTPS DNS API，采用官方 ACS3-HMAC-SHA256 签名，不需要安装 CLI 或 SDK。也接受对应的 `ALIBABA_CLOUD_ACCESS_KEY_*` 变量。
- `DDNS_API_BACKEND=auto|rpc|cli`：默认自动选择，有环境凭据时用 `rpc`，否则使用 `ALIYUN_CLI_PROFILE`。显式选择 `cli` 并提供环境凭据时，映射为官方 CLI 环境变量并设置 `ALIBABA_CLOUD_IGNORE_PROFILE=TRUE`，不创建含密钥的 profile。
- `DDNS_LINE=default` 只匹配对应线路；重复记录或禁用记录会报错。新记录采用 `DDNS_TTL=600`，更新已有记录保留其 TTL。写入后通过 `DescribeDomainRecordInfo` 回读验证。

脚本仅加载服务资产目录下的 `.env`、`.env.local`；进程变量也可由 systemd 的 `EnvironmentFile` 提供。不会把 `.env.example` 当成真实配置，也不会自动读取仓库根目录 `.env`。凭据文件始终保持 root 专有读权限，不把真实值复制进仓库。

## 执行与预览

Linux 基础依赖：Bash 4+、Python 3、GNU `timeout`；指定网卡时还需 `iproute2`，查公网地址时需 `curl`；指定直连 DNS 时需 `dig`（Debian/Ubuntu：`apt-get install bind9-dnsutils`）。缺少依赖会直接报错。基础依赖可用 `apt-get install bash python3 coreutils iproute2 curl` 安装。

仅使用 CLI profile 或显式选择 `cli` 后端时需要阿里云 CLI。运行 `bash skills/dev-ops/scripts/run.sh service ddns install-cli.sh` 下载官方 Linux amd64/arm64 CLI 到 `/opt/aliyun-ddns/bin/`，再将该目录加入 PATH。其他系统参见[官方安装说明](https://www.alibabacloud.com/help/en/cli/install-update-alibaba-cloud-cli)，systemd 和网卡读取功能仅支持 Linux。

准备服务资产目录 `.env` 或导出对应变量，再执行：

```bash
bash skills/dev-ops/scripts/run.sh service ddns aliyun_ddns.sh --dry-run
bash skills/dev-ops/scripts/run.sh service ddns aliyun_ddns.sh
bash skills/dev-ops/scripts/run.sh service ddns certs_fetch.sh
```

`--dry-run` 会查询当前 DNS 并输出拟修改内容，完全不写记录。没有稳定公网地址、查询失败或超时时，立即返回非零，不会清空现有记录。每个 API 调用限时 `DDNS_API_TIMEOUT_SECONDS=30`。脚本不会创建或修改未列入目标的记录类型。

## systemd 持续运行

远程目录统一放在 `/opt/aliyun-ddns/`。从仓库保留以下相对结构复制文件：

```text
/opt/aliyun-ddns/
├── credentials.env -> /absolute/path/to/existing/secrets/.env
├── ddns.env
├── scripts/run.sh
├── scripts/shared/lib/common.sh
├── scripts/services/ddns/aliyun_ddns.sh
├── scripts/services/ddns/aliyun_api.py
└── scripts/services/ddns/ddns_address.py
```

`ddns.env` 只写非敏感目标配置，例如：

```bash
DDNS_TARGETS='example.com|AAAA|home'
DDNS_INTERFACE=eth0
DDNS_LINE=default
DDNS_TTL=600
DDNS_API_TIMEOUT_SECONDS=30
```

若网卡只有内网 IPv4，但同时需要同步路由器的 NAT 出口和本机 IPv6，将目标改为 `example.com|A|home;example.com|AAAA|home`，再增加 `DDNS_IPV4_SOURCE=public`。IPv4 探测会绑定上述网卡；需要绕过系统 DNS 时，再填写 `DDNS_LOOKUP_DNS_SERVER` 为实际可用的直连 DNS 地址。

已有配置可保持原文件，将非敏感网络参数另存为 `/opt/aliyun-ddns/ipv4.conf`，再在 `/etc/systemd/system/aliyun-ddns.service.d/dual-stack.conf` 的 `[Service]` 节追加 `EnvironmentFile=/opt/aliyun-ddns/ipv4.conf`。systemd 按顺序加载环境文件，后加载的同名参数覆盖前值；运行 `systemctl daemon-reload` 后启动 service 即可加载。凭据仍只读取原有文件。

使用 `credentials.env` 软链接引用已有凭据文件。不要把密钥作为命令行参数、写入 unit 文件或重新保存到 CLI profile。将仓库资产中的 `aliyun-ddns.service` 与 `aliyun-ddns.timer` 安装到 `/etc/systemd/system/`，先执行 `systemd-analyze verify`，再运行：

```bash
systemctl daemon-reload
systemctl start aliyun-ddns.service
systemctl enable --now aliyun-ddns.timer
systemctl list-timers aliyun-ddns.timer
journalctl -u aliyun-ddns.service -n 30 --no-pager
```

任务在开机网络就绪后运行，每次完成后 5 分钟再次检查；同一 service 不会重叠执行。失败记录进入 journal，下个周期继续尝试。停止定时更新使用 `systemctl disable --now aliyun-ddns.timer`。

## RAM 权限与 403

`Forbidden.RAM` 表示当前身份未获准访问对应资源。先检查 `assets/services/ddns/aliyun-ddns-policy.json`，将其中的 `example.com` 改为实际 DNS 域名，再由有权管理 RAM 的账号授予目标身份；可将资源 ARN 的账号段 `*` 收紧为主账号 ID。模板只包含四项查询、创建和更新权限，不包含删除记录或其他云产品权限。域名资源的授权规则参见[官方 RAM 定义](https://www.alibabacloud.com/help/en/dns/api-alidns-2015-01-09-ram)。

403 时脚本会停止写入，不应把失败当成已完成；首次部署应等实际试运行和写后回读通过，再启用 timer。不要通过把密钥复制到命令行或日志来排障。

## 证书配置

证书入口继续使用 `ACME_ACCOUNT_EMAIL`、`ACME_CERT_NAME`、`ACME_DOMAINS`、`ACME_CERT_DIR`、`ACME_RELOAD_CMD`。仅配置 DDNS 不会申请证书或重载业务服务。

## 官方接口

- [CLI 环境变量与 profile 优先级](https://www.alibabacloud.com/help/en/cli/environment-variables)
- [原生 HTTPS 请求与 V3 签名](https://www.alibabacloud.com/help/en/sdk/product-overview/v3-request-structure-and-signature)
- [DescribeDomainRecords](https://www.alibabacloud.com/help/en/dns/api-alidns-2015-01-09-describedomainrecords)
- [UpdateDomainRecord](https://www.alibabacloud.com/help/en/dns/api-alidns-2015-01-09-updatedomainrecord)

