#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
printf -v RUN_COMMAND 'bash %q' "${SCRIPT_DIR}/run.sh"
SKILL_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

pick_python() {
  local preferred="${PYTHON:-}"
  local candidates=()

  if [ -n "${preferred}" ]; then
    candidates+=("${preferred}")
  fi
  candidates+=("${SKILL_ROOT}/.venv/bin/python" "${SKILL_ROOT}/.venv/Scripts/python.exe" "python3" "python")

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

if ! PYTHON_BIN="$(pick_python)"; then
  echo "Error: Python is required. Run skills/subtitle-matcher/scripts/bootstrap.sh first." >&2
  exit 1
fi

COMMAND="${1:-help}"
if [ "$#" -gt 0 ]; then
  shift
fi

case "${COMMAND}" in
  bootstrap)
    exec bash "${SCRIPT_DIR}/bootstrap.sh" "$@"
    ;;
  doctor|check)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/doctor.py" "$@"
    ;;
  search-download)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/download_subtitles.py" "$@"
    ;;
  inventory|normalize-existing|validate-subtitle|scan-report|audit-report)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/subtitle_matcher.py" "${COMMAND}" "$@"
    ;;
  help|-h|--help)
    cat <<USAGE
Usage:
  ${RUN_COMMAND} bootstrap [--check-only]
  ${RUN_COMMAND} doctor
  ${RUN_COMMAND} inventory --root /path/to/videos --output inventory.json
  ${RUN_COMMAND} normalize-existing --root /path/to/videos --dry-run
  ${RUN_COMMAND} normalize-existing --root /path/to/videos --apply
  ${RUN_COMMAND} validate-subtitle --video movie.mkv --subtitle movie.chs.srt
  ${RUN_COMMAND} search-download --root /path/to/videos
  ${RUN_COMMAND} scan-report --root /path/to/videos
  ${RUN_COMMAND} audit-report --legacy-csv /path/to/videos/_subtitle_download_report.csv --root /path/to/videos

Windows-only:
  powershell -ExecutionPolicy Bypass -File .\skills\subtitle-matcher\scripts\run.ps1 register-vlc-protocol
USAGE
    ;;
  *)
    echo "Error: unknown command: ${COMMAND}" >&2
    echo "Use ${RUN_COMMAND} help for usage." >&2
    exit 1
    ;;
esac
