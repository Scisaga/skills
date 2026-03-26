#!/usr/bin/env bash
#
# 仓库通用模板渲染器。
# 适用于“模板文件进 git，部署前再生成目标配置”的场景，
# 会把渲染结果写到服务目录中的生成文件里。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=sh/lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

# 这个脚本经常被单独调用，因此 help 信息写得更完整一些。
print_help() {
  cat <<EOF
$(usage_header)

Usage: $(basename "$0") <template> <output> [service-dir]

Renders a template with envsubst after loading shared and service env files.
EOF
}

main() {
  # 支持快速查看帮助，不要求本地已经准备好任何配置文件。
  if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
    print_help
    exit 0
  fi

  [ "$#" -ge 2 ] || die "expected at least 2 arguments"

  local template_path="$1"
  local output_path="$2"
  local service_dir="${3:-${SCRIPT_DIR}}"

  # 渲染时复用和 deploy 包装脚本相同的“共享配置 + 服务配置”优先级。
  load_standard_env "${service_dir}"
  render_template "${template_path}" "${output_path}"
  log "rendered ${output_path}"
}

main "$@"
