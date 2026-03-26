#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=sh/lib/common.sh
source "${SCRIPT_DIR}/../sh/lib/common.sh"

load_env_with_example "${SCRIPT_DIR}"

ALIYUN_ACCESS_KEY_ID="${ALIYUN_ACCESS_KEY_ID:-}"
ALIYUN_ACCESS_KEY_SECRET="${ALIYUN_ACCESS_KEY_SECRET:-}"
ACME_ACCOUNT_EMAIL="${ACME_ACCOUNT_EMAIL:-ops@example.com}"
ACME_CERT_NAME="${ACME_CERT_NAME:-example.com}"
ACME_DOMAINS="${ACME_DOMAINS:-example.com,*.example.com}"
ACME_CERT_DIR="${ACME_CERT_DIR:-/srv/certs/example.com}"
ACME_RELOAD_CMD="${ACME_RELOAD_CMD:-systemctl reload nginx}"
ACME_SH_BIN="${HOME}/.acme.sh/acme.sh"

print_help() {
  usage_header
  cat <<EOF

Usage: $(basename "$0")

Required env:
  ALIYUN_ACCESS_KEY_ID=...
  ALIYUN_ACCESS_KEY_SECRET=...
  ACME_CERT_NAME=example.com
  ACME_DOMAINS=example.com,*.example.com

Optional env:
  ACME_ACCOUNT_EMAIL=ops@example.com
  ACME_CERT_DIR=/srv/certs/example.com
  ACME_RELOAD_CMD=systemctl reload nginx
EOF
}

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  print_help
  exit 0
fi

[ "$#" -eq 0 ] || die "this script is env-driven; configure .env/.env.local instead of CLI flags"

[ -x "${ACME_SH_BIN}" ] || die "acme.sh not found: ${ACME_SH_BIN}"
ensure_value ALIYUN_ACCESS_KEY_ID
ensure_value ALIYUN_ACCESS_KEY_SECRET
ensure_value ACME_CERT_NAME
ensure_value ACME_DOMAINS
ensure_value ACME_CERT_DIR
ensure_value ACME_ACCOUNT_EMAIL

export Ali_Key="${ALIYUN_ACCESS_KEY_ID}"
export Ali_Secret="${ALIYUN_ACCESS_KEY_SECRET}"

mkdir -p "${ACME_CERT_DIR}"

"${ACME_SH_BIN}" --register-account -m "${ACME_ACCOUNT_EMAIL}" >/dev/null 2>&1 || true

declare -a domain_args
IFS=',' read -r -a domain_list <<< "${ACME_DOMAINS}"
for raw_domain in "${domain_list[@]}"; do
  domain="$(printf '%s' "${raw_domain}" | xargs)"
  [ -n "${domain}" ] || continue
  domain_args+=("-d" "${domain}")
done

[ "${#domain_args[@]}" -gt 0 ] || die "no ACME domains configured"

"${ACME_SH_BIN}" --issue --dns dns_ali \
  "${domain_args[@]}" \
  --log

"${ACME_SH_BIN}" --install-cert -d "${ACME_CERT_NAME}" \
  --key-file "${ACME_CERT_DIR}/${ACME_CERT_NAME}.key" \
  --fullchain-file "${ACME_CERT_DIR}/${ACME_CERT_NAME}.crt" \
  --reloadcmd "${ACME_RELOAD_CMD}"

log "certificate refreshed for ${ACME_CERT_NAME}"
