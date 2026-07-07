#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_POSIX_PY="${SKILL_ROOT}/.venv/bin/python"
VENV_WINDOWS_PY="${SKILL_ROOT}/.venv/Scripts/python.exe"

pick_python() {
  local preferred="${PYTHON:-}"
  local candidates=()

  if [ -n "${preferred}" ]; then
    candidates+=("${preferred}")
  fi
  candidates+=("${VENV_POSIX_PY}" "${VENV_WINDOWS_PY}" "python3" "python")

  for candidate in "${candidates[@]}"; do
    if [ -f "${candidate}" ] && "${candidate}" --version >/dev/null 2>&1; then
      echo "${candidate}"
      return 0
    fi
    if command -v "${candidate}" >/dev/null 2>&1 && "${candidate}" --version >/dev/null 2>&1; then
      echo "${candidate}"
      return 0
    fi
  done

  return 1
}

CHECK_ONLY=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --check-only)
      CHECK_ONLY=1
      shift
      ;;
    *)
      echo "Error: unknown option: $1" >&2
      exit 1
      ;;
  esac
done

if ! PYTHON_BIN="$(pick_python)"; then
  echo "Error: Python is required. Install Python 3.10+ or set PYTHON=/path/to/python." >&2
  exit 1
fi

if [ "${CHECK_ONLY}" -eq 0 ]; then
  if [ "${PYTHON_BIN}" != "${VENV_POSIX_PY}" ] && [ "${PYTHON_BIN}" != "${VENV_WINDOWS_PY}" ]; then
    echo "==> Creating subtitle-matcher virtual environment"
    "${PYTHON_BIN}" -m venv "${SKILL_ROOT}/.venv"
    PYTHON_BIN="$(pick_python)"
  fi

  echo "==> Installing subtitle-matcher Python dependencies"
  "${PYTHON_BIN}" -m pip install -r "${SKILL_ROOT}/requirements.txt"
fi

echo "==> Checking subtitle-matcher runtime"
"${PYTHON_BIN}" "${SCRIPT_DIR}/doctor.py"
