#!/usr/bin/env bash
#
# 安装并配置一个主机级的出站代理辅助节点。
# 这个脚本会同时处理三层能力：
# 1. 为局域网 / VPN 客户端提供 Tinyproxy
# 2. 开启 WireGuard 相关内核转发
# 3. 配置 Cloudflare WARP 作为出口链路
# 由于它会直接修改主机系统文件，所以保留命令式安装方式。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=sh/lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

# 默认值针对当前以 VPN 为中心的网络拓扑，但都可以被服务目录配置、shell env 或 CLI 覆盖。
PROXY_PORT="${PROXY_PORT:-8888}"
PROXY_ALLOWED_CIDR="${PROXY_ALLOWED_CIDR:-10.6.0.0/24}"
WARP_EXCLUDED_ROUTE="${WARP_EXCLUDED_ROUTE:-10.6.0.0/16}"
WIREGUARD_INTERFACE_NAME="${WIREGUARD_INTERFACE_NAME:-wg6}"

# help 只展示最高频的开关，更多调优项继续来自 env。
print_help() {
  usage_header
  cat <<EOF

Usage: $(basename "$0") [--proxy-port 8888] [--allow-cidr 10.6.0.0/24]

Installs tinyproxy, enables WireGuard forwarding, and configures Cloudflare WARP.
EOF
}

# 仅解析少量 CLI 覆盖项，其余参数交给 env 文件统一管理。
while [ "$#" -gt 0 ]; do
  case "$1" in
    --proxy-port)
      PROXY_PORT="$2"
      shift 2
      ;;
    --allow-cidr)
      PROXY_ALLOWED_CIDR="$2"
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

load_standard_env "${SCRIPT_DIR}"

# 先安装主机依赖，后续步骤就可以默认相关命令已经存在。
sudo apt-get update
sudo apt-get install -y tinyproxy wireguard resolvconf curl gpg lsb-release ufw

# 直接重写 Tinyproxy 配置文件，保持每次执行后的结果可预测。
sudo tee /etc/tinyproxy/tinyproxy.conf >/dev/null <<EOF
User tinyproxy
Group tinyproxy
Port ${PROXY_PORT}
Timeout 600

DefaultErrorFile "/usr/share/tinyproxy/default.html"
StatFile "/usr/share/tinyproxy/stats.html"
Logfile "/var/log/tinyproxy/tinyproxy.log"

LogLevel Error
PidFile "/run/tinyproxy/tinyproxy.pid"

MaxClients 100
MinSpareServers 5
MaxSpareServers 20
StartServers 10
MaxRequestsPerChild 0

Allow 127.0.0.1
Allow ::1
Allow ${PROXY_ALLOWED_CIDR}

ConnectPort 80
ConnectPort ${PROXY_PORT}
ConnectPort 443
ConnectPort 563
EOF

# 应用代理服务和运行时防火墙变更。
sudo systemctl restart tinyproxy
sudo ufw allow from "${PROXY_ALLOWED_CIDR}"

# 开启内核转发，让 WireGuard 客户端可以访问上游网络。
sudo tee /etc/sysctl.d/wg.conf >/dev/null <<EOF
net.ipv4.ip_forward = 1
net.ipv6.conf.all.forwarding = 1
EOF
sudo sysctl --system >/dev/null

# 若接口配置尚不存在，则先落一个占位配置，方便后续接入 wg-easy 生成内容。
sudo mkdir -p /etc/wireguard
sudo tee "/etc/wireguard/${WIREGUARD_INTERFACE_NAME}.conf" >/dev/null <<EOF
<wg config generate by wg-easy>
EOF
sudo systemctl enable "wg-quick@${WIREGUARD_INTERFACE_NAME}"
sudo systemctl restart "wg-quick@${WIREGUARD_INTERFACE_NAME}"

# 注册 Cloudflare 软件源并连接 WARP。
curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg | sudo gpg --yes --dearmor --output /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] https://pkg.cloudflareclient.com/ $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/cloudflare-client.list >/dev/null
sudo apt-get update
sudo apt-get install -y cloudflare-warp

# WARP 相关命令允许部分已初始化状态，因此重复执行仍然可用。
sudo warp-cli register || true
sudo warp-cli add-excluded-route "${WARP_EXCLUDED_ROUTE}" || true
sudo warp-cli connect || true
