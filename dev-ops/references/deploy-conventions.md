# 部署约定

当任务需要修改部署流程、准备环境变量、渲染模板或安排远程发布时，读取本文件。

## 配置与敏感值

- 只有目标目录提供 `.env.example` 时，才准备 `.env`。
- 需要长期复用且不应提交的敏感值，优先放在未纳入版本控制的 `.env.local` 或远端 shell 环境中。
- 命令式安装脚本优先使用 CLI 参数、默认值和必要交互，不强制依赖 `.env.example`。
- 不要把真实密钥、密码、令牌、证书私钥或真实主机地址写回受版本控制的文件。

## 入口与执行顺序

- 优先使用服务目录自己的 `deploy.sh`、`install.sh` 或主脚本入口。
- 模板化配置应先渲染，再执行部署。
- 需要看脚本支持的参数时，先运行 `./deploy.sh --help` 或对应主脚本的 `--help`。
- 通用环境加载逻辑集中在 `sh/lib/common.sh`。

## 校验与审计

- Docker 可用时，优先执行 `docker compose config` 检查 compose 配置是否能正确展开。
- 需要排查硬编码域名、IP、邮箱、版本捷径或密钥痕迹时，运行 `./sh/audit-hardcoded.sh`。
- 使用模板渲染时，优先通过 `./sh/render-template.sh <template> <output> <service-dir>` 生成目标文件。

## 远程发布

当用户要求发布到远程主机，且 SSH 已可用时：

- 先验证基本连通性与运行时：
  - `ssh <host> hostname`
  - `ssh <host> 'docker --version && docker compose version'`
- 只复制必要目录与公共 shell 库，不同步无关服务目录。
- 在远端目标目录中执行仓库自带入口脚本，例如：
  - `ssh <host> 'cd /srv/dev-ops/<service> && ./deploy.sh'`
  - 若没有 `deploy.sh`，则执行该目录的主脚本，如 `./apply.sh`、`./hy2_inst.sh`
