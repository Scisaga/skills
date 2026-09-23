# 使用说明

## `.env` 加载顺序

脚本按以下顺序读取，先加载的值优先，且不覆盖进程中已经设置的环境变量：

1. 当前工作目录 `.env`
2. skill 根目录 `.env`
3. `scripts/.env`

需要的变量：

```dotenv
GANDI_PAT_TOKEN=
DYNADOT_API_KEY=
DYNADOT_API_SECRET=
```

`.env` 存在但缺少 `python-dotenv` 时，入口会明确报错并提示执行 `bootstrap`。

## 安装与检查

```bash
skills/domain-manager/scripts/run.sh bootstrap
skills/domain-manager/scripts/run.sh doctor
```

`doctor` 只报告依赖是否可用、凭据是否存在和找到哪些 `.env` 文件，不显示值，也不发送网络请求。

## 通用请求

```text
run.sh request <gandi|dynadot> <METHOD> <PATH> [选项]
```

常用选项：

- `--query KEY=VALUE`：可重复，顺序会保留在实际 URL 与 Dynadot 签名中。
- `--body JSON`：直接给出 JSON 请求体。
- `--body-file PATH`：从 UTF-8 文件读取 JSON；使用 `-` 从 stdin 读取。
- `--sandbox`：使用供应商沙箱根地址。
- `--plan`：即使是 GET 也只输出计划，不发送请求。
- `--apply`：允许发送 POST、PUT、PATCH、DELETE 等写请求。
- `--confirm ID`：写请求必须提供与当前请求摘要匹配的确认码。
- `--show-sensitive`：显示响应中的业务敏感字段，例如转移授权码；本地 API 凭据仍永不显示。
- `--timeout SECONDS`：请求超时，默认 30 秒，范围 1–300。

PATH 必须是相对供应商根地址的绝对路径，不能包含 scheme、host、query、fragment 或路径穿越。query 只能通过 `--query` 传递。这保证凭据只会发送到脚本内置的官方 HTTPS 主机。脚本禁用 HTTP 重定向。

## 写操作门禁

首次运行写请求时不要传 `--apply`：

```bash
skills/domain-manager/scripts/run.sh request gandi PUT \
  /v5/livedns/domains/example.com/records/www/A \
  --body-file /tmp/rrset.json
```

输出包含：

```json
{
  "mode": "plan",
  "confirmation": "2f4d...",
  "request": {
    "provider": "gandi",
    "environment": "production",
    "method": "PUT",
    "path_and_query": "/v5/...",
    "body": {}
  }
}
```

复核后原样执行，并加入计划返回的确认码：

```bash
skills/domain-manager/scripts/run.sh request gandi PUT \
  /v5/livedns/domains/example.com/records/www/A \
  --body-file /tmp/rrset.json \
  --apply --confirm 2f4d...
```

确认码绑定供应商、环境、方法、完整编码后的路径与查询参数、规范化 JSON 正文。任一内容改变都会拒绝执行。确认码不是供应商 token，不包含可逆凭据。

## 响应与错误

- 正常输出为 JSON，包含供应商、环境、HTTP 状态、有限的安全响应头和脱敏后的 `data`。
- `3xx` 不跟随跳转，并作为错误退出。
- `4xx`、`5xx` 返回非零退出码。
- 写请求不自动重试。网络超时后，先 GET 回读状态或查询订单，确认未生效后再重新计划。
- `202` 只代表供应商已接收异步任务。根据响应中的 `Location`、任务 ID 或订单 ID 继续查询。
- 默认遮蔽 authinfo、transfer auth code、token、secret 和 password。若必须读取授权码，可临时使用 `--show-sensitive`，不要保存到仓库、聊天或普通日志。

## 常见故障

- `缺少 Python 依赖`：执行 `run.sh bootstrap`。
- `未配置 ...`：确认当前目录 `.env` 中变量名准确，并重新运行 `doctor`。
- Dynadot `401/403`：检查 API key/secret 是否成对、账户 API 是否启用、IP/CIDR 白名单是否包含当前出口地址；设置变更可能需要等待供应商生效。
- Gandi `403`：PAT 可能过期、组织/资源范围不匹配或缺少对应 scope。
- Dynadot `command not recognized`：RESTful v2 为 Beta，回到当前官方命令页核对路径与方法，不切换到 legacy API 猜测调用。
- 确认码不匹配：重新生成计划；不要复用旧确认码或绕过门禁。
