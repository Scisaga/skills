#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${SKILL_ROOT}/.venv"
PYTHON_BIN="${PYTHON:-}"
STAGE=all

if [ "$#" -eq 2 ] && [ "$1" = --stage ]; then
  STAGE="$2"
elif [ "$#" -ne 0 ]; then
  echo "Usage: bootstrap.sh [--stage static|audio|narrated|video|all]" >&2
  exit 1
fi

case "$STAGE" in
  audio) REQUIREMENTS="requirements-audio.txt" ;;
  static|video) REQUIREMENTS="requirements-html.txt" ;;
  narrated|all) REQUIREMENTS="requirements.txt" ;;
  *) echo "Error: unsupported stage $STAGE" >&2; exit 1 ;;
esac

if [ -z "${PYTHON_BIN}" ]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    echo "Error: Python 3 is required." >&2
    exit 1
  fi
fi

VENV_PYTHON="${VENV_DIR}/bin/python"
if [ ! -x "$VENV_PYTHON" ] || ! "$VENV_PYTHON" -m pip --version >/dev/null 2>&1; then
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi
"$VENV_PYTHON" -m pip install -r "${SKILL_ROOT}/$REQUIREMENTS"
if [ "$STAGE" != audio ]; then
  "$VENV_PYTHON" -m playwright install chromium
  "$VENV_PYTHON" "${SCRIPT_DIR}/html_fonts.py"
fi
case "$STAGE" in
  narrated|video|all) bash "${SCRIPT_DIR}/install_ffmpeg.sh" ;;
esac
"$VENV_PYTHON" "${SCRIPT_DIR}/doctor.py" --stage "$STAGE"
