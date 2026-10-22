# 配置与运行

## 环境与依赖

需要 Python 3 和 pip，Bash 或 Windows PowerShell。`requirements.txt` 包含 `python-dotenv` 和 Qwen MP3 编码器 `lameenc`；Azure SDK 在可选 `requirements-azure.txt`。仅用 Qwen 或 ASR 时不要求 Azure Key 或 SDK。

```bash
bash skills/speech/scripts/bootstrap.sh --mode synthesize
bash skills/speech/scripts/bootstrap.sh --mode synthesize --with-azure
bash skills/speech/scripts/bootstrap.sh --mode transcribe
bash skills/speech/scripts/bootstrap.sh --check-only --mode synthesize --check-service
```

Windows 使用同目录的 `bootstrap.ps1` 和 `run.ps1`，参数相同。初始化在技能目录建立 `.venv`（PowerShell 为 `.venv-win`），安装选定依赖；`--check-only` 不安装依赖。没有 Python 时先安装 Python 3 并确保 `python` 可调用。

Azure SDK 的系统运行依赖见 [Microsoft 官方安装说明](https://learn.microsoft.com/azure/ai-services/speech-service/quickstarts/setup-platform)。初始化不创建 Azure 资源，不启动 TTS/ASR 服务，也不下载模型。

## 配置优先级

所有位置按以下顺序补充**尚未定义**的变量，已存在值不被覆盖，包括进程中的空值：

1. 进程环境变量。
2. `--env-file` 指定文件。
3. 当前工作目录 `.env`。
4. 技能目录 `.env`。
5. 脚本目录 `.env`。

命令行的后端参数优先于对应环境变量。显式文件不存在则报错；发现 `.env` 但没有 `python-dotenv` 时提供安装命令并退出，不静默跳过配置。

从当前项目复制仓库 `.env.example` 到项目 `.env`，或将跨项目配置保存在插件缓存以外并用 `--env-file C:/config/speech.env` 引用。从别的项目调用脚本时，不会沿父目录搜索源码仓库根目录 `.env`。

```dotenv
QWEN_TTS_API_BASE=http://127.0.0.1:12309
QWEN_TTS_VOICE_ID=xiaochen-hd
QWEN_TTS_API_KEY=
QWEN_TTS_TIMEOUT_SECONDS=1800
QWEN_TTS_POLL_INTERVAL_SECONDS=2
AZURE_SPEECH_KEY=
AZURE_SPEECH_REGION=eastasia
QWEN_ASR_API_BASE=http://127.0.0.1:12301
```

地址和音色均按自己的服务修改。Qwen 的可选 API Key 用于服务启用 `API_TOKEN` 时的 Bearer 认证。Azure Key 和区域须属于同一 Speech 资源；创建资源见 [Azure TTS 快速开始](https://learn.microsoft.com/azure/ai-services/speech-service/get-started-text-to-speech)。

## 合成

```bash
bash skills/speech/scripts/run.sh list-voices --env-file /config/speech.env
bash skills/speech/scripts/run.sh synthesize --text "欢迎来到演示。" --output-mp3 out/demo.mp3 --output-text out/demo.txt
bash skills/speech/scripts/run.sh synthesize --input-file script.txt --provider qwen3-tts-openai --qwen-voice xiaochen-hd
cat script.txt | bash skills/speech/scripts/run.sh synthesize --stdin --output-mp3 out/script.mp3
bash skills/speech/scripts/run.sh synthesize --input-file script.txt --provider azure-speech --voice zh-CN-XiaoxiaoNeural --style newscast
```

| 参数 | 含义 |
|---|---|
| `--provider` | 默认 `auto`；Qwen 配置、连接、就绪、控制预检或生成失败时整份尝试 Azure；显式选择时不回退 |
| `--qwen-voice` | Qwen 注册音色 ID，默认读 `QWEN_TTS_VOICE_ID`；以查询结果中已就绪的音色为准 |
| `--voice` | Azure 音色，默认 `zh-CN-XiaochenNeural`，不会当作 Qwen ID |
| `--style` | 可选表达风格；服务不能执行时回退或报错，Azure 先校验音色支持的风格 |
| `--rate` / `--pitch` | 语速百分比和音高半音或百分比，兼容既有默认 `+5%` / `+0st`；如 `--pitch +1st`，负值建议 `--rate=-5%` |
| `--max-chars` | 单段字符上限，必须为正整数；超长无标点文本也会切分 |
| `--skip-text-save` | 不保存原文；默认仍保存到 `output.txt` |
| `--speech-key` / `--region` | 可选 Azure 配置覆盖，推荐密钥用外部环境文件 |

MP3 旁生成 `.tts.json`，记录请求后端、实际后端、音色、文本/音频 SHA256、控制参数、回退原因和 Qwen job ID。Qwen 采用服务校验的 WAV，统一编码为一个 MP3。分段中途失败后重新生成整份 Azure 音频，成功后才发布输出；服务失败不会覆盖已有 MP3/元数据。输入或本地文件错误不会切换后端。

## 转写

```bash
bash skills/speech/scripts/run.sh transcribe --input-file demo.mp3 --output-text out/demo.txt
bash skills/speech/scripts/run.sh transcribe --input-file meeting.wav --language zh --prompt "Scisaga, Kubernetes" --output-json out/meeting.json
```

ASR 使用独立服务 `POST /v1/audio/transcriptions`，健康检查为 `GET /health`，默认 `http://127.0.0.1:12301`，优先级 `--api-base > QWEN_ASR_API_BASE > 默认值`。保留 `--language`、`--prompt`、`--temperature`、`--timeout` 等既有参数。大文件用 HTTP multipart 上传，不改为 MCP base64。

当前 ASR 客户端不发送认证头；`ADMIN_TOKEN` 仅保护上游模型热重载，不是转写凭据。需要 ASR 时按 [Scisaga/qwen3-asr-openai](https://github.com/Scisaga/qwen3-asr-openai) 自行准备可访问服务。技能不负责部署或运维，边界见 [ASR 接口说明](qwen3-asr-openai.md)。

## 检查与排障

`doctor --mode synthesize --provider auto` 只检查所选能力的配置和本地依赖。`--check-service` 才向就绪/音色接口或 ASR 健康接口发请求，不生成语音。Qwen 检查成功时不强制要求可选 Azure 回退已配置。要单独验证备用服务，运行 `doctor --mode synthesize --provider azure-speech --check-service`。

- 缺依赖：运行对应初始化入口；Azure 用 `--with-azure`，或 `python -m pip install -r <技能目录>/requirements-azure.txt`。
- Qwen 不就绪、音色不存在：查询 `list-voices`，确认 `conditioning_state=ready`、地址、模型和授权；不要自动创建/删除音色或切换服务模型。
- 控制不支持：保留用户要求，选择支持的后端；不可删去参数后宣称成功。
- Qwen 超时：检查服务队列与网络，按需增加 `QWEN_TTS_TIMEOUT_SECONDS`；客户端只取消自己提交的任务。
- Azure 取消：错误包含 reason、error code 和详情；检查 Key、区域、音色与风格组合。
- ASR 422：确认文件存在且请求包含 multipart `file` 字段；术语不准时按需增加 `--prompt` 和已知语言。
