#!/usr/bin/env bash
#
# 部署 Redis 栈，包括 exporter 和 RedisInsight。
# 由于没有模板渲染步骤，这里主要负责加载配置并校验镜像相关变量。

set -euo pipefail

SERVICE_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=sh/lib/common.sh
source "${SERVICE_DIR}/../sh/lib/common.sh"

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage_header
  echo
  echo "Deploy the Redis stack defined in redis.yaml."
  exit 0
fi

load_standard_env "${SERVICE_DIR}"
ensure_value REDIS_IMAGE
ensure_value REDIS_EXPORTER_IMAGE
ensure_value REDIS_INSIGHT_IMAGE
run_compose_stack "${SERVICE_DIR}" "redis.yaml"
