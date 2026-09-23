#!/usr/bin/env bash
#
# 部署仓库中基于 wg-easy v15 的 WireGuard 服务。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/shared/lib/common.sh
source "${SCRIPT_DIR}/../../shared/lib/common.sh"
SERVICE_ASSETS_DIR="$(service_assets_dir "wireguard")"

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage_header
  echo
  echo "Server-side entrypoint: deploy the WireGuard Easy stack defined in wg-easy.yaml."
  echo "The v15 administrator and VPN settings are completed in the first-run Web UI."
  echo "This script does not install a WireGuard client on the host."
  exit 0
fi

load_standard_env "${SERVICE_ASSETS_DIR}"
ensure_value WG_EASY_IMAGE
ensure_value WG_EASY_BASE_IMAGE
ensure_value WG_PASSWORD_MIN_LENGTH
ensure_value WG_CONTAINER_NAME
ensure_value WG_PORT
ensure_value WG_WEB_BIND
ensure_value WG_WEB_PORT
ensure_value WG_DOCKER_IPV4_ADDRESS
ensure_value WG_DOCKER_IPV4_SUBNET
ensure_value WG_DOCKER_IPV6_ADDRESS
ensure_value WG_DOCKER_IPV6_SUBNET

case "${WG_PASSWORD_MIN_LENGTH}" in
  ''|*[!0-9]*) die "WG_PASSWORD_MIN_LENGTH must be an integer" ;;
esac
[ "${WG_PASSWORD_MIN_LENGTH}" -ge 8 ] || die "WG_PASSWORD_MIN_LENGTH must be at least 8"
[ "${WG_PASSWORD_MIN_LENGTH}" -le 128 ] || die "WG_PASSWORD_MIN_LENGTH must not exceed 128"

if [ "${WG_UI_INSECURE:-false}" = "true" ] && [ "${WG_WEB_BIND}" != "127.0.0.1" ] && [ "${WG_WEB_BIND}" != "::1" ]; then
  die "WG_UI_INSECURE=true is only allowed when WG_WEB_BIND is a loopback address"
fi

run_compose_stack "${SERVICE_ASSETS_DIR}" "wg-easy.yaml"
