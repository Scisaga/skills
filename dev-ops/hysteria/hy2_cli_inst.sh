#!/usr/bin/env bash
#
# 在主机上安装一个 Hysteria 2 客户端网关。
# 脚本会解析服务端域名、安装固定版本客户端二进制，
# 写入同时暴露 HTTP / SOCKS 监听的配置，并注册 systemd 服务。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=sh/lib/common.sh
source "${SCRIPT_DIR}/../sh/lib/common.sh"

HY2_VERSION="${HY2_VERSION:-2.6.5}"
HY2_DOMAIN="${HY2_DOMAIN:-}"
HY2_PASSWORD="${HY2_PASSWORD:-}"
HY2_UDP_PORT_RANGE="${HY2_UDP_PORT_RANGE:-20000-30000}"
HY2_CLIENT_CONFIG="${HY2_CLIENT_CONFIG:-/etc/hysteria/client.yaml}"
HY2_HTTP_PROXY_PORT="${HY2_HTTP_PROXY_PORT:-8888}"
HY2_SOCKS5_PORT="${HY2_SOCKS5_PORT:-8887}"

# 保持纯 CLI 入口，避免客户端安装还要维护单独的 .env 文件。
print_help() {
  cat <<EOF

Usage: $(basename "$0") [options]

Options:
  --domain example.com
  --password secret
  --version 2.6.5
  --udp-range 20000-30000
  --client-config /etc/hysteria/client.yaml
  --http-port 10809
  --socks5-port 10808
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

# 单次主机安装直接靠 CLI 参数和默认值驱动。
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
    --version)
      HY2_VERSION="$2"
      shift 2
      ;;
    --udp-range)
      HY2_UDP_PORT_RANGE="$2"
      shift 2
      ;;
    --client-config)
      HY2_CLIENT_CONFIG="$2"
      shift 2
      ;;
    --http-port)
      HY2_HTTP_PROXY_PORT="$2"
      shift 2
      ;;
    --socks5-port)
      HY2_SOCKS5_PORT="$2"
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

# 在目标主机上手动执行时，允许回退到交互式输入。
[ -n "${HY2_DOMAIN}" ] || read -r -p "请输入服务端域名: " HY2_DOMAIN
[ -n "${HY2_PASSWORD}" ] || read -r -p "请输入连接密码: " HY2_PASSWORD

ensure_value HY2_DOMAIN
ensure_value HY2_PASSWORD

# 先解析一次远端地址，再把结果写入生成的客户端配置。
server_ip="$(getent ahostsv4 "${HY2_DOMAIN}" | awk 'NR==1{print $1}')"
[ -n "${server_ip}" ] || die "cannot resolve HY2_DOMAIN=${HY2_DOMAIN}"

# 安装固定版本的独立二进制。
sudo mkdir -p /etc/hysteria
sudo curl -fsSL "$(download_url_for_arch)" -o /usr/local/bin/hysteria
sudo chmod +x /usr/local/bin/hysteria

# 同时暴露 HTTP 与 SOCKS5 监听，方便局域网内其他主机复用这个网关。
sudo tee "${HY2_CLIENT_CONFIG}" >/dev/null <<EOF
server: ${server_ip}:${HY2_UDP_PORT_RANGE}
auth: ${HY2_PASSWORD}
tls:
  sni: ${HY2_DOMAIN}
bandwidth:
  up: 10 mbps
  down: 10 mbps
http:
  listen: 0.0.0.0:${HY2_HTTP_PROXY_PORT}
socks5:
  listen: 0.0.0.0:${HY2_SOCKS5_PORT}
EOF

# 通过独立 systemd 单元来托管网关进程生命周期。
sudo tee /etc/systemd/system/hy2-client.service >/dev/null <<EOF
[Unit]
Description=Hysteria 2 Client
After=network.target

[Service]
ExecStart=/usr/local/bin/hysteria client -c ${HY2_CLIENT_CONFIG}
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now hy2-client
