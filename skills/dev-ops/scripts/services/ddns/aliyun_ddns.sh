#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/shared/lib/common.sh
source "${SCRIPT_DIR}/../../shared/lib/common.sh"
SERVICE_ASSETS_DIR="$(service_assets_dir "ddns")"

print_help() {
  usage_header
  cat <<EOF

Usage: $(basename "$0") [--dry-run]

Required env:
  DDNS_TARGETS=example.com|A|@,git,reg;example.net|AAAA|@

Optional env:
  ALIYUN_CLI_PROFILE=default
  ALIYUN_ACCESS_KEY_ID / ALIYUN_ACCESS_KEY_SECRET (environment credentials)
  DDNS_API_BACKEND=auto (rpc with environment credentials; cli with a profile)
  DDNS_INTERFACE=eth0 (read a stable public address from this interface)
  DDNS_IPV4_SOURCE=auto (auto, interface, public; public also supports NAT)
  DDNS_LOOKUP_DNS_SERVER= (optional direct DNS server for IP lookup hosts)
  DDNS_LINE=default
  DDNS_TTL=600 (new records only; existing TTL is preserved)
  DDNS_API_TIMEOUT_SECONDS=30
  DDNS_IPV4_LOOKUP_URL=https://ip.3322.net
  DDNS_IPV6_LOOKUP_URL=https://6.ipw.cn

With DDNS_INTERFACE set, auto uses interface addresses. Set DDNS_IPV4_SOURCE=public
for NAT IPv4: query the public lookup service directly through that interface,
with proxies disabled and IPv4 forced. IPv6 keeps using the local interface.
Private IPv4, temporary/deprecated IPv6 and ambiguous interface addresses are rejected.
--dry-run reads current DNS records and prints changes without writing them.
EOF
}

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  print_help
  exit 0
fi

DRY_RUN=0
if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=1
  shift
fi
[ "$#" -eq 0 ] || die "unknown argument; use --help"

# Example files document configuration; they must never override credentials
# supplied by systemd EnvironmentFile or silently become live DNS targets.
load_standard_env "${SERVICE_ASSETS_DIR}"
ALIYUN_CLI_PROFILE="${ALIYUN_CLI_PROFILE:-default}"
DDNS_TARGETS="${DDNS_TARGETS:-}"
DDNS_INTERFACE="${DDNS_INTERFACE:-}"
DDNS_IPV4_SOURCE="${DDNS_IPV4_SOURCE:-auto}"
DDNS_LOOKUP_DNS_SERVER="${DDNS_LOOKUP_DNS_SERVER:-}"
DDNS_LINE="${DDNS_LINE:-default}"
DDNS_TTL="${DDNS_TTL:-600}"
DDNS_API_TIMEOUT_SECONDS="${DDNS_API_TIMEOUT_SECONDS:-30}"
DDNS_API_BACKEND="${DDNS_API_BACKEND:-auto}"
DDNS_IPV4_LOOKUP_URL="${DDNS_IPV4_LOOKUP_URL:-https://ip.3322.net}"
DDNS_IPV6_LOOKUP_URL="${DDNS_IPV6_LOOKUP_URL:-https://6.ipw.cn}"

for dependency in python3 timeout; do
  command -v "${dependency}" >/dev/null 2>&1 || die "missing ${dependency}; on Debian/Ubuntu run: apt-get install python3 coreutils"
done
ensure_value DDNS_TARGETS
if [ -n "${DDNS_INTERFACE}" ]; then
  command -v ip >/dev/null 2>&1 || die "missing ip; on Debian/Ubuntu run: apt-get install iproute2"
fi
case "${DDNS_IPV4_SOURCE}" in
  auto|interface|public) ;;
  *) die "DDNS_IPV4_SOURCE must be auto, interface or public" ;;
esac
[[ "${DDNS_TTL}" =~ ^[1-9][0-9]*$ ]] || die "DDNS_TTL must be a positive integer"
[[ "${DDNS_API_TIMEOUT_SECONDS}" =~ ^[1-9][0-9]*$ ]] || die "DDNS_API_TIMEOUT_SECONDS must be a positive integer"

