#!/usr/bin/env bash
#
# 部署单节点 InfluxDB 栈。
# 由于这个服务没有模板文件，这个包装脚本只负责加载 env、校验必要密钥并启动 compose。

set -euo pipefail

SERVICE_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=sh/lib/common.sh
source "${SERVICE_DIR}/../sh/lib/common.sh"

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage_header
  echo
  echo "Deploy the InfluxDB service defined in single-node.yaml."
  exit 0
fi

load_standard_env "${SERVICE_DIR}"
ensure_value INFLUXDB_IMAGE
ensure_value INFLUXDB_PASSWORD
ensure_value INFLUXDB_TOKEN
run_compose_stack "${SERVICE_DIR}" "single-node.yaml"
