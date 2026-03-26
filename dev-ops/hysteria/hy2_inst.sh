#!/usr/bin/env bash
#
# 直接在主机上安装并配置 Hysteria 2 服务端。
# 脚本会固定二进制版本、写入运行配置、开启 BBR、增加 UDP 转发规则，
# 并注册独立的 systemd 单元。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=sh/lib/common.sh
source "${SCRIPT_DIR}/../sh/lib/common.sh"

HY2_VERSION="${HY2_VERSION:-2.6.5}"
HY2_DOMAIN="${HY2_DOMAIN:-}"
HY2_PASSWORD="${HY2_PASSWORD:-}"
HY2_ACME_EMAIL="${HY2_ACME_EMAIL:-}"
HY2_UDP_PORT_RANGE="${HY2_UDP_PORT_RANGE:-20000-30000}"
HY2_LISTEN_PORT="${HY2_LISTEN_PORT:-443}"
HY2_MASQUERADE_URL="${HY2_MASQUERADE_URL:-http://127.0.0.1:8080}"
HY2_SERVER_CONFIG="${HY2_SERVER_CONFIG:-/etc/hysteria/config.yaml}"

# 这类一次性主机安装脚本优先走 CLI 参数，避免再维护额外的 .env 文件。
print_help() {
  cat <<EOF

Usage: $(basename "$0") [options]

Options:
  --domain example.com
  --password secret
  --email ops@example.com
  --version 2.6.5
  --udp-range 20000-30000
  --listen-port 443
  --masquerade-url http://127.0.0.1:8080
  --server-config /etc/hysteria/config.yaml
  --help
EOF
}

download_url_for_arch() {
  local arch
  arch="$(uname -m)"
  case "${arch}" in
    x86_64) echo "https://github.com/apernet/hysteria/releases/download/app%2Fv${HY2_VERSION}/hysteria-linux-amd64" ;;
    aarch64|arm64) echo "https://github.com/apernet/hysteria/releases/download/app%2Fv${HY2_VERSION}/hysteria-linux-arm64" ;;
    *) die "unsupported architecture: ${arch}" ;;
  esac
}

# 只保留命令行入口，保证脚本拿出来就能独立执行。
while [ "$#" -gt 0 ]; do
  case "$1" in
    --domain)
      HY2_DOMAIN="$2"
      shift 2
      ;;
    --password)
      HY2_PASSWORD="$2"
      shift 2
      ;;
    --email)
      HY2_ACME_EMAIL="$2"
      shift 2
      ;;
    --version)
      HY2_VERSION="$2"
      shift 2
      ;;
    --udp-range)
      HY2_UDP_PORT_RANGE="$2"
      shift 2
      ;;
    --listen-port)
      HY2_LISTEN_PORT="$2"
      shift 2
      ;;
    --masquerade-url)
      HY2_MASQUERADE_URL="$2"
      shift 2
      ;;
    --server-config)
      HY2_SERVER_CONFIG="$2"
      shift 2
      ;;
    --help|-h)
      print_help
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

# 只有在必要参数没有预先提供时，才回退到交互式输入。
[ -n "${HY2_DOMAIN}" ] || read -r -p "请输入解析到此 IP 的域名: " HY2_DOMAIN
[ -n "${HY2_PASSWORD}" ] || read -r -p "请输入连接密码: " HY2_PASSWORD
[ -n "${HY2_ACME_EMAIL}" ] || read -r -p "请输入 ACME 邮箱: " HY2_ACME_EMAIL

ensure_value HY2_DOMAIN
ensure_value HY2_PASSWORD
ensure_value HY2_ACME_EMAIL

# 上游提供独立二进制，因此这里直接下载固定版本并安装。
sudo mkdir -p /etc/hysteria
sudo curl -fsSL "$(download_url_for_arch)" -o /usr/local/bin/hysteria
sudo chmod +x /usr/local/bin/hysteria

# 通过独立的 sysctl drop-in 开启 BBR，重复执行也能保持幂等。
sudo tee /etc/sysctl.d/90-hysteria-bbr.conf >/dev/null <<EOF
net.core.default_qdisc=fq
net.ipv4.tcp_congestion_control=bbr
EOF
sudo sysctl --system >/dev/null

# 根据命令行参数和交互输入生成完整服务端配置。
sudo tee "${HY2_SERVER_CONFIG}" >/dev/null <<EOF
listen: :${HY2_LISTEN_PORT}
udpHop:
  portRange: ${HY2_UDP_PORT_RANGE}
acme:
  domains:
    - ${HY2_DOMAIN}
  email: ${HY2_ACME_EMAIL}
auth:
  type: password
  password: ${HY2_PASSWORD}
masquerade:
  type: proxy
  proxy:
    url: ${HY2_MASQUERADE_URL}
    rewriteHost: true
EOF

# 把 UDP hop 端口段重定向到主监听端口，对外保持单一入口。
iface="$(ip route get 8.8.8.8 | awk '{print $5; exit}')"
sudo iptables -t nat -C PREROUTING -i "${iface}" -p udp --dport "${HY2_UDP_PORT_RANGE/:/-}" -j REDIRECT --to-ports "${HY2_LISTEN_PORT}" 2>/dev/null || \
  sudo iptables -t nat -A PREROUTING -i "${iface}" -p udp --dport "${HY2_UDP_PORT_RANGE/:/-}" -j REDIRECT --to-ports "${HY2_LISTEN_PORT}"

# 持久化防火墙规则，并把长期运行的服务注册给 systemd。
sudo apt-get update
sudo apt-get install -y iptables-persistent
sudo netfilter-persistent save

sudo tee /etc/systemd/system/hy2-server.service >/dev/null <<EOF
[Unit]
Description=Hysteria 2 Server
After=network.target

[Service]
ExecStart=/usr/local/bin/hysteria server -c ${HY2_SERVER_CONFIG}
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# 初次安装完成后，后续生命周期交给 systemd 管理。
sudo systemctl daemon-reload
sudo systemctl enable --now hy2-server
