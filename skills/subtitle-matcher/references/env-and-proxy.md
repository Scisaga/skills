# .env 与代理

## 加载顺序

脚本型流程按以下顺序读取 `.env`：

1. 当前工作目录 `.env`
2. `skills/subtitle-matcher/.env`
3. `skills/subtitle-matcher/scripts/.env`

已存在的 shell 环境变量优先级最高；同名变量不会被后续 `.env` 覆盖。需要临时指定配置时，使用脚本参数 `--env-file`。

## 代理变量

联网访问 ASSRT、SubHD、下载链接、重定向链接或浏览器辅助下载时，允许直接使用 `.env` 中的代理环境变量：

```text
HTTP_PROXY=http://127.0.0.1:7890
HTTPS_PROXY=http://127.0.0.1:7890
ALL_PROXY=socks5://127.0.0.1:7890
NO_PROXY=localhost,127.0.0.1,10.0.0.0/8
```

小写形式也有效：

```text
http_proxy=http://127.0.0.1:7890
https_proxy=http://127.0.0.1:7890
all_proxy=socks5://127.0.0.1:7890
no_proxy=localhost,127.0.0.1
```

## 依赖要求

- 缺少 `python-dotenv` 时，如果存在 `.env`，脚本必须明确提示无法自动加载 `.env`，并给出安装命令。
- 缺少 `requests` 或 `beautifulsoup4` 时，联网字幕源适配器不能静默失败。
- 不在报告中输出代理密码、token 或完整代理 URL；只报告变量名是否已启用。

## 诊断命令

```bash
bash skills/subtitle-matcher/scripts/run.sh doctor
```

```powershell
powershell -ExecutionPolicy Bypass -File .\skills\subtitle-matcher\scripts\run.ps1 doctor
```

`doctor` 应检查 Python 依赖、`ffprobe`、`.env` 加载结果和代理变量是否存在。
