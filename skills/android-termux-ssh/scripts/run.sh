#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

usage() {
  cat <<'EOF'
Usage: run.sh <command> [arguments]

Commands:
  bootstrap         Configure packages, SSH, Boot, API helpers, storage, and Bash inside Termux
  configure-codex   Install/configure official Codex CLI inside native Termux
  verify            Run read-only checks inside Termux
  update-agents     Refresh the managed device context in ~/AGENTS.md
  host-doctor       Inspect an Android device through ADB without changing it
  host-permissions  Preview or apply Android permission/background settings
  build-bluetooth   Build the audited local-only Bluetooth companion APK
  deploy-bluetooth  Install/provision the Bluetooth companion (initial ADB only)
  help              Show this help

Run '<command> --help' for command-specific options.
EOF
}

command_name=${1:-help}
if [[ $# -gt 0 ]]; then shift; fi

case "$command_name" in
  bootstrap) exec bash "$SCRIPT_DIR/bootstrap.sh" "$@" ;;
  configure-codex) exec bash "$SCRIPT_DIR/configure-codex.sh" "$@" ;;
  verify) exec bash "$SCRIPT_DIR/verify-termux.sh" "$@" ;;
  update-agents) exec bash "$SCRIPT_DIR/update-agents-md.sh" "$@" ;;
  host-doctor) exec bash "$SCRIPT_DIR/host-doctor.sh" "$@" ;;
  host-permissions) exec bash "$SCRIPT_DIR/host-android-permissions.sh" "$@" ;;
  build-bluetooth) exec bash "$SCRIPT_DIR/build-bluetooth-companion.sh" "$@" ;;
  deploy-bluetooth) exec bash "$SCRIPT_DIR/deploy-bluetooth-companion.sh" "$@" ;;
  help|-h|--help) usage ;;
  *)
    printf 'Unknown command: %s\n\n' "$command_name" >&2
    usage >&2
    exit 2
    ;;
esac