ALIYUN_CLI_ARGS=(--profile "${ALIYUN_CLI_PROFILE}")
ALIYUN_ACCESS_KEY_ID="${ALIYUN_ACCESS_KEY_ID:-${ALIBABA_CLOUD_ACCESS_KEY_ID:-}}"
ALIYUN_ACCESS_KEY_SECRET="${ALIYUN_ACCESS_KEY_SECRET:-${ALIBABA_CLOUD_ACCESS_KEY_SECRET:-}}"
if [ -n "${ALIYUN_ACCESS_KEY_ID:-}${ALIYUN_ACCESS_KEY_SECRET:-}" ]; then
  ensure_value ALIYUN_ACCESS_KEY_ID
  ensure_value ALIYUN_ACCESS_KEY_SECRET
  export ALIBABA_CLOUD_ACCESS_KEY_ID="${ALIYUN_ACCESS_KEY_ID}"
  export ALIBABA_CLOUD_ACCESS_KEY_SECRET="${ALIYUN_ACCESS_KEY_SECRET}"
  export ALIBABA_CLOUD_IGNORE_PROFILE=TRUE
  ALIYUN_CLI_ARGS=()
  if [ "${DDNS_API_BACKEND}" = auto ]; then
    DDNS_API_BACKEND=rpc
  fi
elif [ "${DDNS_API_BACKEND}" = auto ]; then
  DDNS_API_BACKEND=cli
fi
case "${DDNS_API_BACKEND}" in
  rpc)
    ensure_value ALIBABA_CLOUD_ACCESS_KEY_ID
    ensure_value ALIBABA_CLOUD_ACCESS_KEY_SECRET
    REQUEST_COMMAND=(python3 "${SCRIPT_DIR}/aliyun_api.py")
    ;;
  cli)
    command -v aliyun >/dev/null 2>&1 || die "missing aliyun; run bash ${SCRIPT_DIR}/install-cli.sh, then add /opt/aliyun-ddns/bin to PATH"
    REQUEST_COMMAND=(aliyun "${ALIYUN_CLI_ARGS[@]}" alidns)
    ;;
  *) die "DDNS_API_BACKEND must be auto, rpc or cli" ;;
esac
export DDNS_API_TIMEOUT_SECONDS

if [ "${DDNS_API_BACKEND}" = rpc ]; then
  log "using native Alibaba Cloud DNS API (no CLI or SDK dependency)"
fi

aliyun_request() {
  local payload
  if payload="$(timeout "${DDNS_API_TIMEOUT_SECONDS}s" "${REQUEST_COMMAND[@]}" "$@" 2>&1)"; then
    printf '%s\n' "${payload}"
  else
    printf '%s\n' "${payload}" | python3 -c '
import os, sys
message = sys.stdin.read()
for name in ("ALIYUN_ACCESS_KEY_ID", "ALIYUN_ACCESS_KEY_SECRET", "ALIBABA_CLOUD_ACCESS_KEY_ID", "ALIBABA_CLOUD_ACCESS_KEY_SECRET"):
    value = os.environ.get(name)
    if value:
        message = message.replace(value, "[REDACTED]")
print(message or "Alibaba Cloud DNS request failed or timed out", file=sys.stderr)
'
    return 1
  fi
}

trim() {
  printf '%s' "$1" | xargs
}

