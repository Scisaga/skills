#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${PYTHON:-python3}"
if [ -x "${SKILL_ROOT}/.venv/bin/python" ]; then
  PYTHON_BIN="${SKILL_ROOT}/.venv/bin/python"
elif [ -f "${SKILL_ROOT}/.venv/Scripts/python.exe" ]; then
  PYTHON_BIN="${SKILL_ROOT}/.venv/Scripts/python.exe"
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
    cat <<'USAGE'
Usage:
  video/scripts/run.sh bootstrap [--check-only] [--skip-ffmpeg]
  video/scripts/run.sh doctor
  video/scripts/run.sh install-ffmpeg
  video/scripts/run.sh keyframes --input-file demo.mp4 --output-dir out/frames
  video/scripts/run.sh extract-audio --input-file demo.mp4 --output-file out/demo.wav
  video/scripts/run.sh subtitles --input-file demo.mp4 --output-srt out/demo.srt
  video/scripts/run.sh mux --input-file demo.mkv --subtitle-file out/demo.srt --output-file out/demo.mp4 --check-sync
  video/scripts/run.sh check-sync --input-file demo.mp4 --subtitle-file out/demo.srt
USAGE
    ;;
  *)
    echo "Error: 未知命令: ${COMMAND}" >&2
    echo "使用 \`video/scripts/run.sh help\` 查看帮助。" >&2
    exit 1
    ;;
esac
