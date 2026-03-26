# DDNS

## 准备

```bash
curl https://get.acme.sh | sh
source ~/.bashrc

curl -O https://aliyuncli.alicdn.com/aliyun-cli-linux-latest-amd64.tgz
tar -xzvf aliyun-cli-linux-latest-amd64.tgz
sudo mv aliyun /usr/local/bin/
aliyun configure --profile default
cp .env.example .env
```

建议把真实的 `ALIYUN_ACCESS_KEY_ID`、`ALIYUN_ACCESS_KEY_SECRET` 放到未纳入版本控制的 `.env.local`。

## 配置文件思路

这两个脚本现在都是 **env 驱动**：

- [`aliyun_ddns.sh`](/mnt/c/Users/scisa/Desktop/skills/dev-ops/ddns/aliyun_ddns.sh)
  - 用于同步阿里云 DNS 记录
- [`certs_fetch.sh`](/mnt/c/Users/scisa/Desktop/skills/dev-ops/ddns/certs_fetch.sh)
  - 用于通过 `acme.sh + dns_ali` 申请或续签证书

通常做法是：

1. 把 [`dev-ops/ddns/.env.example`](/mnt/c/Users/scisa/Desktop/skills/dev-ops/ddns/.env.example) 复制成 `.env`
2. 把通用但不敏感的值写进 `.env`
3. 把真实密钥写进 `.env.local`

例如：

```bash
cp .env.example .env
touch .env.local
```

## 同步 DNS 记录

```bash
./aliyun_ddns.sh
```

### `DDNS_TARGETS` 是什么

`DDNS_TARGETS` 用来描述“哪些域名、哪些记录类型、哪些主机记录需要跟随当前公网 IP 自动更新”。

它的格式是：

```bash
DDNS_TARGETS='域名|记录类型|RR列表;域名|记录类型|RR列表;...'
```

一共有三层分隔：

- 分号 `;`
  - 分隔多组目标
- 竖线 `|`
  - 每组内部固定分成 3 段：
    - `域名`
    - `记录类型`
    - `RR列表`
- 逗号 `,`
  - 分隔一组里面的多个 RR

### 一组 target 的含义

比如：

```bash
example.com|A|@,git,reg
```

表示：

- 域名：`example.com`
- 记录类型：`A`
- 需要更新的 RR：
  - `@`，也就是根域名 `example.com`
  - `git`，也就是 `git.example.com`
  - `reg`，也就是 `reg.example.com`

脚本会把这 3 条 A 记录都同步到当前公网 IPv4。

### 为什么要加引号

必须像这样写成：

```bash
DDNS_TARGETS='example.com|A|@,git,reg;example.net|AAAA|@'
```

因为 `|` 和 `;` 在 shell 里本来就有特殊含义，不加引号会被当成管道和命令分隔符。

### 常见写法

只维护一个域名的 IPv4：

```bash
DDNS_TARGETS='example.com|A|@,git,reg'
```

同时维护一个域名的 IPv4 和 IPv6：

```bash
DDNS_TARGETS='example.com|A|@,git;example.com|AAAA|@'
```

同时维护多个域名：

```bash
DDNS_TARGETS='example.com|A|@,git,reg;example.net|A|@;example.org|AAAA|vpn'
```

上面这行的意思是：

- `example.com`：
  - 更新 `example.com`
  - 更新 `git.example.com`
  - 更新 `reg.example.com`
  - 类型是 `A`
- `example.net`：
  - 更新 `example.net`
  - 类型是 `A`
- `example.org`：
  - 更新 `vpn.example.org`
  - 类型是 `AAAA`

### 记录类型怎么选

- `A`
  - 同步当前公网 IPv4
  - 通过 `DDNS_IPV4_LOOKUP_URL` 获取
- `AAAA`
  - 同步当前公网 IPv6
  - 通过 `DDNS_IPV6_LOOKUP_URL` 获取

### 一个可直接用的示例

`.env`：

```bash
ALIYUN_CLI_PROFILE=default
DDNS_TARGETS='example.com|A|@,git,reg;example.com|AAAA|@'
DDNS_IPV4_LOOKUP_URL=https://4.ipw.cn
DDNS_IPV6_LOOKUP_URL=https://6.ipw.cn
```

`.env.local`：

```bash
ALIYUN_ACCESS_KEY_ID=your-access-key-id
ALIYUN_ACCESS_KEY_SECRET=your-access-key-secret
```

然后直接执行：

```bash
./aliyun_ddns.sh
```

## 申请或续签证书

```bash
./certs_fetch.sh
```

### 证书相关变量

`certs_fetch.sh` 不读取 `DDNS_TARGETS`，它只关心证书本身这组变量：

```bash
ACME_CERT_NAME=example.com
ACME_DOMAINS='example.com,*.example.com'
```

含义是：

- `ACME_CERT_NAME`
  - 这次安装证书时使用的主名称
  - 最终输出文件名会是：
    - `${ACME_CERT_DIR}/${ACME_CERT_NAME}.key`
    - `${ACME_CERT_DIR}/${ACME_CERT_NAME}.crt`
- `ACME_DOMAINS`
  - 这次申请证书时要带上的全部域名集合
  - 多个域名之间用逗号分隔

例如：

```bash
ACME_CERT_NAME=example.com
ACME_DOMAINS='example.com,*.example.com'
ACME_CERT_DIR=/srv/certs/example.com
ACME_RELOAD_CMD='systemctl reload nginx'
```

表示：

- 为 `example.com` 和 `*.example.com` 申请/续签证书
- 安装到 `/srv/certs/example.com`
- 安装完成后执行 `systemctl reload nginx`

## 定时任务示例

```cron
10 2 20 */2 * /opt/ddns/certs_fetch.sh > /opt/ddns/certs_fetch.log 2>&1
*/10 * * * * /opt/ddns/aliyun_ddns.sh >> /opt/ddns/aliyun_ddns.log 2>&1
```

## 常见问题

### 1. `DDNS_TARGETS` 一直报格式错误

优先检查：

- 有没有用单引号包起来
- 每组是否都是 `域名|类型|RR列表`
- 多组之间是否用分号 `;`
- RR 列表内部是否用逗号 `,`

### 2. `@` 是什么意思

`@` 表示根域名本身。

例如：

- `example.com|A|@`
  - 对应 `example.com`
- `example.com|A|git`
  - 对应 `git.example.com`

### 3. 脚本会不会自动创建记录

会。

- 找不到记录时会调用 `AddDomainRecord`
- 找到但 IP 不一致时会调用 `UpdateDomainRecord`
- 找到且 IP 相同则跳过

### 4. 为什么不用 CLI 一个个传参数

因为 DDNS 通常是定时任务场景，而且经常要维护多组域名。  
把它统一写进 `.env` / `.env.local` 更稳定，也更适合 cron。
