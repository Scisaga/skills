#!/usr/bin/env bash
#
# 在 Elasticsearch 容器内创建 Kibana 使用的 service account token。
# 这个脚本会被挂进容器并与 Elasticsearch 一起启动，
# 使 Kibana 可以使用 service token，而不是直接用 elastic 超级用户登录。
set -euo pipefail

ES_URL="http://localhost:9200"
ES_USER="elastic"
ES_PASS="${ELASTIC_PASSWORD:-}"
TOKEN_FILE="/token/service-token"
ES_BIN_DIR="/usr/share/elasticsearch/bin"

# 没有 bootstrap 密码，就无法完成 token 创建阶段的认证。
if [ -z "${ES_PASS}" ]; then
  echo "[init-token] ELASTIC_PASSWORD is not set, cannot create Kibana service token."
  exit 1
fi

# 等待 Elasticsearch 完全就绪（带认证）
echo "[init-token] Waiting for Elasticsearch to be ready..."
until curl --silent --fail -u "${ES_USER}:${ES_PASS}" "${ES_URL}/_cluster/health" > /dev/null 2>&1; do
  echo "[init-token] Elasticsearch is not ready yet, retry in 5s..."
  sleep 5
done
echo "[init-token] Elasticsearch is up."

# 如果 token 已存在，就直接跳过
if [ -f "${TOKEN_FILE}" ]; then
  echo "[init-token] Service token already exists at ${TOKEN_FILE}, skip creating."
  exit 0
fi

mkdir -p "$(dirname "${TOKEN_FILE}")"

# elasticsearch-service-tokens CLI 输出的是人类可读文本，这里只提取真正的 token。
echo "[init-token] Creating Kibana service account token (elastic/kibana)..."
RAW_OUTPUT="$("${ES_BIN_DIR}/elasticsearch-service-tokens" create elastic/kibana kibana_token || true)"

# 从输出中解析出真正的 Bearer token:
# 形如：
#   SERVICE_TOKEN elastic/kibana/kibana_token = AAEAAW...
TOKEN="$(printf '%s\n' "${RAW_OUTPUT}" | awk -F' = ' '/^SERVICE_TOKEN / {print $2; exit}')"

if [ -z "${TOKEN}" ]; then
  echo "[init-token] Failed to parse service token from output:"
  echo "-----------"
  echo "${RAW_OUTPUT}"
  echo "-----------"
  exit 1
fi

echo "${TOKEN}" > "${TOKEN_FILE}"
chmod 600 "${TOKEN_FILE}"

# 共享 token 卷最终会被 Kibana 容器入口读取并使用。
echo "[init-token] Service token created and saved to ${TOKEN_FILE}"
