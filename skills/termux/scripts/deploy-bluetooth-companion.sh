#!/usr/bin/env bash
set -Eeuo pipefail

PACKAGE=io.github.scisaga.termuxbluetoothbridge
ACTIVITY="$PACKAGE/.MainActivity"
APK=
SERIAL=
ADB_BIN=${ADB_BIN:-}
SSH_BIN=${SSH_BIN:-}
SSH_HOST=root@PHONE_IP
SSH_PORT=8022
HYPEROS_EXEMPT=0
GREEZE_STATUS=unknown
SKIP_INSTALL=0
RESET_COMPANION_DATA=0

usage() {
  cat <<'EOF'
Usage: deploy-bluetooth-companion.sh [options]

Install and provision the local-only Termux Bluetooth Bridge. ADB is used only
for this initial APK/permission step; the resulting Termux command uses loopback.

Required:
  --apk PATH              signed companion APK
  --serial SERIAL         adb device serial
  --ssh-host USER@IP      working direct-LAN Termux SSH target

Options:
  --ssh-port PORT         Termux SSH port (default: 8022)
  --adb PATH              adb or adb.exe
  --ssh PATH              ssh or ssh.exe
  --skip-install          provision an APK that was installed manually
  --reset-companion-data clear only the companion token/settings before provisioning
  --hyperos-exempt        append companion package to Greeze user exemptions
  -h, --help              show this help
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apk) [[ $# -ge 2 ]] || die "$1 requires a path"; APK=$2; shift 2 ;;
    --serial) [[ $# -ge 2 ]] || die "$1 requires a value"; SERIAL=$2; shift 2 ;;
    --ssh-host) [[ $# -ge 2 ]] || die "$1 requires a value"; SSH_HOST=$2; shift 2 ;;
    --ssh-port) [[ $# -ge 2 ]] || die "$1 requires a value"; SSH_PORT=$2; shift 2 ;;
    --adb) [[ $# -ge 2 ]] || die "$1 requires a path"; ADB_BIN=$2; shift 2 ;;
    --ssh) [[ $# -ge 2 ]] || die "$1 requires a path"; SSH_BIN=$2; shift 2 ;;
    --skip-install) SKIP_INSTALL=1; shift ;;
    --reset-companion-data) RESET_COMPANION_DATA=1; shift ;;
    --hyperos-exempt) HYPEROS_EXEMPT=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done

[[ -n "$APK" && -r "$APK" ]] || die '--apk must name a readable APK'
[[ -n "$SERIAL" ]] || die '--serial is required'
[[ "$SSH_HOST" != root@PHONE_IP ]] || die '--ssh-host is required'
[[ "$SSH_PORT" =~ ^[0-9]+$ ]] || die '--ssh-port must be numeric'

if [[ -z "$ADB_BIN" ]]; then
  if command -v adb >/dev/null 2>&1; then
    ADB_BIN=$(command -v adb)
  else
    candidate=/mnt/c/Users/${USER}/AppData/Local/Android/platform-tools/adb.exe
    [[ -x "$candidate" ]] && ADB_BIN=$candidate
  fi
fi
if [[ -z "$SSH_BIN" ]]; then
  if [[ -x /mnt/c/Windows/System32/OpenSSH/ssh.exe ]]; then
    SSH_BIN=/mnt/c/Windows/System32/OpenSSH/ssh.exe
  elif command -v ssh >/dev/null 2>&1; then
    SSH_BIN=$(command -v ssh)
  fi
fi
[[ -n "$ADB_BIN" && -x "$ADB_BIN" ]] || die 'adb not found; pass --adb'
[[ -n "$SSH_BIN" && -x "$SSH_BIN" ]] || die 'ssh not found; pass --ssh'

ADB=("$ADB_BIN" -s "$SERIAL")
SSH=("$SSH_BIN" -o BatchMode=yes -o ConnectTimeout=8 -p "$SSH_PORT" "$SSH_HOST")
"${ADB[@]}" get-state >/dev/null
"${SSH[@]}" true >/dev/null || die 'direct Termux SSH is not working before deployment'

token=$("${SSH[@]}" 'if [ -s "$HOME/.config/android-termux-ssh/bluetooth-bridge.token" ]; then tr -d "\r\n" < "$HOME/.config/android-termux-ssh/bluetooth-bridge.token"; fi' | tr -d '\r')
if [[ ! "$token" =~ ^[0-9a-fA-F]{64}$ ]]; then
  token=$(openssl rand -hex 32)
fi

if (( SKIP_INSTALL == 0 )); then
  printf 'Installing Bluetooth companion APK...\n'
  apk_argument=$APK
  if [[ "$ADB_BIN" == *.exe ]] && command -v wslpath >/dev/null 2>&1; then
    apk_argument=$(wslpath -w "$APK")
  fi
  "${ADB[@]}" install -r "$apk_argument"
else
  "${ADB[@]}" shell pm path "$PACKAGE" | grep -q '^package:' || \
    die '--skip-install was used but the companion package is not installed'
  printf 'Companion package is already installed; skipping adb install.\n'
fi
if (( RESET_COMPANION_DATA == 1 )); then
  printf 'Clearing only the companion app data before token provisioning...\n'
  "${ADB[@]}" shell pm clear "$PACKAGE" | grep -q '^Success' || \
    die 'could not clear companion app data'
fi
"${ADB[@]}" shell am start -n "$ACTIVITY" --es bridge_token "$token" >/dev/null
for permission in \
  android.permission.BLUETOOTH_SCAN \
  android.permission.BLUETOOTH_CONNECT \
  android.permission.POST_NOTIFICATIONS; do
  "${ADB[@]}" shell pm grant "$PACKAGE" "$permission"
done
"${ADB[@]}" shell am start -n "$ACTIVITY" --es bridge_token "$token" >/dev/null

if (( HYPEROS_EXEMPT == 1 )); then
  current=$("${ADB[@]}" shell settings get global greeze_user_exempt_list | tr -d '\r\n')
  [[ "$current" == null ]] && current=
  for exempt_package in com.termux com.termux.api com.termux.boot "$PACKAGE"; do
    case ",$current," in
      *",$exempt_package,"*) ;;
      *) if [[ -n "$current" ]]; then current="$current,$exempt_package"; else current=$exempt_package; fi ;;
    esac
  done
  "${ADB[@]}" shell settings put global greeze_user_exempt_list "$current"
  GREEZE_STATUS=enabled
fi

# Some OEM ROMs freeze Termux as soon as the companion Activity becomes top-most.
# Return to Termux before provisioning through its direct-LAN SSH service.
"${ADB[@]}" shell am start -n com.termux/com.termux.app.TermuxActivity >/dev/null || true
sleep 1

{
  printf 'BRIDGE_TOKEN=%q\n' "$token"
  printf 'BRIDGE_GREEZE_STATUS=%q\n' "$GREEZE_STATUS"
  cat <<'REMOTE_SCRIPT'
set -Eeuo pipefail
config_dir="$HOME/.config/android-termux-ssh"
install -d -m 700 "$config_dir"
printf '%s\n' "$BRIDGE_TOKEN" > "$config_dir/bluetooth-bridge.token"
chmod 600 "$config_dir/bluetooth-bridge.token"
cat > "$PREFIX/bin/termux-bluetooth" <<'HELPER'
#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
token_file="$HOME/.config/android-termux-ssh/bluetooth-bridge.token"
endpoint=http://127.0.0.1:18765
[[ -s "$token_file" ]] || { echo "Bluetooth bridge token is missing" >&2; exit 1; }
token=$(tr -d '\r\n' < "$token_file")
auth=( -H "Authorization: Bearer $token" )
case "${1:-help}" in
  status)
    exec curl --fail-with-body -sS --max-time 5 "${auth[@]}" "$endpoint/v1/status"
    ;;
  bonded)
    exec curl --fail-with-body -sS --max-time 10 "${auth[@]}" "$endpoint/v1/bonded"
    ;;
  scan)
    seconds=${2:-8}
    [[ "$seconds" =~ ^[0-9]+$ ]] || { echo "scan seconds must be numeric" >&2; exit 2; }
    (( seconds >= 1 && seconds <= 25 )) || { echo "scan seconds must be 1..25" >&2; exit 2; }
    exec curl --fail-with-body -sS --max-time "$((seconds + 8))" -X POST \
      "${auth[@]}" "$endpoint/v1/ble/scan?seconds=$seconds"
    ;;
  open|start)
    exec am start -n io.github.scisaga.termuxbluetoothbridge/.MainActivity
    ;;
  settings)
    exec am start -a android.settings.BLUETOOTH_SETTINGS
    ;;
  help|-h|--help)
    printf '%s\n' 'Usage: termux-bluetooth {start|status|bonded|scan [1..25]|open|settings}'
    ;;
  *)
    echo "unknown command: $1" >&2
    exit 2
    ;;
esac
HELPER
chmod 755 "$PREFIX/bin/termux-bluetooth"
if command -v update-termux-agents >/dev/null 2>&1; then
  update-termux-agents --greeze-status "$BRIDGE_GREEZE_STATUS" || true
fi
REMOTE_SCRIPT
} | "${SSH[@]}" 'bash -s'

sleep 2
printf 'Declared/granted Bluetooth permissions:\n'
"${ADB[@]}" shell dumpsys package "$PACKAGE" | tr -d '\r' | \
  grep -E 'BLUETOOTH_(SCAN|CONNECT)|runtime permissions' || true
printf 'Loopback bridge status through direct SSH:\n'
if ! "${SSH[@]}" 'termux-bluetooth status && printf "\n"'; then
  die 'the loopback bridge is unavailable or its token does not match; rerun with --reset-companion-data only if clearing companion settings is authorized'
fi
printf 'Deployment complete. Daily commands do not require ADB.\n'
