---
name: dev-ops
description: 维护当前仓库中的部署脚本、服务资产、模板渲染、远程发布流程和主机级安装脚本。适用于需要调整 Compose 栈、环境变量约定、部署入口、代理/VPN/DNS/证书脚本，或按服务资产目录排查运维配置的场景。
---

# Dev Ops

## 概述

这个 skill 统一维护 `skills/dev-ops/` 目录下的运维资源。当前结构固定为：

- `scripts/run.sh`：统一入口
- `scripts/bootstrap.sh`：本地前置检查
- `scripts/services/<service>/`：服务脚本入口
- `scripts/shared/`：共享 shell 工具和库
- `assets/services/<service>/`：Compose 文件、模板、`.env.example`、配置目录和其他非执行资产
- `references/`：按主题拆分的运维说明

不要再直接把服务脚本、配置模板和说明文档混放在同一个服务根目录里。

## 工作流

1. 先判断任务属于哪一类：
   - 改统一入口或共享逻辑：看 `scripts/`
   - 改某个服务的部署脚本：看 `scripts/services/<service>/`
   - 改 Compose、模板、`.env.example`、配置目录：看 `assets/services/<service>/`
   - 改说明：看 `references/`
2. 首次检查环境时，先运行 `bash skills/dev-ops/scripts/bootstrap.sh`。
3. 日常执行统一走 `bash skills/dev-ops/scripts/run.sh`，而不是直接从旧目录调用脚本。
4. 如果服务依赖 `.env` 或 `.env.local`，默认把它们放在 `assets/services/<service>/`。
5. 如果服务依赖未纳入版本控制的本地文件，也明确放在对应的 `assets/services/<service>/` 下，例如 Unbound 的本地记录文件。

## 命令模式

```bash
bash skills/dev-ops/scripts/run.sh help
bash skills/dev-ops/scripts/run.sh bootstrap
bash skills/dev-ops/scripts/run.sh audit-hardcoded
bash skills/dev-ops/scripts/run.sh render-template gitlab.nginx.conf gitlab.nginx.rendered.conf gitlab
bash skills/dev-ops/scripts/run.sh service proxy proxy.sh --help
bash skills/dev-ops/scripts/run.sh service wireguard generate-wg-password-hash.sh my-secret
bash skills/dev-ops/scripts/run.sh service wireguard deploy.sh
```

## 资源使用

- 需要确认目录职责和新结构时，读 `references/repo-layout.md`
- 需要确认 `.env`、模板渲染、Compose 校验和远程发布约定时，读 `references/deploy-conventions.md`
- 需要处理 DDNS 或证书同步时，读 `references/ddns-workflows.md`
- 需要处理 Unbound 本地记录或条件转发时，读 `references/unbound-records.md`
- 需要处理 WireGuard 服务端、客户端或密码哈希生成时，读 `references/wireguard-workflows.md`

## 输出规则

- 只改当前任务涉及的服务脚本、服务资产和说明。
- 不把真实密钥、密码、令牌、证书私钥或真实主机地址写进版本控制。
- 新增或修改入口时，同时更新 `SKILL.md`、对应 reference 和 `agents/openai.yaml`。
- 改服务脚本后，优先给出可执行的校验命令，而不是只描述思路。

