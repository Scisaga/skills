#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/../../shared/lib/common.sh"

if [ "${1:-}" = --help ] || [ "${1:-}" = -h ]; then
  echo "Usage: bash $(basename "$0") [install-directory]"
  echo "Download the official Linux CLI to <install-directory>/bin/aliyun (default /opt/aliyun-ddns)."
  exit 0
fi
[ "$#" -le 1 ] || die "expected at most one install directory"
[ "$(uname -s)" = Linux ] || die "this host installer supports Linux; use the official CLI installer for macOS/Windows"
case "$(uname -m)" in
  x86_64) architecture=amd64 ;;
  aarch64|arm64) architecture=arm64 ;;
  *) die "unsupported Linux architecture: $(uname -m)" ;;
esac
require_cmd curl
require_cmd tar
require_cmd install
require_cmd sha256sum
install_dir="${1:-/opt/aliyun-ddns}"
install -d -m 0755 "${install_dir}/bin"
archive="$(mktemp "${install_dir}/aliyun-cli.XXXXXX.tgz")"
binary="$(mktemp "${install_dir}/bin/aliyun.XXXXXX")"
trap 'rm -f "${archive}" "${binary}"' EXIT
curl --connect-timeout 10 --max-time 600 --retry 1 --retry-max-time 650 -fsSL \
  "https://aliyuncli.alicdn.com/aliyun-cli-linux-latest-${architecture}.tgz" -o "${archive}"
sha256sum "${archive}"
tar -xOzf "${archive}" aliyun > "${binary}"
chmod 0755 "${binary}"
"${binary}" version
mv -f "${binary}" "${install_dir}/bin/aliyun"
log "installed official CLI at ${install_dir}/bin/aliyun; no credentials were configured"
