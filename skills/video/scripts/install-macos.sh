#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ARCH="$(uname -m)"

if command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1; then
  echo "ffmpeg 已存在于 PATH，跳过安装。"
  exit 0
fi

if command -v brew >/dev/null 2>&1; then
  brew install ffmpeg
  exit 0
fi

case "${ARCH}" in
  x86_64|amd64) TARGET_DIR="${SKILL_ROOT}/.cache/ffmpeg/macos-x64/bin" ;;
  arm64|aarch64) TARGET_DIR="${SKILL_ROOT}/.cache/ffmpeg/macos-arm64/bin" ;;
  *)
    echo "Error: 暂不支持的 macOS 架构: ${ARCH}" >&2
    exit 1
    ;;
esac

TMP_DIR="$(mktemp -d)"
FFMPEG_ZIP="${TMP_DIR}/ffmpeg.zip"
FFPROBE_ZIP="${TMP_DIR}/ffprobe.zip"

echo "下载 ffmpeg"
curl -L "https://evermeet.cx/ffmpeg/getrelease/zip" -o "${FFMPEG_ZIP}"
echo "下载 ffprobe"
curl -L "https://evermeet.cx/ffmpeg/getrelease/ffprobe/zip" -o "${FFPROBE_ZIP}"

mkdir -p "${TARGET_DIR}"
unzip -qo "${FFMPEG_ZIP}" -d "${TMP_DIR}/ffmpeg"
unzip -qo "${FFPROBE_ZIP}" -d "${TMP_DIR}/ffprobe"

cp "${TMP_DIR}/ffmpeg/ffmpeg" "${TARGET_DIR}/ffmpeg"
cp "${TMP_DIR}/ffprobe/ffprobe" "${TARGET_DIR}/ffprobe"
chmod +x "${TARGET_DIR}/ffmpeg" "${TARGET_DIR}/ffprobe"

echo "FFmpeg 已安装到 ${TARGET_DIR}"
rm -rf "${TMP_DIR}"
