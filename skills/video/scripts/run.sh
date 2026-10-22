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
  bootstrap)
    exec bash "${SCRIPT_DIR}/bootstrap.sh" "$@"
    ;;
  doctor|check)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/doctor.py" "$@"
    ;;
  install-ffmpeg)
    case "$(uname -s)" in
      Linux)
        exec bash "${SCRIPT_DIR}/install-linux.sh" "$@"
        ;;
      Darwin)
        exec bash "${SCRIPT_DIR}/install-macos.sh" "$@"
        ;;
      MINGW*|MSYS*|CYGWIN*)
        exec powershell.exe -ExecutionPolicy Bypass -File "${SCRIPT_DIR}/install-windows.ps1" "$@"
        ;;
      *)
        echo "Error: 未知系统，无法自动安装 ffmpeg。" >&2
        exit 1
        ;;
    esac
    ;;
  keyframes|frames)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/extract_keyframes.py" "$@"
    ;;
  extract-audio|audio)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/extract_audio.py" "$@"
    ;;
  subtitles|asr-subtitles)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/generate_subtitles.py" "$@"
    ;;
  mux|merge)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/merge_subtitles.py" "$@"
    ;;
  check-sync|sync)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/check_subtitle_sync.py" "$@"
    ;;
  help|-h|--help)
    cat <<USAGE
Usage:
  ${RUN_COMMAND} bootstrap [--check-only] [--skip-ffmpeg]
  ${RUN_COMMAND} doctor
  ${RUN_COMMAND} install-ffmpeg
  ${RUN_COMMAND} keyframes --input-file demo.mp4 --output-dir out/frames
  ${RUN_COMMAND} extract-audio --input-file demo.mp4 --output-file out/demo.wav
  ${RUN_COMMAND} subtitles --input-file demo.mp4 --output-srt out/demo.srt
  ${RUN_COMMAND} mux --input-file demo.mkv --subtitle-file out/demo.srt --output-file out/demo.mp4 --check-sync
  ${RUN_COMMAND} check-sync --input-file demo.mp4 --subtitle-file out/demo.srt
USAGE
    ;;
  *)
    echo "Error: 未知命令: ${COMMAND}" >&2
    echo "使用 ${RUN_COMMAND} help 查看帮助。" >&2
    exit 1
    ;;
esac
