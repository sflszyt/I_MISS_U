# I_MISS_U 技术管道全景（PIPELINE.md）

> 从原始素材到可传承数字档案的完整管道配方。基于 mama 档案 MVP 全程实证（2026-08-04 立项 → 2026-08-17 交付），每一节都有真实产物背书。
> 本文档的双重身份：①当前管道的权威技术记录；②未来「构建端 Claude Code skill」的蓝图（见末章）。
> 配套文档：`CLAUDE.md`（铁律）· `docs/HANDOFF.md`（会话交接）· `task_plan.md`/`progress.md`（过程实录）· `findings.md`（技术发现）· `docs/research/`（选型研究）。

---

## 〇、产品形态与设计原则

**形态 C（混合形态，2026-08-04 用户拍板）**：

```
构建端（允许死）                      消费端（必须活 20 年）
┌─────────────────────┐              ┌─────────────────────────┐
│ Claude Code skill    │   编译产出   │ 自包含静态档案目录        │
│ + 29 个 person-      │  ────────→  │ archive_dist/            │
│   generic 工具       │              │ · 开放格式数据层 (JSON)   │
│ + GPU 训练/合成       │              │ · 静态 HTML 浏览层        │
│ + 人工闸门交互        │              │ · BYOK 对话页（裸 fetch） │
└─────────────────────┘              └─────────────────────────┘
```

三条不可动摇的原则（详见 CLAUDE.md 铁律）：

1. **档案优先于对话**：每个功能先问"让档案更完整，还是只让对话更沉浸？"
2. **Tier 分级 + 人工闸门**：Tier-1 家人确认 / Tier-2 可溯源 / Tier-3 模型生成禁作事实；AI 新学到的一切默认 Tier-3。
3. **raw/ 神圣不可侵犯**：只读、永不修改、gitignore、永不出机；一切处理输出到新目录。

**工程方法论（三模型分工）**：Claude 统筹/规格/验收编排，DeepSeek V4 Flash 写实质代码（`scripts/deepseek_call.py`，必带 `DEEPSEEK_NOTHINK=1`，≥32k tokens），Codex GPT-5.6 审核验收（MCP，REJECT 回炉至 ACCEPT）。Claude 直写仅限：一次性探针、声明的 1-3 行 hotfix、纯数据拼装、判断类文书——每次须声明。

---

## 一、管道全景图

```
Stage 1 素材获取          Stage 2 数据层             Stage 3 语音层
┌──────────────┐        ┌──────────────┐          ┌──────────────────┐
│ 微信 DB 解密   │        │ parse_wechat  │          │ 参考选段(用户耳测)  │
│ 语音/视频提取  │──────→ │ → UIF 20909   │───┬───→ │ ASR → 校对闸门 🚪  │
│ 照片归集       │        │ 敏感清理关卡🚪 │   │      │ → SFT 训练        │
└──────────────┘        │ build_bundle  │   │      │ → epoch 耳测 🚪    │
                        └──────────────┘   │      │ → 盲听 🚪 → TTS 服务│
                                           │      └──────────────────┘
                        Stage 4 文字层      │       Stage 5 卡通人
                        ┌───────────────┐  │      ┌──────────────────┐
                        │ rhythm/digest  │←─┤      │ 照片→卡通候选      │
                        │ persona 草稿    │  │      │ → 用户终选 🚪      │
                        │ → Q1-13 确认🚪 │  │      │ → viseme贴片动画   │
                        │ 记忆候选→闸门🚪 │  │      └──────────────────┘
                        │ → Tier-1 记忆册 │  │
                        │ timeline/转写   │  │
                        └───────────────┘  │
                                           ↓
                        Stage 6 对话页 ←──────────── Stage 3 TTS 服务
                        ┌────────────────────────┐
                        │ chat_context(索引化)     │
                        │ 知识源三件套 · BYOK 双协议 │
                        │ 微信式语音回复            │
                        └────────────────────────┘
                                           ↓
                        Stage 7 打包交付 + 远程访问
                        ┌────────────────────────┐
                        │ build_archive → dist    │
                        │ sha256 manifest/verify  │
                        │ Tailscale 私网           │
                        └────────────────────────┘
```

🚪 = 人工闸门（共 7 类，见第九章清单）。

---

## 二、Stage 0：环境与依赖

