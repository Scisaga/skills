# qwen3-asr-openai 参考

本文件用于补充 `speech` skill 依赖的自托管 ASR 服务 `qwen3-asr-openai` 的关键信息。只有在需要了解服务接口、部署方式、环境变量、容量限制或运维行为时再读取。

项目地址：

- GitHub：`https://github.com/Scisaga/qwen3-asr-openai`
- 镜像：`ghcr.io/scisaga/qwen3-asr-openai:latest`

## 项目定位

这个项目把 Qwen3-ASR 封装成一个可自托管推理服务，提供三层能力：

- OpenAI 兼容的转写接口
- HTTP MCP Server
- 内置 Web UI 和 FastAPI 文档页

对 `speech` skill 来说，最直接相关的是 OpenAI 兼容的 HTTP 转写接口，当前 `speech/scripts/transcribe.py` 默认调用这一层。

## 默认地址

本仓库中的 `speech` skill 已将默认地址脱敏并统一为：

```text
http://127.0.0.1:12301
```

常用页面：

- Web UI：`GET /`
- Swagger：`GET /docs`
- ReDoc：`GET /redoc`
- OpenAPI JSON：`GET /openapi.json`
- 健康检查：`GET /health`
- HTTP MCP：`GET/POST /mcp`

## HTTP 转写接口

核心接口：

```text
POST /v1/audio/transcriptions
```

表单字段：

- `file`：必填，音频或视频文件
- `language`：可选，例如 `zh`、`en`
- `prompt`：可选，用于术语、专有名词、会议背景等上下文提示
- `temperature`：可选

返回结构的核心字段：

```json
{"text": "...", "language": "Chinese"}
```

`speech/scripts/transcribe.py` 当前正是按这个接口形态构造 `multipart/form-data` 请求。

## MCP 能力与限制

该服务同时提供 MCP 能力，但 `speech` skill 默认不走 MCP，而是走 HTTP 上传接口。

MCP 暴露内容：

- Tool：`transcribe_audio`
- Resource：`qwen3asr://health`
- Resource：`qwen3asr://usage`
- Prompt：`transcribe_audio_workflow`
- Prompt：`transcript_cleanup_workflow`

MCP 限制：

- 首版只支持 `audio_base64`
- 不支持 `multipart/form-data`
- 不支持 `audio_url`
- 不支持本地路径或 `file://` URI
- 默认大小限制由 `MCP_MAX_INPUT_BYTES` 控制，默认 `33554432` 字节，即 32 MiB

结论：

- 大文件、长音频、视频文件优先继续走 `POST /v1/audio/transcriptions`
- 只有在客户端必须通过 MCP 访问时，才考虑 `audio_base64`

## 部署方式

仓库主推 Docker Compose：

```bash
docker compose up -d --build
```

也支持直接运行 GHCR 镜像，并映射：

- `12301:12301`
- `./models:/models`

服务会把 HuggingFace 缓存写到 `/models`，因此实际部署时应持久化该目录，避免每次重下模型。

## 关键环境变量

以下变量最值得 `speech` skill 使用者了解：

### 模型与设备

- `MODEL_ID`
  - 默认 `Qwen/Qwen3-ASR-1.7B`
- `MODEL_REVISION`
  - 可选，用于锁定 revision，便于复现
- `DEVICE_MAP`
  - 常见值：`cuda:0`、`auto`
- `DTYPE`
  - 常见值：`bfloat16`、`float16`、`float32`
- `MAX_NEW_TOKENS`
  - 控制生成长度
- `MAX_BATCH`
  - 批大小，显存紧张时应保持较小
- `MAX_CONCURRENT_TRANSCRIBE`
  - 控制并发转写数

### 长音频相关

- `CHUNK_SECONDS`
  - 长音频切片时每段长度，默认 600 秒
- `CHUNK_OVERLAP_SECONDS`
  - 段间重叠秒数，默认 1 秒
- `CONTEXT_TAIL_CHARS`
  - 每段追加上一段尾部上下文的字符数，默认 200

### 文本后处理与 MCP

- `NORMALIZE_ZH_NUMBERS`
  - 控制中文数值归一化
  - 示例：`二零二六年 -> 2026年`
- `MCP_MAX_INPUT_BYTES`
  - MCP base64 输入上限

### 服务运行与运维

- `HF_HOME`
  - 模型缓存目录
- `HTTP_PROXY`
  - 拉取 HuggingFace 模型时可用
- `NO_PROXY`
  - 默认可包含 `localhost,127.0.0.1`
- `PORT`
  - 默认 12301
- `ADMIN_TOKEN`
  - 保护 `POST /admin/reload`
- `PRELOAD_MODEL`
  - 控制服务启动时是否预加载模型

## 健康检查内容

`GET /health` 不只是存活探针，还会返回一组运行参数，至少包括：

- `status`
- `model_loaded`
- `model_id`
- `revision`
- `device_map`
- `dtype`
- `max_concurrent_transcribe`
- `chunk_seconds`
- `chunk_overlap_seconds`
- `context_tail_chars`
- `normalize_zh_numbers`
- `mcp_max_input_bytes`

这意味着：

- `speech/scripts/doctor.py` 可以把它当成配置确认接口，而不只是连通性探测
- 当转写效果异常时，可以先看这里确认是否切错模型、dtype、切片参数或后处理开关

## 资源需求与运维建议

README 给出的示例是：

- `Qwen/Qwen3-ASR-1.7B`
- `DTYPE=bfloat16`
- 单卡加载后显存占用约 5.086 GiB

实际运维时还要考虑：

- 长音频会带来额外推理峰值
- 更大的 `MAX_NEW_TOKENS`
- 更高的并发
- 更大的 `MAX_BATCH`

如果遇到显存不足，优先考虑：

- 减小 `MAX_BATCH`
- 减小 `MAX_NEW_TOKENS`
- 换更小模型，例如 README 中提到的 `Qwen/Qwen3-ASR-0.6B`
- 降低并发
- 先切短音频再转写

## 对 speech skill 的直接影响

维护 `speech` skill 时，可以把这个项目理解为“本地可控的 OpenAI 兼容 ASR 后端”。

因此应遵循这些约定：

- 默认对接 `POST /v1/audio/transcriptions`
- 默认地址用 `QWEN_ASR_API_BASE`，未设置时走 `http://127.0.0.1:12301`
- 用 `language` 和 `prompt` 做轻量提示，不要在 skill 侧重复实现切片或归一化逻辑
- 大文件不要改走 MCP base64
- 需要环境确认时先看 `/health`
- 需要人工调试时可以打开 `/docs` 或 `/`
