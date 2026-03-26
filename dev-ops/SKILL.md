---
name: dev-ops
description: 当你在本仓库中处理部署资产、安装脚本、Compose 栈、模板渲染或远程主机发布时使用此 skill。它提供服务入口、配置约定、验证流程和远程部署导航，帮助你在不提交敏感信息的前提下完成维护与发布。
---

# Dev Ops

## 概述

这个 skill 用于维护当前仓库里的运维资产。目标通常是修改服务部署脚本、调整 compose 栈、渲染配置模板、准备环境变量，或把某个服务发布到远程主机。

当前仓库的一级服务目录包括：

- `data-platform/`
- `ddns/`
- `gitlab/`
- `hysteria/`
- `keycloak/`
- `letsencrypt/`
- `minio/`
- `mysql/`
- `proxy/`
- `redis/`
- `sh/`
- `unbound/`
- `wireguard/`

## 工作流

1. 先判断目标目录的运行模式，不要默认所有目录都走 `deploy.sh`。
   - 若目录中有 `.env.example`、compose 文件或模板文件，通常按 compose/env 模式处理，例如 `gitlab/`、`minio/`、`redis/`、`wireguard/` 服务端。
   - 若目录主要由命令式安装脚本组成，通常按主脚本入口处理，例如 `hysteria/`、`letsencrypt/`、`proxy/`。
   - 若目录既是脚本模式，又主要靠 `.env` 持久化业务参数，按 env 驱动脚本处理，例如 `ddns/`。

2. 只有在目标目录提供 `.env.example` 时，才准备 `.env` 或 `.env.local`。
   - 敏感值放在未纳入版本控制的位置，例如 `.env.local` 或远端 shell 环境。
   - 不要把真实密钥、密码、令牌或证书私钥写进受版本控制的文件。
   - 若目录使用额外的本地维护文件，也应写入未纳入版本控制的位置，例如 `unbound/local-records.conf`、`unbound/forward-zones.conf`。

3. 优先使用服务目录自己的真实入口脚本。
   - 服务端 compose 栈优先走 `deploy.sh`。
   - 主机级脚本目录直接走主脚本，例如 `proxy/proxy.sh`、`letsencrypt/apply.sh`、`hysteria/hy2_inst.sh`。
   - `wireguard/` 先区分服务端和客户端：
     - 服务端用 `deploy.sh`
     - 客户端用 `client-inst.sh`
     - 管理后台密码哈希用 `generate-wg-password-hash.sh`
   - `ddns/` 的两个脚本都读取环境变量：
     - `aliyun_ddns.sh` 负责同步 DNS
     - `certs_fetch.sh` 负责申请或续签证书

4. 如果服务使用模板化配置或本地配置清单，先准备配置，再执行部署。
   - 模板化场景优先使用 `sh/render-template.sh`。
   - `unbound/` 不再把记录写进 env，而是维护本地记录文件。

5. 按目录类型选择校验方式。
   - Docker Compose 栈优先用 `docker compose config`。
   - Shell 脚本优先用 `bash -n`。
   - 修改 DNS、代理或客户端安装脚本时，补充运行前提和系统副作用说明。

6. 需要远程部署时，先确认 SSH 连通性，再在远端执行仓库自带入口脚本。

## 命令模式

- 硬编码审计：`./sh/audit-hardcoded.sh`
- 模板渲染：`./sh/render-template.sh <template> <output> <service-dir>`
- 查看入口帮助：`cd <service> && ./<entry>.sh --help`
- 典型示例：
  - `cd wireguard && ./deploy.sh --help`
  - `cd wireguard && ./client-inst.sh --help`
  - `cd proxy && ./proxy.sh --help`
  - `cd letsencrypt && ./apply.sh --help`
- 远程前置检查：
  - `ssh <host> hostname`
  - `ssh <host> 'docker --version && docker compose version'`
- 远程执行入口：
  - `ssh <host> 'cd /srv/dev-ops/<service> && ./deploy.sh'`

## 资源使用

- 需要确认服务目录职责、入口脚本或模式判断时，读取 `references/repo-layout.md`。
- 需要确认 `.env` / `.env.local` 约定、部署顺序、模板渲染或远程发布流程时，读取 `references/deploy-conventions.md`。
- 需要理解 `ddns/` 中 `DDNS_TARGETS`、证书变量和定时任务方式时，读取 `ddns/readme.md`。
- 需要维护 `unbound/` 的本地记录或条件转发时，读取 `references/unbound-records.md`。
- 需要区分 `wireguard/` 的服务端、客户端和密码哈希工具时，读取 `references/wireguard-workflows.md`。
- 需要审计硬编码内容时，使用 `sh/audit-hardcoded.sh`。
- 需要渲染模板时，使用 `sh/render-template.sh`。

## 输出规则

- 不要改动与当前任务无关的服务目录。
- 不要把真实密钥、密码、令牌、证书私钥或真实主机地址写入受版本控制的文件。
- 只有在目标目录已采用 env 模式时，才新增或调整 `.env` 相关文件。
- 若目录依赖本地维护文件或主机系统状态，明确说明这些文件或系统服务需要怎样准备，例如 `unbound/` 的本地记录文件和本机 DNS 服务停用要求。
- 修改部署逻辑后，优先给出可执行的校验命令或远程发布命令，而不是只描述思路。
