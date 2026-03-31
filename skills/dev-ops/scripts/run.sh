#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICES_DIR="${SCRIPT_DIR}/services"

usage() {
  cat <<'EOF'
Usage:
  skills/dev-ops/scripts/run.sh bootstrap
  skills/dev-ops/scripts/run.sh audit-hardcoded
  skills/dev-ops/scripts/run.sh render-template <template> <output> <service>
  skills/dev-ops/scripts/run.sh service <service> <entrypoint> [args...]
  skills/dev-ops/scripts/run.sh help
EOF
}

resolve_service_script() {
  local service_name="$1"
  local entrypoint="$2"
  local candidate="${SERVICES_DIR}/${service_name}/${entrypoint}"

  if [ -f "${candidate}" ]; then
    printf '%s\n' "${candidate}"
    return 0
  fi

  if [[ "${entrypoint}" != *.sh ]] && [ -f "${candidate}.sh" ]; then
    printf '%s\n' "${candidate}.sh"
    return 0
  fi

  return 1
}

main() {
  local command="${1:-help}"
  if [ "$#" -gt 0 ]; then
    shift
  fi

  case "${command}" in
    bootstrap)
      exec bash "${SCRIPT_DIR}/bootstrap.sh" "$@"
      ;;
    audit-hardcoded)
      exec bash "${SCRIPT_DIR}/audit-hardcoded.sh" "$@"
      ;;
    render-template)
      exec bash "${SCRIPT_DIR}/render-template.sh" "$@"
      ;;
    service)
      [ "$#" -ge 2 ] || {
        usage
        exit 1
      }
      local service_name="$1"
      local entrypoint="$2"
      shift 2

      local target_script
      target_script="$(resolve_service_script "${service_name}" "${entrypoint}")" || {
        echo "unknown service entrypoint: ${service_name}/${entrypoint}" >&2
        exit 1
      }
      exec bash "${target_script}" "$@"
      ;;
    help|-h|--help)
      usage
      ;;
    *)
      echo "unknown command: ${command}" >&2
      usage
      exit 1
      ;;
  esac
}

main "$@"

