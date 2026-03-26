#!/usr/bin/env bash
#
# 部署 `es-docker/` 目录下的独立 Elasticsearch / Kibana 栈。
# 两个服务都从宿主机挂载模板化配置，因此必须先渲染再启动 compose。

set -euo pipefail

SERVICE_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=sh/lib/common.sh
source "${SERVICE_DIR}/../sh/lib/common.sh"

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage_header
  echo
  echo "Render elasticsearch/kibana templates and deploy the stack defined in es.yaml."
  exit 0
fi

load_standard_env "${SERVICE_DIR}"
ensure_value ES_DOCKER_ELASTICSEARCH_IMAGE
ensure_value ES_DOCKER_ELASTIC_PASSWORD

# 在 compose 校验与启动前，先渲染 Elasticsearch 与 Kibana 配置。
render_template "${SERVICE_DIR}/elasticsearch/elasticsearch.yml" "${SERVICE_DIR}/elasticsearch/elasticsearch.generated.yml"
render_template "${SERVICE_DIR}/kibana/kibana.yml" "${SERVICE_DIR}/kibana/kibana.generated.yml"

run_compose_stack "${SERVICE_DIR}" "es.yaml"
