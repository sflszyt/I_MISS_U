# VoiceStudio 能否取代本地 TTS（任务 Phase 17）

> 研究日期 2026-09-08 · 用户立项原话："立项：研究下这个项目是否能取代我的本地 tts https://github.com/debpalash/VoiceStudio"
> 方法：workflow 四维只读调查（仓库事实 / 模型与方言 / API 集成面 / 本地现役基线）+ 对抗校核。**校核层因 API 403 中断，5 条校核未执行**（见 §8），收口由主模型完成。未改动任何仓库文件、未安装 VoiceStudio、未启停现役服务。

## 1. 一句话结论

**不能取代引擎层，服务层可借鉴但不建议搬。** 决定性理由是一个代码级断点：VoiceStudio 的 CosyVoice 适配器只接受**一个模型目录**（进程级环境变量 `OMNIVOICE_COSYVOICE_MODEL`），源码中没有任何注入外部 `state_dict` 的钩子；而她的音色恰恰不在模型目录里——`tools/tts_server.py:182-186` 是先用基座建好 `CosyVoice2`，再把 `epoch_14_whole.pt` 过滤后 `llm.load_state_dict(filtered, strict=False)` 打上去。按 VoiceStudio 的方式跑，加载出来的是 WenetSpeech-Wu **基座**，不是她。另有两项默认行为直接伤害档案：**AudioSeal 隐形水印默认开启**、**输出默认响度归一化到 −2.0 dBFS**——默认配置下它会改动写进档案的波形字节。

## 2. 判据

按铁律与现役形态，三道硬门槛任一不过即否决引擎层替换：

1. **音色**：能否加载我们自训练的 CosyVoice2 全量 SFT e14 检查点（`exp_dir/epoch_14_whole.pt`）。不能=换掉她的声音，用户已列为不可接受。
2. **方言**：能否表达 `<|wuyu|>` 前缀 = 上海话 / 裸文本 = 她的沪普 这套双语域切换。
3. **离线**：TTS 链路是否全本地（云 TTS = 铁律 3 直接否决）。

附加判据：替换服务层要重写多少现有能力（`tools/tts_server.py` 588 行）、许可证是否传染。

## 3. VoiceStudio 是什么（仓库事实）

| 项 | 值 |
|---|---|
| 仓库 | https://github.com/debpalash/VoiceStudio（公开、非 fork、未归档） |
| 年龄 | 创建 2026-04-09，最后 push 2026-09-08（调查当天） |
| 热度 | 21,094 stars / 2,620 forks / ~2,121 commits / ~41 contributors |
| 活跃度 | 近五周提交 261/79/135/193/305；开着 71 issue + 21 PR；近 30 天新开 233 issue；最近提交全部由单人 Palash Debnath 推进 |
| 许可证 | **AGPL-3.0**（另有 LICENSE-NOTICE.md 说明各模型上游许可） |
| 形态 | Tauri v2 桌面壳 + React/Vite 前端 + FastAPI 后端（:3900）+ 可选 Docker，非库 |
| 规模 | 仓库 ~79 MB；Python ~9.8 MB 为主语言 |
| 自述 | "完全本地的 ElevenLabs 替代品"，voice cloning / voice design / 视频配音 / 听写 / 转写 / 有声书，宣称 646 语种 |
| 引擎 | 18 个 TTS + 11 个 ASR 的统一封装壳，**无自研 TTS 模型**（默认引擎 = k2-fsa/OmniVoice） |
| 环境 | Windows 10/11 x64 + NVIDIA CUDA 一等支持，Python ≥3.11 / torch ≥2.4（cu128） |
| 曾用名 | OmniVoice-Studio（v0.5.0 起改名，内部标识仍为 `omnivoice` / `OMNIVOICE_*`） |

## 4. 三道硬门槛逐条判定

### 4.1 音色：**不通过**

