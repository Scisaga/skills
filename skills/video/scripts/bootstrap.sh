#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_POSIX_PY="${SKILL_ROOT}/.venv/bin/python"
VENV_WINDOWS_PY="${SKILL_ROOT}/.venv/Scripts/python.exe"
PYTHON_BIN="${PYTHON:-python3}"
CHECK_ONLY=0
SKIP_FFMPEG=0

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

platform_slug() {
  local system_name
  local arch
  system_name="$(uname -s)"
  arch="$(uname -m)"

  case "${arch}" in
    x86_64|amd64) arch="x64" ;;
    arm64|aarch64) arch="arm64" ;;
  esac

  case "${system_name}" in
    Linux) echo "linux-${arch}" ;;
    Darwin) echo "macos-${arch}" ;;
    MINGW*|MSYS*|CYGWIN*) echo "windows-${arch}" ;;
    *) echo "${system_name}-${arch}" ;;
  esac
}

has_local_ffmpeg() {
  local slug
  slug="$(platform_slug)"
  [ -x "${SKILL_ROOT}/.cache/ffmpeg/${slug}/ffmpeg" ] && [ -x "${SKILL_ROOT}/.cache/ffmpeg/${slug}/ffprobe" ] && return 0
  [ -x "${SKILL_ROOT}/.cache/ffmpeg/${slug}/bin/ffmpeg" ] && [ -x "${SKILL_ROOT}/.cache/ffmpeg/${slug}/bin/ffprobe" ] && return 0
  [ -x "${SKILL_ROOT}/.cache/ffmpeg/${slug}/ffmpeg.exe" ] && [ -x "${SKILL_ROOT}/.cache/ffmpeg/${slug}/ffprobe.exe" ] && return 0
  [ -x "${SKILL_ROOT}/.cache/ffmpeg/${slug}/bin/ffmpeg.exe" ] && [ -x "${SKILL_ROOT}/.cache/ffmpeg/${slug}/bin/ffprobe.exe" ] && return 0
  return 1
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --check-only)
      CHECK_ONLY=1
      shift
      ;;
    --skip-ffmpeg)
      SKIP_FFMPEG=1
      shift
      ;;
    *)
      echo "Error: 未知参数: $1" >&2
      exit 1
      ;;
  esac
done

if ! PYTHON_BIN="$(pick_python)"; then
  echo "Error: 找不到 Python 解释器: ${PYTHON_BIN}" >&2
  exit 1
fi

if [ "${CHECK_ONLY}" -eq 0 ]; then
  if [ "${PYTHON_BIN}" != "${VENV_POSIX_PY}" ] && [ "${PYTHON_BIN}" != "${VENV_WINDOWS_PY}" ]; then
    echo "==> 创建 video 本地虚拟环境"
    "${PYTHON_BIN}" -m venv "${SKILL_ROOT}/.venv"
    if PYTHON_BIN="$(pick_python)"; then
      :
    fi
  fi
  echo "==> 安装 video Python 依赖"
  "${PYTHON_BIN}" -m pip install -r "${SKILL_ROOT}/requirements.txt"
fi

if [ "${SKIP_FFMPEG}" -eq 0 ] && { { ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; } && ! has_local_ffmpeg; }; then
  echo "==> 安装 ffmpeg"
  case "$(uname -s)" in
    Linux)
      bash "${SCRIPT_DIR}/install-linux.sh"
      ;;
    Darwin)
      bash "${SCRIPT_DIR}/install-macos.sh"
      ;;
    MINGW*|MSYS*|CYGWIN*)
      powershell.exe -ExecutionPolicy Bypass -File "${SCRIPT_DIR}/install-windows.ps1"
      ;;
    *)
      echo "Warning: 未知系统，跳过 ffmpeg 自动安装。" >&2
      ;;
  esac
fi

echo "==> 检查 video 运行环境"
"${PYTHON_BIN}" "${SCRIPT_DIR}/doctor.py"
