#!/usr/bin/env bash
#
# 部署仓库中基于 wg-easy 的 WireGuard 服务。
# 可选的路由钩子通过 env 注入，并传递给 compose 文件中的环境变量。

set -euo pipefail

SERVICE_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=sh/lib/common.sh
source "${SERVICE_DIR}/../sh/lib/common.sh"

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage_header
  echo
  echo "Server-side entrypoint: deploy the WireGuard Easy stack defined in wg-easy.yaml."
  echo "Use generate-wg-password-hash.sh first to produce WG_PASSWORD_HASH."
  echo "This script does not install a WireGuard client on the host."
  exit 0
fi

load_standard_env "${SERVICE_DIR}"
ensure_value WG_EASY_IMAGE
ensure_value WG_HOST
ensure_value WG_PASSWORD_HASH
run_compose_stack "${SERVICE_DIR}" "wg-easy.yaml"
