#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${PYTHON:-python3}"
CHECK_ONLY=0
MODE="all"
EXTRA_ARGS=()

while [ "$#" -gt 0 ]; do
  case "$1" in
    --check-only)
      CHECK_ONLY=1
      shift
      ;;
    --mode)
      MODE="${2:?missing value for --mode}"
      shift 2
      ;;
    *)
      EXTRA_ARGS+=("$1")
      shift
      ;;
  esac
done

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Error: 找不到 Python 解释器: ${PYTHON_BIN}" >&2
  exit 1
fi

if [ "${CHECK_ONLY}" -eq 0 ]; then
  echo "==> 安装 speech 依赖"
  "${PYTHON_BIN}" -m pip install -r "${SKILL_ROOT}/requirements.txt"
fi

echo "==> 检查 speech 运行环境"
"${PYTHON_BIN}" "${SCRIPT_DIR}/doctor.py" --mode "${MODE}" "${EXTRA_ARGS[@]}"
