#!/usr/bin/env bash
#
# 渲染 GitLab 对外暴露用的 Nginx 配置，并安装到目标目录后重启 Nginx。

set -euo pipefail

SERVICE_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=sh/lib/common.sh
source "${SERVICE_DIR}/../sh/lib/common.sh"

print_help() {
  cat <<EOF
$(usage_header)

Usage: $(basename "$0") [--help]

Renders gitlab.nginx.conf, installs it to the configured nginx path, validates
the configuration, and restarts nginx.
EOF
}

maybe_sudo() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    die "root privileges or sudo are required: $*"
  fi
}

restart_nginx() {
  if command -v systemctl >/dev/null 2>&1; then
    maybe_sudo systemctl restart nginx
    return
  fi

  if command -v service >/dev/null 2>&1; then
    maybe_sudo service nginx restart
    return
  fi

  die "unable to restart nginx: neither systemctl nor service is available"
}

main() {
  if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
    print_help
    exit 0
  fi

  load_env_with_example "${SERVICE_DIR}"

  : "${GITLAB_NGINX_HTTPS_PORT:=${GITLAB_EXTERNAL_PORT}}"
  : "${GITLAB_NGINX_UPSTREAM_PORT:=${GITLAB_HTTP_PORT}}"
  : "${GITLAB_REGISTRY_NGINX_UPSTREAM_HOST:=${GITLAB_NGINX_UPSTREAM_HOST}}"
  : "${GITLAB_REGISTRY_NGINX_UPSTREAM_PORT:=${GITLAB_REGISTRY_BIND_PORT}}"

  ensure_value GITLAB_EXTERNAL_HOST
  ensure_value GITLAB_REGISTRY_EXTERNAL_HOST
  ensure_value GITLAB_NGINX_SSL_CERT
  ensure_value GITLAB_NGINX_SSL_KEY

  if [ -z "${GITLAB_NGINX_REDIRECT_BASE:-}" ]; then
    if [ "${GITLAB_NGINX_HTTPS_PORT}" = "443" ]; then
      GITLAB_NGINX_REDIRECT_BASE='https://$host'
    else
      GITLAB_NGINX_REDIRECT_BASE="https://\$host:${GITLAB_NGINX_HTTPS_PORT}"
    fi
  fi

  export GITLAB_NGINX_HTTP_PORT GITLAB_NGINX_HTTPS_PORT GITLAB_NGINX_SSL_CERT
  export GITLAB_NGINX_SSL_KEY GITLAB_NGINX_UPSTREAM_HOST GITLAB_NGINX_UPSTREAM_PORT
  export GITLAB_REGISTRY_NGINX_UPSTREAM_HOST GITLAB_REGISTRY_NGINX_UPSTREAM_PORT
  export GITLAB_NGINX_REDIRECT_BASE

  local rendered_path="${SERVICE_DIR}/gitlab.nginx.rendered.conf"
  render_template "${SERVICE_DIR}/gitlab.nginx.conf" "${rendered_path}"

  require_cmd nginx
  maybe_sudo mkdir -p "$(dirname "${GITLAB_NGINX_INSTALL_PATH}")"
  maybe_sudo cp "${rendered_path}" "${GITLAB_NGINX_INSTALL_PATH}"
  maybe_sudo nginx -t
  restart_nginx

  log "rendered ${rendered_path}"
  log "installed ${GITLAB_NGINX_INSTALL_PATH}"
}

main "$@"
