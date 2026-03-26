# WireGuard 工作流

当任务涉及 `wireguard/` 目录时，先区分当前是在处理服务端、客户端，还是辅助工具。

## 文件分工

- `wireguard/deploy.sh`
  - 服务端入口。
  - 读取 `wireguard/.env` 或 `.env.local`。
  - 调用 `wireguard/wg-easy.yaml` 部署 `wg-easy` 容器。
- `wireguard/wg-easy.yaml`
  - 服务端 compose 清单。
  - 只给 `deploy.sh` 使用。
- `wireguard/generate-wg-password-hash.sh`
  - 服务端辅助工具。
  - 生成 `WG_PASSWORD_HASH`，供 `deploy.sh` 使用。
- `wireguard/set-passwd.sh`
  - 旧入口兼容包装。
  - 实际会跳转到 `generate-wg-password-hash.sh`。
- `wireguard/client-inst.sh`
  - 客户端入口。
  - 在目标主机安装 `wireguard-tools`，并把现成的客户端 `.conf` 装到 `/etc/wireguard`。
  - 不会部署 `wg-easy` 服务端。

## 典型流程

### 部署服务端

1. 生成后台密码哈希：
   - `cd wireguard && ./generate-wg-password-hash.sh <plain-password>`
2. 把输出写入 `.env.local` 的 `WG_PASSWORD_HASH`
3. 配置 `WG_HOST`、`WG_PORT`、`WG_WEB_PORT` 等服务端参数
4. 执行：
   - `cd wireguard && ./deploy.sh`

### 安装客户端

1. 先从 `wg-easy` 管理界面导出某个客户端配置文件，例如 `client.conf`
2. 在目标主机执行：
   - `cd wireguard && ./client-inst.sh wg0 ./client.conf`
3. 如需通过环境变量驱动，也可设置：
   - `WG_INTERFACE_NAME`
   - `WG_CONFIG_SOURCE`
   - `WG_RERESOLVE_CRON`

## 判断原则

- 需要启动或更新 VPN 服务器：用 `deploy.sh`
- 需要生成或更新后台管理密码哈希：用 `generate-wg-password-hash.sh`
- 需要在某台机器上接入现有 WireGuard 网络：用 `client-inst.sh`
