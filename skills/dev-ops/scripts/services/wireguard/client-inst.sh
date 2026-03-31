#!/usr/bin/env bash
#
# 安装主机级 WireGuard 客户端配置。
# 脚本会把给定配置复制到 /etc/wireguard，开启转发，
# 通过 systemd 启动接口，并安装一个周期性的 DNS 重新解析任务。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/shared/lib/common.sh
source "${SCRIPT_DIR}/../../shared/lib/common.sh"
SERVICE_ASSETS_DIR="$(service_assets_dir "wireguard")"

WG_INTERFACE_NAME="${WG_INTERFACE_NAME:-${1:-}}"
WG_CONFIG_SOURCE="${WG_CONFIG_SOURCE:-${2:-}}"
WG_RERESOLVE_CRON="${WG_RERESOLVE_CRON:-*/2 * * * *}"

# CLI 保持简洁，因为这个脚本通常直接在目标主机上运行。
print_help() {
  usage_header
  cat <<EOF

Usage: $(basename "$0") <wg-interface> <config-file>

Client-side entrypoint:
  - installs wireguard-tools on the host
  - copies an existing client .conf into /etc/wireguard
  - enables wg-quick@<interface>

This script does not deploy the wg-easy server.
EOF
}

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  print_help
  exit 0
fi

load_standard_env "${SERVICE_ASSETS_DIR}"
ensure_value WG_INTERFACE_NAME
ensure_value WG_CONFIG_SOURCE
[ -f "${WG_CONFIG_SOURCE}" ] || die "config file not found: ${WG_CONFIG_SOURCE}"

# 以 wg-quick 期望的严格权限安装配置文件。
sudo install -m 600 "${WG_CONFIG_SOURCE}" "/etc/wireguard/${WG_INTERFACE_NAME}.conf"
sudo apt-get update
sudo apt-get install -y wireguard resolvconf

# 开启转发，让主机在配置需要时可以作为网关使用。
sudo tee /etc/sysctl.d/wg.conf >/dev/null <<EOF
net.ipv4.ip_forward = 1
net.ipv6.conf.all.forwarding = 1
EOF
sudo sysctl --system >/dev/null

sudo systemctl enable "wg-quick@${WG_INTERFACE_NAME}"
sudo systemctl restart "wg-quick@${WG_INTERFACE_NAME}"

# 内置 helper 用于在远端地址变更时，持续刷新基于域名的 peer 解析结果。
sudo ln -sf /usr/share/doc/wireguard-tools/examples/reresolve-dns/reresolve-dns.sh /opt/reresolve-dns.sh
sudo chmod a+x /opt/reresolve-dns.sh

new_job="${WG_RERESOLVE_CRON} /opt/reresolve-dns.sh ${WG_INTERFACE_NAME}"
if crontab -l 2>/dev/null | grep -Fq "${new_job}"; then
  log "Cron job already exists."
else
  (crontab -l 2>/dev/null; echo "${new_job}") | crontab -
fi
