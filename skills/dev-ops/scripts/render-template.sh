#!/usr/bin/env bash
#
# 仓库通用模板渲染器。
# 适用于“模板文件进 git，部署前再生成目标配置”的场景，
# 会把渲染结果写到服务目录中的生成文件里。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/shared/lib/common.sh
source "${SCRIPT_DIR}/shared/lib/common.sh"

# 这个脚本经常被单独调用，因此 help 信息写得更完整一些。
print_help() {
  cat <<EOF
$(usage_header)

Usage: $(basename "$0") <template> <output> <service>

Renders a template from assets/services/<service>/ after loading that service's env files.
EOF
}

main() {
  # 支持快速查看帮助，不要求本地已经准备好任何配置文件。
  if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
    print_help
    exit 0
  fi

  [ "$#" -ge 3 ] || die "expected 3 arguments: <template> <output> <service>"

  local template_input="$1"
  local output_input="$2"
  local service_name="$3"
  local service_dir
  local template_path
  local output_path

  service_dir="$(service_assets_dir "${service_name}")"
  [ -d "${service_dir}" ] || die "service assets directory not found: ${service_dir}"

  if [[ "${template_input}" = /* ]]; then
    template_path="${template_input}"
  else
    template_path="${service_dir}/${template_input}"
  fi

  if [[ "${output_input}" = /* ]]; then
    output_path="${output_input}"
  else
    output_path="${service_dir}/${output_input}"
  fi

  load_standard_env "${service_dir}"
  render_template "${template_path}" "${output_path}"
  log "rendered ${output_path}"
}

main "$@"
