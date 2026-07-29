# qwen3-asr-openai 接入参考

## 范围与权威来源

`speech` 的 ASR 客户端依赖开源项目 [`Scisaga/qwen3-asr-openai`](https://github.com/Scisaga/qwen3-asr-openai) 提供转写服务。

本文件只记录 skill 与该服务之间的依赖边界、最低兼容接口和接入注意事项。Docker、GPU、模型、缓存、多卡、部署、升级和运维参数可能随项目演进，统一以上游仓库 README 为权威来源，不在 skill 中复制维护。

## 依赖边界

- qwen3-asr-openai 是可选外部依赖；只使用 Azure TTS 时无需部署。
- 需要 ASR 时，由使用者按需自行部署服务或提供一个可访问的既有实例。
- `speech` 的 `bootstrap.sh` 只安装本地 Python 依赖并检查环境。
- `speech` 不部署、不启动、不升级 ASR 服务，不下载模型，也不管理 GPU、容器、缓存或服务端配置。
- `video` 的自动字幕能力复用同一个转写客户端，因此生成 ASR 字幕时也需要该服务。

部署入口：

- 项目与部署说明：[`Scisaga/qwen3-asr-openai`](https://github.com/Scisaga/qwen3-asr-openai)
- 容器镜像：`ghcr.io/scisaga/qwen3-asr-openai:latest`

## 最低兼容接口

当前客户端要求服务至少提供：

```text
POST /v1/audio/transcriptions
GET /health
```

`POST /v1/audio/transcriptions` 使用 `multipart/form-data`。当前客户端发送：

- `file`：必填的音频或视频文件；
- `language`：可选语言提示；
- `prompt`：可选上下文或专有名词；
- `temperature`：可选解码温度。

客户端期望 JSON 响应中至少包含字符串字段：

```json
{"text": "..."}
```

上游服务还可以提供时间戳、Web UI、OpenAPI 文档、MCP 和模型管理能力，但这些不是当前 `speech/scripts/transcribe.py` 的最低依赖。

## 配置与检查

默认服务地址：

```text
http://127.0.0.1:12301
```

配置优先级：

```text
--api-base > QWEN_ASR_API_BASE > http://127.0.0.1:12301
```

部署完成后先检查：

```bash
bash skills/speech/scripts/run.sh doctor --mode transcribe
```

再执行转写：

```bash
bash skills/speech/scripts/run.sh transcribe \
  --input-file meeting.wav \
  --language zh \
  --output-text out/meeting.txt
```

## 认证与网络

当前转写客户端不发送 API Key、Bearer token 或其他 `Authorization` header。上游默认的转写接口不使用 `ADMIN_TOKEN`；该 token 只保护管理操作。

不要把默认无认证的转写端口直接暴露到公网。远程部署应使用受信网络、防火墙或反向代理限制访问。若反向代理要求认证，必须先扩展客户端以发送对应凭证，或从受信网络调用；仅新增一个脚本未读取的环境变量不会生效。

## HTTP 与 MCP

qwen3-asr-openai 同时提供 HTTP 转写接口和 MCP。`speech` 默认使用 HTTP 文件上传：

- 避免把音频转成 base64；
- 更适合大文件和长音频；
- 可直接复用 `video` 抽取出的音频文件。

只有调用环境明确要求 MCP 且输入满足上游大小限制时，才考虑 MCP；不要在当前客户端中无条件改用 MCP。

## 兼容性处理

上游部署配置变化通常不要求修改 skill。只有最低接口、认证要求或响应中的 `text` 语义发生不兼容变化时，才同步修改客户端、环境检查和本参考。
