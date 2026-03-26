# Unbound 记录维护

当任务涉及 `unbound/` 目录中的本地域名、PTR、条件转发或上游解析器时，读取本文件。

## 文件职责

- `unbound/.env.example`
  - 只放容器镜像、端口和宿主机 `/etc/resolv.conf` 相关的通用参数。
- `unbound/local-records.conf`
  - 放本地权威记录。
  - 建议从 `unbound/local-records.conf.example` 复制生成。
- `unbound/forward-zones.conf`
  - 放默认上游解析器和条件转发规则。
  - 建议从 `unbound/forward-zones.conf.example` 复制生成。

## 部署前准备

- Unbound 默认要绑定宿主机 `53/tcp` 和 `53/udp`。
- 如果宿主机上已经运行 `systemd-resolved`、`dnsmasq`、`named` 或其他本地 DNS 服务，部署前要先停掉，否则容器会端口冲突。
- 若希望脚本自动处理这件事，使用 `unbound/setup.sh`。
  - 这个入口会先执行 `systemctl disable --now systemd-resolved`
  - 然后重写 `/etc/resolv.conf`
  - 最后再调用 `./deploy.sh`
- 如果只执行 `unbound/deploy.sh`，默认不会替你关闭本机 DNS 服务。

## 记录维护方式

- A / AAAA：
  - `local-data: "git.example.com. A 10.0.0.10"`
  - `local-data: "git-v6.example.com. AAAA 2001:db8::10"`
- PTR：
  - `local-data-ptr: "10.0.0.10 git.example.com"`
- CNAME：
  - `local-data: "registry.example.com. CNAME git.example.com."`
- MX：
  - `local-data: "example.com. MX 10 mail.example.com."`
- TXT：
  - `local-data: "example.com. TXT \"v=spf1 include:_spf.example.com ~all\""`
- 整个私有 zone：
  - `local-zone: "internal.example." static`

## 上游与条件转发

- 默认递归上游：
  - `forward-zone` + `name: .`
- 带 TLS 的上游：
  - `forward-addr: 1.1.1.1@853#cloudflare-dns.com`
- 条件转发：
  - `forward-zone`
  - `name: internal.example.`
  - `forward-addr: 10.0.0.53`

## 维护建议

- 不要把真实内网 IP、私有域名或业务域名提交到版本控制。
- 真实记录写入 `local-records.conf` 和 `forward-zones.conf`，这两个文件应只保留在本机或远端目标主机。
- 修改记录后，先执行 `cd unbound && docker compose -f unbound.yaml config`，再运行 `./deploy.sh`。
