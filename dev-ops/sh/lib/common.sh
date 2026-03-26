#!/usr/bin/env bash
#
# 服务级 deploy/install 包装脚本共享的 shell 工具库。
# 目标是让每个服务脚本都保持轻量且风格一致：
# 加载配置、校验变量、渲染模板，然后调用 compose。

set -euo pipefail

COMMON_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${COMMON_LIB_DIR}/../.." && pwd)"

# 输出带脚本名前缀的日志，方便多脚本混合输出时阅读。
log() {
  printf '[%s] %s\n' "$(basename "$0")" "$*"
}

# 用统一的错误前缀快速失败。
die() {
  printf '[%s] ERROR: %s\n' "$(basename "$0")" "$*" >&2
  exit 1
}

# 在包装脚本真正执行前检查外部依赖是否存在。
require_cmd() {
  local cmd="$1"
  command -v "${cmd}" >/dev/null 2>&1 || die "required command not found: ${cmd}"
}

# 若 env 文件存在，则以 KEY=VALUE 形式加载它。
load_env_file() {
  local env_file="$1"
  if [ -f "${env_file}" ]; then
    # shellcheck disable=SC1090
    set -a && . "${env_file}" && set +a
  fi
}

# 按文件名顺序加载某个目录下的 env 文件集合。
load_env_dir() {
  local env_dir="$1"
  local pattern="$2"
  local env_file

  [ -d "${env_dir}" ] || return 0

  # 使用 find + sort 保证加载顺序稳定，避免依赖 shell glob 排序差异。
  while IFS= read -r env_file; do
    load_env_file "${env_file}"
  done < <(find "${env_dir}" -maxdepth 1 -type f -name "${pattern}" | sort)
}

# 只加载服务目录自身的配置文件，保证每个子目录都可以独立使用。
load_standard_env() {
  local service_dir="$1"

  load_env_file "${service_dir}/.env"
  load_env_file "${service_dir}/.env.local"
}

# 先加载仓库中的示例默认值，再允许本地 env 覆盖。
load_env_with_example() {
  local service_dir="$1"

  load_env_file "${service_dir}/.env.example"
  load_standard_env "${service_dir}"
}

# 在执行前强制要求某个环境变量非空。
ensure_value() {
  local name="$1"
  local value="${!name:-}"
  [ -n "${value}" ] || die "missing required variable: ${name}"
}

# 提供统一的 help 前置说明，保证所有包装脚本对配置加载方式的描述一致。
usage_header() {
  cat <<EOF
Usage: $(basename "$0") [--help]

This script reads configuration from:
  - ./.env
  - ./.env.local

CLI flags override environment variables when the script supports them.
EOF
}

# 使用当前 shell 环境变量渲染模板文件。
render_template() {
  local template_path="$1"
  local output_path="$2"

  require_cmd envsubst
  mkdir -p "$(dirname "${output_path}")"
  envsubst < "${template_path}" > "${output_path}"
}

# 在服务目录中先校验 compose 文件，再启动对应栈。
run_compose_stack() {
  local service_dir="$1"
  local compose_file="$2"

  require_cmd docker
  (
    cd "${service_dir}"
    docker compose -f "${compose_file}" config >/dev/null
    docker compose -f "${compose_file}" up -d
  )
}
