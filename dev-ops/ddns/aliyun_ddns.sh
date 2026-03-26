#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=sh/lib/common.sh
source "${SCRIPT_DIR}/../sh/lib/common.sh"

load_env_with_example "${SCRIPT_DIR}"

ALIYUN_CLI_PROFILE="${ALIYUN_CLI_PROFILE:-default}"
DDNS_TARGETS="${DDNS_TARGETS:-example.com|A|@,git,reg}"
DDNS_IPV4_LOOKUP_URL="${DDNS_IPV4_LOOKUP_URL:-https://4.ipw.cn}"
DDNS_IPV6_LOOKUP_URL="${DDNS_IPV6_LOOKUP_URL:-https://6.ipw.cn}"

print_help() {
  usage_header
  cat <<EOF

Usage: $(basename "$0")

Required env:
  DDNS_TARGETS=example.com|A|@,git,reg;example.net|AAAA|@

Optional env:
  ALIYUN_CLI_PROFILE=default
  DDNS_IPV4_LOOKUP_URL=https://4.ipw.cn
  DDNS_IPV6_LOOKUP_URL=https://6.ipw.cn
EOF
}

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  print_help
  exit 0
fi

[ "$#" -eq 0 ] || die "this script is env-driven; configure .env/.env.local instead of CLI flags"

require_cmd aliyun
require_cmd curl
require_cmd python3
ensure_value DDNS_TARGETS

IPV4_CACHE=""
IPV6_CACHE=""

trim() {
  printf '%s' "$1" | xargs
}

lookup_public_ip() {
  local record_type="$1"

  case "${record_type}" in
    A)
      if [ -z "${IPV4_CACHE}" ]; then
        IPV4_CACHE="$(curl -fsSL "${DDNS_IPV4_LOOKUP_URL}" | tr -d '\r\n')"
      fi
      printf '%s' "${IPV4_CACHE}"
      ;;
    AAAA)
      if [ -z "${IPV6_CACHE}" ]; then
        IPV6_CACHE="$(curl -fsSL "${DDNS_IPV6_LOOKUP_URL}" | tr -d '\r\n')"
      fi
      printf '%s' "${IPV6_CACHE}"
      ;;
    *)
      die "unsupported DDNS record type: ${record_type}"
      ;;
  esac
}

lookup_record() {
  local domain="$1"
  local rr="$2"
  local record_type="$3"
  local payload

  payload="$(aliyun --profile "${ALIYUN_CLI_PROFILE}" alidns DescribeDomainRecords \
    --DomainName "${domain}" \
    --RRKeyWord "${rr}" \
    --Type "${record_type}" \
    --PageSize 100)"

  python3 -c '
import json
import sys

rr = sys.argv[1]
record_type = sys.argv[2]
payload = json.load(sys.stdin)
records = payload.get("DomainRecords", {}).get("Record", [])

for record in records:
    if record.get("RR") == rr and record.get("Type") == record_type:
        print("{}\t{}".format(record.get("RecordId", ""), record.get("Value", "")))
        break
' "${rr}" "${record_type}" <<<"${payload}"
}

add_record() {
  local domain="$1"
  local rr="$2"
  local record_type="$3"
  local public_ip="$4"

  aliyun --profile "${ALIYUN_CLI_PROFILE}" alidns AddDomainRecord \
    --DomainName "${domain}" \
    --RR "${rr}" \
    --Type "${record_type}" \
    --Value "${public_ip}" >/dev/null
}

update_record() {
  local rr="$1"
  local record_id="$2"
  local record_type="$3"
  local public_ip="$4"

  aliyun --profile "${ALIYUN_CLI_PROFILE}" alidns UpdateDomainRecord \
    --RecordId "${record_id}" \
    --RR "${rr}" \
    --Type "${record_type}" \
    --Value "${public_ip}" >/dev/null
}

IFS=';' read -r -a target_specs <<< "${DDNS_TARGETS}"
for raw_spec in "${target_specs[@]}"; do
  spec="$(trim "${raw_spec}")"
  [ -n "${spec}" ] || continue

  IFS='|' read -r domain record_type record_rrs <<< "${spec}"
  domain="$(trim "${domain:-}")"
  record_type="$(trim "${record_type:-}")"
  record_rrs="$(trim "${record_rrs:-}")"

  [ -n "${domain}" ] || die "invalid DDNS target, missing domain: ${spec}"
  [ -n "${record_type}" ] || die "invalid DDNS target, missing type: ${spec}"
  [ -n "${record_rrs}" ] || die "invalid DDNS target, missing RR list: ${spec}"

  public_ip="$(lookup_public_ip "${record_type}")"
  [ -n "${public_ip}" ] || die "failed to resolve public IP for ${record_type}"
  log "current ${record_type} public IP: ${public_ip}"

  IFS=',' read -r -a rr_list <<< "${record_rrs}"
  for raw_rr in "${rr_list[@]}"; do
    rr="$(trim "${raw_rr}")"
    [ -n "${rr}" ] || continue

    fqdn="${domain}"
    if [ "${rr}" != "@" ]; then
      fqdn="${rr}.${domain}"
    fi

    current_record="$(lookup_record "${domain}" "${rr}" "${record_type}")"
    if [ -z "${current_record}" ]; then
      log "adding ${record_type} record for ${fqdn} -> ${public_ip}"
      add_record "${domain}" "${rr}" "${record_type}" "${public_ip}"
      continue
    fi

    record_id="$(printf '%s' "${current_record}" | cut -f1)"
    current_ip="$(printf '%s' "${current_record}" | cut -f2)"

    if [ "${current_ip}" = "${public_ip}" ]; then
      log "skip ${fqdn}, already ${public_ip}"
      continue
    fi

    log "updating ${fqdn} (${record_id}) -> ${public_ip}"
    update_record "${rr}" "${record_id}" "${record_type}" "${public_ip}"
  done
done

log "DDNS sync completed"
