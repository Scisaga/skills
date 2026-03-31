# Usage Guide

## 初始化

首次执行：

```bash
bash skills/speech/scripts/bootstrap.sh
```

只检查环境，不安装依赖：

```bash
bash skills/speech/scripts/bootstrap.sh --check-only
```

## Dependencies

Install:

```bash
pip install azure-cognitiveservices-speech python-dotenv
```

TTS credential:

- `AZURE_SPEECH_KEY`

ASR endpoint:

- `QWEN_ASR_API_BASE`, default `http://127.0.0.1:12301`
- 该地址默认指向自托管项目 `qwen3-asr-openai`；需要接口、部署与运维细节时，读取 `references/qwen3-asr-openai.md`

Optional environment file locations:

- current working directory `.env`
- `skills/speech/.env`
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
- 需要部署、模型切换、MCP 限制或环境变量细节时，读取 `references/qwen3-asr-openai.md`

## 统一入口

- `bash skills/speech/scripts/run.sh bootstrap`: 安装依赖并检查环境
- `bash skills/speech/scripts/run.sh doctor`: 仅检查环境
- `bash skills/speech/scripts/run.sh synthesize ...`: 运行 TTS
- `bash skills/speech/scripts/run.sh transcribe ...`: 运行 ASR

## Important TTS parameters

- `--voice`: Azure voice name such as `zh-CN-XiaochenNeural`
- `--style`: expressive style such as `newscast-casual`
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
- Azure cancellation: verify the speech key, region, and whether the chosen voice/style is supported.
- Corrupted or partial output: reduce `--max-chars` if a request is too large.
- ASR request failure: verify the service is reachable and the audio file exists.
- HTTP 422 from ASR: check that the request is multipart form-data and includes the `file` field.
- Poor recognition on domain terms: retry with `--prompt` and an explicit `--language`.