| 组件 | 位置/版本 | 用途 |
|---|---|---|
| 硬件 | RTX 4090 24GB · i9-14900KF · 64GB RAM | SFT 训练/合成/头像生成，全本地 |
| CosyVoice 源码 | `C:\Users\justin\CosyVoice`（+ third_party/Matcha-TTS） | 语音训练与推理框架 |
| cosyvoice venv | `C:\Users\justin\venvs\cosyvoice`（py3.10, torch 2.3.1+cu121） | 训练/合成/TTS 服务/音频编码（lameenc、soundfile 在此） |
| Wu 权重 | `C:\Users\justin\CosyVoice-models\WenetSpeech-Wu-Speech-Generation`（HF ASLP-lab，Apache-2.0，5 变体） | 沪语底座（CosyVoice2 栈，与 Fun-CosyVoice3 不通用） |
| wenet | `C:\Users\justin\wenet`（PYTHONPATH 引用，无需安装） | u2++ ASR 解码 |
| chatlog-keeper venv | `installers/chatlog-keeper-0.2.0/.venv`（pysilk、numpy 在此） | 微信解密/语音解码 |
| asr venv | `C:\Users\justin\venvs\asr`（funasr/SenseVoiceSmall，CPU） | ASR 草稿（早期用，已被 u2++ 取代） |
| ComfyUI Portable | `~\ComfyUI_portable`（Qwen-Image-Edit-2509 权重 ~28.6G） | 照片→卡通头像 |
| Node.js | v24（PATH） | HTML 产物 harness 验收 |
| 训练工作区 | `~\wu-sft\`（v0/v01_clean27/v01_full44/v02_full/blind_v2/mandarin_a/tts_server） | 语音层全部实验与产物（仓库外，不入 git） |

通用环境坑（详见 findings.md）：PowerShell 5.1 `Set-Content` 写文件带 BOM 会崩 GBK 读取的下游（用 awk/python 写无 BOM）；官方脚本在 Windows 需 `PYTHONUTF8=1`；`Get-Content` 对无 BOM UTF-8 中文行数不可靠——文本处理一律 `python -X utf8`。

---

## 三、Stage 1：素材获取（微信 4.1.x 混合方案）

微信 4.1.x 加密方案变化，chatlog/chatlog-new 均不支持 → 三路混合（研究：`docs/research/wechat-media-extraction.md`）：

1. **文字+图片**：`chatlog-keeper`（MIT，`installers/` 内已配 venv）。取 DB key 要点（记忆 wechat-key-extraction）：微信 4.1.x 登录弹窗期 + 管理员 PowerShell + 显式 `--data-root`。解密链：key 存 `~\ck-data\secrets\` → DB 镜像 `~\ck-mirror`（删 shm）→ 明文库 `~\ck-decrypted`。
2. **视频**：4.1 视频是明文 mp4，直接从 `xwechat_files\<wxid>\msg\video\**\*.mp4` 采集 → `tools/collect_wechat_video.py`（staging + os.link 硬链接原子落盘；微信源文件带 ReadOnly 属性，清理需先 chmod）。
3. **语音**：SILK blob 在加密消息库内 → `tools/extract_wechat_voice.py`（自研）。关键探测结论：sender 归属 = `Msg.real_sender_id` → 同库 `Name2Id` 表 rowid → wxid；`Msg_<md5(room)>` 分片散布 message_0~6；`VoiceInfo` 在 media_0/media_1。**必须用 chatlog-keeper venv 的 python 跑**（pysilk 在那里）；pysilk.decode 要传含 0x02 头的完整 blob。

```
# 语音提取（125 条 WAV，~55 分钟，产 UIF manifest）
installers\chatlog-keeper-0.2.0\.venv\Scripts\python.exe tools\extract_wechat_voice.py --person mama --db-dir ~\ck-decrypted
# 视频采集（215 个 mp4 → raw/wechat/video/<年-月>/）
python tools\collect_wechat_video.py --person mama --db-dir ~\ck-decrypted --video-dir ~\xwechat_files
```

照片：用户手工放入 `raw/photos/`；`tools/ingest_media.py` 清点 + EXIF。未启用源：微博（#14）、朋友圈（#15）——素材到手后各写一个 parser 即可（L1 源适配器架构）。

---

## 四、Stage 2：数据层

### 4.1 UIF 统一中间格式

`schema/uif.schema.json`：4 类记录（message/post/email/media_item），信封字段 `viewpoint`/`source`/`tier`/`provenance`。**下游只消费 UIF**——新增数据源 = 只加一个 parser。

`tools/parse_wechat.py --person mama` → `normalized/wechat_messages.uif.jsonl`。mama 筛选规格（勿退回旧版）：一对一 `laurawang001` 整段 + 4 个群聊完整对话（含他人发言作语境，sender 严格标注）。配置在 `people/mama/wechat_parse_config.json`（gitignore 内）。

### 4.2 敏感清理关卡（任何人物管线的标准步骤）

`tools/scrub_sensitive.py` 三模式：`scan`（模式扫描出报告，配置 `tools/sensitive_patterns.json`）→ 用户指认 record_id 清单 🚪 → `apply`（全派生层删除 + manifest 不含正文）→ `verify`（残留检查须 residue=0）。mama 实例：2024-02-09 凭据交接批 14 条全删（UIF 20923→20909），四下游重建。⚠️ 重跑 parse_wechat 会重新引入，须按 `normalized/scrub_manifest.jsonl` 重新 apply。存量疑似 601 条（`normalized/sensitive_scan_report.*`）闸门页默认剔除，人工复核未完成。

### 4.3 档案数据包

`tools/build_data_bundle.py --person mama` → `archive_out/data/`：7 个年度分片（`messages_YYYY.json`，形态 `{year,count,records[]}`）+ `media_index.json` + `timeline.json`（68 月对账）+ `meta.json`（counts + tier_legend）+ `media/voice` 125 条 + `media/video` 本人 9 条。幂等 + 全量对账 + file_ref 子树锚定。

---

## 五、Stage 3：语音层（最深的一条线）

### 5.1 选型结论（研究：`docs/research/dialect-tts-maturity.md`、`cosyvoice3-deploy.md`）

- **现役**：CosyVoice2-Wu-SFT 底座 + 本人数据 SFT = `~\wu-sft\v02_full\exp\mama_v02f160_llm\epoch_14_whole.pt`
- **双语域（2026-08-16 关键发现）**：合成文本挂 `<|wuyu|>` 前缀 = 上海话；**裸文本 = 她的沪普**（上海口音普通话，A/B 耳测胜过 CosyVoice3 口音指令方案）→ LLM 普通话输出可直喂，无需普→沪本字转换
- **天花板实锤**：CosyVoice2-Wu 公开权重的长句音系上限已达（SS 变体未公开、路线 D 两段式耳测失败）→ **合成定位 = 短句场景**（对话回复/卡通人问候），长内容播真声。观察项：吴语生态 2026-02 起步，留意更强开源沪语 TTS
- Fun-CosyVoice3 普通话线已退役并入主线

### 5.2 数据管线（原始语音 → 训练集）

1. **参考选段**：99 条本人语音普查（61 条 ≥15s）→ 5 条候选切 18s 窗口 → 用户盲选 🚪 → **ref01**（2022-07 健康期日常）固化于 `voice/reference/`（含 manifest/sha256/用户校对转写）
2. **切段**：>30s 长语音（40 条 34 分钟）→ `~\wu-sft\v02_full\scripts\segment_long_voice.py` 能量谷切割 → 101 段（4.7-27.9s），全池 160 条 47.2 分钟
3. **ASR**：u2++（wenet attention_rescoring，自带字典；whisper BPE 会产 U+FFFD 坏字符——已废弃）。解码 yaml `v02_full/asr_input/u2pp_decode.yaml`（发布版缺 input_dim/output_dim 需补 80/5949）
4. **校对闸门** 🚪：`tools/make_correction_page.py` 生成移动优先校对页（15 条/页、24kbps 内嵌、自动标红、回贴码=仅改动 delta + dataset hash 校验；零标红页默认展开）→ 用户逐页回贴 → `tools/apply_corrections.py` 合并（指纹校验）
5. **特征三件套**：extract_embedding + extract_speech_token（CosyVoice tools）→ parquet 用 `v0/make_parquet_single.py`（官方 make_parquet_list 在 Windows 必挂：GBK 编码 + apply_async 吞 spawn 错误）

### 5.3 训练（4090 实证参数）

```bash
# cosyvoice venv + run_train.sh（从 Wu-SFT llm.pt 起训）
# 160 条 47 分钟 × 15 epochs ≈ 视数据量 15-50 分钟；v0.2 CV loss 0.195 / acc 0.964
```

已修的源码坑（CosyVoice 未提交补丁两处）：llm.py 梯度检查点（non-reentrant + use_cache=False）、executor.py cv 阶段 `@torch.inference_mode()` 与 Windows gloo DDP 冲突改 `@torch.no_grad()`。
**工艺红线**：长时 GPU 任务永不用 harness 后台 bash（会被回收误杀且僵尸占显存）——`Start-Process -WindowStyle Hidden` 独立进程 + 日志直写 + Monitor 三态监听；续训 `--checkpoint epoch_N_whole.pt` 自动从 N+1 续起。

### 5.4 评估闸门链

1. **epoch 试听** 🚪：`synth_epoch_samples.py --pad-ms 300`（首尾垫静音防截断）→ `make_listen_page.py` → 用户耳测挑 epoch（历版结论均为 e14；起始幻觉系随机采样，重抽即除）
2. **批量合成**：`tools/synth_blind_batch.py --texts <jsonl> --exp-dir <exp> --epoch 14 --lang {wu,mandarin}`——时长 QC（0.32s/字+2s 上限）自动重抽 + 起始能量标记 + qc_report.jsonl
3. **盲听** 🚪（M1 唯一有效标准）：`make_blind_page.py` 合成×真声乱序 + key 分离。战绩：v0.1 用户本人 3/10 骗过 → v0.2 7/8 骗过（真声 4/4 认出保证测试有效性）。文本必须取训练集外（防背诵失真）

### 5.5 TTS 服务（对话页语音回复后端）

`tools/tts_server.py`（cosyvoice venv 运行，`~\wu-sft\tts_server\start_tts.bat` 一键启动）：
- `GET /health` 探活；`POST /tts` JSON `{"text","lang"?}` → mp3（X-Duration-Seconds 头）；OPTIONS 全 CORS
- 默认 mandarin（=沪普直喂）；120 字上限；串行锁；装载 ~15s、合成 ~6s/句
- 加固：Content-Length 缺失/非法→400、>64KB→413、一切错误断连（防 keep-alive 污染）；`--token` 可选鉴权（默认关=私网信任）
- **音频铁律**：int16 喂 lameenc（float 直喂=全噪音事故）+ 解码回读 RMS 自检

---

## 六、Stage 4：文字层（全部 person-generic）

设计基线：工具吃 `--person <slug>` + UIF；人物/关系特定内容全部进 `persona/relationship.json` 与 `prompts/` 参数化模板，代码零硬编码。

| 工具 | 产出 | 说明 |
|---|---|---|
| `build_rhythm.py` | `persona/rhythm.json` | 9373 条本人消息的长度/时段/连发/回复延迟/标点/口头禅/emoji/语音习惯 |
| `extract_persona_digest.py` | `persona_digest.json`（205KB） | 分年样本/对话窗口/9 组关键词（`tools/persona_keywords.zh.json`），全带 record_id |
| （Claude 子代理起草） | `persona/persona.md` | 46 论断逐条带证据 + 待确认清单；**必写缺点冲突面**（铁律 2）；全文 Tier-3 → 用户逐条裁决 🚪 升级（mama：Q1-Q13 已收口，删除项与禁提话题进 relationship.json taboo_topics） |
| `extract_memory_candidates.py` | `memories/candidates.jsonl`（150 条） | 五信号挖掘（关键词事件/爆发日/长消息/长语音/媒体爆发）+ 配额轮转；支持 `--voice-transcripts/--video-transcripts` 让记忆卡带她说的话 |
| `make_gate_page.py` | `gate_page.html` | 150 卡移动闸门页 🚪：确认/改写/剔除，敏感预标记默认剔除（只扫将进入 memories.md 的可见文本），回贴码=初始状态真 delta |
| `apply_gate_decisions.py` | `memories/memories.md`（Tier-1） | 多轮回贴/pending 回撤/围栏容忍/幂等重生成；dataset hash 校验 |
| `merge_candidate_state.py` | （就地升级 candidates.jsonl） | **重挖不丢裁决**：按 candidate_id 合并，content_changed 标记，carried_forward 结转 |
| `build_voice_transcripts.py` | `normalized/voice_transcripts.jsonl` | 段级 ASR+校对稿聚合回原条目（校对优先，quality 标 corrected/asr_draft）；`--media-kind video` 复用跑视频 |
| `render_timeline.py` | `memories/timeline.md` | 68 月无缺口对账 |

升级路径实证（08-16）：校对完成 → build_voice_transcripts 重建（99/99 corrected）→ 重挖到独立文件 → merge_candidate_state（124/26 裁决零丢失）→ 空 delta 重跑 apply → memories.md 校对文本落位。

---

## 七、Stage 5：卡通人

1. **生成**：ComfyUI（`--disable-auto-launch`，127.0.0.1:8188）+ Qwen-Image-Edit-2509（官方模板从便携包 site-packages 解出，20 步/cfg 4/shift 3）。`tools/gen_avatar_candidates.py`（照片×风格×seed 矩阵，~70s/张，manifest 溯源）→ `tools/make_contact_sheet.py` 拼图直发用户
2. **终选** 🚪：用户挑风格（warm 暖手绘）→ 挑单张（04 s1001）→ 固化 `persona/avatar.png` + `avatar_choice.json`（源照/seed/prompt 溯源）
3. **嘴型/眨眼贴片（2026-08-25/27 重写，取代旧双帧）**：恒定底图为公理——同底图 Qwen 掩码区改口型（嘴部矩形 480,460,700,640 羽化 14；眨眼=双镜片内区，镜框恒用底图像素），程序化合成后烘全尺寸 RGBA 透明叠层（**RGB 取 raw 变体非 comp**——叠加数学 base×(1-α)+raw×α）入 `persona/mouth_*.png / eyes_closed.png`；配置 `persona/mouth_patches.json` v2（states/viseme_map/rms_states/blink+provenance）。候选连播 GIF 审核页用户定稿 🚪。工艺：嘴型 prompt 首轮必夸张，需"温和克制"迭代
4. **口型时间轴**：`tools/build_visemes.py`——Rhubarb Lip Sync `-r phonetic`（语言无关，上海话可用）批跑语音 → `archive_out/data/avatar/visemes.json`（增量模式；新增语音=一条命令）。坑：rhubarb 须 `-o` 文件输出（--machineReadable+stdout 拿不到 JSON）
5. **页面**：`tools/build_avatar_page.py` → `avatar.html`——数据驱动 N 态贴片：**时间轴驱动优先**（audio.currentTime 查 cue，音素级口型）→ 无时间轴回退 RMS 音量驱动（BYOK 动态 TTS 分支）；眨眼调度器（待机也眨）+ ambient 头部微摆；三层模式回退 patch>image>SVG（person-generic）；诊断 HUD（`?debug=1`）。**验收铁律：computed style + 截图像素 diff，inline 遥测不算数**（display 一律显式 'block'，血案见 progress 08-25）。显存管理：ComfyUI 吃紧时 `POST /free`
6. **可选增强（未启动）**：talking-head 预渲染 MP4"特别版"（研究依据 `docs/research/digital-human-rendering.md`）

---

## 八、Stage 6：对话页（BYOK）

- `prompts/chat_system.zh.md`：person-generic 六铁律模板（只说档案有的/记不清就说/Tier 纪律/保留缺点/被问承认模拟/克制依赖——禁"我会一直在这里"）
- `tools/build_chat_context.py --memories-mode index`：system prompt ~2.4 万字符（记忆只嵌"日期·标题"索引，全文走检索）；full 模式保留
- `tools/build_chat_knowledge.py`：`data/memories.json`（124 条 Tier-1）+ `data/transcripts.json`（108 条 Tier-2 语音/视频转写）检索源
- `tools/build_chat_page.py` → `chat.html`（36KB 自包含）：
  - **检索三源混排**：记忆 top3（Tier-1 标签优先）+ 消息 top6 + 转写 top2，CJK 2-gram 打分，预算 2200 字符
  - **双协议 BYOK**：OpenAI 兼容（DeepSeek `https://api.deepseek.com/chat/completions` + `deepseek-chat`）/ Claude 官方（`https://api.anthropic.com/v1/messages`，`x-api-key` + `anthropic-version` + `anthropic-dangerous-direct-browser-access` 头，CORS 直连实测通；SSE 状态机按 provider 隔离防跨协议误触）
  - **微信式语音回复**：探活同主机 :8022 → 回复 ≤120 字合成 → 绿色语音条（点击播放/右键长按"转文字"/「合成语音·非原声」标签守 Tier 纪律）→ 四类失败优雅降级文字
  - file:// 直开引导、永久"非本人"横幅、key 仅存 localStorage

