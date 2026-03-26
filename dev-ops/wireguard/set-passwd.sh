#!/usr/bin/env bash
#
# 兼容旧密码哈希入口名的包装脚本。
# 在运维侧彻底停止调用 `set-passwd.sh` 之前，保留这个跳转入口。

set -euo pipefail

SERVICE_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET_SCRIPT="${SERVICE_DIR}/generate-wg-password-hash.sh"

printf '[%s] %s\n' "$(basename "$0")" \
  "Deprecated helper. Use $(basename "${TARGET_SCRIPT}") for server-side WG_PASSWORD_HASH generation." >&2
exec "${TARGET_SCRIPT}" "$@"
