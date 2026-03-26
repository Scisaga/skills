# 仓库布局

当任务需要判断目标服务目录、入口脚本或配置归属时，读取本文件。

## 服务目录

- `db/`
  - 聚合数据库与可观测组件栈。
  - 入口：`deploy.sh`
- `es-docker/`
  - Elasticsearch / Kibana / exporter 独立部署栈。
  - 入口：`deploy.sh`
- `gitlab/`
  - GitLab 与容器镜像仓库部署清单，以及 registry 证书辅助脚本。
  - 入口：`deploy.sh`、`gen_certs.sh`
- `hysteria/`
  - Hysteria 2 服务端与客户端安装脚本。
  - 入口：`hy2_inst.sh`、`hy2_cli_inst.sh`
- `influxdb/`
  - 单节点 InfluxDB 部署清单。
  - 入口：`deploy.sh`
- `keycloak/`
  - Keycloak 服务部署、主题与微信登录扩展资源。
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
- `prometheus-grafana/`
  - Prometheus、Grafana、Node Exporter 部署与监控配置。
  - 入口：`deploy.sh`、`install.sh`
- `redis/`
  - Redis、Redis Exporter、RedisInsight 部署清单。
  - 入口：`deploy.sh`
- `sh/`
  - 仓库级通用脚本、公共 shell 库、模板渲染工具与审计脚本。
  - 常用脚本：`audit-hardcoded.sh`、`render-template.sh`
- `unbound/`
  - Unbound DNS 服务部署与系统 DNS 接管脚本。
  - 入口：`deploy.sh`、`setup.sh`
- `wireguard/`
  - WireGuard Easy 部署、客户端安装与密码哈希工具。
  - 入口：`deploy.sh`、`client-inst.sh`、`set-passwd.sh`
- `wordpress/`
  - WordPress 容器部署与 Nginx 反代模板。
  - 入口：`deploy.sh`、`render-nginx.sh`

## 判断方式

- 目录内存在 `.env.example`、`docker-compose.yml`、`*.yaml` 或模板文件时，通常按 compose/env 模式处理。
- 目录主要由安装脚本组成，且强调 `--help`、CLI 参数和交互输入时，通常按命令式脚本模式处理。
- 如果一个目录同时包含包装脚本和底层配置，优先从该目录的 `deploy.sh` 或主入口脚本开始。
