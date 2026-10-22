#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
printf -v RUN_COMMAND 'bash %q' "${SCRIPT_DIR}/run.sh"
SKILL_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_PYTHON_POSIX="${SKILL_ROOT}/.venv/bin/python"
VENV_PYTHON_WINDOWS="${SKILL_ROOT}/.venv/Scripts/python.exe"

is_runnable_python() {
  local candidate="$1"
  [ -n "${candidate}" ] || return 1
  if [ -f "${candidate}" ]; then
    "${candidate}" --version >/dev/null 2>&1
    return
  fi
  command -v "${candidate}" >/dev/null 2>&1 &&
    "${candidate}" --version >/dev/null 2>&1
}

pick_python() {
  local candidate
  for candidate in "${VENV_PYTHON_POSIX}" "${VENV_PYTHON_WINDOWS}" "${PYTHON:-}" python3 python; do
    if is_runnable_python "${candidate}"; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done
  return 1
}

usage() {
  cat <<EOF
用法:
  ${RUN_COMMAND} <command> [参数]

命令:
  bootstrap       创建 skill 私有虚拟环境并安装依赖
  doctor          检查依赖、.env 与凭据是否存在；不联网
  request         发送 Gandi v5 或 Dynadot RESTful v2 请求
  test            运行不联网的单元测试

示例:
  ${RUN_COMMAND} doctor
  ${RUN_COMMAND} request gandi GET /v5/domain/domains
  ${RUN_COMMAND} request dynadot GET /restful/v2/accounts/info

安全约束:
  GET/HEAD/OPTIONS 默认直接执行；追加 --plan 可只查看计划。
  其他方法默认只生成计划，必须再传 --apply --confirm <confirmation>。
  凭据只会发送到脚本内置的 Gandi 或 Dynadot 官方 HTTPS 主机。
EOF
}

case "${1:-}" in
  bootstrap)
    shift
    exec bash "${SCRIPT_DIR}/bootstrap.sh" "$@"
    ;;
  help|-h|--help|"")
    usage
    exit 0
    ;;
esac

PYTHON_BIN="$(pick_python || true)"
if [ -z "${PYTHON_BIN}" ]; then
  echo "错误：找不到可用的 Python 解释器。" >&2
  exit 1
fi

if [ "${1:-}" = "test" ]; then
  shift
  exec "${PYTHON_BIN}" -m unittest discover -s "${SKILL_ROOT}/tests" -p 'test_*.py' "$@"
fi

if ! "${PYTHON_BIN}" -c "import dotenv, requests" >/dev/null 2>&1; then
  if [ -f "${PWD}/.env" ] || [ -f "${SKILL_ROOT}/.env" ] || [ -f "${SCRIPT_DIR}/.env" ]; then
    echo "错误：发现 .env，但缺少 python-dotenv，无法自动加载凭据。" >&2
  else
    echo "错误：缺少 Python 依赖 requests 或 python-dotenv。" >&2
  fi
  echo "请先执行：${SCRIPT_DIR}/run.sh bootstrap" >&2
  exit 1
fi

exec "${PYTHON_BIN}" "${SCRIPT_DIR}/domain_api.py" "$@"
