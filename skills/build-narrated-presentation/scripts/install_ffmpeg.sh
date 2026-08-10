#!/usr/bin/env bash
set -euo pipefail

if command -v ffmpeg >/dev/null 2>&1; then
  ffmpeg -version | head -n 1
  exit 0
fi

run_privileged() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    echo "Error: root or sudo is required to install ffmpeg." >&2
    exit 1
  fi
}

if command -v apt-get >/dev/null 2>&1; then
  run_privileged apt-get update
  run_privileged apt-get install -y ffmpeg
elif command -v dnf >/dev/null 2>&1; then
  run_privileged dnf install -y ffmpeg
elif command -v yum >/dev/null 2>&1; then
  run_privileged yum install -y ffmpeg
elif command -v pacman >/dev/null 2>&1; then
  run_privileged pacman -Sy --needed --noconfirm ffmpeg
elif command -v brew >/dev/null 2>&1; then
  brew install ffmpeg
else
  echo "Error: no supported package manager found; install ffmpeg from https://ffmpeg.org/download.html" >&2
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "Error: ffmpeg was installed but is not available on PATH; open a new shell and retry." >&2
  exit 1
fi
ffmpeg -version | head -n 1