---

## 九、Stage 7：打包交付与远程访问

### 9.1 正式打包

`tools/build_archive.py --person mama` → `people/mama/archive_dist/`（161 文件 241.7MB）：
- 白名单拷贝（default-deny：avatar/chat/data 全树；review 页全剔）+ text/ 文字层四件（persona/memories/timeline/rhythm；**刻意不含** relationship.json/candidates.jsonl）
- 生成干净 index.html + README.txt + start_server 双脚本
- 六项一致性硬校验：分片对账（兼容 `{records:[]}` 与裸数组）、chat 分片存在性、离线红线三正则（src/href + srcset + css url 外链即失败）
- `archive_manifest.json` 逐文件 sha256 + `--verify` 对账 + `--dry-run` 严格零写盘 + 幂等 reconcile（期望集+两遍清扫）
- 验收标准：拷走后无网机器可打开（Playwright 三页真浏览器验收零 console 错误）

### 9.2 远程访问（Tailscale userspace 私网）

- 隐私底线：档案绝不裸公网隧道（铁律 3）；Tailscale = 端到端私网
- **架构（被逼出来的）**：腾讯电脑管家拦 SYSTEM 服务出网（WSAEACCES + DNS 失败，本地拦截特征）→ **userspace-networking 模式、提权用户态 tailscaled + `--unattended`**（系统服务已停用禁用）；登录自启任务 `TailscaleUserspace`
- 现网：justin-pc `100.116.45.2` + iphone182；访问 `http://100.116.45.2:8020/`（TTS 走同主机 8022，页面用 `location.hostname` 自适应 LAN/Tailscale）
- 组网流程（headless）：手机 login.tailscale.com 生成 auth key → PC `tailscale up --auth-key=... --unattended`
- 已知风险：管家若日后拦用户态进程需回家白名单；UDP 受限走 DERP TCP 中继

