# DDNS 工作流

当任务涉及阿里云 DDNS 同步或通过 `acme.sh` 获取证书时，使用本文件。

## 资产位置

- 环境变量模板：`assets/services/ddns/.env.example`
- 可执行脚本：
  - `scripts/services/ddns/aliyun_ddns.sh`
  - `scripts/services/ddns/certs_fetch.sh`

## 使用方式

1. 复制 `assets/services/ddns/.env.example` 为本地 `.env` 或 `.env.local`
2. 填入阿里云凭据、域名规则和证书目录
3. 用统一入口执行：

```bash
bash skills/dev-ops/scripts/run.sh service ddns aliyun_ddns.sh
bash skills/dev-ops/scripts/run.sh service ddns certs_fetch.sh
```

## 关键变量

- `DDNS_TARGETS`
- `ALIYUN_CLI_PROFILE`
- `ALIYUN_ACCESS_KEY_ID`
- `ALIYUN_ACCESS_KEY_SECRET`
- `ACME_CERT_NAME`
- `ACME_DOMAINS`
- `ACME_CERT_DIR`

## 输出要求

- 不在仓库里保存真实 AK/SK
- 如需定时任务，说明应该把哪条命令放进 crontab，而不是把 crontab 本身写回仓库

