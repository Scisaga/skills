#!/usr/bin/env bash
#
# 部署当前目录下的 MinIO 栈。
# 这个包装脚本比较薄，只负责加载配置、校验镜像与 root 凭据，然后调用 compose。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/shared/lib/common.sh
source "${SCRIPT_DIR}/../../shared/lib/common.sh"
SERVICE_ASSETS_DIR="$(service_assets_dir "minio")"

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage_header
  echo
  echo "Deploy the MinIO stack defined in docker-compose.yml."
  exit 0
fi

load_standard_env "${SERVICE_ASSETS_DIR}"
ensure_value MINIO_IMAGE
ensure_value MINIO_ROOT_USER
ensure_value MINIO_ROOT_PASSWORD
run_compose_stack "${SERVICE_ASSETS_DIR}" "docker-compose.yml"
