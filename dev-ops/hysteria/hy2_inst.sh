#!/usr/bin/env bash
#
# 直接在主机上安装并配置 Hysteria 2 服务端。
# 脚本会固定二进制版本、写入运行配置、开启 BBR、增加 UDP 转发规则，
# 并注册独立的 systemd 单元。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=sh/lib/common.sh
source "${SCRIPT_DIR}/../sh/lib/common.sh"

readonly HY2_INSTALL_DIR="/etc/hysteria"
readonly HY2_SERVER_CONFIG="/etc/hysteria/config.yaml"
readonly HY2_BINARY_PATH="/usr/local/bin/hysteria"
readonly HY2_BBR_SYSCTL="/etc/sysctl.d/90-hysteria-bbr.conf"
readonly HY2_SYSTEMD_UNIT="/etc/systemd/system/hy2-server.service"

hy2_version="2.7.1"
hy2_domain=""
hy2_password=""
hy2_acme_email=""
hy2_obfs_password=""
hy2_udp_port_range="20000-30000"
hy2_listen_port="443"
hy2_masquerade_url="http://127.0.0.1:8080"

# 这类一次性主机安装脚本优先走 CLI 参数，避免再维护额外的 .env 文件。
print_help() {
  cat <<EOF

Usage: $(basename "$0") [options]

Options:
  --domain example.com
  --password secret
  --email ops@example.com
  --version 2.7.1
  --obfs-password secret
  --udp-range 20000-30000
  --listen-port 443
  --masquerade-url http://127.0.0.1:8080
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

# 只保留命令行入口，保证脚本拿出来就能独立执行。
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
    --email)
      hy2_acme_email="$2"
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
    --listen-port)
      hy2_listen_port="$2"
      shift 2
      ;;
    --masquerade-url)
      hy2_masquerade_url="$2"
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
prompt_value hy2_domain "请输入解析到此 IP 的域名"
prompt_value hy2_password "请输入连接密码" true
prompt_value hy2_acme_email "请输入 ACME 邮箱"
[ -n "${hy2_obfs_password}" ] || read -r -s -p "如需启用 obfs 请输入密码（留空则禁用）: " hy2_obfs_password; printf '\n'

ensure_value hy2_domain
ensure_value hy2_password
ensure_value hy2_acme_email

# 上游提供独立二进制，因此这里直接下载固定版本并安装。
sudo mkdir -p "${HY2_INSTALL_DIR}"
sudo curl -fsSL "$(download_url_for_arch "${hy2_version}")" -o "${HY2_BINARY_PATH}"
sudo chmod +x "${HY2_BINARY_PATH}"

# 通过独立的 sysctl drop-in 开启 BBR，重复执行也能保持幂等。
sudo tee "${HY2_BBR_SYSCTL}" >/dev/null <<EOF
net.core.default_qdisc=fq
net.ipv4.tcp_congestion_control=bbr
EOF
sudo sysctl --system >/dev/null

# 根据命令行参数和交互输入生成完整服务端配置。
sudo tee "${HY2_SERVER_CONFIG}" >/dev/null <<EOF
listen: :${hy2_listen_port}
udpHop:
  portRange: ${hy2_udp_port_range}
acme:
  domains:
    - ${hy2_domain}
  email: ${hy2_acme_email}
auth:
  type: password
  password: ${hy2_password}
masquerade:
  type: proxy
  proxy:
    url: ${hy2_masquerade_url}
    rewriteHost: true
EOF

if [ -n "${hy2_obfs_password}" ]; then
  sudo tee -a "${HY2_SERVER_CONFIG}" >/dev/null <<EOF
obfs:
  type: salamander
  salamander:
    password: ${hy2_obfs_password}
EOF
fi

# 把 UDP hop 端口段重定向到主监听端口，对外保持单一入口。
iface="$(ip route get 8.8.8.8 | awk '{print $5; exit}')"
sudo iptables -t nat -C PREROUTING -i "${iface}" -p udp --dport "${hy2_udp_port_range/:/-}" -j REDIRECT --to-ports "${hy2_listen_port}" 2>/dev/null || \
  sudo iptables -t nat -A PREROUTING -i "${iface}" -p udp --dport "${hy2_udp_port_range/:/-}" -j REDIRECT --to-ports "${hy2_listen_port}"

# 持久化防火墙规则，并把长期运行的服务注册给 systemd。
sudo apt-get update
sudo apt-get install -y iptables-persistent
sudo netfilter-persistent save

sudo tee "${HY2_SYSTEMD_UNIT}" >/dev/null <<EOF
[Unit]
Description=Hysteria 2 Server
After=network.target

[Service]
ExecStart=${HY2_BINARY_PATH} server -c ${HY2_SERVER_CONFIG}
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# 初次安装完成后，后续生命周期交给 systemd 管理。
sudo systemctl daemon-reload
sudo systemctl enable --now hy2-server
