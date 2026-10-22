#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

PROXY_URL=
CA_BUNDLE=${PREFIX:-}/etc/tls/cert.pem
CODEX_VERSION=latest
NO_SANDBOX=0
FULL_ACCESS=0
SKIP_INSTALL=0
NO_PROXY_VALUE='localhost,127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,.local'

usage() {
  cat <<'EOF'
Usage: configure-codex.sh [options]

Install and configure the official Codex CLI in native Termux. Android is not
an officially documented Codex platform, so this script verifies the runtime
and installs only OpenAI's matching Linux ARM64/x64 package workaround.

Options:
  --proxy URL          HTTP CONNECT proxy used by Codex and HTTPS tools
  --ca-bundle PATH     PEM CA bundle (default: $PREFIX/etc/tls/cert.pem)
  --version VERSION    Codex version or npm tag (default: latest)
  --no-proxy VALUE     comma-separated NO_PROXY value
  --no-sandbox         persist sandbox_mode="danger-full-access"
  --full-access        disable both sandbox and approval prompts
  --skip-install       keep the existing Codex packages; configure only
  -h, --help           show this help

Neither permissive mode is implied. --no-sandbox keeps on-request approvals;
--full-access also sets approval_policy="never". Use either only after the user
explicitly accepts the corresponding access level.
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --proxy) [[ $# -ge 2 ]] || die "$1 requires a value"; PROXY_URL=$2; shift 2 ;;
    --ca-bundle) [[ $# -ge 2 ]] || die "$1 requires a value"; CA_BUNDLE=$2; shift 2 ;;
    --version) [[ $# -ge 2 ]] || die "$1 requires a value"; CODEX_VERSION=$2; shift 2 ;;
    --no-proxy) [[ $# -ge 2 ]] || die "$1 requires a value"; NO_PROXY_VALUE=$2; shift 2 ;;
    --no-sandbox) NO_SANDBOX=1; shift ;;
    --full-access) FULL_ACCESS=1; shift ;;
    --skip-install) SKIP_INSTALL=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done

(( NO_SANDBOX == 0 || FULL_ACCESS == 0 )) || die '--no-sandbox and --full-access are mutually exclusive'
(( FULL_ACCESS == 0 )) || NO_SANDBOX=1

[[ ${PREFIX:-} == */com.termux/files/usr ]] || die 'run this script inside the standard Termux environment'
[[ -n "$CA_BUNDLE" && "$CA_BUNDLE" == /* ]] || die 'CA bundle must be an absolute path'
[[ -r "$CA_BUNDLE" && -s "$CA_BUNDLE" ]] || die "CA bundle is not readable or is empty: $CA_BUNDLE"
[[ "$CODEX_VERSION" =~ ^[0-9A-Za-z.+-]+$ ]] || die 'Codex version contains unsupported characters'
if [[ -n "$PROXY_URL" ]]; then
  [[ "$PROXY_URL" =~ ^https?://[^[:space:]]+$ ]] || die 'proxy must be an http:// or https:// URL'
  export HTTP_PROXY="$PROXY_URL" HTTPS_PROXY="$PROXY_URL" ALL_PROXY="$PROXY_URL"
  export http_proxy="$PROXY_URL" https_proxy="$PROXY_URL" all_proxy="$PROXY_URL"
fi
export NO_PROXY="$NO_PROXY_VALUE" no_proxy="$NO_PROXY_VALUE"
export CODEX_CA_CERTIFICATE="$CA_BUNDLE" SSL_CERT_FILE="$CA_BUNDLE"
export NODE_EXTRA_CA_CERTS="$CA_BUNDLE" npm_config_cafile="$CA_BUNDLE"

codex_bin="$PREFIX/bin/codex"
wrapper_marker='# Managed Codex launcher for native Termux.'
if [[ -e "$codex_bin" && ! -L "$codex_bin" ]] \
    && ! grep -Fq -- "$wrapper_marker" "$codex_bin" 2>/dev/null; then
  die "refusing to replace an unmanaged file: $codex_bin"
fi

if (( SKIP_INSTALL == 0 )); then
  command -v pkg >/dev/null 2>&1 || die 'pkg is unavailable'
  pkg install -y nodejs-lts
  npm install -g "@openai/codex@$CODEX_VERSION"

  npm_root=$(npm root -g)
  package_json="$npm_root/@openai/codex/package.json"
  [[ -r "$package_json" ]] || die "installed Codex package metadata is missing: $package_json"
  installed_version=$(node -e 'console.log(require(process.argv[1]).version)' "$package_json")
  node_platform=$(node -p 'process.platform')
  node_arch=$(node -p 'process.arch')

  if [[ "$node_platform" == android ]]; then
    case "$node_arch" in
      arm64|x64) platform_arch=$node_arch ;;
      *) die "unsupported Android Node architecture: $node_arch" ;;
    esac
    npm install -g --force \
      "@openai/codex-linux-$platform_arch@npm:@openai/codex@${installed_version}-linux-${platform_arch}"
  fi
fi

command -v codex >/dev/null 2>&1 || die 'codex is not on PATH after installation'
command -v npm >/dev/null 2>&1 || die 'npm is unavailable'
npm_root=$(npm root -g)
package_json="$npm_root/@openai/codex/package.json"
[[ -r "$package_json" ]] || die "installed Codex package metadata is missing: $package_json"
installed_version=$(node -e 'console.log(require(process.argv[1]).version)' "$package_json")
node_platform=$(node -p 'process.platform')
node_arch=$(node -p 'process.arch')
if [[ "$node_platform" == android ]]; then
  case "$node_arch" in
    arm64|x64) platform_arch=$node_arch ;;
    *) die "unsupported Android Node architecture: $node_arch" ;;
  esac
  runtime_package_json="$npm_root/@openai/codex-linux-$platform_arch/package.json"
  [[ -r "$runtime_package_json" ]] \
    || die "matching official Codex runtime package is missing: $runtime_package_json"
  runtime_package_version=$(node -e 'console.log(require(process.argv[1]).version)' "$runtime_package_json")
  expected_runtime_version="${installed_version}-linux-${platform_arch}"
  [[ "$runtime_package_version" == "$expected_runtime_version" ]] \
    || die "Codex package/runtime mismatch: $installed_version vs $runtime_package_version"
fi
codex_version_output=$(codex --version) || die 'Codex runtime did not start'
reported_version=${codex_version_output##* }
[[ "$reported_version" == "$installed_version" ]] \
  || die "Codex package/CLI mismatch: $installed_version vs $reported_version"

managed_dir="$HOME/.config/android-termux-ssh"
install -d -m 700 "$managed_dir" "$HOME/.codex"
network_env="$managed_dir/network-env.sh"
network_tmp=$(mktemp "$PREFIX/tmp/android-termux-network-env.XXXXXX")
config_tmp=$(mktemp "$PREFIX/tmp/android-termux-codex-config.XXXXXX")
bashrc_tmp=$(mktemp "$PREFIX/tmp/android-termux-bashrc.XXXXXX")
wrapper_tmp=$(mktemp "$PREFIX/tmp/android-termux-codex-wrapper.XXXXXX")

cleanup() {
  [[ -f "$network_tmp" ]] && unlink "$network_tmp"
  [[ -f "$config_tmp" ]] && unlink "$config_tmp"
  [[ -f "$bashrc_tmp" ]] && unlink "$bashrc_tmp"
  [[ -f "$wrapper_tmp" ]] && unlink "$wrapper_tmp"
}
trap cleanup EXIT

{
  printf '%s\n' '# Managed by android-termux-ssh for tools that require the configured egress proxy.'
  if [[ -n "$PROXY_URL" ]]; then
    printf 'export HTTP_PROXY=%q\n' "$PROXY_URL"
    printf 'export HTTPS_PROXY=%q\n' "$PROXY_URL"
    printf 'export ALL_PROXY=%q\n' "$PROXY_URL"
    printf 'export http_proxy=%q\n' "$PROXY_URL"
    printf 'export https_proxy=%q\n' "$PROXY_URL"
    printf 'export all_proxy=%q\n' "$PROXY_URL"
  fi
  printf 'export NO_PROXY=%q\n' "$NO_PROXY_VALUE"
  printf 'export no_proxy=%q\n' "$NO_PROXY_VALUE"
  printf 'export CODEX_CA_CERTIFICATE=%q\n' "$CA_BUNDLE"
  printf 'export SSL_CERT_FILE=%q\n' "$CA_BUNDLE"
  printf 'export NODE_EXTRA_CA_CERTS=%q\n' "$CA_BUNDLE"
  printf 'export npm_config_cafile=%q\n' "$CA_BUNDLE"
} > "$network_tmp"
install -m 600 "$network_tmp" "$network_env"

codex_launcher="$npm_root/@openai/codex/bin/codex.js"
[[ -r "$codex_launcher" ]] || die "Codex JavaScript launcher is missing: $codex_launcher"
{
  printf '%s\n' '#!/data/data/com.termux/files/usr/bin/bash'
  printf '%s\n' '# Managed Codex launcher for native Termux.'
  printf '%s\n' 'set -Eeuo pipefail'
  printf '%s\n' '[[ -r "$HOME/.config/android-termux-ssh/network-env.sh" ]] && \'
  printf '%s\n' '  . "$HOME/.config/android-termux-ssh/network-env.sh"'
  printf 'exec %q %q "$@"\n' "$PREFIX/bin/node" "$codex_launcher"
} > "$wrapper_tmp"
[[ -L "$codex_bin" ]] && unlink "$codex_bin"
install -m 755 "$wrapper_tmp" "$codex_bin"

bashrc="$HOME/.bashrc"
touch "$bashrc"
network_source='[[ -r "$HOME/.config/android-termux-ssh/network-env.sh" ]] && . "$HOME/.config/android-termux-ssh/network-env.sh"'
if ! grep -Fqx -- "$network_source" "$bashrc"; then
  printf '%s\n' "$network_source" > "$bashrc_tmp"
  cat "$bashrc" >> "$bashrc_tmp"
  install -m 600 "$bashrc_tmp" "$bashrc"
fi
bash -n "$bashrc" "$network_env"

config_file="$HOME/.codex/config.toml"
[[ -f "$config_file" ]] || : > "$config_file"
if (( NO_SANDBOX == 1 )); then
  backup_dir="$HOME/.local/state/android-termux-ssh/backups"
  install -d -m 700 "$backup_dir"
  config_backup="$backup_dir/config.toml.$(date -u +%Y%m%dT%H%M%SZ).$$"
  cp -p -- "$config_file" "$config_backup"
  if (( FULL_ACCESS == 1 )); then approval_value=never; else approval_value=on-request; fi
  awk -v approval_value="$approval_value" '
    BEGIN { inserted=0; in_root=1 }
    in_root && /^[[:space:]]*approval_policy[[:space:]]*=/ { next }
    in_root && /^[[:space:]]*sandbox_mode[[:space:]]*=/ { next }
    in_root && /^[[:space:]]*\[/ {
      if (!inserted) {
        print "approval_policy = \"" approval_value "\""
        print "sandbox_mode = \"danger-full-access\""
        print ""
        inserted=1
      }
      in_root=0
    }
    { print }
    END {
      if (!inserted) {
        if (NR > 0) print ""
        print "approval_policy = \"" approval_value "\""
        print "sandbox_mode = \"danger-full-access\""
      }
    }
  ' "$config_file" > "$config_tmp"
  install -m 600 "$config_tmp" "$config_file"
fi

. "$network_env"
printf 'Codex: %s\n' "$codex_version_output"
if codex login status >/dev/null 2>&1; then
  printf 'Authentication: logged in\n'
else
  printf 'Authentication: not logged in; run codex login --device-auth\n'
fi
if (( NO_SANDBOX == 1 )); then
  if (( FULL_ACCESS == 1 )); then
    printf 'Permissions: full access by explicit user choice; sandbox and approvals are disabled\n'
  else
    printf 'Sandbox: disabled by explicit user choice; interactive approvals remain on-request\n'
  fi
else
  printf 'Sandbox: unchanged\n'
fi
printf 'Network environment: %s\n' "$network_env"
