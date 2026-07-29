#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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
  cat <<'EOF'
用法:
  /absolute/path/to/gitlab-issue/scripts/run.sh <command> [参数]

命令:
  bootstrap       创建 skill 私有虚拟环境并安装依赖
  create          创建 issue
  read            读取 issue
  list            列出 issue
  update          更新 issue
  comment         评论 issue
  delete-note     删除评论
  delete          删除 issue，必须传 --yes

示例:
  /absolute/path/to/gitlab-issue/scripts/run.sh list --state opened
  /absolute/path/to/gitlab-issue/scripts/run.sh read --iid 40 --notes

约束:
  仅适用于当前自托管 GitLab 仓库。
  必须配置 GITLAB_BASE_URL 和 GITLAB_PRIVATE_TOKEN。
  当前 origin 与 GITLAB_BASE_URL 不匹配时会在发送 token 前终止。
EOF
}

if [ "${1:-}" = "bootstrap" ]; then
  shift
  exec bash "${SCRIPT_DIR}/bootstrap.sh" "$@"
fi

PYTHON_BIN="$(pick_python || true)"
if [ -z "${PYTHON_BIN}" ]; then
  echo "错误：找不到可用的 Python 解释器。" >&2
  exit 1
fi

if [ "$#" -eq 0 ]; then
  usage
  exit 1
fi

case "${1:-}" in
  help|-h|--help)
    usage
    exit 0
    ;;
esac

if ! "${PYTHON_BIN}" -c "import dotenv, requests" >/dev/null 2>&1; then
  echo "错误：缺少 Python 依赖 requests 或 python-dotenv。" >&2
  echo "请先执行：${SCRIPT_DIR}/run.sh bootstrap" >&2
  exit 1
fi

exec "${PYTHON_BIN}" "${SCRIPT_DIR}/gitlab_issue.py" "$@"
