#!/usr/bin/env bash
#
# 生成 wg-easy 所需格式的 bcrypt 风格密码哈希。
# 这样可以避免把明文管理密码直接放进 compose 的 env 文件里。

set -euo pipefail

SERVICE_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=sh/lib/common.sh
source "${SERVICE_DIR}/../sh/lib/common.sh"

WG_EASY_IMAGE="${WG_EASY_IMAGE:-ghcr.io/wg-easy/wg-easy:14}"
PLAIN_PASSWORD="${1:-}"

# 这个脚本故意只暴露一个参数，因为唯一输出就是密码哈希。
if [ "${PLAIN_PASSWORD}" = "--help" ] || [ "${PLAIN_PASSWORD}" = "-h" ]; then
  usage_header
  echo
  echo "Generate a WG_PASSWORD_HASH value for WireGuard Easy."
  echo
  echo "Usage: $(basename "$0") <plain-password>"
  echo
  echo "Example:"
  echo "  $(basename "$0") my-secret-password"
  exit 0
fi

require_cmd docker
[ -n "${PLAIN_PASSWORD}" ] || die "plain password is required"

# 直接复用 wg-easy 镜像本身生成哈希，确保格式始终与部署版本一致。
WG_PASSWORD_HASH="$(docker run --rm "${WG_EASY_IMAGE}" wgpw "${PLAIN_PASSWORD}")"

log "Generated WG_PASSWORD_HASH. Paste this into wireguard/.env or wireguard/.env.local:"
printf 'WG_PASSWORD_HASH=%s\n' "${WG_PASSWORD_HASH}"
