#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"

if [ -x "$VENV_PYTHON" ]; then
  PYTHON_BIN="$VENV_PYTHON"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "错误：未找到 python3 或 python。" >&2
  exit 1
fi

if [ ! -x "$VENV_PYTHON" ]; then
  echo "Creating virtual environment at $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
  PYTHON_BIN="$VENV_PYTHON"
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
"$PYTHON_BIN" "$ROOT_DIR/scripts/check_runtime.py"

echo "Bootstrap completed."
