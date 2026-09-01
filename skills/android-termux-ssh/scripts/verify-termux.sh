#!/data/data/com.termux/files/usr/bin/bash
set -u

failures=0
warnings=0

ok() { printf 'OK   %s\n' "$*"; }
warn() { printf 'WARN %s\n' "$*"; warnings=$((warnings + 1)); }
fail() { printf 'FAIL %s\n' "$*"; failures=$((failures + 1)); }

if [[ ${PREFIX:-} != */com.termux/files/usr ]]; then
  printf 'ERROR: run this verifier inside Termux\n' >&2
  exit 2
fi

printf 'Termux user: %s (uid=%s)\n' "$(whoami)" "$(id -u)"
printf 'PREFIX: %s\n' "$PREFIX"

if command -v sshd >/dev/null 2>&1 && sshd -t; then ok 'sshd configuration'; else fail 'sshd configuration'; fi

if [[ -s "$HOME/.ssh/authorized_keys" ]]; then
  ok 'authorized_keys is non-empty'
  ssh-keygen -lf "$HOME/.ssh/authorized_keys" 2>/dev/null || fail 'authorized_keys fingerprint parsing'
  key_mode=$(stat -c '%a' "$HOME/.ssh/authorized_keys" 2>/dev/null || true)
  [[ "$key_mode" == 600 ]] && ok 'authorized_keys mode is 600' || warn "authorized_keys mode is $key_mode (expected 600)"
else
  fail 'authorized_keys is missing or empty'
fi

export SVDIR="$PREFIX/var/service"
if command -v sv >/dev/null 2>&1 && sv status "$PREFIX/var/service/sshd" 2>&1 | grep -q '^run:'; then
  ok 'runit sshd service is running'
else
  fail 'runit sshd service is not running'
fi

boot_script="$HOME/.termux/boot/start-sshd"
if [[ -x "$boot_script" ]]; then ok 'Termux:Boot sshd script'; else fail 'Termux:Boot sshd script'; fi

if [[ -s "$HOME/AGENTS.md" ]] && grep -Fq '<!-- BEGIN android-termux-ssh managed context -->' "$HOME/AGENTS.md"; then
  ok 'login-root AGENTS.md device context'
else
  fail 'login-root AGENTS.md device context is missing'
fi

port=8022
managed_sshd="$PREFIX/etc/ssh/sshd_config.d/20-android-termux-ssh.conf"
if [[ -r "$managed_sshd" ]]; then
  configured_port=$(awk '$1 == "Port" {print $2; exit}' "$managed_sshd")
  [[ -n "$configured_port" ]] && port=$configured_port
fi
printf 'Configured SSH port: %s\n' "$port"

if command -v ss >/dev/null 2>&1; then
  if ss -ltn 2>/dev/null | grep -Eq "[:.]${port}[[:space:]]"; then
    ok "TCP $port is listening"
  elif timeout 3 bash -c 'exec 3<>/dev/tcp/127.0.0.1/$1' _ "$port" 2>/dev/null; then
    ok "TCP $port accepts loopback connections (Android hid socket details from ss)"
  else
    warn "could not confirm TCP $port with ss or a loopback connection"
  fi
else
  if timeout 3 bash -c 'exec 3<>/dev/tcp/127.0.0.1/$1' _ "$port" 2>/dev/null; then
    ok "TCP $port accepts loopback connections"
  else
    warn 'ss is unavailable and the loopback port check failed'
  fi
fi

if command -v termux-wake-lock >/dev/null 2>&1; then ok 'termux-wake-lock command'; else fail 'termux-wake-lock command'; fi

if command -v termux-wifi-scaninfo >/dev/null 2>&1; then ok 'Termux:API CLI'; else warn 'Termux:API CLI not installed'; fi
if command -v remote-camera-photo >/dev/null 2>&1; then ok 'camera helper'; else warn 'camera helper not installed'; fi
if command -v termux-bluetooth >/dev/null 2>&1; then
  if bluetooth_status=$(termux-bluetooth status 2>/dev/null); then
    if grep -Fq '"scanPermission":true' <<<"$bluetooth_status" \
        && grep -Fq '"connectPermission":true' <<<"$bluetooth_status"; then
      ok 'local-only Bluetooth companion and Android permissions'
    else
      warn "Bluetooth companion responded but permissions are incomplete: $bluetooth_status"
    fi
  else
    fail 'Bluetooth companion helper is installed but the loopback service is unavailable'
  fi
elif command -v termux-bluetooth-scaninfo >/dev/null 2>&1; then
  ok 'Bluetooth scan CLI detected; verify its source and Android permissions'
elif command -v remote-bluetooth-settings >/dev/null 2>&1; then
  warn 'official Bluetooth scan/connect CLI is unavailable; only the Bluetooth settings helper is installed'
else
  warn 'Bluetooth integration is unavailable'
fi

if [[ -d "$HOME/storage/downloads" ]]; then
  [[ -r "$HOME/storage/downloads" ]] && ok 'downloads storage is readable' || fail 'downloads storage read access'
  [[ -w "$HOME/storage/downloads" ]] && ok 'downloads storage is writable' || fail 'downloads storage write access'
else
  warn '~/storage/downloads is unavailable'
fi

printf '\nSummary: failures=%d warnings=%d\n' "$failures" "$warnings"
(( failures == 0 ))
