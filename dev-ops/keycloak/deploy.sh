#!/usr/bin/env bash
#
# 部署带有仓库自定义主题和 provider 挂载的 Keycloak 容器。
# 这里没有模板渲染步骤，包装脚本主要负责校验 bootstrap 管理员凭据并启动服务。

set -euo pipefail

SERVICE_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=sh/lib/common.sh
source "${SERVICE_DIR}/../sh/lib/common.sh"

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage_header
  echo
  echo "Deploy the Keycloak service defined in keycloak.yaml."
  exit 0
fi

load_standard_env "${SERVICE_DIR}"
ensure_value KEYCLOAK_IMAGE
ensure_value KEYCLOAK_ADMIN_PASSWORD
run_compose_stack "${SERVICE_DIR}" "keycloak.yaml"
