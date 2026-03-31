#!/usr/bin/env bash
#
# 为 GitLab registry 集成生成一对自签名证书。
# 默认写入当前服务目录下的 certs/，也可通过环境变量覆盖输出目录。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/shared/lib/common.sh
source "${SCRIPT_DIR}/../../shared/lib/common.sh"
SERVICE_ASSETS_DIR="$(service_assets_dir "gitlab")"

load_env_with_example "${SERVICE_ASSETS_DIR}"
CERTS_DIR="${GITLAB_CERTS_DIR}"

case "${CERTS_DIR}" in
  /*) ;;
  ./*) CERTS_DIR="${SERVICE_ASSETS_DIR}/${CERTS_DIR#./}" ;;
  *) CERTS_DIR="${SERVICE_ASSETS_DIR}/${CERTS_DIR}" ;;
esac

require_cmd openssl
mkdir -p "${CERTS_DIR}"
cd "${CERTS_DIR}"
# 先生成临时口令文件，供后续密钥生成过程使用。
openssl rand -hex -out password_file 32
# 生成 CSR 和对应的私钥材料。
openssl req -new -passout file:password_file -newkey rsa:4096 -batch > registry.csr
# 导出 registry 容器可直接读取的未加密 RSA 私钥。
openssl rsa -passin file:password_file -in privkey.pem -out registry.key
# 在本地对 CSR 进行签名，生成一个长期有效的自签名证书。
openssl x509 -in registry.csr -out registry.crt -req -signkey registry.key -days 10000
