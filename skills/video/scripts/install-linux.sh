#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ARCH="$(uname -m)"

if command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1; then
  echo "ffmpeg 已存在于 PATH，跳过安装。"
  exit 0
fi

if [ "$(id -u)" -eq 0 ]; then
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update
    apt-get install -y ffmpeg
    exit 0
  fi
  if command -v dnf >/dev/null 2>&1; then
    dnf install -y ffmpeg
    exit 0
  fi
  if command -v yum >/dev/null 2>&1; then
    yum install -y epel-release || true
    yum install -y ffmpeg
    exit 0
  fi
  if command -v pacman >/dev/null 2>&1; then
    pacman -Sy --noconfirm ffmpeg
    exit 0
  fi
  if command -v zypper >/dev/null 2>&1; then
    zypper --non-interactive install ffmpeg
    exit 0
  fi
  if command -v apk >/dev/null 2>&1; then
    apk add --no-cache ffmpeg
    exit 0
  fi
fi

case "${ARCH}" in
  x86_64|amd64) BUILD_ARCH="linux64" ; TARGET_DIR="${SKILL_ROOT}/.cache/ffmpeg/linux-x64" ;;
  aarch64|arm64) BUILD_ARCH="linuxarm64" ; TARGET_DIR="${SKILL_ROOT}/.cache/ffmpeg/linux-arm64" ;;
  *)
    echo "Error: 暂不支持的 Linux 架构: ${ARCH}" >&2
    exit 1
    ;;
esac

TMP_DIR="$(mktemp -d)"
ARCHIVE="${TMP_DIR}/ffmpeg.tar.xz"
URL="https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-${BUILD_ARCH}-gpl.tar.xz"

echo "下载 FFmpeg: ${URL}"
curl -L "${URL}" -o "${ARCHIVE}"
tar -xJf "${ARCHIVE}" -C "${TMP_DIR}"

EXTRACTED_DIR="$(find "${TMP_DIR}" -maxdepth 1 -type d -name 'ffmpeg-*' | head -n1)"
if [ -z "${EXTRACTED_DIR}" ]; then
  echo "Error: 未找到解压后的 FFmpeg 目录。" >&2
  rm -rf "${TMP_DIR}"
  exit 1
fi

rm -rf "${TARGET_DIR}"
mkdir -p "${TARGET_DIR}"
cp -a "${EXTRACTED_DIR}/." "${TARGET_DIR}/"

echo "FFmpeg 已安装到 ${TARGET_DIR}"
echo "可将 ${TARGET_DIR}/bin 加入 PATH，或依赖 video skill 自动发现。"
rm -rf "${TMP_DIR}"
