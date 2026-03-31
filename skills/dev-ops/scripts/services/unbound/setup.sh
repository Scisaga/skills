#!/usr/bin/env bash
#
# 一个主机级辅助脚本：既部署 Unbound，也把 /etc/resolv.conf 指向它。
# 只应在希望“宿主机自身也通过 Unbound 解析 DNS”的机器上使用。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/shared/lib/common.sh
source "${SCRIPT_DIR}/../../shared/lib/common.sh"
SERVICE_ASSETS_DIR="$(service_assets_dir "unbound")"

print_help() {
  usage_header
  cat <<EOF

Also updates /etc/resolv.conf to point to the local unbound instance.
This entrypoint disables systemd-resolved before deployment so port 53 can be claimed by unbound.
EOF
}

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  print_help
  exit 0
fi

load_standard_env "${SERVICE_ASSETS_DIR}"

# 先关闭默认的 resolver 管理器，避免它继续覆盖 /etc/resolv.conf。
sudo systemctl disable --now systemd-resolved
sudo rm -f /etc/resolv.conf

# 让宿主机优先使用本地 Unbound，再保留一个上游回退 DNS。
sudo tee /etc/resolv.conf >/dev/null <<EOF
nameserver ${NET_DNS_RESOLVER:-127.0.0.1}
nameserver ${NET_UPSTREAM_DNS_PRIMARY:-8.8.8.8}
EOF

# 容器部署部分复用面向 compose 的 deploy 包装脚本。
"${SCRIPT_DIR}/deploy.sh"

echo "Current /etc/resolv.conf content:"
cat /etc/resolv.conf