lookup_public_ip() {
  local record_type="$1"
  local lookup_url source_mode=auto lookup_host resolve_entry dns_answer
  local -a curl_args=(-q --noproxy '*' --proxy '' --connect-timeout 5 --max-time 15 -fsS)

  if [ "${record_type}" = A ]; then
    source_mode="${DDNS_IPV4_SOURCE}"
  fi
  if [ "${source_mode}" = auto ]; then
    if [ -n "${DDNS_INTERFACE}" ]; then source_mode=interface; else source_mode=public; fi
  fi

  if [ "${source_mode}" = interface ]; then
    ensure_value DDNS_INTERFACE
    ip -j address show dev "${DDNS_INTERFACE}" | \
      python3 "${SCRIPT_DIR}/ddns_address.py" interface "${record_type}"
    return
  fi

  case "${record_type}" in
    A) lookup_url="${DDNS_IPV4_LOOKUP_URL}"; curl_args+=(-4) ;;
    AAAA) lookup_url="${DDNS_IPV6_LOOKUP_URL}"; curl_args+=(-6) ;;
    *)
      die "unsupported DDNS record type: ${record_type}"
      ;;
  esac
  command -v curl >/dev/null 2>&1 || die "missing curl; on Debian/Ubuntu run: apt-get install curl"
  if [ -n "${DDNS_INTERFACE}" ]; then
    curl_args+=(--interface "${DDNS_INTERFACE}")
  fi
  if [ -n "${DDNS_LOOKUP_DNS_SERVER}" ]; then
    command -v dig >/dev/null 2>&1 || die "missing dig; on Debian/Ubuntu run: apt-get install bind9-dnsutils"
    lookup_host="$(python3 -c 'import sys; from urllib.parse import urlsplit; print(urlsplit(sys.argv[1]).hostname or "")' "${lookup_url}")" || return $?
    [ -n "${lookup_host}" ] || die "IP lookup URL has no hostname"
    dns_answer="$(dig +short +time=2 +tries=1 "@${DDNS_LOOKUP_DNS_SERVER}" "${lookup_host}" "${record_type}")" || return $?
    resolve_entry="$(python3 "${SCRIPT_DIR}/ddns_address.py" resolve "${record_type}" --url "${lookup_url}" <<<"${dns_answer}")" || return $?
    curl_args+=(--resolve "${resolve_entry}")
  fi
  curl "${curl_args[@]}" "${lookup_url}" | \
    python3 "${SCRIPT_DIR}/ddns_address.py" validate "${record_type}"
}

lookup_record() {
  local domain="$1"
  local rr="$2"
  local record_type="$3"
  local payload

  payload="$(aliyun_request DescribeDomainRecords \
    --DomainName "${domain}" \
    --RRKeyWord "${rr}" \
    --TypeKeyWord "${record_type}" \
    --SearchMode EXACT \
    --PageSize 100)" || return $?

  python3 -c '
import json
import sys

rr = sys.argv[1]
record_type = sys.argv[2]
line = sys.argv[3]
payload = json.load(sys.stdin)
records = payload.get("DomainRecords", {}).get("Record", [])
if payload.get("TotalCount", len(records)) > 100:
    raise SystemExit("too many DNS records; refusing an incomplete lookup")
matches = [r for r in records if r.get("RR") == rr and r.get("Type") == record_type and r.get("Line", "default") == line]
if len(matches) > 1:
    raise SystemExit("multiple matching DNS records; refusing to update an arbitrary record")
if matches:
    record = matches[0]
    if record.get("Status", "ENABLE") != "ENABLE":
        raise SystemExit("matching DNS record is disabled; refusing to publish it silently")
    print("{}\t{}\t{}".format(record["RecordId"], record["Value"], record.get("TTL", 600)))
' "${rr}" "${record_type}" "${DDNS_LINE}" <<<"${payload}"
}

verify_record() {
  local record_id="$1" rr="$2" record_type="$3" expected_ip="$4"
  local payload
  payload="$(aliyun_request DescribeDomainRecordInfo --RecordId "${record_id}")" || return $?
  python3 -c '
import ipaddress, json, sys
record = json.load(sys.stdin)
rr, kind, expected, line = sys.argv[1:]
if (record.get("RR") != rr or record.get("Type") != kind
    or record.get("Line", "default") != line or record.get("Status") != "ENABLE"
    or ipaddress.ip_address(record.get("Value", "")) != ipaddress.ip_address(expected)):
    raise SystemExit("DNS read-back verification failed")
' "${rr}" "${record_type}" "${expected_ip}" "${DDNS_LINE}" <<<"${payload}"
}

