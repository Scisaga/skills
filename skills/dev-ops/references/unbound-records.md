# Unbound 记录维护

当任务涉及 Unbound 的本地记录、条件转发或本机 DNS 接管时，使用本文件。

## 资产位置

- 环境变量模板：`assets/services/unbound/.env.example`
- 记录模板：
  - `assets/services/unbound/local-records.conf.example`
  - `assets/services/unbound/forward-zones.conf.example`
- Compose 文件：`assets/services/unbound/unbound.yaml`
- 脚本入口：
  - `scripts/services/unbound/deploy.sh`
  - `scripts/services/unbound/setup.sh`

## 本地维护文件

- 真实记录写入：
  - `assets/services/unbound/local-records.conf`
  - `assets/services/unbound/forward-zones.conf`
- 这两个文件应只保留在本机或远端目标主机，不提交到仓库

## 使用方式

```bash
bash skills/dev-ops/scripts/run.sh service unbound deploy.sh
bash skills/dev-ops/scripts/run.sh service unbound setup.sh
```

## 约定

- `deploy.sh` 会在缺文件时从 `.example` 模板生成本地文件
- `setup.sh` 额外会停用 `systemd-resolved` 并重写 `/etc/resolv.conf`
- 修改记录后，先执行：

```bash
cd skills/dev-ops/assets/services/unbound
docker compose -f unbound.yaml config
```

再运行部署脚本

