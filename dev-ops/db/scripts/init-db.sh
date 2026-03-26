#!/usr/bin/env bash
#
# TimescaleDB 容器内使用的 Postgres 初始化钩子。
# 它会根据环境变量创建主库和附加业务库，并以幂等方式为每个库启用需要的扩展。
set -euo pipefail

# 这个脚本运行在容器初始化阶段，因此日志前缀要自包含，便于排查。
log() {
  echo "[init-db] $*"
}

# 集群级管理查询统一从内置的 postgres 数据库执行。
psql_super() {
  psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname "postgres" "$@"
}

# 仅在数据库尚不存在时创建，保持幂等。
create_database_if_not_exists() {
  local database="$1"
  log "Ensuring database '${database}' exists..."

  local exists
  exists="$(psql_super -tAc "SELECT 1 FROM pg_database WHERE datname='${database}'" || true)"

  if [[ "${exists}" != "1" ]]; then
    log "Creating database '${database}' with owner '${POSTGRES_USER}'..."
    psql_super -c "CREATE DATABASE \"${database}\" OWNER \"${POSTGRES_USER}\""
  else
    log "Database '${database}' already exists, skip creation."
  fi
}

# 为仓库中的应用工作负载启用预期的扩展集合。
enable_extensions() {
  local database="$1"

  for ext in timescaledb pg_stat_statements; do
    log "Enabling extension '${ext}' in database '${database}' (IF NOT EXISTS)..."
    psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname "${database}" <<-EOSQL
      CREATE EXTENSION IF NOT EXISTS ${ext};
EOSQL
  done
}

main() {
  # 先确保镜像约定中的主数据库存在。
  if [[ -n "${POSTGRES_DB:-}" ]]; then
    create_database_if_not_exists "${POSTGRES_DB}"
  fi

  # 再处理逗号分隔 env 中声明的附加业务库。
  local extra_dbs="${POSTGRES_MULTIPLE_DATABASES:-}"
  if [[ -n "${extra_dbs}" ]]; then
    log "Multiple databases requested: ${extra_dbs}"
    IFS=',' read -ra DBS <<< "${extra_dbs}"
    for db in "${DBS[@]}"; do
      db="$(echo "${db}" | xargs)"   # 去掉前后空格
      [[ -z "${db}" ]] && continue
      create_database_if_not_exists "${db}"
    done
  fi

  # 最后对数据库列表去重，并逐个启用所需扩展。
  declare -A seen=()
  local name

  # 把主库和附加库拼成一次遍历，过程中跳过重复项。
  for name in "${POSTGRES_DB:-}" ${extra_dbs//,/ }; do
    name="$(echo "${name}" | xargs)"
    [[ -z "${name}" ]] && continue
    if [[ -n "${seen[$name]:-}" ]]; then
      continue
    fi
    seen["$name"]=1
    enable_extensions "${name}"
  done

  log "Done."
}

main "$@"
