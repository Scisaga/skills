#!/usr/bin/env bash
#
# 部署 GitLab 及其配套的容器镜像仓库。
# 这个包装脚本故意保持简单：加载 env、校验几个关键变量，
# 然后启动 `gitlab.yaml` 定义的 compose 栈。

set -euo pipefail

SERVICE_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=sh/lib/common.sh
source "${SERVICE_DIR}/../sh/lib/common.sh"

build_url() {
  local scheme="$1"
  local host="$2"
  local port="${3:-}"

  if [ -n "${port}" ]; then
    printf '%s://%s:%s' "${scheme}" "${host}" "${port}"
  else
    printf '%s://%s' "${scheme}" "${host}"
  fi
}

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage_header
  echo
  echo "Deploy the GitLab and registry stack defined in gitlab.yaml."
  exit 0
fi

load_standard_env "${SERVICE_DIR}"

# 只在 env 中暴露原子化的地址与端口字段，完整 URL 在这里组合。
: "${GITLAB_EXTERNAL_SCHEME:=https}"
: "${GITLAB_EXTERNAL_HOST:=gitlab.example.com}"
: "${GITLAB_EXTERNAL_PORT:=443}"
: "${GITLAB_HTTP_PORT:=8080}"
: "${GITLAB_INTERNAL_HTTP_PORT:=80}"
: "${GITLAB_SSH_PORT:=222}"
: "${GITLAB_DNS_PRIMARY:=1.1.1.1}"
: "${GITLAB_CONFIG_DIR:=./config}"
: "${GITLAB_DATA_DIR:=./data}"
: "${GITLAB_LOG_DIR:=./logs}"
: "${GITLAB_GITDATA_DIR:=./gitdata}"
: "${GITLAB_CERTS_DIR:=./certs}"

: "${GITLAB_REGISTRY_EXTERNAL_SCHEME:=https}"
: "${GITLAB_REGISTRY_EXTERNAL_HOST:=registry.example.com}"
: "${GITLAB_REGISTRY_EXTERNAL_PORT:=5050}"
: "${GITLAB_REGISTRY_BIND_PORT:=5050}"
: "${GITLAB_REGISTRY_INTERNAL_PORT:=5000}"
: "${GITLAB_REGISTRY_DATA_DIR:=./certs/shared/registry}"
: "${GITLAB_REGISTRY_ISSUER:=gitlab-registry}"

: "${SMTP_HOST:=mail.example.com}"
: "${SMTP_PORT:=465}"
: "${SMTP_DOMAIN:=example.com}"
: "${SMTP_TLS:=true}"
: "${SMTP_FROM:=noreply@example.com}"
: "${SMTP_REPLY_TO:=noreply@example.com}"

GITLAB_EXTERNAL_URL="$(build_url "${GITLAB_EXTERNAL_SCHEME}" "${GITLAB_EXTERNAL_HOST}" "${GITLAB_EXTERNAL_PORT}")"
GITLAB_REGISTRY_EXTERNAL_URL="$(build_url "${GITLAB_REGISTRY_EXTERNAL_SCHEME}" "${GITLAB_REGISTRY_EXTERNAL_HOST}" "${GITLAB_REGISTRY_EXTERNAL_PORT}")"
GITLAB_REGISTRY_HOST="${GITLAB_REGISTRY_EXTERNAL_HOST}"
GITLAB_REGISTRY_PORT="${GITLAB_REGISTRY_EXTERNAL_PORT}"
GITLAB_REGISTRY_AUTH_REALM="${GITLAB_EXTERNAL_URL}/jwt/auth"

export GITLAB_EXTERNAL_URL GITLAB_REGISTRY_EXTERNAL_URL GITLAB_REGISTRY_HOST
export GITLAB_REGISTRY_PORT GITLAB_REGISTRY_AUTH_REALM
export GITLAB_HTTP_PORT GITLAB_INTERNAL_HTTP_PORT GITLAB_SSH_PORT GITLAB_DNS_PRIMARY
export GITLAB_CONFIG_DIR GITLAB_DATA_DIR GITLAB_LOG_DIR GITLAB_GITDATA_DIR GITLAB_CERTS_DIR
export GITLAB_REGISTRY_BIND_PORT GITLAB_REGISTRY_INTERNAL_PORT GITLAB_REGISTRY_DATA_DIR
export GITLAB_REGISTRY_ISSUER SMTP_HOST SMTP_PORT SMTP_USERNAME SMTP_PASSWORD
export SMTP_DOMAIN SMTP_TLS SMTP_FROM SMTP_REPLY_TO GLOBAL_TIMEZONE GITLAB_IMAGE
export GITLAB_CONTAINER_NAME GITLAB_REGISTRY_IMAGE GITLAB_REGISTRY_CONTAINER_NAME

ensure_value GITLAB_IMAGE
ensure_value GITLAB_EXTERNAL_HOST
run_compose_stack "${SERVICE_DIR}" "gitlab.yaml"
