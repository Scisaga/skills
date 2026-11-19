#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
printf -v RUN_COMMAND 'bash %q' "${SCRIPT_DIR}/run.sh"

usage() {
  cat <<EOF
Usage: ${RUN_COMMAND} <command> [arguments]

Commands:
  bootstrap         Configure packages, SSH, Boot, API helpers, storage, and Bash inside Termux
  configure-codex   Install/configure official Codex CLI inside native Termux
  verify            Run read-only checks inside Termux
  update-agents     Refresh the managed device context in ~/AGENTS.md
  host-doctor       Inspect an Android device through ADB without changing it
  host-permissions  Preview or apply Android permission/background settings
  build-bluetooth   Build the audited local-only Bluetooth companion APK
  deploy-bluetooth  Install/provision the Bluetooth companion (initial ADB only)
  desktop-plan      Show the optional desktop profile without changing a device
  desktop-install   Install/configure Debian/Xfce and selected applications in native Termux
  desktop-doctor    Check desktop components without starting a desktop
  desktop-verify    Gate effective policy, boot, screen-off and GPU evidence
  desktop-baseline  Compare desktop readbacks and verify a recovery bundle
  gpu-probe         Measure only an explicitly isolated Chromium debug instance
  window-probe      Inspect live Xfwm state; explicit --apply allows a reversible redraw comparison
  memory-report     Read Android/Termux PSS, memtrack and physical ZRAM; compare matched snapshots
  present-report    Analyze saved SurfaceFlinger timestamps offline; never contacts a device
  context-block     Preview/apply one reviewed UTF-8 AGENTS block with backup and readback
  desktop-context   Refresh native and guest managed desktop context
  repair-panel      Reposition a stale auto-hide trigger without restarting applications
  build-manager     Build the graphical Android manager and both launcher entries
  deploy-manager    Install/provision only the separate-UID manager APK
  launcher-plan     Inventory Android entries for a Termux home-screen folder
  network-doctor    Check VPN, proxy and DNS in host/native mode
  host-tools        Download user-local Android platform-tools or JDK
  help              Show this help

Run '<command> --help' for command-specific options.
EOF
}

command_name=${1:-help}
if [[ $# -gt 0 ]]; then shift; fi

run_python() {
  local interpreter candidate
  local -a candidates=(python3 python)
  [[ ${OSTYPE:-} != msys* && ${OSTYPE:-} != cygwin* ]] || candidates=(python python3)
  for candidate in "${candidates[@]}"; do
    interpreter=$(command -v "$candidate" || true)
    [[ -n "$interpreter" && "$interpreter" != */Microsoft/WindowsApps/* ]] || continue
    if "$interpreter" -c 'import sys; sys.exit(sys.version_info < (3, 10))' >/dev/null 2>&1; then
      exec "$interpreter" "$SCRIPT_DIR/$1" "${@:2}"
    fi
  done
  printf '%s\n' 'Python 3.10+ required. Termux: pkg install python; Windows: winget install Python.Python.3.12; Debian/Ubuntu: sudo apt install python3; macOS: brew install python' >&2
  exit 1
}

case "$command_name" in
  bootstrap) exec bash "$SCRIPT_DIR/bootstrap.sh" "$@" ;;
  configure-codex) exec bash "$SCRIPT_DIR/configure-codex.sh" "$@" ;;
  verify) exec bash "$SCRIPT_DIR/verify-termux.sh" "$@" ;;
  update-agents) exec bash "$SCRIPT_DIR/update-agents-md.sh" "$@" ;;
  host-doctor) exec bash "$SCRIPT_DIR/host-doctor.sh" "$@" ;;
  host-permissions) exec bash "$SCRIPT_DIR/host-android-permissions.sh" "$@" ;;
  build-bluetooth) exec bash "$SCRIPT_DIR/build-bluetooth-companion.sh" "$@" ;;
  deploy-bluetooth) exec bash "$SCRIPT_DIR/deploy-bluetooth-companion.sh" "$@" ;;
  desktop-plan) run_python desktop_setup.py plan "$@" ;;
  desktop-install) exec bash "$SCRIPT_DIR/install-desktop.sh" "$@" ;;
  desktop-doctor) run_python desktop_setup.py doctor "$@" ;;
  desktop-verify) run_python desktop_verify.py "$@" ;;
  desktop-baseline) run_python desktop_baseline.py "$@" ;;
  gpu-probe) run_python gpu_probe.py "$@" ;;
  window-probe) run_python window_probe.py "$@" ;;
  memory-report) run_python memory_report.py "$@" ;;
  present-report) run_python presentation_timing.py "$@" ;;
  context-block) run_python managed_context.py "$@" ;;
  desktop-context) run_python desktop_setup.py update-context "$@" ;;
  repair-panel) run_python desktop_setup.py repair-panel "$@" ;;
  build-manager) run_python build_desktop_manager.py "$@" ;;
  deploy-manager) run_python deploy_desktop_manager.py "$@" ;;
  launcher-plan) run_python launcher_plan.py "$@" ;;
  network-doctor) run_python network_doctor.py "$@" ;;
  host-tools) run_python host_tools.py "$@" ;;
  help|-h|--help) usage ;;
  *)
    printf 'Unknown command: %s\n\n' "$command_name" >&2
    usage >&2
    exit 2
    ;;
esac
