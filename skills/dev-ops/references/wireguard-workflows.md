# WireGuard 工作流

当任务涉及 `wg-easy` 服务端、主机级客户端安装或密码哈希生成时，使用本文件。

## 资产位置

- 环境变量模板：`assets/services/wireguard/.env.example`
- Compose 文件：`assets/services/wireguard/wg-easy.yaml`

## 脚本入口

- 服务端部署：`scripts/services/wireguard/deploy.sh`
- 宿主机 VPN 子网路由：`scripts/services/wireguard/install-host-route.sh`
- 客户端安装：`scripts/services/wireguard/client-inst.sh`

## 典型流程

1. 复制 `assets/services/wireguard/.env.example` 为 `.env` 或 `.env.local`，按目标主机调整端口和 Docker 子网。

2. 部署服务端

```bash
bash skills/dev-ops/scripts/run.sh service wireguard deploy.sh
```

3. 默认管理界面只监听远端 loopback；从本机建立 SSH 隧道：

```bash
ssh -L 51821:127.0.0.1:51821 <host>
```

然后访问 `http://127.0.0.1:51821`，在首次运行向导中设置管理员、公网主机名、WireGuard 地址、DNS、Allowed IPs 和 keepalive。

首次运行向导和管理面板中的 WireGuard 接口端口应与 `.env` 的 `WG_PORT` 保持一致；Compose 会把同一个 UDP 端口从宿主机映射到容器。

4. 如需在目标主机安装客户端

```bash
bash skills/dev-ops/scripts/run.sh service wireguard client-inst.sh wg0 ./client.conf
```

5. 如需让运行 wg-easy 的宿主机直接访问 VPN 客户端网段，先在 `.env` 中确认 `WG_HOST_ROUTE_CIDR` 与 wg-easy 接口 CIDR 一致，再安装持久路由：

```bash
bash skills/dev-ops/scripts/run.sh service wireguard install-host-route.sh
```

该入口安装 `wg-easy-host-route.service`。服务会等待 Docker 容器就绪，再将 VPN 子网路由到固定的 `WG_DOCKER_IPV4_ADDRESS`；执行 `docker compose down` 删除网桥后，应在栈恢复时重启该 systemd 服务。

## 说明

- 当前服务端资产面向 wg-easy v15；v14 的 `PASSWORD_HASH`、`WG_HOST` 和 `WG_DEFAULT_*` 等环境变量不再使用。
- 服务端默认基于固定的 `WG_EASY_BASE_IMAGE` 构建本地镜像，将上游硬编码的管理员密码最小长度改为 `WG_PASSWORD_MIN_LENGTH`。Dockerfile 会校验上游代码特征，若新版本结构发生变化则构建失败，避免静默生成未打补丁的镜像。
- 升级 `WG_EASY_BASE_IMAGE` 时，要同步调整本地镜像标签、重新执行 `docker compose build --pull`，并验证首次设置、登录和 CLI 重置密码三条路径。
- 从 v14 升级时必须先备份 `wg0.json`，再按 wg-easy 官方迁移流程导入；不要直接替换镜像标签。
- `WG_UI_INSECURE=true` 仅允许与 loopback 绑定配合使用。经 HTTPS 反向代理发布时将其设为 `false`。
- `deploy.sh` 只负责 `wg-easy` 服务端
- `client-inst.sh` 只负责宿主机 WireGuard 客户端
- v15 的管理员密码通过首次运行向导或容器内 CLI 管理，不再生成 `PASSWORD_HASH`

