# WireGuard 工作流

当任务涉及 `wg-easy` 服务端、主机级客户端安装或密码哈希生成时，使用本文件。

## 资产位置

- 环境变量模板：`assets/services/wireguard/.env.example`
- Compose 文件：`assets/services/wireguard/wg-easy.yaml`

## 脚本入口

- 服务端部署：`scripts/services/wireguard/deploy.sh`
- 客户端安装：`scripts/services/wireguard/client-inst.sh`
- 管理密码哈希：`scripts/services/wireguard/generate-wg-password-hash.sh`

## 典型流程

1. 先生成 `WG_PASSWORD_HASH`

```bash
bash skills/dev-ops/scripts/run.sh service wireguard generate-wg-password-hash.sh <plain-password>
```

2. 把结果写入 `assets/services/wireguard/.env` 或 `.env.local`

3. 部署服务端

```bash
bash skills/dev-ops/scripts/run.sh service wireguard deploy.sh
```

4. 如需在目标主机安装客户端

```bash
bash skills/dev-ops/scripts/run.sh service wireguard client-inst.sh wg0 ./client.conf
```

## 说明

- `deploy.sh` 只负责 `wg-easy` 服务端
- `client-inst.sh` 只负责宿主机 WireGuard 客户端
- 不再保留旧的 `set-passwd.sh` 兼容入口