---

## 十、人工闸门总清单（skill 交互设计的骨架）

| # | 闸门 | 形式 | 频次 |
|---|---|---|---|
| G1 | 语音参考选段耳测 | MP3 直发 + 聊天选择 | 一次 |
| G2 | ASR 转写校对 | 校对页（回贴码） | 每批转写 |
| G3 | epoch 试听 + 盲听 | 试听页/盲听页 + AskUserQuestion | 每次重训 |
| G4 | 敏感记录指认 | scan 报告 + record_id 清单 | 每次数据摄入 |
| G5 | persona 论断确认 | 草稿直发 + 逐条问答 | persona 更新时 |
| G6 | 记忆卡裁决 | 闸门页（回贴码） | 每次重挖（merge 保状态） |
| G7 | 头像/说话帧终选 | 拼图直发 + 聊天选择 | 一次（可否决重抽） |

**移动 review 定式**（全部闸门共用）：HTML <1MB/页、大按钮、回贴码最短化（delta + dataset hash）、音频逐条 MP3 直发（聊天渲染器不播内嵌音频，浏览器可以）、图片拼图直发、选择题用 AskUserQuestion。

---

## 十一、工程铁律与工艺沉淀（血泪版）

**音频**：①MP3 编码必须 int16（float 直喂 lameenc = 全噪音+伪男声，用户耳测才抓出）②凡产音频的工具内置解码回读自检（sf.read 回读，时长±10% + RMS 阈值）③"连真素材都坏 → 缺陷在打包层非生成层"④坏 MP3 体积恰为正常 2 倍可作嗅探。

