#!/usr/bin/env bash
set -u -o pipefail

ADB_BIN=${ADB:-adb}
SERIAL=
PORT=8022
failures=0
warnings=0

usage() {
  cat <<'EOF'
Usage: host-doctor.sh [--adb PATH] [--serial SERIAL] [--port PORT]

Read-only Android/Termux checks. This script does not install packages or change settings.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --adb) [[ $# -ge 2 ]] || { usage >&2; exit 2; }; ADB_BIN=$2; shift 2 ;;
    --serial) [[ $# -ge 2 ]] || { usage >&2; exit 2; }; SERIAL=$2; shift 2 ;;
    --port) [[ $# -ge 2 ]] || { usage >&2; exit 2; }; PORT=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

command -v "$ADB_BIN" >/dev/null 2>&1 || { printf 'ERROR: adb not found: %s\n' "$ADB_BIN" >&2; exit 2; }
ADB_CMD=("$ADB_BIN")
[[ -n "$SERIAL" ]] && ADB_CMD+=(-s "$SERIAL")

adb_shell() { "${ADB_CMD[@]}" shell "$@" | tr -d '\r'; }
ok() { printf 'OK   %s\n' "$*"; }
warn() { printf 'WARN %s\n' "$*"; warnings=$((warnings + 1)); }
fail() { printf 'FAIL %s\n' "$*"; failures=$((failures + 1)); }

state=$("${ADB_CMD[@]}" get-state 2>/dev/null | tr -d '\r' || true)
[[ "$state" == device ]] || { printf 'ERROR: no usable adb device (state=%s)\n' "${state:-none}" >&2; exit 2; }

manufacturer=$(adb_shell getprop ro.product.manufacturer)
model=$(adb_shell getprop ro.product.model)
release=$(adb_shell getprop ro.build.version.release)
sdk=$(adb_shell getprop ro.build.version.sdk)
abi=$(adb_shell getprop ro.product.cpu.abi)
printf 'Device: %s %s, Android %s (API %s), %s\n' "$manufacturer" "$model" "$release" "$sdk" "$abi"

packages=(com.termux com.termux.api com.termux.boot)
declare -A package_uid
for package_name in "${packages[@]}"; do
  if adb_shell pm path "$package_name" 2>/dev/null | grep -q '^package:'; then
    dump=$(adb_shell dumpsys package "$package_name")
    version=$(awk -F= '/versionName=/{print $2; exit}' <<<"$dump")
    uid=$(adb_shell pm list packages -U "$package_name" | awk -v target="package:$package_name" '$1 == target {sub(/^uid:/, "", $2); print $2; exit}')
    package_uid[$package_name]=$uid
    ok "$package_name installed (version=${version:-unknown}, uid=${uid:-unknown})"
  elif [[ "$package_name" == com.termux ]]; then
    fail "$package_name is not installed"
  else
    warn "$package_name is not installed"
  fi
done

if [[ -n ${package_uid[com.termux]:-} ]]; then
  for package_name in com.termux.api com.termux.boot; do
    if [[ -n ${package_uid[$package_name]:-} && ${package_uid[$package_name]} != "${package_uid[com.termux]}" ]]; then
      fail "$package_name does not share the Termux UID"
    fi
  done
fi

if adb_shell ss -ltn 2>/dev/null | grep -Eq "[:.]${PORT}[[:space:]]"; then
  ok "TCP $PORT is listening"
else
  warn "TCP $PORT was not visible in Android ss output"
fi

ip_address=$(adb_shell ip -4 -o addr show wlan0 2>/dev/null | awk '{split($4,a,"/"); print a[1]; exit}')
[[ -n "$ip_address" ]] && printf 'Wi-Fi IP: %s\n' "$ip_address" || warn 'Wi-Fi IPv4 address not found'

power=$(adb_shell dumpsys power)
wakefulness=$(grep -m1 'mWakefulness=' <<<"$power" | sed 's/^[[:space:]]*//')
printf 'Power: %s\n' "${wakefulness:-unknown}"
wake_line=$(grep -m1 "termux:service-wakelock" <<<"$power" | sed 's/^[[:space:]]*//' || true)
if [[ -z "$wake_line" ]]; then
  warn 'Termux partial wake lock not found'
elif [[ "$wake_line" == *DISABLED* ]]; then
  fail "Termux wake lock is disabled: $wake_line"
else
  ok "Termux wake lock: $wake_line"
fi

deviceidle=$(adb_shell cmd deviceidle whitelist 2>/dev/null || true)
for package_name in "${packages[@]}"; do
  if adb_shell pm path "$package_name" >/dev/null 2>&1; then
    grep -q ",$package_name," <<<"$deviceidle" && ok "$package_name is in DeviceIdle whitelist" || warn "$package_name is not in DeviceIdle whitelist"
  fi
done

if [[ "${manufacturer,,}" == *xiaomi* || "${manufacturer,,}" == *redmi* ]]; then
  millet=$(adb_shell settings get system MILLET_NO_RESTRICT_APP 2>/dev/null || true)
  printf 'HyperOS/MIUI MILLET_NO_RESTRICT_APP: %s\n' "${millet:-unset}"
  millet_compact=${millet//[[:space:]]/}
  for package_name in "${packages[@]}"; do
    if adb_shell pm path "$package_name" >/dev/null 2>&1; then
      case ",$millet_compact," in
        *",$package_name,"*) ok "$package_name is in the Greeze no-restrict list" ;;
        *) warn "$package_name is absent from the Greeze no-restrict list" ;;
      esac
    fi
  done
fi

forwards=$("${ADB_CMD[@]}" forward --list 2>/dev/null | tr -d '\r')
if [[ -n "$forwards" ]]; then
  warn 'ADB forwards exist; final standalone verification must remove them'
  printf '%s\n' "$forwards"
else
  ok 'no ADB forwards'
fi

printf '\nSummary: failures=%d warnings=%d\n' "$failures" "$warnings"
(( failures == 0 ))
