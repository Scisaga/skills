---
name: domain-manager
description: 通过 Gandi Public API 与 Dynadot RESTful API 安全查询和管理域名、DNS、nameserver、DNSSEC、续费、转移及联系人等资源。适用于需要检查域名资产、修改解析或执行注册商域名操作的场景；不适用于其他注册商或仅做本地 DNS 排障。
---

# Domain Manager

## 概述

使用统一脚本向 Gandi v5 或 Dynadot RESTful v2 发送经过认证的域名管理请求。脚本固定可信 API 主机、自动加载凭据、为 Dynadot 生成 HMAC-SHA256 签名，并对所有写操作执行“生成计划 → 校验确认码 → 执行”的门禁。

Dynadot RESTful v2 官方仍标记为 Beta。每次使用不熟悉的命令、付费操作或高影响操作前，先核对当前官方文档，不凭记忆猜测路径、HTTP 方法或请求体。

## 工作流

1. 先读取 [references/api-routing.md](references/api-routing.md)，确认供应商、环境、端点和请求体。
2. 执行 `scripts/run.sh doctor`，只检查依赖与凭据是否存在，不输出凭据值。
3. 对写操作先省略 `--apply` 运行一次，保存脚本输出的请求摘要与 `confirmation`。
4. 向用户复述供应商、生产或沙箱环境、域名、方法、路径、查询参数和变更内容；涉及购买、注册、续费、转移、删除、联系人、nameserver 或 DNSSEC 时，必须在执行前取得明确授权。
5. 只有计划内容与授权完全一致时，原样追加 `--apply --confirm <confirmation>` 执行。请求体或查询参数变化会使确认码失效。
6. 写后使用独立 GET 请求回读状态。异步接口返回 `202` 时，按响应中的任务或资源位置继续查询，不把“已接受”报告为“已完成”。

## 命令模式

统一入口：

```bash
/absolute/path/to/domain-manager/scripts/run.sh doctor
/absolute/path/to/domain-manager/scripts/run.sh request gandi GET /v5/domain/domains --query per_page=20
/absolute/path/to/domain-manager/scripts/run.sh request dynadot GET /restful/v2/accounts/info
```

Gandi DNS 写操作先生成计划，再使用确认码执行：

```bash
/absolute/path/to/domain-manager/scripts/run.sh request gandi PUT \
  /v5/livedns/domains/example.com/records/www/A \
  --body '{"rrset_ttl":300,"rrset_values":["192.0.2.10"]}'

/absolute/path/to/domain-manager/scripts/run.sh request gandi PUT \
  /v5/livedns/domains/example.com/records/www/A \
  --body '{"rrset_ttl":300,"rrset_values":["192.0.2.10"]}' \
  --apply --confirm <confirmation>
```

Dynadot 请求同样使用该门禁；脚本会按实际编码后的 path、query、request body 和 UUID 生成 `X-Signature`：

```bash
/absolute/path/to/domain-manager/scripts/run.sh request dynadot PUT \
  /restful/v2/domains/example.com/nameservers \
  --body-file /absolute/path/to/request.json
```

沙箱测试追加 `--sandbox`。完整参数和输出格式见 [references/usage.md](references/usage.md)。

## 资源使用

- 选择供应商、端点和认证规则：[references/api-routing.md](references/api-routing.md)
- 查看计划门禁、参数、敏感输出和排障：[references/usage.md](references/usage.md)
- 统一入口：[scripts/run.sh](scripts/run.sh)
- 安装隔离依赖：[scripts/bootstrap.sh](scripts/bootstrap.sh)
- 请求与签名实现：[scripts/domain_api.py](scripts/domain_api.py)

## 输出规则

- 不输出 `GANDI_PAT_TOKEN`、`DYNADOT_API_KEY`、`DYNADOT_API_SECRET`、认证头或签名。
- 默认递归遮蔽响应中的 token、secret、password、authinfo 和 transfer auth code；只有确需读取业务密钥时才使用 `--show-sensitive`，且不得把该值转述到对话、日志或提交文件中。
- 不把 dry-run 计划表述为已执行，不把 HTTP `202` 表述为最终成功。
- 不自动重试写请求，避免重复注册、续费、购买或重复变更。
- 不批量写入。Dynadot v2 明确限制单次创建、更新或删除为一个对象或动作；跨域名变更逐项计划、逐项确认、逐项回读。
- API 错误必须返回非零退出码，并保留已脱敏的状态码、请求 ID 与错误体供排查。