- 加载入口：`backend/services/tts_backend.py` L1843-1863，`_resolved_model_dir()` 读 `OMNIVOICE_COSYVOICE_MODEL`（默认 `pretrained_models/Fun-CosyVoice3-0.5B`），`_ensure_loaded()` 调 `AutoModel(model_dir=model_dir)`。**只有目录，没有 checkpoint 路径参数，没有 per-request 覆盖。**
- 好消息（须记）：上游 `AutoModel` 会按目录里的 `cosyvoice2.yaml` 自动分派到 `CosyVoice2` 类，构造参数（`load_jit/load_trt/load_vllm/fp16` 全 False）与我们 `tools/tts_server.py:177` **完全一致**——"加载一个 CosyVoice2 模型目录"它做得到。
- 断点：它只能加载模型目录里现成的 `llm.pt`。我们的音色是运行时打进去的 state_dict 补丁，不在目录里。
- 存在绕道：把我们 filtered 后的 state_dict 烘成 `llm.pt`、写进一份复制的模型目录。**但这是我们自己在 VoiceStudio 之外维护的手工工序，不是它的功能**，且每次换 epoch 都要重烘一份完整模型目录。
- 另一独立断点：SFT 分支硬编码取第一个 speaker——`spks = self._model.list_available_spks(); spk = spks[0] if spks else "中文女"`，`kw` 只读 `ref_audio/ref_text/instruct/language` 四键，**没有选 speaker 的入口**。
- 再一条：它面向 CosyVoice **3**，`display_name = "CosyVoice 3 (9 langs, zero-shot, instruct, Apache-2.0)"`；docstring 声称支持 v1/v2/v3，但三者共用一个 engine id，**唯一区分依据是目录名 basename**。
- 部署现实：`docs/engines/cosyvoice.md` 原文——"The packaged release has no supported direct CosyVoice runtime installation path today"，打包版 MSI 今天没有任何受支持的 CosyVoice 运行时安装路径；下载权重不装运行时；它是**进程内 adapter 而非隔离 sidecar**，要求 VoiceStudio 后端那个解释器本身能 `import cosyvoice.cli.cosyvoice.AutoModel`，官方明说不桥接 CosyVoice 自己的 Python 3.10 conda 环境，且把上游 pin 装进它的共享 venv **会与其他引擎冲突**。

### 4.2 方言：**不通过**

- 646 语种目录里**没有吴语/上海话**（有 yue 粤语、cmn、nan 闽南）。
- CosyVoice 适配器 `LANG_TAGS` 只有 10 个标记（zh/en/ja/ko/yue/de/es/fr/it/ru），**没有 `<|wuyu|>`**。
- 语言标记只在 `elif ref_audio:` 的 cross_lingual 分支拼接为 `f"{lang_tag}{text}"`——我们走的路径根本不会拼任何标记。
- 实测（调查方所做）：`<|wuyu|>` 前缀能在它的文本归一化里原样存活；但 **800 字符（CJK 约 320）自动分块**会让长文本只有第一块带前缀——后续分块直接掉回沪普域。
- 结论：我们"前缀=沪语 / 裸文本=沪普"的双语域在它的调用面上**没有对应概念**。

### 4.3 离线：**通过**（但有两条档案层警告）

- TTS 链路全本地，无任何云 TTS 后端。云只出现在：可选的 LLM 翻译/润色、可选的 OpenAI 兼容 ASR 端点、远程 worker、首次下载权重。铁律 3 不构成否决。
- ⚠️ **AudioSeal 隐形水印默认开启**（`watermark.invisible` 默认 True），只能全局开关、无 per-request 字段——默认会在写进档案的波形里嵌入水印。
- ⚠️ **输出默认 mastering 后响度归一化到 −2.0 dBFS**——默认会改变她声音的字节。
- 这两条与"档案二十年可打开、格式与内容不被第三方处理链污染"直接冲突，采用则必须逐项关闭并回读验证。

## 5. 服务层对照

调查对 `tools/tts_server.py`（588 行）做了逐行盘点，结论：**18 项能力属于"我们特有、必须重写"**（9 项在音频路径、9 项在会话/记忆路径），只有约 6 项是通用 HTTP 脚架（CORS、token、串行锁、MP3 编码、基本入参校验）。

| 能力 | 我们（tts_server.py） | VoiceStudio | 判定 |
|---|---|---|---|
| 加载自训练 SFT 检查点 | `:177-191` 基座 + `strict=False` state_dict 补丁 | 只接目录 | **我们特有，必须重写** |
| `<\|wuyu\|>` 双语域 | `:31` `WU_PREFIX`、`:196` 按 lang 注入 | 无此概念 | **我们特有** |
| 起音爆音淡入 `soften_onsets` | 8B-11，30 ms 升余弦 | 无（针对本检查点缺陷的专用后处理） | **我们特有** |
| 时长 QC 回抽 / 拖尾复读闸门 | 有 | 无 | **我们特有** |
| 分句流水线 | 8B-10，≤30 字分条各自合成 | **它更强**：`/ws/tts` 真流式 PCM16 ~200 ms 分块 + 句级并行 + `ttfa_ms`/`rtf` | 对方也有且更好 |
| `/session` 日志 + 17 字段白名单 + 路径穿越防护 | Phase 15 | 无对应概念 | **我们特有** |
| 去抖自动摄入 → `sessions_<viewer>.json` | Phase 15，5 秒去抖 | 无 | **我们特有** |
| viewer 白名单字段 | Phase 15 | 无 | **我们特有** |
| CORS `Expose-Headers` 三个自定义头（页面据此画语音条宽度） | 有 | 默认只允许 loopback/Tauri 源 | **我们特有的跨域合同** |
| OpenAI 兼容端点 | 无 | `POST /v1/audio/speech`、`/v1/audio/transcriptions`、`/v1/audio/voices` | 对方也有 |
| MCP server / CLI 批处理 | 无 | `/mcp`、`omnivoice-infer(-batch)` | 对方也有 |
| voice-profile CRUD / 引擎自省 | 无 | 有 | 对方也有 |
| token 鉴权 | `--token` + `X-TTS-Token` | loopback 不鉴权，非 loopback 有 PIN/API key/可信网段三道闸 | 双方都有 |

