#!/data/data/com.termux/files/usr/bin/bash
set -u

failures=0
warnings=0

ok() { printf 'OK   %s\n' "$*"; }
warn() { printf 'WARN %s\n' "$*"; warnings=$((warnings + 1)); }
fail() { printf 'FAIL %s\n' "$*"; failures=$((failures + 1)); }

csv_has_entry() {
  local csv=$1 entry=$2
  case ",$csv," in
    *,"$entry",*) return 0 ;;
    *) return 1 ;;
  esac
}

toml_root_value() {
  local key=$1 file=$2
  [[ -r "$file" ]] || return 0
  awk -F= -v wanted="$key" '
    /^[[:space:]]*\[/ { exit }
    {
      lhs=$1
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", lhs)
      if (lhs == wanted) {
        value=$0
        sub(/^[^=]*=[[:space:]]*/, "", value)
        sub(/[[:space:]]*#.*/, "", value)
        gsub(/^[[:space:]"]+|[[:space:]"]+$/, "", value)
        print value
        exit
      }
    }
  ' "$file"
}

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

codex_network_env="$HOME/.config/android-termux-ssh/network-env.sh"
if [[ -r "$codex_network_env" ]]; then
  network_mode=$(stat -c '%a' "$codex_network_env" 2>/dev/null || true)
  [[ "$network_mode" == 600 ]] && ok 'Codex network environment mode is 600' \
    || warn "Codex network environment mode is ${network_mode:-unknown} (expected 600)"
  # shellcheck disable=SC1090
  . "$codex_network_env"
  if csv_has_entry "${NO_PROXY:-}" localhost \
      && csv_has_entry "${NO_PROXY:-}" 127.0.0.1 \
      && csv_has_entry "${NO_PROXY:-}" ::1; then
    ok 'NO_PROXY protects localhost, IPv4 loopback, and IPv6 loopback'
  else
    fail 'NO_PROXY must contain exact localhost, 127.0.0.1, and ::1 entries'
  fi
  if [[ -n "${CODEX_CA_CERTIFICATE:-}" && -s "$CODEX_CA_CERTIFICATE" ]]; then
    ok 'Codex CA bundle is readable and non-empty'
  else
    fail 'Codex CA bundle is missing, unreadable, or empty'
  fi
fi

if command -v codex >/dev/null 2>&1; then
  if codex_version=$(codex --version 2>/dev/null); then
    ok "Codex runtime: $codex_version"
  else
    fail 'Codex command exists but does not start'
  fi
  if command -v npm >/dev/null 2>&1 && command -v node >/dev/null 2>&1; then
    npm_root=$(npm root -g 2>/dev/null || true)
    main_package_json="$npm_root/@openai/codex/package.json"
    node_arch=$(node -p 'process.arch' 2>/dev/null || printf unknown)
    runtime_package_json="$npm_root/@openai/codex-linux-$node_arch/package.json"
    if [[ -r "$main_package_json" && -r "$runtime_package_json" ]]; then
      main_version=$(node -e 'console.log(require(process.argv[1]).version)' "$main_package_json" 2>/dev/null || printf unknown)
      runtime_version=$(node -e 'console.log(require(process.argv[1]).version)' "$runtime_package_json" 2>/dev/null || printf unknown)
      reported_version=${codex_version##* }
      if [[ "$runtime_version" == "${main_version}-linux-${node_arch}" \
          && "$reported_version" == "$main_version" ]]; then
        ok "Codex main/runtime/CLI versions match: $main_version"
      else
        fail "Codex version mismatch: main=$main_version runtime=$runtime_version cli=$reported_version"
      fi
    else
      fail 'Codex official npm main package or matching Linux runtime metadata is missing'
    fi
  else
    fail 'Node/npm is unavailable for Codex package verification'
  fi
  if codex login status >/dev/null 2>&1; then ok 'Codex ChatGPT authentication'; else warn 'Codex is not logged in'; fi
  codex_config="$HOME/.codex/config.toml"
  codex_sandbox=$(toml_root_value sandbox_mode "$codex_config")
  codex_approval=$(toml_root_value approval_policy "$codex_config")
  printf 'Codex policy: sandbox=%s approval=%s\n' "${codex_sandbox:-default}" "${codex_approval:-default}"
  if [[ "$codex_sandbox" == danger-full-access && "$codex_approval" == never ]]; then
    ok 'Codex Full access is explicitly configured'
  elif [[ "$codex_sandbox" == danger-full-access && "$codex_approval" == on-request ]]; then
    ok 'Codex sandbox is disabled while interactive approvals remain enabled'
  else
    warn 'Codex is not configured for either managed unsandboxed policy'
  fi
  if [[ -r "$PREFIX/bin/codex" ]] \
      && grep -Fq '# Managed Codex launcher for native Termux.' "$PREFIX/bin/codex"; then
    ok 'Codex managed proxy/CA launcher'
  else
    warn 'Codex managed launcher is absent; npm update may have restored its symlink'
  fi
  auth_file="$HOME/.codex/auth.json"
  if [[ -f "$auth_file" ]]; then
    auth_mode=$(stat -c '%a' "$auth_file" 2>/dev/null || true)
    [[ "$auth_mode" == 600 ]] && ok 'Codex auth cache mode is 600' \
      || warn "Codex auth cache mode is ${auth_mode:-unknown} (expected 600)"
  else
    warn 'Codex auth cache is missing'
  fi
else
  warn 'Codex CLI is not installed'
fi

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

ssh_start_directory_file="$HOME/.config/android-termux-ssh/ssh-start-directory"
if [[ -r "$ssh_start_directory_file" ]]; then
  IFS= read -r ssh_start_directory < "$ssh_start_directory_file" || true
  if [[ "${ssh_start_directory:-}" == /* && -d "$ssh_start_directory" \
      && -r "$ssh_start_directory" && -w "$ssh_start_directory" \
      && -x "$ssh_start_directory" ]]; then
    ok "interactive SSH start directory: $ssh_start_directory"
  else
    fail "interactive SSH start directory is invalid or unavailable: ${ssh_start_directory:-empty}"
  fi
  if [[ "${ssh_start_directory:-}" == /storage/emulated/0/* ]]; then
    if command -v git >/dev/null 2>&1; then
      git_safe_directory="$ssh_start_directory/*"
      if git config --global --get-all safe.directory 2>/dev/null \
          | grep -Fqx -- "$git_safe_directory"; then
        ok "Git safe.directory is scoped to the shared workspace subtree"
      else
        fail "Git safe.directory is missing for $git_safe_directory"
      fi
    else
      warn 'Git is not installed for the configured shared SSH workspace'
    fi
  fi
fi

workspace_alias="$HOME/workspace"
if [[ -L "$workspace_alias" ]]; then
  workspace_target=$(readlink -f -- "$workspace_alias" 2>/dev/null || true)
  if [[ -n "$workspace_target" && -d "$workspace_alias" \
      && -r "$workspace_alias" && -w "$workspace_alias" \
      && -x "$workspace_alias" ]]; then
    ok "shared workspace alias: ~/workspace -> $workspace_target"
  else
    fail 'shared workspace alias is broken or unavailable'
  fi
  if [[ "$workspace_target" == /storage/emulated/0/* ]] \
      && command -v git >/dev/null 2>&1; then
    git_safe_directory="$workspace_target/*"
    if git config --global --get-all safe.directory 2>/dev/null \
        | grep -Fqx -- "$git_safe_directory"; then
      ok 'Git safe.directory is scoped to the shared workspace target'
    else
      fail "Git safe.directory is missing for $git_safe_directory"
    fi
  fi
elif [[ -e "$workspace_alias" ]]; then
  warn '~/workspace exists but is not a symlink'
fi

printf '\nSummary: failures=%d warnings=%d\n' "$failures" "$warnings"
(( failures == 0 ))
