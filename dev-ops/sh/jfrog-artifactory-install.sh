#!/usr/bin/env bash
#
# 面向单机场景的 Artifactory OSS 安装脚本。
# 适用于更偏好直接使用 docker run 而不是 compose 项目的主机。
# 它会先准备所需的数据目录结构，再以固定端口和卷挂载启动容器。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=sh/lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

JFROG_ARTIFACTORY_IMAGE="${JFROG_ARTIFACTORY_IMAGE:-releases-docker.jfrog.io/jfrog/artifactory-oss:7.111.7}"
JFROG_ARTIFACTORY_DATA_DIR="${JFROG_ARTIFACTORY_DATA_DIR:-/opt/jfrog/artifactory/var}"
JFROG_ARTIFACTORY_PORT_UI="${JFROG_ARTIFACTORY_PORT_UI:-8081}"
JFROG_ARTIFACTORY_PORT_ROUTER="${JFROG_ARTIFACTORY_PORT_ROUTER:-8082}"

# 先提供 help 快捷出口，这样即使还没有 env 文件也能先查看脚本用途。
if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage_header
  echo
  echo "Install Artifactory OSS using the configured image and host data directory."
  exit 0
fi

load_standard_env "${SCRIPT_DIR}"
ensure_value JFROG_ARTIFACTORY_IMAGE

# Artifactory 期望其 var 目录由 uid/gid 1030 持有且可写。
sudo mkdir -p "${JFROG_ARTIFACTORY_DATA_DIR}/etc"
sudo touch "${JFROG_ARTIFACTORY_DATA_DIR}/etc/system.yaml"
sudo chown -R 1030:1030 "${JFROG_ARTIFACTORY_DATA_DIR}"

# 这里直接使用 docker run，因为这个服务被设计成独立单体部署。
docker run --name artifactory -d --restart=always \
  -p "${JFROG_ARTIFACTORY_PORT_UI}:8081" \
  -p "${JFROG_ARTIFACTORY_PORT_ROUTER}:8082" \
  -v "${JFROG_ARTIFACTORY_DATA_DIR}:/var/opt/jfrog/artifactory" \
  "${JFROG_ARTIFACTORY_IMAGE}"