现役性能基线（服务端自记，非估算）：冷启动 14.0–15.9 s（异常一次 73.5 s）；8B-10 分条 synth 中位 3.56 s / p90 5.43 s / max 7.63 s（n=44）；RTF 0.79。

## 6. 若采用 / 不采用

**若采用（不推荐）**，只有两种真实形态：
- (a) 把 filtered state_dict 烘成 `llm.pt` + 复制一份模型目录，靠它跑——赌一个未验证的加载路径，且丢掉 `<|wuyu|>` 域、speaker 选择、我们全部 18 项特有能力；
- (b) 给它写一个我们检查点的 engine adapter——**这是对一个 AGPL 代码库的仓库内 fork，不是配置变更**。

**AGPL-3.0 的具体风险（与 F-乙 直接相关）**：纯本机自用不分发无义务；但 F-乙 正是要把服务经 Cloudflare 隧道**开给爸爸这个他人访问**——若届时服务层含 VoiceStudio 后端代码，AGPL §13 网络条款会要求向使用者提供对应源码，传染我们的服务层。这条在 F-乙 语境下不是理论风险。

**可借鉴的局部（推荐，零许可风险）**：
1. **`/v1/audio/speech` OpenAI 兼容契约**——在我们自己的 `tts_server.py` 上加一个兼容端点（只抄接口形状，不抄代码），换 TTS 工具时不必改页面。
2. **`/ws/tts` 的流式思路**——PCM16 ~200 ms 分块 + 句级并行 + 返回 `ttfa_ms`/`rtf`，比我们现在"整条合成完再回传"能显著降低首音延迟。这对 F-乙（爸爸端经 CF 隧道、两人同时在线 TTS 排队）是**当前最有价值的一条**。
3. **loopback 不鉴权、非 loopback 三道闸**的网络姿态设计，正好对应 F-乙 的 `--tokens viewer:token` 需求。

## 7. 裁决建议

**建议：不取代，保留现役 CosyVoice2-Wu SFT + `tools/tts_server.py`；把 VoiceStudio 当作服务层设计的参考实现。** 理由排序：① 她的音色加载路径不被支持且无 speaker 入口（门槛 1 不过）② `<|wuyu|>` 无对应概念（门槛 2 不过）③ 水印与响度归一化默认改字节（伤档案）④ AGPL 在 F-乙 的对外服务形态下有传染风险 ⑤ 18 项特有能力需重写，收益仅换来一个我们不需要的 GUI。

**建议用户拍板的点（非阻塞，可稍后）**：
- P1 是否把「`/ws/tts` 式流式 + 首音延迟指标」立为 8B 后续项（对 F-乙 体验直接加分）——推荐是，排在 F-乙 主线之后。
- P2 是否加一个 `/v1/audio/speech` 兼容端点作为长期解耦（成本约半天）——推荐是，但优先级低于 F-乙。
- P3 是否保留 VoiceStudio 作为**泛化线**（给别人建档时、对方没有 4090、用得上它的 18 引擎与 GUI）的候选——推荐记录在 `GENERALIZATION.md`，不在妈妈档使用。

## 8. 来源与核实状态

**已完成**：四维只读调查全部完成（仓库事实 / 模型与方言 / API 集成面 / 本地现役基线），共 27+27+n 条 claim，来源为 GitHub API、仓库源码原文（`backend/services/tts_backend.py` L1782-1905、`docs/engines/cosyvoice.md`、`docs/engines/README.md`、`pyproject.toml`）与本仓库 `tools/tts_server.py` 逐行核对。

**核实缺口（必须知道）**：对抗校核层 13 个 agent 中 **6 个因 `Failed to authenticate. API Error: 403 Request not allowed` 未执行**（5 条 claim 校核 + 收口 agent）。已完成的 3 条校核全部针对本地基线（`tools/tts_server.py` 的 `<|wuyu|>` 注入与检查点加载路径），结论均为 refuted=false（即论断成立）。**关于 VoiceStudio 本身的论断只经过一轮调查、未经对抗校核**——尽管它们全部附有源码行号与 API 字段级证据，采信前若要动工程仍应实机复核。

**unverifiable（须实测）**：我们的 CosyVoice2 全量 SFT e14 检查点能否被 v3 时代的 `AutoModel` 实际加载（仓库层面无法证实，只能装了试）；烘成 `llm.pt` 的绕道是否真能出她的音色；`<|wuyu|>` 前缀在它 800 字符分块后的实际表现；它在 4090 上的实测 RTF 与我们 0.79 的对比。

**未做**：没有安装 VoiceStudio、没有下载其权重、没有实机跑任何合成。本报告全部结论基于源码与文档阅读。
