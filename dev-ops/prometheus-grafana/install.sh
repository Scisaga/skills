#!/usr/bin/env bash
#
# 兼容旧使用习惯保留的入口。
# 实际部署逻辑统一委托给 deploy.sh，避免出现两套实现。

set -euo pipefail

exec "$(cd "$(dirname "$0")" && pwd)/deploy.sh" "$@"
