#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pick_python() {
  local preferred="${PYTHON:-}"
  local candidates=()

  if [ -n "${preferred}" ]; then
    candidates+=("${preferred}")
  fi
  candidates+=("${SCRIPT_DIR}/../.venv/bin/python" "${SCRIPT_DIR}/../.venv/Scripts/python.exe" "python3" "python")

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

PYTHON_BIN="$(pick_python || true)"
if [ -z "${PYTHON_BIN}" ]; then
  echo "Error: 找不到可用的 Python 解释器。" >&2
  exit 1
fi
COMMAND="${1:-help}"

if [ "$#" -gt 0 ]; then
  shift
fi

case "${COMMAND}" in
  synthesize|tts)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/synthesize.py" "$@"
    ;;
  transcribe|asr)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/transcribe.py" "$@"
    ;;
  doctor|check)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/doctor.py" "$@"
    ;;
  bootstrap)
    exec "${SCRIPT_DIR}/bootstrap.sh" "$@"
    ;;
  help|-h|--help)
    cat <<'USAGE'
Usage:
  skills/speech/scripts/run.sh bootstrap [--check-only] [--mode all|synthesize|transcribe]
  skills/speech/scripts/run.sh doctor [--mode all|synthesize|transcribe]
  skills/speech/scripts/run.sh synthesize [synthesize.py args...]
  skills/speech/scripts/run.sh transcribe [transcribe.py args...]

Examples:
  skills/speech/scripts/run.sh bootstrap
  skills/speech/scripts/run.sh synthesize --text "你好" --output-mp3 out/demo.mp3
  skills/speech/scripts/run.sh transcribe --input-file demo.wav --output-text out/demo.txt
USAGE
    ;;
  *)
    echo "Error: 未知命令: ${COMMAND}" >&2
    echo "使用 \`skills/speech/scripts/run.sh help\` 查看帮助。" >&2
    exit 1
    ;;
esac
