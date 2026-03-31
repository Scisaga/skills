#!/usr/bin/env bash
#
# 通过 Certbot 的手动挑战流程申请证书。
# 域名集合和 ACME 服务端点优先通过 CLI 参数传入，
# 同时保留在目标主机上一次性执行的交互式能力。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/shared/lib/common.sh
source "${SCRIPT_DIR}/../../shared/lib/common.sh"

LETSENCRYPT_DOMAINS="${LETSENCRYPT_DOMAINS:-}"
LETSENCRYPT_EMAIL="${LETSENCRYPT_EMAIL:-}"
LETSENCRYPT_SERVER="${LETSENCRYPT_SERVER:-https://acme-v02.api.letsencrypt.org/directory}"
LETSENCRYPT_CHALLENGE="${LETSENCRYPT_CHALLENGE:-dns}"

# 证书申请通常是一次性主机操作，直接用 CLI 参数比维护 .env 更直观。
print_help() {
  cat <<EOF

Usage: $(basename "$0") [options]

Options:
  --domains example.com,*.example.com
  --email ops@example.com
  --server https://acme-v02.api.letsencrypt.org/directory
  --challenge dns
  --help
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --domains)
      LETSENCRYPT_DOMAINS="$2"
      shift 2
      ;;
    --email)
      LETSENCRYPT_EMAIL="$2"
      shift 2
      ;;
    --server)
      LETSENCRYPT_SERVER="$2"
      shift 2
      ;;
    --challenge)
      LETSENCRYPT_CHALLENGE="$2"
      shift 2
      ;;
    --help|-h)
      print_help
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

# 域名和邮箱在交互式执行时允许临时输入，避免再维护额外配置文件。
[ -n "${LETSENCRYPT_DOMAINS}" ] || read -r -p "请输入域名列表（逗号分隔）: " LETSENCRYPT_DOMAINS
[ -n "${LETSENCRYPT_EMAIL}" ] || read -r -p "请输入 ACME 邮箱: " LETSENCRYPT_EMAIL

# 域名集合未明确前不执行，避免误申请。
ensure_value LETSENCRYPT_DOMAINS
ensure_value LETSENCRYPT_EMAIL

# 按需安装 certbot，保证未预装的主机也能直接运行这个脚本。
if ! command -v certbot >/dev/null 2>&1; then
  sudo snap install --classic certbot
fi

if [ ! -e /usr/bin/certbot ]; then
  sudo ln -s /snap/bin/certbot /usr/bin/certbot
fi

# 把逗号分隔的域名列表展开成 certbot 需要的重复 `-d` 参数。
declare -a domain_args
IFS=',' read -r -a domains <<< "${LETSENCRYPT_DOMAINS}"
for domain in "${domains[@]}"; do
  domain_args+=("-d" "${domain}")
done

# 实际的 ACME 交互由 certbot 完成，这个包装脚本只负责整理输入参数。
sudo certbot certonly \
  --manual \
  --preferred-challenges "${LETSENCRYPT_CHALLENGE}" \
  --email "${LETSENCRYPT_EMAIL}" \
  --agree-tos \
  --server "${LETSENCRYPT_SERVER}" \
  "${domain_args[@]}"
