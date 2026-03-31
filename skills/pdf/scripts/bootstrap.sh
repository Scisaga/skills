#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
VENV_PYTHON_POSIX="$VENV_DIR/bin/python"
VENV_PYTHON_WINDOWS="$VENV_DIR/Scripts/python.exe"

is_runnable_python() {
  local candidate="$1"
  [ -n "${candidate}" ] || return 1
  [ -f "${candidate}" ] || return 1
  "${candidate}" --version >/dev/null 2>&1
}

if is_runnable_python "$VENV_PYTHON_POSIX"; then
  PYTHON_BIN="$VENV_PYTHON_POSIX"
elif is_runnable_python "$VENV_PYTHON_WINDOWS"; then
  PYTHON_BIN="$VENV_PYTHON_WINDOWS"
elif command -v python3 >/dev/null 2>&1 && python3 --version >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1 && python --version >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "错误：未找到 python3 或 python。" >&2
  exit 1
fi

if ! is_runnable_python "$VENV_PYTHON_POSIX" && ! is_runnable_python "$VENV_PYTHON_WINDOWS"; then
  echo "Creating virtual environment at $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
  if is_runnable_python "$VENV_PYTHON_POSIX"; then
    PYTHON_BIN="$VENV_PYTHON_POSIX"
  elif is_runnable_python "$VENV_PYTHON_WINDOWS"; then
    PYTHON_BIN="$VENV_PYTHON_WINDOWS"
  else
    echo "错误：创建虚拟环境后仍未找到可用的 Python 解释器。" >&2
    exit 1
  fi
fi

echo "Using Python: $PYTHON_BIN"
"$PYTHON_BIN" --version

if ! "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
  echo "错误：当前 Python 没有可用的 pip。" >&2
  exit 1
fi

echo "Upgrading pip inside $VENV_DIR"
"$PYTHON_BIN" -m pip install --upgrade pip

echo "Installing dependencies from $ROOT_DIR/requirements.txt"
"$PYTHON_BIN" -m pip install -r "$ROOT_DIR/requirements.txt"

echo "Running environment checks"
"$PYTHON_BIN" "$SCRIPT_DIR/doctor.py"

echo "Bootstrap completed."
