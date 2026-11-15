#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ ${1:-} == --help || ${1:-} == -h ]]; then
  printf '%s\n' 'Usage: run.sh desktop-install [--profile FILE] [--apps code,chromium,office,vlc|none] --apply [--adopt-existing]'
  printf '%s\n' 'Run desktop-plan first. Installation runs inside native Termux; it does not install Android APKs or stop an active desktop.'
  exit 0
fi
if ! command -v python >/dev/null 2>&1; then
  printf '%s\n' 'Missing Python. In native Termux run: pkg install python' >&2
  exit 1
fi
exec python "$SCRIPT_DIR/desktop_setup.py" install "$@"
