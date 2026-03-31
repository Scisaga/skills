#!/usr/bin/env bash
#
# 在主机上安装一个 Hysteria 2 客户端网关。
# 脚本会解析服务端域名、安装固定版本客户端二进制，
# 写入同时暴露 HTTP / SOCKS 监听的配置，并注册 systemd 服务。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/shared/lib/common.sh
source "${SCRIPT_DIR}/../../shared/lib/common.sh"

readonly HY2_INSTALL_DIR="/etc/hysteria"
readonly HY2_CLIENT_CONFIG="/etc/hysteria/client.yaml"
readonly HY2_BINARY_PATH="/usr/local/bin/hysteria"
readonly HY2_SYSTEMD_UNIT="/etc/systemd/system/hy2-client.service"

hy2_version="2.7.1"
hy2_domain=""
hy2_password=""
hy2_obfs_password=""
hy2_udp_port_range="20000-30000"
hy2_http_proxy_port="8888"
hy2_socks5_port="8887"

# 保持纯 CLI 入口，避免客户端安装还要维护单独的 .env 文件。
print_help() {
  cat <<EOF

Usage: $(basename "$0") [options]

Options:
  --domain example.com
  --password secret
  --version 2.7.1
  --obfs-password secret
  --udp-range 20000-30000
  --http-port 10809
  --socks5-port 10808
  --help
EOF
}

download_url_for_arch() {
  local version="$1"
  local arch
  arch="$(uname -m)"
  case "${arch}" in
    x86_64) echo "https://github.com/apernet/hysteria/releases/download/app%2Fv${version}/hysteria-linux-amd64" ;;
    aarch64|arm64) echo "https://github.com/apernet/hysteria/releases/download/app%2Fv${version}/hysteria-linux-arm64" ;;
    *) die "unsupported architecture: ${arch}" ;;
  esac
}

prompt_value() {
  local name="$1"
  local prompt="$2"
  local hidden="${3:-false}"

  [ -n "${!name:-}" ] && return 0

  if [ "${hidden}" = "true" ]; then
    read -r -s -p "${prompt}: " "${name}"
    printf '\n'
  else
    read -r -p "${prompt}: " "${name}"
  fi
}

# 单次主机安装直接靠 CLI 参数和默认值驱动。
while [ "$#" -gt 0 ]; do
  case "$1" in
    --domain)
      hy2_domain="$2"
      shift 2
      ;;
    --password)
      hy2_password="$2"
      shift 2
      ;;
    --obfs-password)
      hy2_obfs_password="$2"
      shift 2
      ;;
    --version)
      hy2_version="$2"
      shift 2
      ;;
    --udp-range)
      hy2_udp_port_range="$2"
      shift 2
      ;;
    --http-port)
      hy2_http_proxy_port="$2"
      shift 2
      ;;
    --socks5-port)
      hy2_socks5_port="$2"
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
prompt_value hy2_domain "请输入服务端域名"
prompt_value hy2_password "请输入连接密码" true
[ -n "${hy2_obfs_password}" ] || read -r -s -p "如需启用 obfs 请输入密码（留空则禁用）: " hy2_obfs_password; printf '\n'

ensure_value hy2_domain
ensure_value hy2_password

# 先解析一次远端地址，再把结果写入生成的客户端配置。
server_ip="$(getent ahostsv4 "${hy2_domain}" | awk 'NR==1{print $1}')"
[ -n "${server_ip}" ] || die "cannot resolve hy2_domain=${hy2_domain}"

# 安装固定版本的独立二进制。
sudo mkdir -p "${HY2_INSTALL_DIR}"
sudo curl -fsSL "$(download_url_for_arch "${hy2_version}")" -o "${HY2_BINARY_PATH}"
sudo chmod +x "${HY2_BINARY_PATH}"

# 同时暴露 HTTP 与 SOCKS5 监听，方便局域网内其他主机复用这个网关。
sudo tee "${HY2_CLIENT_CONFIG}" >/dev/null <<EOF
server: ${server_ip}:${hy2_udp_port_range}
auth: ${hy2_password}
tls:
  sni: ${hy2_domain}
bandwidth:
  up: 100 mbps
  down: 100 mbps
http:
  listen: 0.0.0.0:${hy2_http_proxy_port}
socks5:
  listen: 0.0.0.0:${hy2_socks5_port}
EOF

if [ -n "${hy2_obfs_password}" ]; then
  sudo tee -a "${HY2_CLIENT_CONFIG}" >/dev/null <<EOF
obfs:
  type: salamander
  salamander:
    password: ${hy2_obfs_password}
EOF
fi

# 通过独立 systemd 单元来托管网关进程生命周期。
sudo tee "${HY2_SYSTEMD_UNIT}" >/dev/null <<EOF
[Unit]
Description=Hysteria 2 Client
After=network.target

[Service]
ExecStart=${HY2_BINARY_PATH} client -c ${HY2_CLIENT_CONFIG}
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now hy2-client