**HTML 工具生成定式**：①模板一律 `r"""` raw + `__X__`+replace（%格式化撞 CSS 百分号、非 raw 撞 JS \n）②关键 JS 逻辑抽纯函数挂 window 供 harness 直测③验收三级：node --check → **忠实 stub 全脚本执行**（getElementById 对不存在 id 必须返回 null，过宽 stub 吞空引用崩溃）→ e2e 驱动真实交互流（假流式/fallback 丢块只有这层能抓）。

**审核工艺**：①Codex 对 CJK 文件的"语法错误"指控一律先 py_compile/json.load/node 实证（累计 6 次误报）②给 Codex 的复审 prompt 明确"跑命令验证勿目测"③**审核方自己的破坏性实验会污染共享测试环境**——复现缺陷必须干净连接/干净状态（TTS 分帧攻击污染 keep-alive 导致误判 BLOCKER 一案）④同文件三轮回炉失败即停，换外科 hotfix（三振协议）⑤共享契约的成对工具必须联审。

**DeepSeek 管线**：流式调用器唯一可靠（非流式被网络掐）；`DEEPSEEK_NOTHINK=1` 必带（推理烧光正文）；≥32k tokens；产物剥围栏（可能带前导解说，按 shebang/编码行定位真起点）+ py_compile；修改既有文件=嵌全文出全文+git diff 逐 hunk 核对改动面。

