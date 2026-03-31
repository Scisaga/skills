#!/usr/bin/env bash
#
# 对仓库中常见硬编码部署值做一次轻量审计。
# 它本质上是一个快速的 grep 保护网，不是严格意义上的安全扫描器。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# 使用 ripgrep 是为了保证在重构过程中也能频繁执行而不拖慢节奏。
if ! command -v rg >/dev/null 2>&1; then
  echo "rg is required" >&2
  exit 1
fi

cd "${REPO_ROOT}"

# 这个模式会有意放宽匹配范围，方便维护者人工复查所有看起来像版本捷径、
# 密钥、邮箱或 IP 的内容。
rg -n \
  --glob '!**/.git/**' \
  --glob '!**/dist/**' \
  --glob '!**/.cache/**' \
  --glob '!**/*.json' \
  --glob '!**/*.lock' \
  '(latest|releases/latest|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|([0-9]{1,3}\.){3}[0-9]{1,3}|PASSWORD=|TOKEN=|SECRET=|ACCESS_KEY=|private_key|-----BEGIN)' \
  .
