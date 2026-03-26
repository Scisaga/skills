#!/usr/bin/env bash
#
# 部署独立的 MySQL 栈。
# 这个包装脚本主要用于统一配置加载方式和必要变量校验。

set -euo pipefail

SERVICE_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=sh/lib/common.sh
source "${SERVICE_DIR}/../sh/lib/common.sh"

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage_header
  echo
  echo "Deploy the MySQL stack defined in mysql.yaml."
  exit 0
fi

load_standard_env "${SERVICE_DIR}"
ensure_value MYSQL_IMAGE
ensure_value MYSQL_ROOT_PASSWORD
run_compose_stack "${SERVICE_DIR}" "mysql.yaml"
