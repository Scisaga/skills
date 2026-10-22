# 自托管 Qwen3 TTS

上游：[Scisaga/qwen3-tts-openai](https://github.com/Scisaga/qwen3-tts-openai)。本技能只调用已部署实例，不部署服务、下载模型或变更音色。

`QWEN_TTS_API_BASE` 为服务根地址，末尾 `/` 或 `/v1` 可归一化。其余变量与 Slides 相同，见 [usage.md](usage.md)。私有网络地址默认绕过环境代理。

## 客户端协议

1. `GET /ready`，要求模型 ready，读取能力。
2. `GET /v1/voices`，精确选择 `voice_id`；要求 conditioning 已就绪且与当前模型相符。
3. `POST /v1/narrations/compile`，提交 SSML 和音色，检查 unsupported 控制与 postprocessing 声明。
4. `POST /v1/narrations`，固定 `compatibility="build-narrated-presentation"`；此值是服务协议，与技能改名无关。
5. 有时限轮询 `/v1/jobs/<id>`；超时只取消自己的任务。
6. 下载音频、timeline 与 manifest，校验字节数、SHA256、PCM WAV 格式、时长、连续时间轴和 SSML 编译结果。
7. 同一后端和音色完成所有段，再用本地 `lameenc` 编码 MP3。

客户端 `scripts/qwen_tts_client.py` 自包含，不导入 Slides。`--rate`、`--pitch`、`--style` 均进入 SSML；服务不支持或没有执行所要求的控制时拒绝输出。`auto` 可整体回退 Azure，显式 Qwen 则失败。服务以 DSP 执行语速/音高时允许，但必须有执行声明。输出不声称具有逐字 forced alignment，时长粒度记录为句子或短片段。

## 结果记录

MP3 旁的 `.tts.json` 保存实际 provider、voice、模型/conditioning 身份、job IDs、控制参数、输入与输出摘要。任务证据和 WAV 在临时目录验证完成后清理；需要深入排障时读取日志中的 job ID，在实例中查询，不把服务密钥写入结果文件。
