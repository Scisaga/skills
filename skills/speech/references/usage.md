# Usage Guide

## 外部服务与凭证

### TTS：Azure AI Speech

使用 TTS 前需要：

- Azure 订阅；
- 已创建的 Azure AI Speech 资源；
- 该资源的 key，配置为 `AZURE_SPEECH_KEY`；
- 该资源所在区域，配置为 `AZURE_SPEECH_REGION`。

在 Azure Portal 中打开 Speech 资源的 **Keys and Endpoint** 页面取得 key 和区域。区域必须属于同一个资源；key 与区域不匹配会导致鉴权或请求失败。Microsoft 官方准备说明见：

- [Azure AI Speech TTS quickstart](https://learn.microsoft.com/azure/ai-services/speech-service/get-started-text-to-speech)

本 skill 使用自己的环境变量名 `AZURE_SPEECH_KEY` 和 `AZURE_SPEECH_REGION`。配置优先级如下：

```text
--speech-key > AZURE_SPEECH_KEY
--region > AZURE_SPEECH_REGION > eastasia
```

TTS 会调用 Azure 云服务并可能产生 Azure 用量费用。不要把 key 写入 `SKILL.md`、命令示例、Git 历史或公开日志；优先放在已被 Git 忽略的 `.env` 中。

### ASR：qwen3-asr-openai

ASR 不是本地 Python 包内置推理，而是一个可选的外部服务依赖。运行转写前，使用者必须按需自行部署或取得一台可访问的开源 [`Scisaga/qwen3-asr-openai`](https://github.com/Scisaga/qwen3-asr-openai) 服务，并提供：

```text
POST /v1/audio/transcriptions
GET /health
```

本 skill 默认访问 `http://127.0.0.1:12301`。配置优先级如下：

```text
--api-base > QWEN_ASR_API_BASE > http://127.0.0.1:12301
```

当前 `transcribe.py` 不发送 API Key 或 `Authorization` header，项目默认的转写接口也不要求 key。服务端的 `ADMIN_TOKEN` 只用于保护 `POST /admin/reload`，不是转写凭证。若远程部署通过反向代理增加了认证，当前客户端不能直接携带该认证信息，需要先扩展客户端或通过受信网络访问。

`speech` 的 `bootstrap.sh`、`doctor.py` 和转写脚本都不会部署、启动或升级该服务，也不会下载 ASR 模型。部署可能涉及 Docker、NVIDIA GPU/容器运行时、模型缓存和模型下载网络；具体命令、资源要求、模型选择及运维参数以上游仓库 README 为准。本地的 `qwen3-asr-openai.md` 只记录 skill 需要的依赖边界和客户端契约。

### 本地软件

- Bash，用于 `bootstrap.sh` 和 `run.sh`；
- Python 3 与 pip；
- `azure-cognitiveservices-speech`，仅 TTS 使用；
- `python-dotenv`，用于自动加载 `.env`。

Windows 原生运行 Azure Speech SDK 时，可能还需要 Microsoft Visual C++ Redistributable 2015–2022；Linux 上该 SDK 要求 x64。`bootstrap.sh` 只安装 Python 包，不安装这些系统组件，也不部署任何外部服务。

## 初始化

从仓库根目录准备本地配置：

```bash
cp .env.example .env
```

按实际使用的能力填写变量。只用 ASR 时可不填 Azure 项；只用 TTS 时可不启动本地 ASR。

只使用 TTS 时：

```bash
bash skills/speech/scripts/bootstrap.sh --mode synthesize
```

只使用 ASR 时：

```bash
bash skills/speech/scripts/bootstrap.sh --mode transcribe
```

两项服务都已配置时：

```bash
bash skills/speech/scripts/bootstrap.sh --mode all
```

只检查环境，不安装依赖：

```bash
bash skills/speech/scripts/bootstrap.sh --check-only --mode synthesize
```

`--mode` 默认为 `all`，会同时要求 Azure Key 和可访问的 ASR 服务。

## Dependencies

Install:

```bash
pip install azure-cognitiveservices-speech python-dotenv
```

TTS configuration:

- `AZURE_SPEECH_KEY`
- `AZURE_SPEECH_REGION`, default `eastasia`

ASR endpoint:

- `QWEN_ASR_API_BASE`, default `http://127.0.0.1:12301`
- 该地址默认指向使用者自行部署的 `qwen3-asr-openai`；依赖边界与兼容接口见 `references/qwen3-asr-openai.md`，实际部署以上游仓库 README 为准

Optional environment file locations:

- current working directory `.env`
- `skills/speech/.env`
- `skills/speech/scripts/.env`
- explicit file passed through `--env-file`

## TTS commands

Short inline text:

```bash
bash skills/speech/scripts/run.sh synthesize --text "欢迎来到演示。" --output-mp3 out/demo.mp3
```

Read from file:

```bash
bash skills/speech/scripts/run.sh synthesize --input-file script.txt --output-mp3 out/demo.mp3
```

Read from stdin:

```bash
cat script.txt | bash skills/speech/scripts/run.sh synthesize --stdin --output-mp3 out/demo.mp3
```

## ASR commands

Basic transcription:

```bash
bash skills/speech/scripts/run.sh transcribe --input-file demo.mp3 --output-text out/demo.txt
```

With known language and prompt:

```bash
bash skills/speech/scripts/run.sh transcribe \
  --input-file meeting.wav \
  --language zh \
  --prompt "Servforce.AI, Qwen3-ASR-openai, Kubernetes" \
  --output-text out/meeting.txt
```

Save raw JSON too:

```bash
bash skills/speech/scripts/run.sh transcribe --input-file meeting.wav --output-json out/meeting.json
```

## ASR service notes

- 当前 `speech` skill 的转写脚本对接的是 `qwen3-asr-openai` 的 HTTP 上传接口：`POST /v1/audio/transcriptions`
- 健康检查优先看 `GET /health`
- 服务自带 Web UI、Swagger 和 MCP；但本 skill 默认走 HTTP 上传接口，而不是 MCP
- 对大文件或长音频，优先继续走 HTTP 上传接口，不要改成 MCP base64 传输
- 本 skill 不自动部署或管理 ASR 服务；部署、模型切换、资源和运维细节以[上游仓库](https://github.com/Scisaga/qwen3-asr-openai)为准
- 需要确认 skill 实际依赖的接口、认证和传输边界时，读取 `references/qwen3-asr-openai.md`

## 统一入口

- `bash skills/speech/scripts/run.sh bootstrap`: 安装依赖并检查环境
- `bash skills/speech/scripts/run.sh doctor`: 仅检查环境
- `bash skills/speech/scripts/run.sh synthesize ...`: 运行 TTS
- `bash skills/speech/scripts/run.sh transcribe ...`: 运行 ASR

## Important TTS parameters

- `--voice`: Azure voice name such as `zh-CN-XiaochenNeural`
- `--style`: 可选表达风格；默认不设置。风格必须与音色匹配，例如 `zh-CN-XiaoxiaoNeural + newscast` 或 `zh-CN-XiaochenNeural + livecommercial`
- `--rate`: speaking rate such as `+5%`
- `--pitch`: pitch offset such as `+0st`
- `--region`: Azure Speech region, default `eastasia`
- `--max-chars`: maximum characters per chunk before splitting long text

## Important ASR parameters

- `--api-base`: ASR service base URL
- `--language`: optional language hint such as `zh` or `en`
- `--prompt`: optional domain terms to improve recognition
- `--temperature`: optional decode temperature
- `--timeout`: request timeout in seconds

## Troubleshooting

- Missing dependency: run `bash skills/speech/scripts/bootstrap.sh`.
- Empty output: check that input text is not blank.
- Azure cancellation: 脚本会保留 Azure 返回的 cancellation reason、error code 和 error details；按详情检查密钥、区域、音色或请求内容。
- Unsupported voice/style: 指定 `--style` 时脚本会先查询 Azure 音色清单；根据错误列出的可用风格改用有效组合，或省略 `--style`。
- Corrupted or partial output: reduce `--max-chars` if a request is too large.
- ASR request failure: verify the service is reachable and the audio file exists.
- HTTP 422 from ASR: check that the request is multipart form-data and includes the `file` field.
- Poor recognition on domain terms: retry with `--prompt` and an explicit `--language`.
