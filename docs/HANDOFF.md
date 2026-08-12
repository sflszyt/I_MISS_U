# 交接文档（HANDOFF）

> 给下一个会话的 Claude（或未来的自己）。最后更新：**2026-08-12 深夜，四层大跃进会话收尾、清理上下文前**。
> 读这份之前先读 `CLAUDE.md`（铁律），再读仓库根的 `task_plan.md` / `progress.md` / `findings.md`（MVP 计划与实时状态）。研究依据在 `docs/research/`。

## ⓪ 当前最热状态（2026-08-12 深夜，先看这里）

**MVP 四层齐头并进后的状态**。详细 phase 看 `task_plan.md`，一句话版：

- **语音层 90%**：模型定稿 **v0.1-full44 epoch14**（`~/wu-sft/v01_full44/exp/mama_v01f44_llm/`；起始幻觉=随机采样所致，重抽即除，用户已确认"干净了"）。`tools/synth_blind_batch.py` 已闭环入库（texts JSONL + 时长 QC 自动重抽 + qc_report）**但未实跑**。下一步：盲听文本清单定稿 → GPU 实跑 → 家人盲听（M1 关口，批次建议见 dialect-tts-maturity.md）
- **数据层 ✅**：`archive_out/data/` 228MB（但见下面敏感记录清理——2024 分片需重建）
- **文字层 90%（工具链全备，剩用户动作）**：digest/candidates/timeline/闸门页/apply 五工具全部闭环入库。**memories/timeline.md 已产**（68 月对账精确）；**gate_page.html（150 卡 192KB，6 条敏感默认剔除）已发用户手机**——用户逐卡 确认/改写/剔除 → 复制回贴码发回 → `python tools/apply_gate_decisions.py --person mama --decisions <存回贴码的文件>` 产 **memories/memories.md（Tier-1）**（支持多轮回贴、action pending 回撤、```json 围栏容忍）。**persona.md 草稿 306 行 46 论断已发用户**（全 Tier-3 + Q1-Q13 待确认，Q1 身份对应最优先）。3d 契约要点：回贴码=对 candidates.jsonl 初始状态的真 delta（dataset hash e17d30763dee 校验；候选文件重生成后 hash 会变，旧回贴码须 --allow-dataset-mismatch 或重发页面）
- **卡通人 90%（4e-集成完成 2026-08-12）**：头像 04 s1001（用户拍板）+ 说话帧 avatar_open.png（Qwen-Image-Edit seed1002，溯源在 avatar_choice.json open_frame 块，**用户可否决重抽**）。build_avatar_page.py 图片双帧模式闭环（Codex ACCEPT 零发现）：音量驱动双帧口型（mouthFrameFor 纯函数 0.04/90ms，阈值经真实语音 RMS 分布验证）+bob 弹动+SVG 回退（person-generic）+data/avatar reconcile。**体验：LAN http://192.168.3.69:8020/avatar.html（8020 常驻）**。剩：4c 合成语音入清单（等盲听）、4d BYOK 对话页（Tier-3 禁陈述提示词）
- **JS 产物 harness 定式（2026-08-12 二次教训固化）**：DOM stub 必须**忠实**——getElementById 对 HTML 中不存在的 id 返回 null（模板 scratchpad/avatar_harness2.js）；过宽的"任意 id 都给元素"stub 会吞掉全部空引用崩溃
- ✅ **敏感记录清理已闭环（2026-08-12）**：`tools/scrub_sensitive.py`（scan/apply/verify 三模式，person-generic）+ `tools/sensitive_patterns.json` 入库（DeepSeek×2 + Codex ACCEPT with fixes + 一行声明 hotfix）；2024-02-09 凭据批 **14 条已从全部派生层删除**（UIF 20923→20909），四下游全量重建，**verify residue=0**。审计清单 `people/mama/normalized/scrub_manifest.jsonl`（无正文）。⚠️ 两个尾巴：①日后重跑 parse_wechat 会重新引入这 14 条，须按 manifest 重新 apply；②删后全量扫描剩 **601 条疑似**（high 273/medium 50/low 278，报告 normalized/sensitive_scan_report.{jsonl,md}），供 3d 闸门页默认剔除 + 人工复核，**未经用户逐条确认前不得自动删**
- **persona 提炼数据边界（用户问过）**：persona/digest/rhythm 只用了**文字消息**；音频仅以计数参与（[语音]76/[通话]74 占位符统计），语音**内容**与视频完全未进 persona。可选增强（未立项）：99 条语音转写反哺口语语域、视频日期反哺记忆卡片
- ✅ **4d BYOK 对话页完成（2026-08-12）——MVP 四层工具链全部闭环**：`prompts/chat_system.zh.md`（六铁律模板）+ `tools/build_chat_context.py`（18074 字 system prompt，含 persona 全文+Tier 纪律+防伪造回退）+ `tools/build_chat_page.py`（chat.html 23KB：BYOK 设置/客户端检索 7 分片/真流式 SSE 纯函数状态机/永久非本人横幅）。Codex 三轮至 ACCEPT；测试三件套 harness（契约 16/SSE 6/e2e 2）沉淀 scratchpad。**体验：LAN http://192.168.3.69:8020/chat.html（⚙ 里填端点+模型+key）**；入口 index.html 已重排"档案体验"区
- **下回合建议顺序**：①用户回贴码到达后 apply_gate_decisions 产 memories.md → 重跑 build_chat_context 让对话页吃上 Tier-1 记忆 ②盲听批次实跑（等文本清单）+ 4c TTS 样本入 avatar 清单 ③601 条敏感疑似人工复核 ④Phase 5 正式打包（并入 persona/memories 人读文件、剔除 review 页、无网机器验收）
- **HTML 工具生成定式（2026-08-12 第三批教训固化）**：①模板一律 `r"""` raw 字符串 + `__X__`+.replace 插值（%格式化撞 CSS 百分号、非 raw 撞 JS \n 两个坑各炸过一次）；②页面 JS 的关键逻辑抽纯函数挂 window 供 harness 直测；③验收层级三级走全：node --check（语法）→ 忠实 stub 全脚本执行（空引用）→ e2e 驱动真实交互流（集成缺陷如假流式/fallback 丢块只有这层能抓）
- **审核工艺升级（2026-08-12 固化）**：凡产出含 JS 的页面，验收标准 = Node stub-DOM **实际执行**断言行为契约（harness 模板存 scratchpad/gate_harness.js，可复用），node --check 只算下限；Codex/查看器对 CJK 文件的"语法错误"类指控一律先 py_compile/json.load/node 实证（累计 3 次误报）
- **环境现场**：ComfyUI 可能还在后台跑（127.0.0.1:8188，起服命令见 progress 08-12 节；显存吃紧就 POST /free）；语音合成用 cosyvoice venv；DeepSeek 必带 `DEEPSEEK_NOTHINK=1`（写法：`$env:DEEPSEEK_NOTHINK="1"; python scripts/deepseek_call.py <spec> <out> 32000`，产物剥围栏+py_compile）
- **移动 review 定式**：HTML <1MB/页大按钮；音频逐条 MP3 直发（聊天渲染器不播内嵌音频）；图片拼图 SendUserFile 直发；选择题用 AskUserQuestion 按钮
- **本会话审核实录速览**（详见 progress.md）：五个工具 DeepSeek×2~4 轮 + Codex 多轮至通过；Codex 一次误报（"语法错误"经 py_compile 实证不存在）——**对 Codex 判定要抽查验证，不盲从**

## 一、项目一句话

为逝去的亲人建可传承数字档案（档案优先于对话，20 年后仍能打开）。首个对象：**mama**（已离开），**上海话为主辅普通话**，素材全数码、全用户（justin）视角。

## 二、已定决策（grill 会话拍板，勿重新讨论）

| 决策 | 结论 |
|---|---|
| 多人架构 | 方案 A：单仓库多人，`people/<slug>/`，工具/prompts 通用 |
| 产品形态 | **混合 C**（构建端 Claude skill + 消费端自包含静态 HTML + 可选 BYOK 对话页）✅ 用户已确认 |
| 语音选型 | Fun-CosyVoice3 主选（含上海话）· VoxCPM2 备选 · GPT-SoVITS 普通话对照；M1 必做跨方言 A/B，**家人盲听是唯一标准**；跨方言掉音色就尊重素材语言 |
| 微信导出（**已定案 2026-08-04**） | 用户微信实测 **4.1.11.24**。chatlog/chatlog-new 不支持 4.1.x（出局）。**采用混合方案**：①文字+图片→ `chatlog-keeper`（MIT，已在 4.1.11 取到 key 并缓存，`wechat`+`images` 命令）；②视频→ **直接复制** `xwechat_files/<wxid>/msg/video/**/*.mp4`（4.1 视频是明文 mp4，实测 387 个）；③语音→ **自研提取器**（SILK blob 在加密消息库内，需先探测表/字段，DeepSeek 写 Codex 审，pilk/silk→wav）。详见 `docs/research/wechat-media-extraction.md`。备选交叉验证：`LifeArchiveProject/WeChatDataAnalysis`（无协议、DMCA靶心，用完即弃）。chatlog-keeper 源码在 `installers/chatlog-keeper-0.2.0/`，已建 .venv 装好依赖 |
| 数据源架构 | 源适配器 → UIF 统一中间格式（`schema/uif.schema.json`）→ 下游只消费 UIF |
| 三条自我保护约束 | 已入 CLAUDE.md 铁律（Tier 分级+人工闸门 / 保留完整性 / 沉浸度克制） |
| 硬件 | RTX 4090 24GB + i9-14900KF + 64GB RAM，全本地无约束 |

## 三、Phase 1 已交付（全部经 DeepSeek 写 + Codex 三轮审核 ACCEPT）

- `CLAUDE.md` 三大铁律 · 仓库骨架 · `.gitignore`（people/ 隔离）
- `schema/uif.schema.json` + README（4 类记录：message/post/email/media_item；信封含 viewpoint/tier/provenance）
- `docs/research/wechat-export.md` · `docs/research/form-factor.md`
- `tools/ingest_media.py`（媒体清点+EXIF+报告）· `tools/silk_decode.py`（备用）· `tools/backup_check.py`（备份审计）
- `scripts/deepseek_call.py`（流式调用器，唯一可靠通道）

## 四、下一步（按序）

**微信导出与媒体提取的 RE 已全部跑通验证**（2026-08-05），完整配方见 `docs/research/wechat-media-extraction.md` 第三点五节。关键状态：
- 全量文字已导出 → `people/mama/raw/wechat/export_full/wechat_messages.json`（75万条；妈妈 laurawang001 6968 条）
- 语音 84/85、视频 13/25 已验证可提取（真实 60s 语音样本已解码到 `~/ck-decrypted/sample_mama_voice.wav`）
- 解密环境：key 在 `~/ck-data/secrets/`，db 镜像(已删shm)在 `~/ck-mirror`，明文库在 `~/ck-decrypted`，pysilk-mod 已装进 venv

**待建（DeepSeek 写 + Codex 审）**：
1. ~~`tools/extract_wechat_voice.py`（#11）~~ ✅ **已完成（2026-08-05，DeepSeek 两轮 + Codex 两轮审核 ACCEPT）**：实跑 5 会话共提取 **125 条 WAV（妈妈 99 条，总时长约 55 分钟）**，仅 1 条缺 blob（2021-12-22 一条，VoiceInfo 无行），0 解码失败 0 警告。产物：`processed/wechat_voice/<room>/` + `normalized/wechat_voice_manifest.jsonl`（UIF media_item，schema 校验通过，含 svr_id/chat_room/create_time_epoch/sender_wxid 关联键）+ `wechat_voice_report.md`。**运行须用 chatlog-keeper venv 的 python**（pysilk 在那里）：`installers\chatlog-keeper-0.2.0\.venv\Scripts\python.exe tools\extract_wechat_voice.py --person mama --db-dir ~\ck-decrypted`。原探测记录：sender 归属 = `Msg.real_sender_id` → 同 db `Name2Id` 表 rowid → wxid；Msg_<md5(room)> 分片散布在 message_0~6；VoiceInfo 在 media_0（3151 行全账号）+ media_1（1 行），列序 chat_name_id/create_time/local_id/svr_id/voice_data/data_index
2. ~~`tools/collect_wechat_video.py`（#12）~~ ✅ **已完成（2026-08-05，DeepSeek 三轮 + Codex 两轮 ACCEPT + 热修复确认）**：5 会话 540 条视频消息，**215 个 mp4 在本地并已采集入 `raw/wechat/video/<年-月>/`（1.91 GB，妈妈发的 9 个）**，其余 325 个未下载/CDN 过期。manifest `normalized/wechat_video_manifest.jsonl`（UIF media_item，schema 全过）。要点：raw 只新增不变量用 staging+os.link 硬链接原子落盘实现；微信源 mp4 带 ReadOnly 属性，staging 清理需 _force_unlink（chmod 后删）。运行：`python tools\collect_wechat_video.py --person mama --db-dir ~\ck-decrypted --video-dir ~\xwechat_files`
3. ~~`tools/parse_wechat.py`（#13）~~ ✅ **已完成（2026-08-05，DeepSeek 两轮 + Codex 三轮审核 ACCEPT）**：已产出 `people/mama/normalized/wechat_messages.uif.jsonl`（20923 条，妈妈 9386 条，jsonschema 全量校验通过，report 见同目录）。配置在 `people/mama/wechat_parse_config.json`（gitignore 内，重建时需按下述规格重写）。媒体 ref 由 #11/#12 后续按 chat_room+ts+sender_wxid 关联合并。**筛选规格（2026-08-05 核实后扩充，勿退回旧版）**：①一对一会话 `chat_room=laurawang001` 整段收录（6968 条，妈妈发 5048）；②**群聊补抓**——妈妈在 4 个群发过 4338 条（全部文字）：家庭群 `17586423176@chatroom`（她 3622/群 6981，成员仅她+justin+爸爸）、`25722082802@chatroom`（430）、`5030199976@chatroom`（147）、`3758229935@chatroom`（139），这些群的完整对话（含他人发言作为前后文）一并收录；③UIF 中 `chat_room` 区分语境（私聊/家庭群/亲友群），他人消息 sender 必须清晰标注，不得与妈妈本人的话混入 persona 语料
4. ~~**M0 收尾**~~ **备份关口已由用户明确豁免（2026-08-05："不要去管备份了，假设资料很安全"）**——backup_check/双备份不再阻塞后续里程碑，勿再催办。照片/家庭录像清点（ingest_media）仍待素材导入 raw 后进行
   - **新立项（2026-08-05，用户拍板）——数据源扩展**：
     - **微博（#14）**：两部分素材——①她自己微博账号的全部内容；②**用户（justin）微博下她的评论/回复**。适配器 `tools/parse_weibo.py` 输出 UIF post 记录（schema 已支持 author/comments）。前置：素材获取方式待研究（她的账号官方导出是否可行/网页存档抓取；justin 自己的微博可官方导出后筛她的评论），先由用户收集 raw → `people/mama/raw/weibo/`
     - **微信朋友圈（#15）**：她的朋友圈（含 justin 可见的点赞/评论互动）。适配器 `tools/parse_moments.py` 输出 UIF post 记录（source=wechat_moments）。前置：朋友圈数据在手机端，导出方式待研究（微信自带"个人信息导出"里朋友圈部分/手机备份工具），先由用户收集 raw → `people/mama/raw/moments/`
     - 两者共同点：先解决**素材到手**，adapter 都是纯解析（模式同 #13，DeepSeek 写 + Codex 审）
5. **M1 语音验证（进行中，2026-08-05 启动）**：
   - ✅ 素材普查：妈妈 99 条语音中 61 条 ≥15s（爱发 60s 长语音），参考素材充足
   - ✅ 候选试听：5 条最连续长语音切 18s 窗口发用户试听，**用户确认"音质可以"**（SILK 窄带可作克隆基底）
   - ✅ 参考固化：`people/mama/voice/reference/`（5 条 full + 5 条 clip18 + reference_manifest.json 含溯源/窗口偏移/sha256）
   - ✅ 环境搭建完成（2026-08-05）：CosyVoice 源码在 `C:\Users\justin\CosyVoice`，py3.10 venv 在 `C:\Users\justin\venvs\cosyvoice`（torch 2.3.1+cu121，cuda 可用），模型在 `C:\Users\justin\CosyVoice-models\Fun-CosyVoice3-0.5B`。装机坑：setuptools<81 约束修 whisper 构建、wget 需 --no-build-isolation 补装、prompt 传**文件路径**别传 load_wav 张量。冒烟脚本 `scratchpad/clone_smoke.py`（带参=zero-shot prompt_text 文件）。单句合成约 4-5s
   - ✅ 首轮 A/B（2026-08-05）：**用户判定音色"非常像妈妈"（关键 go 信号）**，但 instruct2 模式**发音不够地道**。已跑 zero-shot 版（prompt_text 用 ASR 草稿保守清理，非用户校对定稿）做对比，待用户听 zero-shot 是否改善发音
   - ✅ 二次研究（2026-08-05，workflow）：发音不地道判定为**工程问题非模型天花板**，最高杠杆三步=校对转写/吴语本字/换病中参考；完整调优指南与 VoxCPM2 备选触发条件见 `docs/research/cosyvoice3-deploy.md` 第五节
   - ✅ 5 条参考内容 ASR 识别（判健康期）：ref01(2022-07 设计花坛庭院,最日常) / ref02(聊买房) / ref03(2020-12 验血病中,当前主参考待换) / ref04(聊买房) / ref05(2021-11 失眠吃药)
   - ✅ 参考定稿：**ref01**（2022-07 健康期日常，用户从 5 条盲选，音色"非常像"）；转写已由用户校对（`voice/reference/ref01_transcript.txt`，上海话本字）
   - ✅ zero-shot 正路跑通（格式坑已解：源码 `llm.py:585` 确认 CosyVoice3 需 `指令<|endofprompt|>转写`；f0 崩溃因 tts_text split 出极短分句→改连贯长句）。但**用户判定 zero-shot 上海话发音仍不地道**，instruct2 也不地道 → CosyVoice3 上海话发音走不通
   - **决定（2026-08-07 用户）**：上海话**暂时保留 instruct2 版作为基线**（音色对、发音将就），存档于 `people/mama/voice/baseline_instruct2_20260807/`（配置见该目录 README + deploy 文档第六节）。音色链路已完全稳（最难部分成了）
   - ✅ **方言 TTS 深挖完成（08-07 首轮 + 08-08 补跑，报告 `docs/research/dialect-tts-maturity.md`）**。决定性发现：**CosyVoice2-Wu 全套权重已公开**（HF `ASLP-lab/WenetSpeech-Wu-Speech-Generation`，Apache-2.0 免申请，5 变体，SS 最佳 IMOS≈4.0，原生 zero-shot 克隆 + `<|wuyu|>` 标签，参考按 16kHz 加载窄带不吃亏）。路线修订：**B0**（Wu 底座 zero-shot，零训练）> B1（+她 55 分钟 AP-BWE 增强后本地 SFT，4090 可跑）> **D**（新增：沪语 TTS→Seed-VC timbre-only 换她音色，两段式绕开克隆×方言死结）> C（CosyVoice3 拼音标注只是字音补丁，音系天花板被本机 tokenizer 代码实锤）> A（退普通话，仅对照）。**工程红线：Wu 权重是 CosyVoice2 栈的 llm.pt，与 Fun-CosyVoice3 不通用**
   - ✅ B0 已跑（08-08，Wu 权重 5 变体全下载至 `C:\Users\justin\CosyVoice-models\WenetSpeech-Wu-Speech-Generation\`）：B0 zero-shot vs instruct2 基线 A/B 样本、instruct-prosody 韵律探针、语速探针（1.08/1.15 档）均已生成（存档 `~/wu-sft/v0/listen_archive/`）
   - ✅ **B1 v0 SFT 端到端跑通（08-09 深夜，重启电脑后本会话恢复）**：Wu ASR（Understanding whisper-medium + wenet attention_rescoring）转写妈妈 45 条 ≤30s 语音（8.2 分钟）→ embedding/speech_token → parquet → 4090 全量 SFT LLM 15 epoch（约 14 分钟，最终 train-cv loss 0.092/acc 0.989）。工作区已从临时 scratchpad 迁至 **`C:\Users\justin\wu-sft\v0\`**（数据/脚本/配置/启动脚本 run_train.sh/checkpoints epoch_0..14 约 30GB）
   - 训练三连坑（已修，勿再踩）：①backward OOM = 白天推理残留显存，重启即愈；②GBK 编码的 ds_stub 废稿经 PYTHONPATH 遮蔽 venv 内 ASCII 版 stub → SyntaxError（正版 stub 已装在 cosyvoice venv site-packages，勿加 PYTHONPATH）；③cv 阶段 `@torch.inference_mode()` 与 Windows gloo DDP `_sync_buffers` 冲突 → 已改 `@torch.no_grad()`（executor.py:146）。CosyVoice 未提交补丁两处：llm.py 梯度检查点（non-reentrant + use_cache=False）、executor.py cv 装饰器
   - ⚠️ **分工违规记录（08-09 用户查账指出）**：08-07~09 所有代码（探针/SFT 管线/源码补丁）均 Claude 直写，未走 DeepSeek/Codex，违反铁律 1。已送 Codex 补审，判定 **REJECT**：45 条转写中 **14 条含 U+FFFD 坏字符（26 处）**属不可接受监督噪声；extract_speech_token_cpu.py 对 >30s 音频静默空 token（本批未中招但属管线隐患）；cv==train 仅算冒烟。两处源码补丁 ACCEPT。**v0 checkpoints 只算管线冒烟产物，不作验收**
   - **下一步（按序）**：①14 条脏转写处理——生成 HTML 试听页供用户校对（或先剔除出 31 条干净版）→ 重建 parquet → v0.1 重训（DeepSeek 写清洗/重建脚本 + Codex 审，恢复分工）；②DeepSeek 修管线 blocker（空 token fail-fast、parquet 命名、accum_grad 奇数批 flush）；③v0/v0.1 checkpoint 逐 epoch 合成同文本样本（重点 epoch 2-5 防过拟合）→ 与 B0 zero-shot、instruct2 基线三方 A/B → 家人盲听（批次建议见 dialect-tts-maturity.md）
   - ASR 草稿环境：`C:\Users\justin\venvs\asr`（funasr+SenseVoiceSmall，CPU）；3号切片草稿在 `scratchpad/asr_draft_clip18.txt`
   - 环境事实：ffmpeg 不在 PATH；pysilk/numpy 在 chatlog-keeper venv；磁盘余 1.1TB

**注意 pysilk.decode 要传完整含 0x02 头的 blob（剥离会报 Not a valid silk_data）。**

## 五、工程注意事项（血泪教训，别再踩）

- **DeepSeek 调用**：只用 `python scripts/deepseek_call.py <spec> <out> 32000`。非流式会被网络掐断；<32k tokens 会被推理烧光正文；生成后 strip markdown 围栏 + `py_compile`；`scripts/deepseek.ps1` 勿用于含中文的文件（PS 5.1 响应解码乱码）
- **DEEPSEEK_API_KEY** 在用户级环境变量（Bash 工具进程可能不继承，可作第 4 参数传入）。⚠️ key 曾在对话明文出现，已提醒用户轮换
- **pilk**（silk_decode 依赖）在 Python 3.13 无 wheel——不阻塞（主路径 chatlog 直出 MP3），真需要时装 VS Build Tools 或用 py3.11
- **控制台中文乱码**是 GBK 代码页显示问题，文件都是 UTF-8，勿在脚本里强改 stdout 编码（Codex 建议保持现状）
- 审核循环战绩参考：Codex 第一轮抓过 3 个 blocker（--person 路径注入写 raw/），修复模式是 slug 正则 + resolve() 锚定校验——新工具写 spec 时直接把这两条要求写进去

## 六、用户待办

- [ ] 今晚：chatlog 导出微信（先冷备份微信数据目录！版本 ≥4.0.3.36 需降级或 wx_key 取密钥，见 wechat-export.md 第五节）
- [ ] DeepSeek API key 轮换
- [ ] 准备两个备份目标（一个异地，如 NAS/网盘加密包/亲戚家硬盘）
