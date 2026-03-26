#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON:-python3}"
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
  speech/scripts/run.sh bootstrap [--check-only] [--mode all|synthesize|transcribe]
  speech/scripts/run.sh doctor [--mode all|synthesize|transcribe]
  speech/scripts/run.sh synthesize [synthesize.py args...]
  speech/scripts/run.sh transcribe [transcribe.py args...]

Examples:
  speech/scripts/run.sh bootstrap
  speech/scripts/run.sh synthesize --text "你好" --output-mp3 out/demo.mp3
  speech/scripts/run.sh transcribe --input-file demo.wav --output-text out/demo.txt
USAGE
    ;;
  *)
    echo "Error: 未知命令: ${COMMAND}" >&2
    echo "使用 \`speech/scripts/run.sh help\` 查看帮助。" >&2
    exit 1
    ;;
esac
