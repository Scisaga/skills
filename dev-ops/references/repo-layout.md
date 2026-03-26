# 仓库布局

当任务需要判断目标服务目录、入口脚本或配置归属时，读取本文件。

## 服务目录

- `data-platform/`
  - 聚合数据库与可观测组件栈。
  - 入口：`deploy.sh`
- `ddns/`
  - 阿里云 DNS 动态记录同步与 acme.sh 证书续签脚本。
  - 入口：`aliyun_ddns.sh`、`certs_fetch.sh`
  - 补充说明：`readme.md`
- `gitlab/`
  - GitLab 与容器镜像仓库部署清单，以及 registry 证书辅助脚本。
  - 入口：`deploy.sh`、`gen_certs.sh`、`render-nginx.sh`
- `hysteria/`
  - Hysteria 2 服务端与客户端安装脚本。
  - 入口：`hy2_inst.sh`、`hy2_cli_inst.sh`
- `keycloak/`
  - Keycloak 服务部署清单。
  - 入口：`deploy.sh`
- `letsencrypt/`
  - Certbot 证书申请脚本。
  - 入口：`apply.sh`
- `minio/`
  - MinIO 对象存储部署清单。
  - 入口：`deploy.sh`
- `mysql/`
  - MySQL 服务部署清单与配置目录。
  - 入口：`deploy.sh`
- `proxy/`
  - 主机级 Tinyproxy、WireGuard 转发与可选 WARP 出口脚本。
  - 入口：`proxy.sh`
- `redis/`
  - Redis、Redis Exporter、RedisInsight 部署清单。
  - 入口：`deploy.sh`
- `sh/`
  - 仓库级通用脚本、公共 shell 库、模板渲染工具与审计脚本。
  - 常用脚本：`audit-hardcoded.sh`、`render-template.sh`
- `unbound/`
  - Unbound DNS 服务部署、本地记录维护模板与系统 DNS 接管脚本。
  - 入口：`deploy.sh`、`setup.sh`
- `wireguard/`
  - WireGuard 服务端部署、客户端安装与密码哈希工具。
  - 服务端入口：`deploy.sh`
  - 客户端入口：`client-inst.sh`
  - 辅助工具：`generate-wg-password-hash.sh`、`set-passwd.sh`

## 判断方式

- 目录内存在 `.env.example`、`docker-compose.yml`、`*.yaml` 或模板文件时，通常按 compose/env 模式处理。
- 目录主要由安装脚本组成时，通常按命令式脚本模式处理，但仍需区分是 env 驱动脚本还是交互式脚本。
- `wireguard/` 需要先区分服务端和客户端入口。
- `ddns/` 需要通过 `.env` / `.env.local` 理解业务参数，而不是只看 CLI。
- 如果一个目录同时包含包装脚本和底层配置，优先从该目录的 `deploy.sh` 或主入口脚本开始。
