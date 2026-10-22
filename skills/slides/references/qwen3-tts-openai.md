# Qwen3 自托管配音

## 服务选择与配置

接入项目：[Scisaga/qwen3-tts-openai](https://github.com/Scisaga/qwen3-tts-openai)。使用已部署实例；客户端不部署服务、不下载模型，也不创建或修改服务上的音色。

新项目默认 `voice_profile.provider=auto`：先尝试 Qwen3，连接、鉴权、模型/音色就绪检查、编排预检或生成失败时，再尝试 Azure。切换原因写入章节元数据和 `build_state.json`，控制台明确提示。Azure 仍需有效的 `AZURE_SPEECH_KEY`、匹配的 `AZURE_SPEECH_REGION` 和 SDK；两者均不可用时返回非零退出码并保留失败原因。

可显式选择 `qwen3-tts-openai`（失败即停）或 `azure-speech`。已有显式 Azure 配置不会自动改写；用 `configure-voice --provider auto` 迁移。`synthesize` 从不更改已批准的声音配置。

在当前工作目录的 `.env` 中配置，完整变量见仓库根目录 `.env.example`：

```dotenv
QWEN_TTS_API_BASE=http://127.0.0.1:12309
QWEN_TTS_API_KEY=
QWEN_TTS_VOICE_ID=xiaochen-hd
QWEN_TTS_TIMEOUT_SECONDS=1800
QWEN_TTS_POLL_INTERVAL_SECONDS=2
```

- `QWEN_TTS_API_BASE` 使用可访问实例的根地址；接受末尾 `/` 或 `/v1`，兼容部署在反向代理子路径下的服务。私有 IP、localhost 和 `.local` 主机直连，其他地址遵循系统代理配置。
- `QWEN_TTS_API_KEY` 只在实例设置 `API_TOKEN` 时填写；以 Bearer header 发送，不写入项目、摘要或日志。
- `QWEN_TTS_VOICE_ID` 是可选的配置默认值。执行 `configure-voice --provider auto` 或 `--provider qwen3-tts-openai` 时，若项目尚未绑定音色，则从该变量写入 `voice_profile.qwen_voice`。显式 `--qwen-voice` 优先；生产合成只读项目内的音色，避免环境变化绕过审批。不从多个音色中任意挑选。
- 超时包括排队和生成时间。到期或中断后尝试取消本客户端提交的任务；取消是服务端安全边界上的请求，未确认取消会报告。不会无限轮询、自动重复提交或调整服务参数。

环境变量优先级：现有进程变量 > `--env-file`（如有）> 当前工作目录 `.env` > skill 根目录 `.env` > `scripts/.env`。逐个补充缺失值，不覆盖先前值。发现 `.env` 但缺少 `python-dotenv` 时给出安装命令。

## 音色绑定与试听

```bash
run.sh doctor --stage audio --provider auto --check-service
run.sh list-voices
run.sh configure-voice --project PROJECT --provider auto \
  --qwen-voice xiaochen-hd --voice zh-CN-XiaochenNeural
run.sh voice-audition --project PROJECT --provider qwen3-tts-openai
```

Windows 使用 `scripts/run.ps1` 的同名命令。`list-voices` 输出 ID、就绪状态与名称。`qwen_voice` 必须是实例上已就绪的注册音色 ID；Azure 的预置名称不能直接当作 Qwen ID。`--voice` 保留 Azure 音色名称，供回退使用。选择不同 Qwen 音色、provider 或 Azure 音色后，需重新批准 narration。

当前实例的音色 ID 如下，其他实例以 `list-voices` 返回值为准：

| 音色 | voice_id |
|---|---|
| 晓辰 HD · 亲切女声 | `xiaochen-hd` |
| 晓晓 · 欢快女声 | `xiaoxiao` |
| 晓辰 · 自然女声 | `xiaochen` |
| Qwen 官方英文示例 | `qwen-en` |
| Qwen 官方中文示例 | `qwen-zh` |

上述实例的旧 `voice_<UUID>` ID 已失效。更新 `.env` 不会覆盖项目已绑定的 `qwen_voice`；已有项目应显式运行上面的 `configure-voice --qwen-voice xiaochen-hd` 迁移，再重新批准 narration。新建音色可使用自定义 ID，客户端不限制 ID 前缀或 UUID 格式。

比较多个 Qwen 音色时传 `voice-audition --provider qwen3-tts-openai --voices ID_A,ID_B`；比较 Azure 时传 `--provider azure-speech --voices zh-CN-XiaochenNeural,zh-CN-XiaoxiaoNeural`。不传 `--voices` 时使用当前绑定。每个试听保存 MP3、SSML 和实际服务身份；试听不更改生产配置。

## 编排、真实边界与证据

逐章节提交与 Azure 完全相同的最终 SSML，通过 `voice_mapping` 把其中的 Azure 名称映射到注册 Qwen ID；正文、alias、say-as、最终 rate/pitch、段落停顿和 page bookmark 均保留。`direction` 继续作为审阅依据；不把自然语言导演说明冒充模型已执行的表达指令。

链路为：

```text
GET /ready + GET /v1/voices
→ POST /v1/narrations/compile（预检全部章节，无 GPU 生成）
→ POST /v1/narrations（每章一个任务）
→ GET /v1/jobs/{job_id}（有时限的轮询）
→ 下载 full-wav、timeline、manifest（逐项校验字节数和 SHA256）
→ 检查实际 WAV 的连续页边界与完整覆盖
→ 按真实 PCM 边界切分，编码每页 MP3
→ audio-timeline + audio QA
```

客户端不使用仅支持纯文本的 `/v1/audio/speech` 来替代章节编排。Qwen 按自然句或短段生成，再拼接章节；这不能保证 Azure 式跨句连续声学上下文，也不提供字级对齐。页边界来自实际已合成 PCM 的服务时间轴，不是按字数估算的时间戳。试听需关注句间音色和衔接。

始终设置 `allow_degraded=false`、`allow_experimental=false`。例如当前 Base 后端无法执行部分 `style` 或 `<phoneme>`，预检会失败；`auto` 改走 Azure，Qwen 专用模式直接报错，不静默删除控制项。以实例实时能力和预检结果为准。

项目保留 `video/scripts/<chapter>.qwen-{plan,job,timeline,manifest}.json`。章节 bookmark 元数据记录实际 provider、音色、实例、模型版本、参考音色指纹、生成粒度、边界来源、证据文件 SHA256 和回退原因。

实际服务身份进入音频 fingerprint；实例、模型、参考音色、provider 或 voice 变化会重建缓存。一次生产只允许一个实际身份：即使中途失败或指定 `--pages`，切换 Azure 后也重新检查全部章节，重建不匹配的音频。audio QA 校验实际身份与已批准配置、证据摘要，并拒绝混用两种服务、音色或模型版本。

`--dry-run` 不发网络请求、不加载服务模型、不写文件，只描述当前配置的计划；它不表示服务已通过连通性或编排预检。
