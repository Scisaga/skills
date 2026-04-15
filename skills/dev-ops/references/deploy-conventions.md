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

## 数据库服务部署前检查

- 当任务涉及数据库类服务部署、扩容、迁移或重建时，不要直接假设目标服务器的存储路径和资源分配
- 这里的数据库类服务包括但不限于：
  - PostgreSQL / TimescaleDB
  - Elasticsearch
  - MongoDB
  - Redis
  - Qdrant
  - MinIO
- 在真正执行部署前，先了解目标服务器的存储配置，再给出建议，而不是直接写死数据目录

### 需要先了解的内容

- 数据盘和挂载点：
  - 例如 `/mnt/data1`、`/data`、`/srv`、独立块设备或 RAID 挂载点
- 各挂载点的容量和剩余空间
- 目标目录所在文件系统类型和读写权限
- 是否已经存在同类服务数据目录，避免覆盖现有数据
- 当前磁盘是否同时承载日志、备份、对象存储或其他高 IO 服务
- 是否有单独的数据盘适合数据库落盘，而不是和系统盘混用

### 建议方式

- 先检查远端存储布局，再向用户说明推荐的数据目录、原因和权衡
- 典型建议内容至少包括：
  - 建议把主数据放在哪个挂载点
  - 配置文件、Compose 文件和脚本仍放在哪个服务目录
  - 日志、数据、备份是否需要分目录
  - 当前机器是否适合直接部署，还是应先扩容磁盘或调整目录规划
- 如果远端已经有明显更合适的数据盘，例如 `/mnt/data1`，优先建议把数据库主数据放到该挂载点，而不是默认写到 `/opt/<service>` 或系统盘

### 执行前确认

- 在用户明确确认之前，不直接执行以下动作：
  - `docker compose up -d`
  - 创建或切换数据库主数据目录
  - 修改已有数据库服务的数据挂载路径
  - 迁移、覆盖或清理已有数据库数据目录
- 如果只是前期分析，可以先：
  - 查看磁盘和挂载点
  - 检查现有目录结构
  - 给出推荐方案
- 一旦涉及数据库数据落盘位置或已有数据迁移，必须要求用户明确确认后再执行

### 默认提醒方式

- 准备部署数据库服务前，先提醒用户确认目标服务器的存储配置和预期数据落盘位置
- 如果你发现目标机器同时存在系统盘和独立数据盘，先给出推荐挂载点，并说明为什么这样更合适
- 如果用户没有明确指定数据目录，只给建议，不直接替用户决定最终数据路径
- 如果目标目录下已经存在旧数据，先提示风险和处理选项，等待用户明确确认

## 远程访问凭据准备

- 当任务涉及远程服务器部署、巡检或修改时，先提醒用户确认本机已经具备可用的 SSH 凭据，而不是直接假设当前环境能登录远端
- 优先让用户在本机本地完成凭据准备，不要把私钥、口令或其他敏感凭据写进仓库
- 如果用户同时在 Windows 和 WSL 中工作，且 Windows 已经配置过 SSH，优先检查是否需要把 Windows 用户目录下的 `.ssh` 同步到 WSL 的 `~/.ssh`

### Windows 和 WSL 的 `.ssh` 同步

- 典型来源：
  - Windows：`C:\\Users\\<user>\\.ssh`
  - WSL：`~/.ssh`
- 如果 WSL 中缺少 `config`、私钥、公钥或 `known_hosts`，可以把以下文件同步到 `~/.ssh`：
  - `config`
  - `id_*`
  - `id_*.pub`
  - `known_hosts`
  - `known_hosts.old`
- 同步后必须修正权限，避免 OpenSSH 因权限过宽而拒绝读取私钥：

```bash
install -d -m 700 ~/.ssh
chmod 700 ~/.ssh
chmod 600 ~/.ssh/config ~/.ssh/id_* ~/.ssh/known_hosts ~/.ssh/known_hosts.old 2>/dev/null || true
chmod 644 ~/.ssh/*.pub 2>/dev/null || true
```

### SSH 配置和连通性校验

- 先确认 `~/.ssh/config` 中是否存在目标主机别名，必要时提醒用户补齐 `Host`、`HostName`、`User`
- 可以先用下面的命令验证 SSH 别名是否被正确解析：

```bash
ssh -G <host>
```

- 再用非交互方式验证当前凭据是否真的可登录：

```bash
ssh -o BatchMode=yes -o ConnectTimeout=5 <host> 'hostname && whoami'
```

- 如果别名解析失败，优先检查：
  - 当前 `ssh` 是否读取了预期的 `~/.ssh/config`
  - `HostName` 是否是可解析的 DNS 名称或有效 IP
  - 当前网络、VPN 或内网路由是否可达

### `ssh-agent` 和 `ssh-add`

- 如果私钥带 passphrase，且需要在 WSL 中反复访问远端，应提醒用户先准备 `ssh-agent`
- 典型检查命令：

```bash
ssh-add -l
```

- 如果 agent 中还没有加载身份，提醒用户执行：

```bash
ssh-add ~/.ssh/id_ed25519
```

- 如果当前 shell 没有 agent，也可以先启动：

```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
```

- 如果用户是长期在 WSL 内执行远程运维，建议把 agent 启动和复用逻辑放到 shell 初始化文件里，例如 `~/.bashrc`
- 在确认 agent 可用后，再重复执行一次非交互 SSH 登录测试，避免后续部署中途因为认证失败而中断

### 提醒用户的默认说法

- 需要远程部署前，先提醒用户确认当前环境已经准备好 SSH 凭据、主机别名和网络连通性
- 如果用户在 Windows 中能登录，但 WSL 中不能登录，优先提示检查 `C:\\Users\\<user>\\.ssh` 和 `~/.ssh` 是否一致
- 如果远端提示 `Permission denied (publickey,password)`，优先提示检查：
  - WSL 中是否有对应私钥
  - 私钥权限是否正确
  - 私钥是否已经通过 `ssh-add` 加入 agent
  - 目标主机是否接受这把公钥
- 除非用户明确要求，否则不要让用户把私钥内容直接贴到对话里

## 远程主机目录约定

- 涉及远程服务器部署时，默认将服务部署目录放在 `/opt/<service>/`
- 除系统级配置外，不把服务部署文件散落在 `/root`、`/home/<user>` 等目录
- 如目标环境已有强约束，例如面板托管、Kubernetes 或 PaaS，以目标环境约定为准

### Docker Compose 类服务

- 远程目录通常包含：
  - `docker-compose.yml`
  - `.env`
  - 服务所需的挂载配置、模板渲染结果或本地数据目录
- 默认先执行：
  - `docker compose -f /opt/<service>/docker-compose.yml config`
- 再在对应目录执行：
  - `docker compose up -d`
- 如果仓库已提供封装脚本，优先执行封装脚本，而不是在远端手工拼装 Compose 命令

### 非 Docker 服务

- 如果服务不使用 Docker，则远程目录中应包含对应部署脚本或运行脚本，以及必要配置文件
- 至少应明确：
  - 安装或发布入口
  - 启动方式
  - 停止或重启方式
  - 依赖的配置文件位置
- 如果仓库已提供统一入口，远程执行时仍优先走仓库入口，而不是临时手写命令

