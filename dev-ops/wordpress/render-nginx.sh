#!/usr/bin/env bash
#
# 渲染 WordPress 对外暴露用的 Nginx 反向代理模板。
# 源文件以模板形式保存在 git 中，证书路径、域名和上游地址则通过 env 注入到生成文件。

set -euo pipefail

SERVICE_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=sh/lib/common.sh
source "${SERVICE_DIR}/../sh/lib/common.sh"

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage_header
  echo
  echo "Render nginx-wp.conf to nginx-wp.rendered.conf."
  exit 0
fi

load_standard_env "${SERVICE_DIR}"
render_template "${SERVICE_DIR}/nginx-wp.conf" "${SERVICE_DIR}/nginx-wp.rendered.conf"
