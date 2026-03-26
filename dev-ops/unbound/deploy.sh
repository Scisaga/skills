#!/usr/bin/env bash
#
# 渲染并部署 Unbound DNS 容器。
# 记录文件使用本地维护的 conf 清单，避免把真实域名和内网地址写入仓库模板。

set -euo pipefail

SERVICE_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=sh/lib/common.sh
source "${SERVICE_DIR}/../sh/lib/common.sh"

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage_header
  echo
  echo "Seed local unbound record files when missing and deploy unbound.yaml."
  echo "Before deploy, make sure no local DNS service is still binding port 53."
  echo "Use ./setup.sh if you want this directory to also disable systemd-resolved and rewrite /etc/resolv.conf."
  exit 0
fi

load_standard_env "${SERVICE_DIR}"
ensure_value UNBOUND_IMAGE

seed_local_file() {
  local example_file="$1"
  local target_file="$2"

  if [ ! -f "${target_file}" ]; then
    cp "${example_file}" "${target_file}"
    log "seeded $(basename "${target_file}") from example template"
  fi
}

seed_local_file "${SERVICE_DIR}/local-records.conf.example" "${SERVICE_DIR}/local-records.conf"
seed_local_file "${SERVICE_DIR}/forward-zones.conf.example" "${SERVICE_DIR}/forward-zones.conf"

run_compose_stack "${SERVICE_DIR}" "unbound.yaml"
