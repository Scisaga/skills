#!/usr/bin/env bash
#
# 部署 Redis 栈，包括 exporter 和 RedisInsight。
# 由于没有模板渲染步骤，这里主要负责加载配置并校验镜像相关变量。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/shared/lib/common.sh
source "${SCRIPT_DIR}/../../shared/lib/common.sh"
SERVICE_ASSETS_DIR="$(service_assets_dir "redis")"

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage_header
  echo
  echo "Deploy the Redis stack defined in docker-compose.yaml."
  exit 0
fi

load_standard_env "${SERVICE_ASSETS_DIR}"
ensure_value REDIS_IMAGE
ensure_value REDIS_EXPORTER_IMAGE
ensure_value REDIS_INSIGHT_IMAGE
run_compose_stack "${SERVICE_ASSETS_DIR}" "docker-compose.yaml"
