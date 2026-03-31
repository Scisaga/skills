# 仓库布局

当任务需要判断某个文件应该放在哪里时，使用这份布局说明。

## 顶层结构

- `scripts/run.sh`
  - 聚合入口，负责分发 `bootstrap`、`audit-hardcoded`、`render-template` 和 `service` 子命令
- `scripts/bootstrap.sh`
  - 只做本地前置检查，不执行真实部署
- `scripts/shared/`
  - 通用 shell 库和共享脚本
- `scripts/services/<service>/`
  - 该服务的可执行入口脚本
- `assets/services/<service>/`
  - 该服务的 Compose 文件、模板、`.env.example`、配置目录、示例文件和本地维护文件模板
- `references/`
  - 运维说明与导航文档

## 当前服务

- `data-platform`
- `ddns`
- `gitlab`
- `hysteria`
- `keycloak`
- `letsencrypt`
- `minio`
- `mysql`
- `proxy`
- `redis`
- `unbound`
- `wireguard`

## 判断规则

- 要执行某个服务：优先看 `scripts/services/<service>/`
- 要改 Compose、YAML、模板、`.env.example` 或配置目录：看 `assets/services/<service>/`
- 要改通用帮助函数、模板渲染或审计逻辑：看 `scripts/shared/` 或 `scripts/`
- 要补说明文档：看 `references/`

不要再把用户可执行脚本直接放回 `assets/services/<service>/`。
