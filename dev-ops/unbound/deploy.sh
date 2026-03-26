#!/usr/bin/env bash
#
# 渲染并部署 Unbound DNS 容器。
# 本地记录和转发器配置都采用模板形式保存，这样 DNS 拓扑可以放到 env 中管理，
# 同时仍然能够生成可重复的配置文件。

set -euo pipefail

SERVICE_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=sh/lib/common.sh
source "${SERVICE_DIR}/../sh/lib/common.sh"

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage_header
  echo
  echo "Render unbound config templates and deploy unbound.yaml."
  exit 0
fi

load_standard_env "${SERVICE_DIR}"
ensure_value UNBOUND_IMAGE

# 在启动容器前，先渲染两个会被 bind mount 进去的 Unbound 配置片段。
render_template "${SERVICE_DIR}/a-records.conf" "${SERVICE_DIR}/a-records.generated.conf"
render_template "${SERVICE_DIR}/forward-records.conf" "${SERVICE_DIR}/forward-records.generated.conf"
run_compose_stack "${SERVICE_DIR}" "unbound.yaml"
