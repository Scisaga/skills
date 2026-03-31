#!/usr/bin/env bash
#
# 部署 Keycloak 容器。
# 这里没有模板渲染步骤，包装脚本主要负责校验 bootstrap 管理员凭据并启动服务。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/shared/lib/common.sh
source "${SCRIPT_DIR}/../../shared/lib/common.sh"
SERVICE_ASSETS_DIR="$(service_assets_dir "keycloak")"

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage_header
  echo
  echo "Deploy the Keycloak service defined in keycloak.yaml."
  exit 0
fi

load_standard_env "${SERVICE_ASSETS_DIR}"
ensure_value KEYCLOAK_IMAGE
ensure_value KEYCLOAK_ADMIN_PASSWORD
run_compose_stack "${SERVICE_ASSETS_DIR}" "keycloak.yaml"
