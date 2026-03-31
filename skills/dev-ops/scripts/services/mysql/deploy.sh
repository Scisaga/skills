#!/usr/bin/env bash
#
# 部署独立的 MySQL 栈。
# 这个包装脚本主要用于统一配置加载方式和必要变量校验。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/shared/lib/common.sh
source "${SCRIPT_DIR}/../../shared/lib/common.sh"
SERVICE_ASSETS_DIR="$(service_assets_dir "mysql")"

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage_header
  echo
  echo "Deploy the MySQL stack defined in mysql.yaml."
  exit 0
fi

load_standard_env "${SERVICE_ASSETS_DIR}"
ensure_value MYSQL_IMAGE
ensure_value MYSQL_ROOT_PASSWORD
run_compose_stack "${SERVICE_ASSETS_DIR}" "mysql.yaml"