add_record() {
  local domain="$1"
  local rr="$2"
  local record_type="$3"
  local public_ip="$4"

  local record_id payload
  payload="$(aliyun_request AddDomainRecord \
    --DomainName "${domain}" \
    --RR "${rr}" \
    --Type "${record_type}" \
    --Value "${public_ip}" \
    --Line "${DDNS_LINE}" \
    --TTL "${DDNS_TTL}")" || return $?
  record_id="$(python3 -c 'import json, sys; print(json.load(sys.stdin)["RecordId"])' <<<"${payload}")" || return $?
  verify_record "${record_id}" "${rr}" "${record_type}" "${public_ip}"
}

update_record() {
  local rr="$1"
  local record_id="$2"
  local record_type="$3"
  local public_ip="$4"
  local ttl="$5"

  aliyun_request UpdateDomainRecord \
    --RecordId "${record_id}" \
    --RR "${rr}" \
    --Type "${record_type}" \
    --Value "${public_ip}" \
    --Line "${DDNS_LINE}" \
    --TTL "${ttl}" >/dev/null || return $?
  verify_record "${record_id}" "${rr}" "${record_type}" "${public_ip}"
}

declare -A ADDRESS_CACHE=()
TARGET_COUNT=0
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

  [[ "${record_type}" = A || "${record_type}" = AAAA ]] || die "unsupported DDNS record type: ${record_type}"
  if [ -z "${ADDRESS_CACHE[${record_type}]:-}" ]; then
    ADDRESS_CACHE["${record_type}"]="$(lookup_public_ip "${record_type}")"
  fi
  public_ip="${ADDRESS_CACHE[${record_type}]}"
  [ -n "${public_ip}" ] || die "failed to resolve public IP for ${record_type}"
  log "current ${record_type} public IP: ${public_ip}"

  IFS=',' read -r -a rr_list <<< "${record_rrs}"
  for raw_rr in "${rr_list[@]}"; do
    rr="$(trim "${raw_rr}")"
    [ -n "${rr}" ] || continue
    TARGET_COUNT=$((TARGET_COUNT + 1))

    fqdn="${domain}"
    if [ "${rr}" != "@" ]; then
      fqdn="${rr}.${domain}"
    fi

    log "sync target ${record_type} ${fqdn} (line=${DDNS_LINE}, interface=${DDNS_INTERFACE:-public-lookup}, dry_run=${DRY_RUN})"
    current_record="$(lookup_record "${domain}" "${rr}" "${record_type}")"
    if [ -z "${current_record}" ]; then
      log "add ${record_type} ${fqdn} -> ${public_ip} (dry_run=${DRY_RUN})"
      if [ "${DRY_RUN}" -eq 0 ]; then
        add_record "${domain}" "${rr}" "${record_type}" "${public_ip}"
      fi
      continue
    fi

    record_id="$(printf '%s' "${current_record}" | cut -f1)"
    current_ip="$(printf '%s' "${current_record}" | cut -f2)"
    current_ttl="$(printf '%s' "${current_record}" | cut -f3)"

    if [ "$(printf '%s' "${current_ip}" | python3 "${SCRIPT_DIR}/ddns_address.py" validate "${record_type}")" = "${public_ip}" ]; then
      log "skip ${fqdn}, already ${public_ip}"
      continue
    fi

    log "update ${record_type} ${fqdn} (${record_id}) ${current_ip} -> ${public_ip} (dry_run=${DRY_RUN})"
    if [ "${DRY_RUN}" -eq 0 ]; then
      update_record "${rr}" "${record_id}" "${record_type}" "${public_ip}" "${current_ttl}"
    fi
  done
done

[ "${TARGET_COUNT}" -gt 0 ] || die "DDNS_TARGETS contains no usable targets"
log "DDNS sync completed (targets=${TARGET_COUNT}, interface=${DDNS_INTERFACE:-public-lookup}, dry_run=${DRY_RUN})"