**Windows 特有**：PS 5.1 内联 python -c 引号/&& 必炸（写脚本文件跑）；Set-Content BOM 坑；`Get-ChildItem -Filter` 不支持字符类；服务/SYSTEM 进程操作需真提权（本机 UAC 静默提权 ConsentPromptBehaviorAdmin=0）；长时 GPU 任务 Start-Process 脱钩（见 5.3）。

**数据**：候选/裁决类文件重生成前先想状态保留（merge_candidate_state 模式）；派生层可从 raw 重建=删除零风险；record_id/candidate_id 用内容确定性哈希保跨轮稳定。

---

## 十二、Skill 化蓝图（初心的落地路径）

### 12.1 为什么是 Claude Code skill（2026-08-04 已定，MVP 后再确认）

- 构建端需要的正是 Claude Code 的形态：**编排一批 CLI 工具 + 与用户多轮交互闭合闸门 + 判断类生成（persona 起草）**——这就是本项目 12 天里实际发生的事，skill 只是把它从"会话中的默契"固化为"可复用的流程"
- "允许死"：skill 依赖 Claude/DeepSeek/GPU 都可以，因为它只负责生产；产物（archive_dist）不依赖任何活的服务
- 29 个工具已按 person-generic 纪律建成，天然是 skill 的执行层

