# 部署约定

当任务涉及部署入口、环境变量、模板渲染或远程发布时，遵循本文件。

## 环境变量

- 只有服务资产目录提供 `.env.example` 时，才准备 `.env` 或 `.env.local`
- 默认放置位置：
  - `assets/services/<service>/.env`
  - `assets/services/<service>/.env.local`
- 敏感值不写回 `.env.example`

## 统一入口

- 环境检查：`bash skills/dev-ops/scripts/run.sh bootstrap`
- 硬编码审计：`bash skills/dev-ops/scripts/run.sh audit-hardcoded`
- 模板渲染：`bash skills/dev-ops/scripts/run.sh render-template <template> <output> <service>`
- 服务脚本：`bash skills/dev-ops/scripts/run.sh service <service> <entrypoint> [args...]`

## Compose 类服务

- 先在服务资产目录校验 Compose：
  - `docker compose -f <compose-file> config`
- 再执行对应服务脚本
- Compose 文件、模板和本地配置都放在 `assets/services/<service>/`

## 主机级脚本

- 例如 `proxy`、`hysteria`、`letsencrypt`
- 这类脚本可以直接修改目标主机系统，输出中要明确前置条件和副作用

## 模板渲染

- 统一走 `scripts/render-template.sh`
- 相对路径默认相对 `assets/services/<service>/`
- 生成文件仍然写回该服务资产目录

## 远程执行

- 先确认 SSH 和远端依赖可用
- 在远端优先执行仓库自带入口，而不是手工重组命令

