---
name: dev-ops
description: 当你在本仓库中处理部署资产、安装脚本、Compose 栈、模板渲染或远程主机发布时使用此 skill。它提供服务入口、配置约定、验证流程和远程部署导航，帮助你在不提交敏感信息的前提下完成维护与发布。
---

# Dev Ops

## 概述

这个 skill 用于维护当前仓库里的运维资产。目标通常是修改服务部署脚本、调整 compose 栈、渲染配置模板、准备环境变量，或把某个服务发布到远程主机。

当前仓库的一级服务目录包括：

- `db/`
- `es-docker/`
- `gitlab/`
- `hysteria/`
- `influxdb/`
- `keycloak/`
- `letsencrypt/`
- `minio/`
- `mysql/`
- `prometheus-grafana/`
- `redis/`
- `sh/`
- `unbound/`
- `wireguard/`
- `wordpress/`

## 工作流

1. 先判断目标目录属于 compose/env 模式还是命令式脚本模式。
   - 若目录中有 `.env.example`、compose 文件或模板文件，通常按 compose/env 模式处理。
   - 若目录主要由安装脚本组成，且强调 `--help`、CLI 参数和交互输入，通常按命令式脚本模式处理。

2. 只有在目标目录提供 `.env.example` 时，才准备 `.env`。
   - 敏感值放在未纳入版本控制的位置，例如 `.env.local` 或远端 shell 环境。
   - 不要把真实密钥、密码、令牌或证书私钥写进受版本控制的文件。

3. 优先使用服务目录自己的入口脚本。
   - 首选 `deploy.sh`。
   - 若目录没有 `deploy.sh`，则执行该目录的主脚本，例如 `apply.sh`、`install.sh`、`hy2_inst.sh`。

4. 如果服务使用模板化配置，先渲染模板，再执行部署。

5. Docker 可用时，用 `docker compose config` 校验 compose 配置是否能正确展开。

6. 需要远程部署时，先确认 SSH 连通性，再在远端执行仓库自带入口脚本。

## 命令模式

- 硬编码审计：`./sh/audit-hardcoded.sh`
- 模板渲染：`./sh/render-template.sh <template> <output> <service-dir>`
- 查看包装脚本帮助：`cd <service> && ./deploy.sh --help`
- 远程前置检查：
  - `ssh <host> hostname`
  - `ssh <host> 'docker --version && docker compose version'`
- 远程执行入口：
  - `ssh <host> 'cd /srv/dev-ops/<service> && ./deploy.sh'`

## 资源使用

- 需要确认服务目录职责、入口脚本或模式判断时，读取 `references/repo-layout.md`。
- 需要确认 `.env` / `.env.local` 约定、部署顺序、模板渲染或远程发布流程时，读取 `references/deploy-conventions.md`。
- 需要审计硬编码内容时，使用 `sh/audit-hardcoded.sh`。
- 需要渲染模板时，使用 `sh/render-template.sh`。

## 输出规则

- 不要改动与当前任务无关的服务目录。
- 不要把真实密钥、密码、令牌、证书私钥或真实主机地址写入受版本控制的文件。
- 只有在目标目录已采用 env 模式时，才新增或调整 `.env` 相关文件。
- 修改部署逻辑后，优先给出可执行的校验命令或远程发布命令，而不是只描述思路。
