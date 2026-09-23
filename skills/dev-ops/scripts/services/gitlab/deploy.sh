#!/usr/bin/env bash
#
# 部署 GitLab。
# 这个包装脚本故意保持简单：加载 env、校验几个关键变量，
# 然后启动 `gitlab.yaml` 定义的 compose 栈。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/shared/lib/common.sh
source "${SCRIPT_DIR}/../../shared/lib/common.sh"
SERVICE_ASSETS_DIR="$(service_assets_dir "gitlab")"

build_url() {
  local scheme="$1"
  local host="$2"
  local port="${3:-}"

  if [ -n "${port}" ] && ! { [ "${scheme}" = "https" ] && [ "${port}" = "443" ]; } && ! { [ "${scheme}" = "http" ] && [ "${port}" = "80" ]; }; then
    printf '%s://%s:%s' "${scheme}" "${host}" "${port}"
  else
    printf '%s://%s' "${scheme}" "${host}"
  fi
}

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage_header
  echo
  echo "Deploy the GitLab stack defined in gitlab.yaml."
  exit 0
fi

load_env_with_example "${SERVICE_ASSETS_DIR}"

GITLAB_EXTERNAL_URL="$(build_url "${GITLAB_EXTERNAL_SCHEME}" "${GITLAB_EXTERNAL_HOST}" "${GITLAB_EXTERNAL_PORT}")"
SMTP_REPLY_TO="${SMTP_REPLY_TO:-${SMTP_FROM}}"

export GITLAB_EXTERNAL_URL
export GITLAB_HTTP_PORT GITLAB_INTERNAL_HTTP_PORT GITLAB_SSH_PORT GITLAB_DNS_PRIMARY
export GITLAB_CONFIG_DIR GITLAB_DATA_DIR GITLAB_LOG_DIR GITLAB_GITDATA_DIR
export SMTP_HOST SMTP_PORT SMTP_USERNAME SMTP_PASSWORD
export SMTP_DOMAIN SMTP_TLS SMTP_FROM SMTP_REPLY_TO GLOBAL_TIMEZONE GITLAB_IMAGE
export GITLAB_CONTAINER_NAME

ensure_value GITLAB_IMAGE
ensure_value GITLAB_EXTERNAL_HOST
run_compose_stack "${SERVICE_ASSETS_DIR}" "gitlab.yaml"
