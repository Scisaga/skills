#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

check_cmd() {
  local cmd="$1"
  command -v "${cmd}" >/dev/null 2>&1 || {
    echo "[bootstrap] missing command: ${cmd}" >&2
    return 1
  }
}

check_docker_compose() {
  command -v docker >/dev/null 2>&1 || {
    echo "[bootstrap] missing command: docker" >&2
    return 1
  }
  docker compose version >/dev/null 2>&1 || {
    echo "[bootstrap] docker compose plugin is unavailable" >&2
    return 1
  }
}

main() {
  local failed=0

  check_cmd bash || failed=1
  check_cmd ssh || failed=1
  check_cmd envsubst || failed=1
  check_docker_compose || failed=1

  if [ "${failed}" -ne 0 ]; then
    echo "[bootstrap] prerequisite check failed" >&2
    exit 1
  fi

  echo "[bootstrap] prerequisites ready"
  echo "[bootstrap] shared scripts: ${SCRIPT_DIR}"
}

main "$@"
