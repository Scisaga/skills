#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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
    exec "${SCRIPT_DIR}/bootstrap.sh" "$@"
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
    cat <<'USAGE'
Usage:
  skills/subtitle-matcher/scripts/run.sh bootstrap [--check-only]
  skills/subtitle-matcher/scripts/run.sh doctor
  skills/subtitle-matcher/scripts/run.sh inventory --root /path/to/videos --output inventory.json
  skills/subtitle-matcher/scripts/run.sh normalize-existing --root /path/to/videos --dry-run
  skills/subtitle-matcher/scripts/run.sh normalize-existing --root /path/to/videos --apply
  skills/subtitle-matcher/scripts/run.sh validate-subtitle --video movie.mkv --subtitle movie.chs.srt
  skills/subtitle-matcher/scripts/run.sh search-download --root /path/to/videos
  skills/subtitle-matcher/scripts/run.sh scan-report --root /path/to/videos
  skills/subtitle-matcher/scripts/run.sh audit-report --legacy-csv /path/to/videos/_subtitle_download_report.csv --root /path/to/videos

Windows-only:
  powershell -ExecutionPolicy Bypass -File .\skills\subtitle-matcher\scripts\run.ps1 register-vlc-protocol
USAGE
    ;;
  *)
    echo "Error: unknown command: ${COMMAND}" >&2
    echo "Use skills/subtitle-matcher/scripts/run.sh help for usage." >&2
    exit 1
    ;;
esac