### 12.2 Skill 结构草案

```
.claude/skills/memorial-archive/
├── SKILL.md              # 主流程：七 Stage 编排 + 闸门交互协议 + 铁律引用
├── references/
│   ├── pipeline.md       # 即本文档（按 Stage 分节供按需加载）
│   ├── gates.md          # 七闸门的页面生成/回贴码解析规程
│   └── voice-training.md # GPU 训练细则（红线/参数/续训）
└── scripts/              # 薄封装：按 stage 串联 tools/ 的调用序列
```

触发形态：`/memorial-archive new <slug>`（建档）、`/memorial-archive ingest`（增量素材）、`/memorial-archive retrain`（语音重训）、`/memorial-archive package`（打包交付）。

### 12.3 泛化缺口清单（skill 化前要还的债）

| 缺口 | 现状 | 动作 |
|---|---|---|
| 机器路径硬编码 | synth_blind_batch/tts_server 默认值指向本机绝对路径（有 CLI 覆盖） | 引入 `people/<slug>/profile.json` + 机器配置（venv/模型/工作区路径），工具读配置 |
| 语音训练脚本在仓库外 | segment/train/parquet 脚本散在 `~\wu-sft\` | 收编进 `tools/voice/`，person-generic 化 |
| 数据源覆盖 | 仅微信（4.1.x 特定） | 微博/朋友圈/email parser（架构已留位：一源一 parser 出 UIF） |
| 语言泛化 | ASR/TTS 链路沪语特定 | 选型矩阵参数化（粤语/川渝…各有对应底座）；普通话人物走 Fun-CosyVoice3 zero-shot 即可（免训练） |
| relationship 模板 | 亲子已验证 | 祖孙/伴侣/挚友的 prompts 参数化（结构已支持） |
| 闸门自动化程度 | 页面生成+回贴码解析全自动，发送/催办靠会话 | skill 内固化"生成→直发→等回贴→apply"循环 |
| TTS/档案站服务化 | ~~start_tts.bat / start_server.bat 手动~~ → **已解决（T14，2026-09-09→10）**：`scripts/start_services.ps1` 五服务编排 + `scripts/register_startup_task.ps1` 登录自启任务 | 尚未 person-generic（路径写死在脚本顶部配置段）；隧道路径未活体验证 |

### 12.4 建议推进顺序

1. **还泛化债**（上表前两行：配置化 + 语音脚本收编）——纯工程，DeepSeek+Codex 流水线
2. **写 SKILL.md v0**：把本文档的 Stage/闸门流程转成 skill 指令（判断类，Claude 写）
3. **第二人物实战验证**：用一个新 slug（哪怕小数据集）从头走一遍 skill，暴露隐藏的 mama 特化
4. 数据源与语言扩展按需求排期

---

*最后更新：2026-08-17。本文档随管道演进维护；重大变更同步 HANDOFF.md。*
