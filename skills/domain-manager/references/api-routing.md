# API 路由与认证

本文用于选择供应商、环境、路径和认证方式。端点与参数可能更新；不熟悉的操作、付费操作和 Dynadot 生产写入应在执行当日复核官方文档。

## Gandi

- 生产根地址：`https://api.gandi.net`
- 沙箱根地址：`https://api.sandbox.gandi.net`
- 认证：`Authorization: Bearer <GANDI_PAT_TOKEN>`
- 脚本仅接受以 `/v5/` 开头的路径。
- 官方文档：
  - 总览：<https://api.gandi.net/docs/>
  - 认证：<https://api.gandi.net/docs/authentication/>
  - 域名：<https://api.gandi.net/docs/domains/>
  - LiveDNS：<https://api.gandi.net/docs/livedns/>

常用已核对路径：

| 目的 | 方法与路径 |
|---|---|
| 列出域名 | `GET /v5/domain/domains` |
| 域名详情 | `GET /v5/domain/domains/{domain}` |
| 自动续费 | `PATCH /v5/domain/domains/{domain}/autorenew` |
| 注册局 nameserver | `GET/PUT /v5/domain/domains/{domain}/nameservers`，以当前文档为准 |
| LiveDNS 状态/启用 | `GET/POST /v5/domain/domains/{domain}/livedns` |
| LiveDNS DNSSEC | `/v5/domain/domains/{domain}/livedns/dnssec`，方法按当前文档选择 |
| 列出 DNS 记录 | `GET /v5/livedns/domains/{fqdn}/records` |
| 单个 RRset | `GET/PUT/PATCH/DELETE /v5/livedns/domains/{fqdn}/records/{name}/{type}` |
| 续费 | `/v5/domain/domains/{domain}/renew`，先 GET 报价/条件，再按文档执行写请求 |
| 转出 | `/v5/domain/domains/{domain}/transferout` |

Gandi 某些域名订单接口支持 `Dry-Run: 1`，但这不是所有 LiveDNS 接口的统一能力。本 skill 的脚本使用本地计划门禁，不假设供应商 dry-run 一定可用。

## Dynadot

- 生产根地址：`https://api.dynadot.com`
- 沙箱根地址：`https://api-sandbox.dynadot.com`
- 当前 RESTful 主版本：`v2`；官方文档仍标记为 Beta。
- 认证：`Authorization: Bearer <DYNADOT_API_KEY>`
- 签名：敏感请求要求 `X-Signature`。脚本对所有 Dynadot 请求签名。
- 脚本仅接受以 `/restful/v2/` 开头的路径。
- 官方命令文档：<https://www.dynadot.com/domain/api-document>
- API 设置说明：<https://www.dynadot.com/help/question/find-API-settings>

签名原文由以下四项以换行拼接，然后使用 `DYNADOT_API_SECRET` 做 HMAC-SHA256，最后标准 Base64 编码：

```text
apiKey + "\n" + fullPathAndQuery + "\n" + xRequestId + "\n" + requestBody
```

脚本会确保签名使用的 query 编码和 JSON 正文与实际发送字节完全一致。不要在脚本外预先生成签名，也不要把 API key 放进查询参数。

Dynadot 文档提供域名列表/详情、DNS、nameserver、DNSSEC、续费、转移、联系人、锁定、隐私和 aftermarket 等命令。其路径和 body 字段以当前命令页为唯一依据；不要根据命令名称自行推断。Dynadot 不支持批量创建、更新或删除，需逐个对象调用。

## 环境选择

- 未传 `--sandbox` 时使用生产环境。
- 沙箱需要对应供应商的沙箱凭据；生产凭据通常不能直接用于沙箱。
- 当前公开变量名固定为 `GANDI_PAT_TOKEN`、`DYNADOT_API_KEY`、`DYNADOT_API_SECRET`。若以后引入独立沙箱变量，应先修改脚本和根目录 `.env.example`，不要临时复用含义不清的变量。
