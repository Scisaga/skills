#!/usr/bin/env bash
#
# 安装 systemd oneshot 服务，使宿主机通过 wg-easy 容器访问 VPN 客户端子网。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/shared/lib/common.sh
source "${SCRIPT_DIR}/../../shared/lib/common.sh"
SERVICE_ASSETS_DIR="$(service_assets_dir "wireguard")"

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage_header
  echo
  echo "Host-side entrypoint: install a persistent route to the wg-easy VPN subnet."
  exit 0
fi

load_env_with_example "${SERVICE_ASSETS_DIR}"
ensure_value WG_CONTAINER_NAME
ensure_value WG_DOCKER_IPV4_ADDRESS
ensure_value WG_HOST_ROUTE_CIDR
ensure_value WG_HOST_ROUTE_WAIT_SECONDS
require_cmd install
require_cmd systemctl

case "${WG_HOST_ROUTE_WAIT_SECONDS}" in
  ''|*[!0-9]*) die "WG_HOST_ROUTE_WAIT_SECONDS must be an integer" ;;
esac

tmp_env="$(mktemp)"
trap 'rm -f "${tmp_env}"' EXIT
printf '%s\n' \
  "WG_CONTAINER_NAME=${WG_CONTAINER_NAME}" \
  "WG_CONTAINER_IPV4=${WG_DOCKER_IPV4_ADDRESS}" \
  "WG_HOST_ROUTE_CIDR=${WG_HOST_ROUTE_CIDR}" \
  "WG_HOST_ROUTE_WAIT_SECONDS=${WG_HOST_ROUTE_WAIT_SECONDS}" \
  > "${tmp_env}"

sudo install -m 0755 "${SERVICE_ASSETS_DIR}/wg-easy-host-route" /usr/local/sbin/wg-easy-host-route
sudo install -m 0644 "${SERVICE_ASSETS_DIR}/wg-easy-host-route.service" /etc/systemd/system/wg-easy-host-route.service
sudo install -m 0600 "${tmp_env}" /etc/default/wg-easy-host-route
sudo systemctl daemon-reload
sudo systemctl enable --now wg-easy-host-route.service
sudo systemctl --no-pager --full status wg-easy-host-route.service
