#!/usr/bin/env bash
#
# 部署当前目录中的 Prometheus + Grafana 栈。
# 由于 Prometheus 读取的是生成配置文件，因此必须先渲染再启动 compose。

set -euo pipefail

SERVICE_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=sh/lib/common.sh
source "${SERVICE_DIR}/../sh/lib/common.sh"

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage_header
  echo
  echo "Render Prometheus config and deploy pmth-gfn.yaml."
  exit 0
fi

load_standard_env "${SERVICE_DIR}"
ensure_value GRAFANA_PASSWORD

# 这个栈里只有 Prometheus 配置需要模板渲染。
render_template "${SERVICE_DIR}/prometheus/prometheus.yml" "${SERVICE_DIR}/prometheus/prometheus.generated.yml"
run_compose_stack "${SERVICE_DIR}" "pmth-gfn.yaml"
