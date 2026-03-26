#!/usr/bin/env bash
#
# 部署单容器版 WordPress 栈。
# 这个包装脚本为简单服务统一了 env 加载和 compose 校验流程。

set -euo pipefail

SERVICE_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=sh/lib/common.sh
source "${SERVICE_DIR}/../sh/lib/common.sh"

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage_header
  echo
  echo "Deploy the WordPress container defined in wordpress.yaml."
  exit 0
fi

load_standard_env "${SERVICE_DIR}"
ensure_value WORDPRESS_IMAGE
ensure_value WORDPRESS_HTTP_PORT
run_compose_stack "${SERVICE_DIR}" "wordpress.yaml"
