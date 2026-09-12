# MVP 生产计划（纯微信数据）· 2026-08-09 立项

> 用户指令："修复deepseek后，全力先生产mvp（纯基于微信数据的数据层/语音层/文字层/虚拟桌面卡通人）"
> 铁律：实质代码 DeepSeek 写 + Codex 审；Claude 只统筹与一次性探针（须声明）。人工闸门与 Tier 分级不因 MVP 而豁免。

## 目标（MVP 定义）

只用已到手的微信素材（UIF 20923 条 + 语音 99 条 + 视频 215 个），产出一个能打开、能听、能看、能聊的最小档案：
- **数据层**：档案数据包（开放格式 JSON，消费端可直接 fetch）
- **语音层**：Wu-SFT v0.1 干净重训 + 批量合成能力
- **文字层**：persona.md + rhythm.json + timeline.md + 记忆卡片（全部 Tier-2 标注，升级须用户确认）
- **卡通人**：自包含 HTML 桌面卡通形象（不做真人脸），音量驱动口型，可播她的语音，BYOK 对话可选

## Phases

### Phase 0：修复 DeepSeek 管道 — status: complete
- 根因实测：v4-flash 推理链烧光 token（60k 中 59.1k）；`thinking:{"type":"disabled"}` 有效，`reasoning_effort` 无效
- 修复：deepseek_call.py 支持 DEEPSEEK_NOTHINK=1 / DEEPSEEK_MODEL 环境变量（Claude 自举补丁，已声明）
- 验证：关推理后 13-31s 稳定产出 5-20KB 完整文件，已连续 4 次成功

### Phase 1：语音层 — status: complete（2026-08-16 v0.2 e14 定稿现役；M1 以用户本人盲听 v2 于 08-21 关口；下列 1a-1f 为历史记录）
- ✅ 1a 校对页发用户（45 条全量、18 条标红；DeepSeek 两轮 + Codex 两轮 ACCEPT；工具存 ~/wu-sft/v0/scripts/make_correction_html_final.py）→ **等用户回贴 corrections.jsonl**
- ✅ 1b 干净数据先行重训 v0.1-clean27（27 条＝45−18，非原计划 31；epoch_0..14 存 ~/wu-sft/v01_clean27/exp/mama_v01c27_llm/，最终 loss 0.072/acc 0.992）
- ✅ 1d 三方试听页已发用户（epochs 2/4/8/14 × 3 文本；synth_epoch_samples + make_listen_page 均 DeepSeek 写 + Codex ACCEPT with fixes）→ **等用户 epoch 排序反馈**
- ✅ 1d 用户反馈（2026-08-11）：**epoch14 总体最好**，但头尾有小部分被切。探针实锤（wav 第 0ms 即 RMS 0.05-0.07，无起始静音；文本3 末 50ms 仍 0.067）：合成/导出侧无首尾缓冲
- ✅ 1c 头尾截断已修：synth_epoch_samples.py 加 --pad-ms 300/--exp-tag（DeepSeek 两轮 + Codex ACCEPT，存 v01_full44/），9 条样本探针验证首尾全静音；空 token/embedding 以探针代偿（44/44 全过）
- ✅ 1e 满血重训完成（2026-08-11）：v01_full44 44 条 15 epochs，final loss 0.095/acc 0.986（exp/mama_v01f44_llm）。A/B 终选页 ab_final.html 已上局域网入口（full44 e8/e14 vs clean27 e14 对照，全部带 pad）。坑：PS Set-Content 写 utt2spk 带 BOM 崩 extract_embedding（GBK 读），改 awk 无 BOM
- ✅ 1e 用户定稿（2026-08-12）：**盲听候选 = v01_full44 epoch14**。"开头 1s 奇怪的话"已探针实锤：300ms 垫为纯静音（0.000），怪话是模型随机起始幻觉（02 号重抽后 8.2s→5.4s 消失），用户确认重抽版"干净了"
- 🔶 1f 批量合成脚本：tools/synth_blind_batch.py 已闭环入库（54c2668，DeepSeek×2 + Codex ACCEPT with fixes 已修）——texts JSONL + 时长 QC 自动重抽 + 起始能量标记 + qc_report.jsonl；**待盲听文本清单定稿后 GPU 实跑验证**（批次建议见 dialect-tts-maturity.md）
- ✅ 1f 实跑收官（2026-08-12）：盲听批 10/10 全绿（文本取自她真实消息 held-out）；盲听页工具 make_blind_page 闭环（float32 编码事故用户耳测抓出，修复+解码回读自检入 findings）
- ✅ **盲听预演（用户本人）**：合成 3/10 骗过（两条 5 分），真声 4/4 全认出——音色达标实锤；用户定性"音色很像，上海话发音还是很奇怪"
- **发音攻坚判定链（2026-08-12 深夜，全部用户耳测实锤）**：①本字改写 A/B → 一样怪（文本分布错位非主因）；②路线 D 探针（Wu-SFT 底座 × 用户原生音 prompt × 本字长句 97-123 字）→ **"拉胯的不行"**；③SS 变体查证**未公开发布**（仓库仅 CPT/SFT/instruct×2，论文指标无权重）→ **探针已是公开最强变体，CosyVoice2-Wu 公开权重的长句音系天花板实锤，路线 D 关闭**（观察项：吴语生态 2026-02 才起步，留意后续更强开源沪语 TTS）
- ✅ **v0.2 定稿（2026-08-16 用户裁决："有比v0.1好点，v0.2 e14"）**：**现役模型切换 → mama_v02f160_llm epoch14（双语域：<|wuyu|>=沪语 / 裸文本=沪普）**；v01f44 e14 退役。CV loss 0.195/acc 0.964（中途误杀事故从 e6 续训恢复，见 progress）；--lang 开关 Codex 补审 ACCEPT（五项全过）。**盲听 v2 物料就绪**：blind_v2.html 12 条（v0.2 e14 合成 8 句训练集外文本 + pilot 真声 4）+ key 分离，已发用户 → **家人盲听已取消（2026-08-21 用户裁决"移除这项"）：M1 以用户本人盲听 v2（8 条骗过 7，08-16）为最终依据关闭，物料保留不催办**。原始记录：校对收口——用户回贴 p3=12/p4=1/p5=1 共 14 处修正，p1/p2/p6/p7/p8 用户裁决整页通过（"总体目测都挺准确的，直接通过"）。数据合并 prep_v02_data.py（Claude 声明直写，纯数据拼装）：**160 条 = v01 44 + 新 116，47.2 分钟，零 utt 冲突、零超 30s、空文本零**。特征三件套复用 CosyVoice tools（parquet 用 v0/make_parquet_single.py 绕 Windows spawn 坑，PYTHONUTF8=1 防 GBK）→ parquet 127.9MB → run_train.sh 启动 mama_v02f160_llm 15 epochs。**训后待办：epoch 试听 A/B（对照 v01f44 e14）→ 家人盲听 M1**。诚实预期：改善渐进非质变；长句地道度受底座天花板压制
- **合成的 MVP 定位（依铁律"尊重素材语言"重校）**：短句场景用（卡通人问候/对话页短回复——v0.1 已可骗过），长内容播她真声（检索匹配）；**47 分钟全量转写本身是档案资产**（不依赖 TTS 成败：转写进 bundle 可检索、语音层唯一 Tier-2 文本化）
- 🔶 **普通话备选线（2026-08-13 用户立项）**：Fun-CosyVoice3 × ref01 零训练——她的音色说普通话（模型主场，官方 CER 1.45%）。首批 13 条已发用户（盲听同 10 句 instruct2 全跑 + 3 条 zero-shot 模式对照，300ms 垫+MP3，存 wu-sft/mandarin_a/probe1）→ **等用户三判：跨语掉音色否/自然度/模式取舍**。若过关：作为长句场景的可用合成兜底（沪语线专攻短句），Tier-3 标注纪律不变（合成音明示非本人口音）
- 完成标准：有一版用户认可"可进盲听"的模型（✅ full44 e14）+ 批量合成脚本（✅ 1f）；v0.2 为增强线

### Phase 2：数据层 — status: complete（2026-08-10 凌晨，Codex ACCEPT，已提交 6fe8275）
- ✅ tools/build_data_bundle.py（DeepSeek×4 轮 + Codex×2 轮）：archive_out/data/ = 7 年度分片(20923) + media_index + timeline(68月) + meta + 语音125/本人视频9 拷贝，228MB，幂等 + 全量对账 + file_ref 子树锚定

### Phase 3：文字层 — status: complete（2026-08-16 收官：memories.md 124 条 Tier-1、persona Q1-Q13 08-13 全收口、3c-3f 全 ✅）
- **设计基线（2026-08-12 用户重申）**：项目未来泛化到一切人物（父母/配偶/子女/朋友/anyone），MVP 基于 mama。**所有 Phase 3 工具必须 person-generic**：吃 `--person <slug>` + UIF，人物/关系特定内容全部进 `people/<slug>/persona/relationship.json` 配置与 prompts/ 参数化模板，工具代码零硬编码人名/关系
- ✅ 3a tools/build_rhythm.py（DeepSeek×3 轮 + Codex×3 轮 ACCEPT）：persona/rhythm.json + archive_out/data/rhythm.json——9386 条 subject 消息的长度/时段/连发/回复延迟/标点/口头禅23条/表情/语音习惯，精确 skip 计数
- ✅ 3b-① tools/extract_persona_digest.py 闭环入库（1afd573，DeepSeek×3 + Codex 三轮 + sender hotfix）；实跑产出 206KB persona_digest.json（分年样本/14 对话窗口/9 组关键词，全带 record_id）
- ✅ 3b-② persona.md 草稿完成（2026-08-12 深夜，Claude 子代理起草）：46 条论断 T01-T46 逐条带 record_id 证据 + 待确认清单 Q1-Q13，含"缺点与冲突面"9 条（铁律 2 达标），全文 Tier-3 标注 → ~~等用户逐条确认~~ **Q1 于 08-12 晚确认、Q2-Q13 于 08-13 会话全收口（见 3b-③/progress）**
- ✅ **敏感记录处理 — complete（2026-08-12，DeepSeek×2 + Codex REJECT→ACCEPT with fixes + Claude 声明 hotfix 一行）**：2024-02-09 凭据交接批（账号密码/记账/抗癌药记录）从**全部派生层删除**——normalized UIF、archive_out/data 年度分片、memories/candidates.jsonl、persona_digest.json；**raw/ 保留不动**（铁律 1 只读且永不出机）。实现（DeepSeek 写 + Codex 审）：清理工具走"凭据模式扫描 + 用户指认 record_id 清单"双通道 → 删除后重跑 bundle/candidates/digest 保证无残留 → 闸门页对疑似敏感候选默认剔除。**此步骤已泛化为任何人物管线的标准关卡**（记忆 sensitive-data-cleanup.md）
  - 侦察实锤（2026-08-12）：2024-02-09 共 **14 条**（13 subject + 1 viewpoint_owner，text 7/link 4/image 3）；扩散：messages_2024.json 14/14、persona_digest 4/14、candidates.jsonl 4/14、media_index 0（图片未进 bundle）、persona.md 0（仅 12 位前缀引用+行为描述，无内容复制）。4 条长文本（827/806/5790/4167 字）命中 pwd/acct/bank/money/med 模式为凭据主体
  - **删除清单定稿：全部 14 条**（整批交接会话；链接 URL 可能含文档 token 一并删；派生层删除可从 raw 重建，零不可恢复风险）
  - 工具设计：tools/scrub_sensitive.py（person-generic）三模式 scan（模式扫描出报告）/apply（record_id 清单删除+manifest 不含正文）/verify（全派生层 record_id 残留检查）；模式配置 tools/sensitive_patterns.json 外置；⚠️ 若日后重跑 parse_wechat 会重新引入，须按 manifest 重新 apply
  - ✅ 执行完毕（2026-08-12）：apply 删 14 条（UIF 20923→20909，manifest 落盘不含正文）→ 四下游全量重建（bundle messages=20909/227.76MB、rhythm、digest 204.7KB、candidates 150 条配额 61/23/22/22/22 不变）→ **verify ids=14 files=32 residue=0**
  - 疑似队列存量：删除后全量 scan 601 条疑似（high 273/medium 50/low 278）→ people/mama/normalized/sensitive_scan_report.{jsonl,md}，供 3d 闸门页"疑似敏感默认剔除"与后续人工复核
  - Codex 审核实录：v1 REJECT 9 条中 2 条"语法错误"BLOCKER 系误报（py_compile+json.load 双实证；Codex 读带 CJK 文件误判，第二次发生）；7 条真实发现回炉 DeepSeek v2 全修；终审 ACCEPT with fixes 仅剩 ids 文件 .lower() 一行（Claude 声明 hotfix）
- ✅ 3f 对话页知识源升级（2026-08-16 晚，DeepSeek×4 + Codex 批审 ACCEPT with fixes 一行 hotfix）：build_chat_context --memories-mode index（prompt 89.5k→23.9k 字符）+ 新工具 build_chat_knowledge.py（memories.json 124 Tier-1 / transcripts.json 108 Tier-2 检索源）+ build_chat_page 检索三源化（retrieveKnowledge 纯函数、Tier-1 优先带标签、404 容错）；harness 四套 20/20+16/16+6/6+2/2 全绿；转写进档案检索层=原任务④一并落地
- ✅ 3e 状态保留合并 + 记忆卡 corrected 升级（2026-08-16 晚）：tools/merge_candidate_state.py 闭环入库（DeepSeek 一发 + Codex ACCEPT with fixes 两处声明 hotfix + 十场景冒烟，702085e）；voice_transcripts 99/99 全 corrected（draft 归零）→ 重挖+合并（124/26 裁决零丢失，38 卡内容升级）→ memories.md 重生成
- ✅ 3c 两件全完成：①tools/extract_memory_candidates.py 闭环入库（7f34bb4，150 条候选）；②tools/render_timeline.py 闭环入库（2026-08-12，DeepSeek×3 + Codex REJECT→ACCEPT：gap 锚定月修正/ASCII 路径/死代码清理，合成缺月用例验证）→ **memories/timeline.md 已产**（68 月无缺口，头部对账 20909/9373 与清理后 UIF 精确一致）
- ✅ 3d 闸门页+apply 双工具闭环入库（2026-08-12，Codex 三轮 REJECT→REJECT→**ACCEPT 零发现**）：tools/make_gate_page.py（150 卡 192KB 自包含移动页，敏感可见文本预标记 6 条默认剔除，localStorage 草稿，回贴码 delta 契约）+ tools/apply_gate_decisions.py（多文件 later-wins 合并、```json 围栏容忍、action confirm/reject/pending 三态、敏感复检 confirmed_flagged、幂等重生成 memories.md Tier-1）。**审核升级：Codex 与 Claude 双方均用 Node stub-DOM 实际执行页面 JS 验证契约七场景矩阵**（工具 harness 存 scratchpad/gate_harness.js，抓到 v2 的"未动卡片全量导出"High 实锤）→ **gate_page.html 已发用户手机，等回贴码** → apply 后产 memories/memories.md（Tier-1）
- 完成标准：persona/ 与 memories/ 目录齐备，Tier 标注完整，闸门页可用（✅ 全部达成：memories.md 124 条 Tier-1 08-13 产出、08-16 校对升级重生成；persona Q1-Q13 08-13 收口）

### Phase 4：卡通人（消费端）— status: complete（口型架构后续被 Phase 7 全面取代，见下）
- ✅ **4e-集成完成（2026-08-12，DeepSeek×2 + Codex REJECT→ACCEPT 零发现 + 两处声明 hotfix）**：build_avatar_page.py 图片头像模式——`persona/avatar.png`（静息帧=定稿笑容）+ `persona/avatar_open.png`（说话帧，Qwen-Image-Edit seed1002 生成，1001 背景跑偏/1003 眼翻白已淘汰，溯源入 avatar_choice.json open_frame 块）按音量双帧切换（纯函数 mouthFrameFor：0.04 阈值经 Codex 用 125 条真实语音 RMS 分布验证 + 90ms 帧保持 + 假驱动交替）+ bob 弹动；资产 reconcile 进 archive_out/data/avatar/（陈旧自动清理）；无头像人物回退 SVG（person-generic 保持）；预览页 Pillow 降采样内嵌 0.26MB
  - 审核实录：Codex R1 REJECT 抓 #avatar 契约破坏（图片模式 TypeError，我方 harness stub 过宽漏过）+ 陈旧资产不清理；R2 双方各自用"忠实 stub"（缺失 id 返回 null + rAF/play/pause 派发）执行双页全脚本干净 → ACCEPT。hotfix×2（声明）：JS 常量未定义补两行、Python 层死常量三行删除
  - 验证方式：LAN http://192.168.3.69:8020/avatar.html（8020 服务在跑）；两帧图已发用户手机（用户可否决说话帧，重抽即换）
- ✅ tools/build_avatar_page.py（DeepSeek×5 轮 + Codex×3 轮）：archive_out/avatar.html（37KB）+ start_server.bat/.sh——SVG 卡通（圆脸眨眼腮红，非真人脸）+ AnalyserNode 音量驱动嘴型 + 600ms 静音伪驱动 fallback + 125 条原声播放列表（data/media/voice 相对路径）+ 续播守卫
- ⏸ 4c 合成语音入清单——搁置：被 :8022 tts_server 动态合成取代（chat/companion 语音条实时生成），静态 TTS 样本未入 data/media/tts/；离线档案若需合成样本再立项
- ✅ **4d BYOK 对话页完成（2026-08-12，DeepSeek×5 轮 + Codex 两轮 REJECT→ACCEPT + 3 处声明 hotfix）**：三件套——`prompts/chat_system.zh.md`（person-generic 提示词模板，Claude 写：六条铁律=只说档案有的/记不清就说/Tier 标注纪律/保留缺点/不假装真人/克制依赖）+ `tools/build_chat_context.py`（模板渲染+rhythm 蒸馏+persona 全文含 Tier-3 声明嵌入+缺 memories 时防伪造回退文案+占位符漂移守卫，18074 字 system prompt）+ `tools/build_chat_page.py`（archive_out/chat.html 23KB 自包含：BYOK 设置抽屉 localStorage、客户端检索 7 分片 CJK 2-gram 打分 top6 带日期 Tier-2 标注、真流式 SSE 状态机 sseCreate/Feed/Finish 纯函数、非流式 fallback、AbortController、永久"非本人"横幅、消息 textContent 零 XSS）
  - 审核历程：v1 esc 未定义 → v2 %格式化撞 CSS 百分号 → v3 非 raw 模板 \n 变真换行（JS 语法错）+ IIFE 罩住纯函数（两处声明 hotfix：r 前缀+window 导出）→ Codex R1 REJECT 5 条全实锤（分片 URL 双 .json 后缀检索全死/resp.text() 假流式/raw guard 弱/气泡头像 onerror 删整泡/context 固定输入绕守卫）→ v4 修 → Codex R2 仍 REJECT（EOF 尾缓冲丢最后 delta，Node 仿真实证）→ v5 SSE 纯函数状态机 → Codex R3 抓 v5 新回归（fallback 只存首 chunk）→ 声明 hotfix 累积 + **e2e harness**（捕获事件处理器+脚本化 reader 驱动真实 send 流，双场景过）→ **ACCEPT**
  - 测试资产沉淀（scratchpad 可复用）：chat_harness（16 纯函数契约）、sse_harness（6 SSE 场景）、e2e_harness（真实 send 流驱动）
  - 入口页 index.html 已加"档案体验"区（avatar+chat 卡片，直写声明）；LAN http://192.168.3.69:8020/chat.html
- ✅ 4e 形象升级全链路完成：照片→卡通生成链（gen_avatar_candidates.py + make_contact_sheet.py）→ 用户终选 04 s1001 → 双帧说话动画集成（见上）
- 用户验证方式：运行 archive_out/start_server.bat → 浏览器开 http://localhost:8020/avatar.html

### Phase R：移动 review 体验（2026-08-10 用户提出）— status: complete（R1/R2 Codex ACCEPT，R3 已执行）
- 背景：用户手机端 Claude 远控家里电脑，现有 review 回收通道不友好（校对页打字+长 JSONL 回贴；avatar 需电脑 localhost）
- ✅ R1 build_avatar_page.py 增 --preview N/--preview-bitrate/--preview-max-mb（DeepSeek 4 轮 + Codex 3 轮至 ACCEPT）：archive_out/avatar_preview.html（0.18MB，5 条本人语音内嵌，时序 2020-12→2024-01）
- ✅ R2 make_correction_page.py v2（DeepSeek 3 轮 + Codex 2 轮 ACCEPT）：回贴码只含改动项 + meta 带 page/source_dataset(45条全集hash)/source_total + 44px 剔除大按钮 + 底部固定操作条 + 中文化；旧 localStorage 草稿兼容（当页 dataset 不变：1页 49c37dea7933 / 2页 8320cfbc70c0；全集 5af37542bea2）
- ✅ R3 试听 epoch 排序改 AskUserQuestion 聊天按钮收集
- 原则固化：今后所有 review 页移动优先（<1MB/页、大按钮、回贴码最短化、能用聊天按钮就不让用户打字）
- 回贴码还原规则（1e 执行时用）：以 source_dataset=5af37542bea2 校验全集版本；每 utt 三态：不出现=保留原转写 / {"utt","text"}=改文 / {"utt","drop":true}=剔除
- **R4 实测修正（2026-08-10 用户实测）**：手机聊天 HTML 渲染器播不了内嵌音频（校对页无音频、avatar 预览播放无反应）→ 音频改逐条 MP3 直发（校对 18 条按页编号 + 试听 12 条按文本×epoch 已发）；HTML 页降级为无声编辑面；avatar 口型 demo 只能电脑看，待办：无声演示模式或录屏（见记忆 audio-review-via-html）

### Phase 5：合流交付 — status: complete（2026-08-16 深夜，MVP 交付）
- ✅ tools/build_archive.py（DeepSeek×3 轮 + Codex ACCEPT with fixes 五项全修 + 专项验收 11/11）：archive_out → **archive_dist（161 文件 / 241.7MB 自包含）**——白名单拷贝（review 页全剔）+ text/ 文字层四件 + 生成干净 index/README/启动脚本 + 六项一致性硬校验（离线红线三正则：src/href+srcset+css url）+ sha256 manifest + --verify/--dry-run（严格零写盘）+ 幂等 reconcile
- 完成标准达成：**Playwright 真浏览器三页验收零 console 错误**（index/avatar/chat）；--verify 161/0/0/0；拷走 archive_dist 即为完整档案（刻意不含 relationship.json/candidates.jsonl 构建端文件）
- 用户裁决记录：盲听 v2 回贴系用户本人（7/8 骗过；"不重要"），M1 家人盲听不阻塞 MVP 交付

### Phase 6：GPT-SoVITS 泛化普粤管道（任务 #14，2026-08-18 用户拍板）— status: **complete（2026-08-21 收官）**
> 用户指令："根据妈妈声音做一套泛化的普通话和粤语管道，用 GPT-SoVITS"。依据：docs/research/tts-frontier-2026.md 分语域选型定案；设计要点 HANDOFF ⓪⁺⁺⁺⁺ 第 3 条
- 原则：person-generic（people/<slug>/ + voice_profile 参数化）；repo+CLI 不走 WebUI；抽卡对策=ASR 回读 CER 自动淘汰+人工尾筛；管道代码 DeepSeek 写 + Codex 审；A/B 对照现役 v0.2 e14 沪普域（裸文本），盲听唯一标准
- ✅ 6a 环境底座完成（2026-08-18）：整合包 7.6GB 魔搭直链下载解压至 ~/gpt-sovits/GPT-SoVITS-v2pro-20250604（v2Pro/ProPlus 底模+sv 模型全在）；api_v2 服务 :9880 脱钩常驻（workdir/tts_infer_v2pro.yaml，cuda+half）；**zero-shot 冒烟 16/16 全出**（3 参考×4 句普通话 all_zh + 4 句粤语 all_yue，~2s/条，seed 42）；**抽卡当场实锤**（refB_h01 14 字仅 0.7s 截断）→ QC 必要性验证；8 条代表样本 MP3 已发用户手机（三参考同题对照 + 长句 + 粤语三条）→ **等用户耳测三判：音色像否/哪个参考最像/粤语音色保持否**
  - 参考候选（从 v02 数据挑，5-10s 带校对转写）：refA=20211229_115226_s03（7.4s 转写近纯普通话）/ refB=20220204_154243（8.3s 健康期沪语密）/ refC=20211221_173049（7.3s 中密度）；语言代码 all_zh/all_yue；输出 32kHz
- ✅ 6b 转写策略实验定案（2026-08-21 用户终局耳测，四方对照页 gsv_review.html 走 Tailscale）：**普通话=臂C（沪语本字直喂+g2p_char_map）**；臂 A 落选；**参考确认 refA（近普转写，音色最像）**。裁决已写入 gsv_profile.json defaults/decision_log。过程：语域标注 160 条（wu 90/mixed 57/mandarin 13→筛子集臂数据不足否决）；两臂各 s2+s1 微调+同题合成；四方对照（现役 v0.2 e14 / zero-shot / 臂C / 臂A）
- ✅ 6c+6d 工具化闭环入库（3fd0e65，DeepSeek×2 + Codex REJECT→ACCEPT with fixes + 声明 hotfix×7）：**tools/gsv_pipeline.py** 五子命令（prepare/preprocess/train/synth/verify）person-generic；voice_profile 参数化首实例 people/mama/voice/gsv_profile.json（gitignore 内）；raw guard 全覆盖/bert 缓存失效规则/4 列 TSV 对账/runtime 子进程 bert 校验/QC 重抽。冒烟：prepare 与探针产物字节级零差异；synth 实战 8 条重抽救回 3 条
- ✅ 6e 合成+QC 收官（2026-08-21）：**ASR 回读 CER 自动淘汰入库**（DeepSeek×2 + Codex ACCEPT with fixes→复核 ACCEPT）——引擎 SenseVoiceSmall（venvs/asr，单模型 zh/yue，探针实证 CER 0-0.07/错配 1.0）；gsv_pipeline synth 批后两轮：round1 全量回读判 PASS/CER_SUSPECT/ASR_ERROR（cer_max 默认 0.30，profile asr_qc 块+--cer-max/--no-asr-qc）→ round2 对"时长 PASS 且 CER 超标"者 seed+2000 重抽（采纳=时长 PASS 且 cer 更低）；新增内部 `_asr` 子命令（跨 venv 子进程、PEOPLE_DIR 守卫）；报告新增 asr_status/cer/asr_text/cer_retried/cer_retry_cer/final_ok。冒烟实录：r2 重抽 cer 0.54 更差被正确拒收（抽卡废品门控实战）。A/B 试听页已由 gsv_review.html 覆盖（耳测已收口）
- ✅ 6f 粤语跨语言验证定案（2026-08-21 用户耳测）：**粤语=零样本默认**——两臂微调与 zero-shot 听感无差（"都差不多"），取零成本路径；音色跨语言保持可用。观察=y02 同句在三批中均 QC 难产（句式难度非模型差异）
- 记音字发现（子代理）：校对转写含大量同音记音字（雪小辈=血小板/带生=戴森/亦添人名多变体）——档案转写层潜在改进项，动校对稿需用户闸门，未立项
- 现场事实（2026-08-18 探查）：GPT-SoVITS 不在盘；wu-sft/v02_full/data 八件套在位；processed/wechat_voice 125 WAV 在位；GPU 5.9/24GB 空闲

### Phase 7：数字人渲染升级（任务 #17，2026-08-23 用户立项）— status: **Phase 0+1 complete（2026-08-27 收官）**
> 背景：Phase 4 双帧口型用户两报"疯狂闪烁"，三根因修复仍闪 → 架构判死（两张独立 AI 整图互换必然全图抖动）。研究收口 `docs/research/digital-human-rendering.md`：主线=viseme 嘴部贴片+预计算时间轴
- ✅ **Phase 0 三态贴片（08-25）**：恒定底图（s3002 闭嘴）+ 全尺寸 RGBA 透明嘴贴片（half/open，用户定稿 A 温和版）；build_avatar_page.py patch 模式（三层回退 patch>image>SVG）。**上线次日用户报"没变化"→ 真根因=`style.display=''` 被 CSS 类规则回落吃掉，贴片从未渲染**（此前验证采 inline 遥测=假阳性）→ 修复=显示全显式 'block'+scale 改打 img；诊断 HUD 常驻（?debug=1）；**像素级验收铁律固化**（computed style+截图 diff，memory: verify-rendered-pixels）
- ✅ **Phase 1 viseme 时间轴（08-26/27，用户定稿"先按照这些定稿"）**：Rhubarb 1.14.0 phonetic 批跑 125 条=18516 cues → `tools/build_visemes.py`（增量）；运行时数据驱动 N 态（mouth_patches.json v2：viseme_map/rms_states/blink + fallback resolve），时间轴驱动优先/RMS 回退（BYOK 动态分支）；资产定稿 W1 大张/R1 圆唇/嘟唇并入/B1 眨眼（双镜片内区替换镜框恒底图）；眨眼调度器+ambient 微摆=整脸微活。审核链：DeepSeek×4 轮 + Codex REJECT（3 实锤）→ ACCEPT + 声明 hotfix×5。验收：六通道 8s 采样全动（TL 178/178）+ 慢放/克隆节点像素实拍
- ⬜ **可选增强（待用户点头）**：talking-head 预渲染 MP4"特别版"（3-5 条珍贵语音，InfiniteTalk/EchoMimicV3/LivePortrait+JoyVASA 候选，逐帧人工验收）

### Phase 8：桌面陪伴型数字人可行性研究（任务 #18，2026-08-27 用户立项）— status: **research complete → 用户裁决 2026-08-28 继续推进（8A 开工，见下）**
> 用户指令："研究是否可以构建桌面陪伴型数字人，用户利用打字或语音与他/她进行交互，她返回语音或文本"
- ✅ 研究执行（workflow wf_c886ce8b-4b8：6 维并行 + 8 条载重论断对抗校核，6 confirmed/2 refuted，含 4 组本机实测探针——CosyVoice 流式首包 2.2-4.4s / GSV 流式 ~1.07s / SenseVoice 0.1-0.4s / Rhubarb 每句 +1.1s）
- ✅ 报告成文 `docs/research/desktop-companion.md`：**技术=拼装级可行**（三积木全在库，缺口只是合流页+壳+语音输入；avatar RMS 分支与 chat TTS 语音条"各持一半"，blob 接 analyser 即通）；壳选型两轨（轨0 Edge --app 零代码 / 轨1 Tauri v2）；对话层 BYOK DeepSeek 主线（thinking:disabled 一行修正）；**伦理三档判定：常驻桌宠不应做 / 上限形态="打开才在的档案对话窗口"（条件 a-f：只应答/关窗道别/Tier 标签不减配/真实节律限速/使用统计自见+三月自查/预写告别协议）/ "维持现状不做"是合理默认**
- 校核两翻案入 findings：上海话本地 ASR 存在（Dolphin zh-SHANGHAI，待实测）；"本地 LLM 只能 8-14B"推理链不成立
- ✅ **用户裁决（2026-08-28）："继续推进桌面陪伴"** → 按报告第七节 Phase A 开工，上限形态（打开才在的对话窗），条件 a-f 全部为硬规格；常驻/托盘/自启/主动搭话永久排除
- **架构决策（2026-08-28）：iframe 组合，非大合并页**。companion.html `<iframe>` 内嵌现有 avatar.html（face-only），父页放对话 UI，TTS blob 喂给 iframe 的 audio#player（匹配不到时间轴→RMS 口型）。理由=避免重构 1941 行、避免触碰已像素验收上线的 avatar.html；avatar 仅两处追加式默认不变小改。同源 iframe 直接 contentWindow 存取
- **Phase 8A 开工清单（2026-08-28）**：
  - ✅ 8A-0 告别/降级协议 docs/companion-farewell-protocol.md（条件 f，Claude 起草用户可改；第五格留用户填）
  - ~~8A-1~~ **已被取代（2026-08-28 架构决策 iframe 组合，avatar.html 零改动；face-only 与外部音频由 companion 父页注入实现，见 8A-2a）**。原计划：build_avatar_page.py 两处追加式小改（DeepSeek+Codex）：①face-only 显示模式（?mode=face 隐藏播放列表 chrome 只留脸）②接收外部音频（postMessage/或父页直接设 audio#player.src 播 TTS blob 触发 RMS 口型）。**验收=无参数/无消息时 avatar.html 重建字节级一致 + 像素级口型复验**
  - ✅ 8A-2a **核心闭环完成**（2026-08-28，DeepSeek 写 + Codex REJECT→REJECT→ACCEPT + 声明 hotfix）：tools/build_companion_page.py 入库；companion.html（父页 iframe avatar.html face-only + 复用 chat 三源检索/SSE 双协议/buildMessages/TTS → blob 路由进 iframe audio#player 触发 RMS 口型）。Codex 两轮抓 3 BLOCKER（三源检索退化/分片键名 data.shards→message_shards/加载时序无门控）+ 2 MAJOR（停止按钮禁用/saveSettings 提前放行与并发双发）；DeepSeek 整函数重生成漂移严重（标识符全猜错）→ 改外科式声明 hotfix + contextLoaded/sendPending 双门控（比 chat.html 更严）→ ACCEPT。Codex 误报 1 条（send 监听被注释吞，cat -A 实证独立成行）。**真浏览器冒烟全绿**：iframe 同源可存取+player 可达+chrome 隐藏脸可见+抽屉+两处非本人标识+deepseek-v4-flash 占位符（console 仅 favicon404+TTS未启二良性）。thinking:disabled(仅 deepseek 端点)+占位符修正一并落地（8A-3 折入）
  - ⬜ 8A-2b 条件 a-e 伦理护栏：关窗道别语（取 rhythm/语料 Tier-2）+ 空闲「去忙了」离场 + rhythm.json 真实节律限速 + 使用统计自见卡（首页/三月自查）；另修 contextLoaded 混用「未加载/已失败」两义的非阻塞瑕疵
  - 🔶 8A-3 companion 侧已落地（8A-2a 加 thinking:disabled 仅 deepseek 端点、8B-5 PROVIDERS 预填 deepseek-v4-flash）；**chat.html 本体未动**（build_chat_page.py 占位符仍 deepseek-chat，chat.html mtime 08-17）。原计划：chat 构建器两处小修（payload 加 thinking:{type:disabled} 仅 endpoint 含 deepseek 时 + 占位符 deepseek-chat→deepseek-v4-flash；companion 与 chat.html 同源共享，一并修）
  - ✅ 8A-4 轴五 sessions 采集——已由 8B-7 落地（2026-09-01）：tts_server.py 加 POST /session → people/<slug>/sessions/*.jsonl（第二纪元，数字人话语永久 Tier-3）
  - ⬜ 8A-5（Playwright 桌面+iPhone 视口验收已在 8B 完成；剩壳 + 完整真机验收=8B-4）壳=Edge --app 快捷方式（刻意不自启不置顶）+ Playwright 真浏览器验收 + 像素级口型验收 + 用户真机验收

### Phase 9：蕾咪桌宠效果研究（任务 #19，2026-08-28 用户立项）— status: **research complete → 用户裁决 2026-08-28 方案甲先（→ Phase 8B-甲）**
> 用户指令："立项研究 kira-remy-official，我想把数字人做成这种效果"
- ✅ 仓库全量克隆逐行拆解（~14k 行 Python）+ 本地 v1.2.1 实装对照 → `docs/research/kira-remy-analysis.md`
- 核心发现：**"效果"=透明无边框桌宠立绘窗+情绪表情立绘切换+打字机气泡**；技术栈仅 PyQt5+8 张 PNG（无 Live2D/无语音/口型仅 Open-Shut 双帧）；完全开源可二创，无 20 年红线冲突
- 对照判定：口型/语音/人格/记忆四项我们领先；**要补的只有情绪表情资产 + 桌宠壳形态**
- 落地候选（等裁决）：**方案甲**=companion 页内补情绪表情层（ComfyUI 情绪贴片 4-6 个+用户定稿闸门+关键词驱动，资产两形态通用）→ **方案乙**=桌宠壳（PyQt5 QWebEngineView 透明窗装我们 HTML 运行时 / Tauri v2；仍守"打开才在"：无托盘无自启关窗道别）；推荐甲→乙
- 借形不借魂：蕾咪的常驻/主动搭话/游戏化/恋人模式/云识图全部排除（条件 a-f 与铁律 3）
- ✅ **用户裁决（2026-08-28）：方案甲先，且硬要求=iPhone/Mac/PC 三平台 HTML 正常运行**

### Phase 8B-甲：情绪表情层 + 三平台兼容（2026-08-28 开工）— status: in_progress（8B-1~3b / 8B-5~11 全 ✅；剩 8B-4 完整真机验收）
> 用户指令："方案甲先 确保所有平台（iphone/mac/pc）html可正常运行"
- ✅ 8B-1+8B-2 **兼容加固与情绪层运行时完成**（2026-08-28，DeepSeek 全文回显+区域纪律模式 + Codex REJECT(2 Major+1 Medium 全实锤)→hotfix×4→ACCEPT）：①iOS 解锁 unlockAudio（send 手势内 SILENT_WAV 静音 play/pause + 合成 click 派发进 iframe 触发 avatar audioCtx.resume）②播放被拒→气泡 ▶"播放她的声音"按钮兜底（同步 throw/promise reject 双路径，按钮保留可重试）③CSS：viewport-fit=cover/100dvh/safe-area/16px 防缩放/tap-highlight ④情绪层：iframe 注入 emotion-overlay（显式 inline style 不挂 mouth-patch 类、插眨眼层之下）+ emotions.json 数据驱动（404 静默关）+ 关键词检测 + 同名防呆滞(刷新计时) + 回落。**工艺沉淀：DeepSeek"全文回显+区域纪律+diff 校验"11 块 146 行零漂移**（对照上次整函数重生成漂移事故）。验证：Playwright 桌面全绿 + emotion DOM 机制 computed style 实测(block/none/层序/全尺寸加载) + iPhone 390×844 视口布局全绿（无横滚/输入栏贴底/16px）
- **用户裁决（2026-08-29）：不全身化，维持半身框**——全身立绘方案（资产重做+一致性风险）被否，8B-3 按原计划在现有底图上做；全身化留作远期可选（蕾咪"全身动画"实为整图切换已拆穿，无骨骼动画）
- ✅ 8B-3 **情绪贴片首轮候选 → 用户定稿**（2026-08-29 生成；**2026-09-01 用户定稿：四情绪均取种子 5002**，Claude 对照表推荐——排除 happy s5003 瞳孔变棕/sad s5003 带泪珠）：ComfyUI 复用 4e/Phase1 管线（Qwen-Image-Edit，gen_avatar_candidates.build_graph）生成 4 情绪×3 种子=12 张（happy 弯眼笑/sad 蹙眉心疼/stern 嗔怪抿嘴/think 侧看思考）；**意外之喜=首轮即温和不夸张、形象一致性全保持**（prompt 预置"嘴/镜框/发/脸锁死不变"+温和克制，无 Phase1 的夸张返工）。烘焙数学=双镜片内区(blink 同 rects,羽化8)+眉带(羽化10)，ImageChops.lighter 合并 mask，composite base×(1-α)+cand×α；抽验 sad 合成图无接缝无鬼影嘴不变。审核页 archive_out/emo_review.html（12 GIF 底图↔情绪 0.8s 交替，16MB）已上 8020 → ~~等用户每情绪选 1 或重做~~ 已定稿 s5002（见 8B-3b）。默认微笑=底图本身（第 5 态无需生成）
- ✅ 8B-3b **烘焙 + 激活完成**（2026-09-01，DeepSeek×2 + Codex REJECT(1 BLOCKER 3 MAJOR 1 MINOR 全实锤)→回炉→ACCEPT with fixes(1 MAJOR)→声明 hotfix→**ACCEPT**）：①新工具 `tools/bake_face_patch.py`（person-generic：候选整图→全尺寸 RGBA 贴片，掩码=矩形填充→GaussianBlur(feather)→lighter 合并=审核页同数学，内建 alpha_composite 自验 ≤2，单任务/--jobs 批任务，负路径全守卫）②`build_avatar_page.py` 新增 `load_emotion_assets`：persona/emotions.json（裸文件名）→ 校验→复制→archive 侧改写 `data/avatar/<name>?v=<hash>` → reconcile 白名单；无 emotions.json 时 archive 旧副本被清=companion 404 静默关 ③`persona/emotions.json`：sad>stern>think>happy 键序=优先级，关键词取自 rhythm 口头禅+persona 论断，Codex 子串误报实证后 r2 收窄（去标点/单字/泛词）④验证：烘焙贴片叠底图 vs emo_review 用户审核合成图 max_diff=0（所见即所得）；重烘字节级一致；Playwright mock SSE 走真实运行时 detect→show→切换→7.8s 回落，computed display/src/1104×944/层序全对，截图人眼确认蹙眉与弯眼真实渲染。原始 12 候选+manifest 存 `versions/emo_candidates_20260829/`
- ✅ **8B-5 多服务商抽屉**（2026-09-01 用户提出，DeepSeek×2 + Codex ACCEPT with fixes→ACCEPT）：服务商下拉 OpenAI/Anthropic/DeepSeek/Kimi/自定义，选中即预填端点+模型（gpt-5.6 / claude-opus-5 / deepseek-v4-flash / kimi-k3，ID 均经官方文档核实，四家端点浏览器 CORS 预检实测通过）；`settings.profiles[provider]` 各自记忆 URL/模型/Key，抽屉内 `draftProfiles` 草稿区（关抽屉不保存即丢弃）；旧版存档按 URL 自动归类（openai+deepseek 地址→deepseek）；**空字段一律补默认值**（`withDefaults`，用户二报「切到 DeepSeek 没预填」的根因=只存 key 的旧存档，r3 修，Codex ACCEPT）。Playwright E2E：迁移/五家预填/草稿保留/取消路径/Kimi Bearer 协议/Anthropic x-api-key 协议/新用户默认 DeepSeek 全绿
- ✅ **8B-6 修 bug：TTS 念完接播训练语音**（2026-09-01 用户真机实报）：根因=avatar.html `ended` 无条件 `playAt(cur+1)`，companion 灌进 `#player` 的 TTS blob 播完即触发首条真实语音。修法=ended 首行 `blob:` 音源守卫（1 行声明 hotfix，Codex ACCEPT；独立档案页零影响）。E2E：真实 :8022 TTS 播完→player 停在 blob、now-title 未变、脸复位。**注意 avatar.html 因此有改动，archive_dist 尚未重新同步**
- ✅ **8B-7 微信式时间分隔 + 轴五 sessions 日志**（2026-09-01 用户提出，DeepSeek×2（两文件）+ Codex ACCEPT with fixes(4 MAJOR 全实锤)→回炉→hotfix→**ACCEPT**）：①聊天栏与上一条消息间隔 >5 分钟在气泡上方居中显示时间（今天 HH:MM / 昨天 / 星期X / M月D日 / 跨年带年），`lastMessageTs` 消息间隔语义；②`tools/tts_server.py` 新增 `POST /session`（白名单字段、session_id 正则防穿越、realpath 守卫）与 `/tts` 可选 session_id/turn → WAV 原子另存（`open('xb')`，同 turn 加 `_2..`）+ `simulacrum_audio` 记录；落盘 `people/mama/sessions/YYYY-MM/session_<id>.jsonl` + `audio/`（GENERALIZATION 轴五既定格式，记录含 ts/provider/model/emotion/tts 状态/retrieval_used 标签）；③companion 侧 logSession（user/simulacrum/event: session_start·tts_failed·llm_error），服务不在时 localStorage 排队（qid 去重删、500 上限）恢复后补传。E2E：分隔线 0/4/8/12 分钟仅 1 条；真实 TTS 四轮全部落盘（含断线补传第 3 轮）；WAV 24kHz mono PCM16
- ✅ **8B-8 TTS 念白剥括号**（2026-09-02 用户实报 `[捂脸]`/`（瞟一眼）` 被念出，DeepSeek + Codex ACCEPT）：tts_server `/tts` 合成前 `strip_brackets`（[]/【】/（）/() 成对剥除，不动点循环处理嵌套，空白压缩；剥空→400），时长 QC 按剥后文本；气泡显示不变；simulacrum_audio 记录附 `spoken_text`（与原文不同时）。服务端统一剥，chat.html 语音条同受益
- ✅ **8B-9 分句语音流水线 + 微信式「正在输入」**（2026-09-02 用户提出，DeepSeek×3 + Codex REJECT×2(3 BLOCKER 全实锤：ended 归属误伤新回合/showPlayButton 手点分支漏设 activePlay/短尾段)→hotfix→**ACCEPT**）：回复按句切段，首段先合成先播、后段边播边合成串行接上（首声≈首段合成而非全文）；**每段文字随该段语音开播同刻浮现**（文声同步，`voiceTurn` 状态机+`activePlay` 归属校验防旧回合 ended 误推进新回合）；发送后气泡先显示三点打字动画（CSS）。TTS 不可用/超 240 字→文字节奏兜底；停止键亮出已生成文字；cancelVoiceTurn 文字永不丢；safetyTimer 20s 防挂死。E2E：并发压力(旧回合播中发新回合)、autoplay 拦截后手点按钮多段推进、纯文字兜底全绿
- ✅ **8B-11 起音爆音抑制**（2026-09-07 用户报"每段语音开头一声很短的声音"；DeepSeek×2 + Codex REJECT(2: 静音前缀用错阈值 / 首次发声只认第 0 帧)→ACCEPT）：实测模型每次开口前 ~15 ms 爆音（RMS 2–3×、峰值 2×、重心 800 Hz，每句起音都有，两语域一致）→ tts_server 出口 `soften_onsets`（5 ms 帧 RMS 起音检测：首次发声或 ≥200 ms 静音后 >0.01；30 ms 升余弦淡入，不裁剪；`--onset-fade-ms` 0 关闭），WAV/MP3 同受益，companion 语音条与批量合成统一修；单测 6 例（两处起音比 3.16→0.66、底噪不误触、短停顿不误触、短前导仍淡入、fade=0 原样、空/静音安全）
- ✅ **8B-10 微信式语音条 + ≤30 字分条发送**（2026-09-05 用户反馈两条：默认发语音条可点回味、下方备注文字；回复过长就不出声要拆成 ≤30 字多条各自合成。DeepSeek 两轮区域产出零漂移 + Claude 声明 hotfix 8 处；三视角 workflow 审查 26 发现→对抗核证 10 确认全部修复；**Codex 三轮：REJECT(5)→REJECT(1)→ACCEPT，09-06**；Codex 抓出：标点-only 合并可超 30/丢开头标点、30 s 超时未盖 body、降级 Audio 拒绝不清动画、零样本节律误导、回合进行中回放绕开 activePlay——全部声明式 hotfix 修复并 E2E 复验）：根因=`TTS_TOTAL_MAX=240` 全文超长整段跳过语音（sessions 7/17 条 `skipped_length`）；现 `splitMessages`（换行→句末标点→子句标点→硬切且不拆代理对，≤MSG_MAX=30）每条独立 `.bubble.subject`，三点占位串行；前 MSG_MAX_VOICE=12 条各自 `/tts`（30 s 超时→文字），语音条 `.voice-bar`（CSS 声波弧 + `X-Duration-Seconds` 时长）+ `.voice-text`；回合结束可回放/再点停（`stopReplay` 模块级、降级 Audio 可停）；旧回合 ▶ 按钮受守卫且 cancel 即移除；文字延时成闸门（`vt.waiting`）；内部气泡 `noDivider`；标签/标点-only 条不送 TTS；Blob 保留最近 60 条；抽屉「语音条下方显示文字」开关（`storageKey+'_ui'`，默认开）；sessions simulacrum 记 `tts∈{requested,partial,unavailable}` + `messages`（tts_server 白名单加 int 校验）。同时修 `build_rhythm_block` 键全错（模型此前从未见"中位 17 字/69% 单条/70% 无句末标点"），提示词加"一行一条 ≤30 字"。E2E（Playwright route-mock 真运行时）两轮：TTS 不可用降级/15 条 partial + 单条 500/打断顺序/回放停止/开关持久化/旧 ▶ 劫持/流式期间回放收口/单条挂起 30 s 超时/纯表情行/空回复 全绿；真 :8022 冒烟 29 字 5.5 s 出声
- 🔶 8B-4 验收：Playwright 桌面 + iPhone 视口模拟 ✅；**用户真机首测 2026-09-01 通过（API 配置成功、文字+语音回复通）**；完整真机验收（iPhone/Mac 经 Tailscale，含情绪层）待继续

### Phase 10：dsh-im 研究——persona 接入各 IM 平台文字+语音（任务 #20，2026-08-29 用户立项）— status: research complete（2026-08-29 收口）→ 等用户裁决方向
> 用户指令："研究 xmanrui/dsh-im，作为桌面陪伴外的另一个副产品，把'调教好的'虚拟人物接入各平台（尤其微信）文字+语音聊天，卡通形象不需要"
> 关联既有结论必须核：messaging-channels.md（个人号协议伪造已否决 >80% 封号）+ 任务 #16 微信 UIA NO-GO（4.1.12.26 铁证）——本项目是第三种微信接入路径
- ground truth：dsh-im=Cordis 框架通道网关，把 9 IM（飞书/微信/钉钉/企微/QQ/Slack/TG/Discord/WA）接入本机"DeepSeek Harness"；官方 SDK（企微 aibot/QQ 官方 bot/钉钉 stream）+ 微信个人号走 iLink 长轮询协议；MIT/948★；**README 未提语音**（用户要语音=空白）
- ✅ workflow 研究收口（wf_26efff09-b58，11 代理/96 万 tokens，6 confirmed/1 refuted/1 unclear）→ docs/research/dsh-im-analysis.md
- **核心发现**：①dsh-im=连接层非大脑（DeepSeek Harness 的 Cordis 插件，接 persona 要写冒充 Harness 的本机 shim，非即插即用）②**微信 iLink 是腾讯 2026 官方个人号 Bot 协议（ClawBot），第三条路，实质更新我们"微信封死"结论**——绕开 UIA(#16)与 hook 灰产两死因、reply-only 天然契合"永不主动"；**但校核 refuted"官方=可给家人用"**：它是"机主控自己 agent"设计、dsh-im 直连属未授权客户端、家人向拓扑无据、腾讯可随时终止+裁定可连哪些 AI ③**不发原生语音条**（她真声只能当文件发，发语音条=逐平台自建转码 SILK/opus/AMR）④企微 aibot 对家人个人微信 NO-GO
- **裁决（分层）**：自用（绑自己号+仅自己模式+轴五 sessions 采集）=有条件 GO 低风险；**家人向（妈妈进家人聊天列表）=默认 NO-GO**（第三方受众+沉浸/欺骗最大化，比桌面陪伴更保守；先例=某团队拒绝把逝母微信记录做数字分身）；即便全员知情同意仍劝阻常驻形态
- **用户可自查两硬点**：①微信 设置>插件 看有无 ClawBot 入口（秒级，判你号在不在 iLink 灰度，无需弃号）②iLink 能否发原生语音条（动工前活体验证）
- ⬜ 等用户裁决方向（自用验证 / 家人向按闸门 / 先不做）

### Phase 11：OCR 控制电脑端微信聊天研究（任务 #21，2026-08-29 用户立项）— status: research complete（2026-08-29 收口）→ 等用户裁决方向
> 用户指令："研究通过 OCR 控制已登录的电脑端微信与别人聊天（语音+文字）；社交媒体见过相关 skills，上 GitHub 找开源"
> 定位：这是微信第四条路径。前三条=①UIA 自动化(#16 NO-GO)②iLink 官方协议(#20，家人向 NO-GO)③服务号/企微(需主体)。OCR+模拟键鼠=任务#16 报告"替代方案#2/#3"（读像素不读控件，绕 UIA 死因；swigger/wechat-ocr wxocr.dll 已在报告点名）
- ✅ workflow 研究收口（wf_6b7db20f-956，11 代理，3 confirmed/2 refuted/2 unclear）→ docs/research/wechat-ocr-automation.md
- **核心发现**：①**GitHub 有零件没成品**（swigger/wechat-ocr 964★ 只是引擎/jxyk2007 91★ 发文字/omni-bot 542★ 实为 DB 读+OCR 只定位发送）；你社媒看到的"skill"最像 YoKo(LeoMusk 83★)/pywechat(1874★)——**但都是 UIA 路线，在你 4.1.12.26 上已被 #16 判死** ②**★新事实：微信 PC 4.1.9+（你 4.1.12.26 已有）支持发原生语音条（按住右Alt）**，配 VB-Cable 虚拟声卡+keyDown/keyUp 可发她真声语音条——**实质更新"PC 只能当文件发"旧结论**；唯一 iLink 给不了的能力，但音色可能被微信 AGC/降噪劣化(待活体 A/B)③收沪语语音=微信自带转文字不认上海话，须绕 DB/文件取音频喂本机 ASR ④校核 refuted 两条强论断：OCR 非"唯一绕开 UIA"(DB 读才是可靠读侧，我们 #16 已列)、非"独占家人可达格子"(iLink 扫码同样可达，被排除靠伦理非技术)
- **裁决**：自用=低风险 GO（但 TG/iLink 自用比脆弱 OCR 更干净）；**家人向=默认 NO-GO，且比 iLink 更甚**（OCR 劫持"看着像真人在用"的号、零 bot 标识、欺骗性最强、能发冒真度最高语音条=技术加分即伦理加压）
- ⬜ 等用户裁决（自用验证 / 先不做）；报告已建议并入四路径存档

### Phase 12：iOS 专属 App 部署 + 从 0 到 1 建档 App 产品化研究（任务 #22，2026-09-02 用户立项）— status: research in_progress
> 用户指令：a/ "电脑端做完的 companion，如何在手机端（iOS）可以部署？做一个专属 APP 可行不？这样就不用硬部署微信了" b/ "基于研究 a，目前从 0 到 1 能否做成 app 自动化？电脑用户直接将训练数据（聊天记录、语音、照片、视频等）拖入应用，应用全程引导用户进行配置以及审核（逃不掉的人工审核例如语音和卡通形象），最后产出 companion"
> 定位：a = 消费端第三形态（现有=Tailscale 开 :8020 网页；微信四路径全 NO-GO/等裁决）；b = 构建端产品化（form-factor.md 定的"构建端=Claude Code skill 允许死"要重审；GENERALIZATION.md 五轴是需求基线）。硬约束：TTS 现役 CosyVoice2 SFT 依赖 4090；people/ 永不上传；铁律 2 三条须变成产品功能而非文档
- ✅ 内部盘点 3 路（workflow：companion 运行时依赖 15 项 / 0→1 管线人机分工 33 项 / 伦理约束 39 项，09-02）；外部扫描 7 路因账号限额失败 → 用户指令"一个一个来"，改由主模型逐条补查
- ✅ **a 收口（09-02）→ `docs/research/ios-app-deployment.md`**：结论=A1 主屏 Web App（iOS 26 默认作为 Web App 打开，只需加 apple-touch-icon；http 无 secure-context 需求；ttsBase 取 location.protocol 故 tailscale serve https 零改动）推荐；A2 WKWebView 壳技术可行但收益全在 6.2 ③ 禁区、不推荐；她的声音出不了 4090（端侧运行时只跑官方 CosyVoice3/Qwen3-TTS 检查点，SFT .pt 无运行时）；A5 云 GPU 铁律 3.2 NO-GO；建议另立 A3′ 有声档案（预渲染语音库进 archive_dist）；前提 8A-2b 先上。待裁决 D1–D5
- ✅ **a 用户裁决（2026-09-03）**：D1 接受 A1 + 同意 8A-2b 先行；D2 https 跳过；D3 A3′ 有声档案立项（→ Phase 13）；D4 A2 壳先不做、看 A1 效果；D5 PC 常开、服务手动拉起
- ⬜ A1 实施（排在 8A-2b 之后）：build_companion_page.py 加 apple-touch-icon（avatar 静帧）→ coder 子代理写 / Codex 审 → 真机添加到主屏幕、首次重输 key → 并入 8B-4 验收
- ✅ **b 收口（09-03）→ `docs/research/build-app-productization.md`**：结论="产出 companion 的自动化 App"改为"产出档案的建档工作台"（B1 向导式，预留 B2 agent 工作台，B3 云端 NO-GO）；确定性步骤可 GUI 封装、七道闸门是产品本体不可压缩；三条硬边界=微信取 key 永不可自动（用户自带导出件）/ 她的声音需 4090 级（GPU 分档、不提供云 TTS）/ Claude 承担的判断力工作只能"固化配方+失败即止"或内置 agent；给陌生人的前提=铁律 2 从文档变功能（§4 表，8A-2b 超集）；分期 P0 债清偿→P1 MVP→P2 判断力层→P3 打包，工程量推断 5–10× 妈妈档 12 天。待裁决 E1–E6
- ⬜ 用户裁决 E1–E6

### Phase 13：A3′ 有声档案——预渲染语音库进 archive_dist（2026-09-03 用户立项，源自 #22-a D3）— status: planned
> 定位：档案侧净增量，"PC 关机也有她的声音"的唯一路径；只播 Tier-1/2 来源句，模型生成的新句子没有声音（天然把 Tier-3 关在门外）。产物 WAV + JSON 清单，20 年可放。不是 companion 的替代
- ⬜ 选句：Tier-1 记忆卡（124 条）+ rhythm 常用句/问候/告别语（Tier-2）→ 用户过一遍闸门
- ⬜ 批量合成：e14 离线（`<|wuyu|>` 沪语 / 裸文本沪普按素材语言）+ ASR CER 回读 QC + 用户抽听
- ⬜ archive_dist 一页：检索式对话只播预渲染句，未命中说"我记不太清了"（无声）；`build_archive.py` 重打包一并收（M3 欠账）
- ⬜ 用户验收

### Phase 14：给爸爸的六段语音（任务 #23，2026-09-06 用户立项）— status: **complete**（09-07 用户已转发给爸爸并关闭）
> 用户原话："我将和虚拟人周五晚上进行的对话发给了我爸，他很触动，将图片内虚拟人的所有文本的6大段语音发给我"
> 素材：sessions 2026-09-04 21:45 会话 turn 6–11（136/110/276/235/267/334 字；其中 4 段当晚因 `TTS_TOTAL_MAX` 未出过声）。产物 = 整段 WAV（档案格式）+ MP3（微信发送）+ manifest（Tier-3 标注、来源 turn、sha256）+ 两语域对照试听页
> 伦理注记：话语是模型生成（Tier-3），不是她说过的话；受众为配偶（近亲属、已知情）。产物文件与试听页均带"合成语音·非本人原声"标识；不进 archive_dist；建议用户转发时向爸爸明说是合成
- ✅ 两语域各合成 6 段（110 句 0 失败，wu 42–92 s / mandarin 33–81 s）→ 试听页（8020 站 review/for_dad/ + SendUserFile）→ **用户选 wu 上海话域**（09-06）→ 6 个 MP3 已 SendUserFile 发出
- ✅ 09-07 用户已发给爸爸、关闭本项。顺带发现：**每段语音开头有 ~15 ms 爆音**（模型每次开口固有，companion 语音条同样有）→ 立 8B-11 在 tts_server 出口做起音淡入

### Phase 15：跨会话记忆（轴五 ②④ 落地：ingest_sessions + 第四检索源 + 上次对话卡）— status: **complete（2026-09-08，Codex 四轮 ACCEPT；剩用户真机验收）**
- ✅ Task 1 `tools/ingest_sessions.py`（摄入，按 viewer 分文件，确定性+原子写+敏感省略）
- ✅ Task 2 tts_server 去抖自动摄入（`SessionsIngestScheduler`，写入后 5 秒重算）+ `/session` 白名单加 viewer/exclude
- ✅ Task 3 companion 页：`--viewer`、第四检索源（Tier-2/Tier-3 标签）、上次对话卡注入系统提示、抽屉「本次不记」开关
- ✅ Task 4 提示词第 7 条铁律「往次对话纪律」+ build_archive 排除 `sessions_*.json` + 文档
- 测试首次入库 `tests/`：36 例 unittest + 1 套 E2E（15 断言）
- ⏳ 剩：用户真机验收（~~PC/iPhone 各强刷一次~~ 09-10 起静态站已发 no-cache，不必再强刷）
- 用户三项裁决（09-07）：双方都记、她的话永久 Tier-3；页面"本次不记"开关 + sessions/exclude.txt；静态 sessions.json + tts_server 自动刷。规格见 docs/superpowers/specs/2026-09-07-cross-session-memory-design.md（待写）。

### Phase 16：任务 #24——爸爸以丈夫角色对话（F-乙 公网 https 独立站）— status: **in_progress**（2026-09-07 立项研究 → 2026-09-08 用户裁决 F-乙 开工）
> 研究报告 `docs/research/dad-husband-companion.md`（F0–F18 十九个裁决点）；**2026-09-08 用户一次性裁决全部 19 项，选定 F-乙 路线**
> 追加指令：所有产物进新目录 `people/mama_for_father/`，**儿子视角部分一个字节不动**（验收=默认参数重建 companion.html diff 为空）

**用户裁决（2026-09-08，19 项全定）**

| 点 | 裁决 | 后果备注 |
|---|---|---|
| F-乙 路线 | 公网 https：Cloudflare Tunnel + Access + 独立站 | 工程量最大路线；不需开防火墙/端口转发（cloudflared 主动出站） |
| 域名 | 现在买（Cloudflare Registrar ~$10/年） | 用户动作 |
| CF 账号 | 无，用户去注册 + 开 Zero Trust | 用户动作 |
| 爸爸鉴权 | 邮箱一次性 PIN + 1 个月会话 | 前提=他能在手机收邮件 |
| POC | 先做连通性 POC 再全量工程 | POC-1 只打假 origin，绝不指向 :8020 |
| 裁剪范围 | **全量，不裁剪** | 爸爸设备可拿到母子一对一 6,835 条（含她对儿子讲的关于他的话）。已知情裁决 |
| CF 边缘明文 | 接受，隧道常开 | 与 `progress.md:203`「裸公网隧道违背铁律 3 底线」有张力，Access 鉴权为缓解非消除 |
| 会话记录 | 全记（含爸爸原话） | 必须当面明示「记录落在儿子电脑上」 |
| 上次对话卡 | 开（第四检索源 + 跨会话连续性） | 依恋风险最高档，用户已知情 |
| 关系层 | **A 诚实标注** | 提示词明写：档案由儿子建立、对话者是她丈夫、二人私事一律「记不清」 |
| 8A-2b 护栏 | **先上线，护栏后补** | b/d/e 记为欠账；(c) 因大字说明卡裁决而提前落地 |
| 透明度 | 每次打开大字说明卡（点「我知道了」才进对话） | = 护栏 (c) |
| 语音 | 给 + `<\|wuyu\|>` 上海话域 + MSG_MAX_VOICE 保持 12 | 两人同时在线会排队，后到者可能整段转文字 |
| 禁区措辞 | Claude 起草 → 用户逐条认可 | 含 F10 冲突面原则：保留脾气特质 / 不主动转述她对儿子讲的关于他的负面话 / 被问不否认 / 绝不编造吵架事件 |
| PC 运维 | 全做（自启 + 自动登录 + Update 活动时段 + 探活重试 + 离线页） | 推翻 D5「手动拉起」 |
| 打包七项 | 除 ⑦ 外全做 | ①facets 不进 dist ②rhythm_dad 重算 ③token+PC 代理持 key ④检索只取 sender=她 ⑤知情同意入档（含声音使用同意）⑥覆盖决策写 progress。**⑦ 请爸爸做 Tier-1 确认人/导出他手机聊天=暂不做**，等他用过再提 |
| F0 前置 | 不问爸爸想要什么，照 F-乙 做 | 按「能和她说说话」设计 |

**实施任务（T1–T16）**
- ⬜ T1 用户动作：买域名 + 注册 Cloudflare + 开 Zero Trust 组织
- ✅ T2 POC 完成（09-08，假 origin，探针 Claude 直写已声明）：**腾讯电脑管家不拦 cloudflared**（与它拦 Tailscale 的 SYSTEM 服务不同）；**QUIC 在 Surfshark 下每 ~90s 断**（`no recent network activity`）→ config.yml 钉死 `protocol: http2`；trycloudflare 快速隧道 DNS 从未生效（两个临时域名经 Google/CF 双 DoH 均 NXDOMAIN，非污染，是 CF 侧没建记录）→ 改用命名隧道绕过
- ✅ T1/T3 用户完成域名 `justmissingyou.com` + Cloudflare 账号 + Zero Trust（09-08）
- ✅ **隧道与 Access 就位（09-08）**：命名隧道 `imissu-father`（`e55190d4-1c4e-4934-a4a9-ff9681b8fc8a`）+ CNAME `dad.justmissingyou.com` + config.yml（ingress：`^/(tts|health|session)$`→:8022，其余→:8021）；**Access 全路径拦截已实测**（`/`、`/health`、`POST /tts` 三者均 302 跳登录页）；邮箱一次性 PIN + 1 个月会话，白名单=爸爸邮箱（记于 people/ 配置）
- ✅ 用户把 cloudflared 加入 Surfshark Bypasser → 边缘落点由 `ewr`（美东）改为 `hkg`（香港）
- ⚠️ **暴露事件（09-08，已关闭）**：POC 期间 ingress 把 `/tts|/health|/session` 指向**正在运行的真实 tts_server**（`--token` 默认空、零鉴权），窗口约 3–4 分钟，其间任何人可驱动 4090 合成语音、向 `/session` 写日志。发现后立即停隧道。域名当天新建未公开，但 tts_server 访问日志被禁用（`:250-251`），**无法证明零访问**。纪律修正：Access 生效 + `--token` 开启两件都完成前，隧道不长跑
- 📌 实测吞吐 20–25 KB/s（美东落点时），回传为 MP3 非 WAV，≤30 字单条约 50 KB → 约 2.5 s 传输 + 合成中位 3.56 s ≈ 首条 6 s 出声；香港落点后未复测（Access 挡住需登录）
- 📌 已知待处理：Access session 过期时页面 fetch 会收到 302 跳登录页而非 401，TTS 请求将拿到 HTML 而非 MP3 → 需在 T12 老人 UX 做友好降级
- ✅ T3 POC-2（2026-09-11）：爸爸首次登录——先发现 Access 只有 Cloudflare 账号登录（One-time PIN 从未启用，09-08 只验了 302），用户启用后爸爸用**微信内置浏览器**登录对话，大陆可达性实证通过
- ⬜ T4 独立站 `people/mama_for_father/site/`：目录联接 `data` → `people/mama/archive_out/data`（零拷贝全量）+ 独立端口 + 根目录不放审核页/开发者 index
- ⬜ T5 `prompts/chat_system.husband.zh.md`（A 诚实标注；填上现模板 `:5` 的称呼悬空位）
- ⬜ T6 `people/mama_for_father/config/relationship.father.json` + `facets.json`（称呼、禁区、同意日期、声音使用同意）
- ✅ T7 `tools/build_chat_context.py` 加 `--relationship` + 三个新占位符（`archive_builder_zh`/`relationship_block`/`taboo_block`）——DeepSeek 写 → Codex 两轮（REJECT 4 条 → ACCEPT）→ 落盘；默认参数输出除 `generated_at` 外逐字节相同；顺带修好 `taboo_topics` 从未进提示词的既有缺陷
- ✅ **T8 `tools/build_companion_page.py` 六项参数化完成**（09-08→09，DeepSeek 七轮 + Codex 三轮 REJECT→REJECT→ACCEPT）：`--context-path` / `--out-name` / `--lang` / `--tts-origin`（auto|same|URL）/ `--tts-token` / viewer≠owner 时 storageKey 后缀 + page tag
  - **默认参数产出与基线逐字节相同（70395 字节）**，儿子版零影响
  - 爸爸版实测：`data_father/chat_context.json` / `lang:'wu'` / `var ttsBase = location.origin;` / 三处 `X-TTS-Token` 均在 headers 对象内 / `storageKey='companion_mama_byok_father'` / `page:'companion_father'`
  - 安全校验 10/10 拒绝：`../`、Windows 反斜杠 `..`、rooted path、`%2e%2e`、单引号注入、非 .json 扩展名、`</script>` 逃逸、带路径的 origin、非法 token 字符、token 末尾换行
  - **验收方法教训**：首轮我只用 grep 数 `X-TTS-Token` 出现次数就判"通过"，Codex 发现 token 分支根本不工作（占位符残留、`var TTS_TOKEN` 未生成、header 落在 fetch options 顶层而非 headers 内）。改用结构级探针（残留占位符 / 声明数 / headers 内嵌正则 / 提取 `<script>` 跑 `node --check`）后才抓到后续的 `},,` 双逗号等语义错误。**字符串存在 ≠ 位置正确**
  - 已知非阻塞限制（Codex 判定）：`--tts-origin` 仍接受语义无效 host（如 `:99999`），只会导致 TTS 探测失败降级，非注入
- ⬜ 独立站骨架已建：`people/mama_for_father/{config,site}`，`site/data` 目录联接 → `archive_out/data`（零拷贝全量），`site/data_father/` 放爸爸专属 context（**不可写进联接目录，否则污染儿子档案**）；`site/companion.html` 当前用占位 token 生成，**上线前须用真 token 重生成**
- ⬜ T9 LLM 代理（PC 持 key，OpenAI 兼容，固定 model + `thinking:disabled` + 限速/日额度 + 鉴权）——爸爸端不存 key
- ✅ **T9/T10 `tools/tts_server.py` 多 viewer token 完成**（09-09，DeepSeek 三轮 + Codex 两轮 REJECT→ACCEPT）
  - `--tokens viewer:token[,...]`（与 `--token` 互斥）；`hmac.compare_digest` 常数时间比对；**服务端认定 viewer**，客户端 body 里自称的 viewer 一律被覆盖
  - Codex 抓到的两条：① `hmac.compare_digest(str,str)` 遇非 ASCII 抛 `TypeError` 而非返回 401（已实锤复现）→ 改为先 `TOKEN_RE.fullmatch` 再比对 ② `__init__` 冗余赋值超出区域纪律 → 删除，`__init__` 与基线逐字符相同
  - 我抓到的一条：正则用 `.match()`+`$` 导致 `owner:TOKEN\n` 通过、viewer 变成 `'owner\n'` → 改 `fullmatch`
  - **活体鉴权矩阵**（重启服务实测）：无 token / 错误 / 过短 / 非 ASCII / 含分号 → 全部 401 且服务不崩；owner、father 正确 token → 200
  - **viewer 覆盖活体验证**：客户端发 `"viewer":"forged"`，落盘记录里是 `owner` / `father`
  - 服务已重启并启用：`token=multi(2 viewers)`，模型 15.3 s 加载；启动方式 `~/venvs/cosyvoice/Scripts/python.exe -X utf8 tools/tts_server.py --tokens ...`（脱钩 Start-Process）
  - token 生成并记入 `people/mama_for_father/config/{relationship.father.json,tokens.env}`（gitignore）；两个页面已用各自 token 重新生成（儿子版 70536 B、爸爸版 70513 B，结构探针 ALL PASS）
- ✅ **T10b 服务端完成：`tools/llm_proxy.py`（新建 366 行，纯标准库）**（09-09，DeepSeek 五轮 + Codex 两轮 REJECT→ACCEPT）
  - key 只在 PC，爸爸浏览器零凭据；`X-TTS-Token` 鉴权（与 tts_server 同套 token，`fullmatch` 形状校验 + `hmac.compare_digest`）；按 viewer 计 rpm/daily 限速；请求体重写（model 强制、max_tokens 压制、字段白名单、deepseek 注入 `thinking:disabled`）；SSE 流式逐块透传；日志只记元数据**绝不记 messages 内容**；无 tokens / 无 key / 非法 tokens 一律拒绝启动
  - **五轮里前四轮都是致命问题，且全部是活体测试才抓到的**（py_compile 与静态检查一概发现不了）：
    ① `import hmac` 却从未调用，用字典查找命中 token
    ② `ProxyServer` 从未设置 `proxy` 属性 → `AttributeError`，`/health` 空响应、形状合法的 token 直接崩连接
    ③ 为做 key 脱敏把流式改成先 `read()` 读完再分块 → 等于取消流式
    ④ **`self.rfile.read(MAX_BODY+1)` 读到 EOF**，而 HTTP/1.1 keep-alive 下客户端不关连接 → 每个请求都阻塞到客户端超时（实测 curl 25 s 收 0 字节）。改为按 `Content-Length` 读（照 `tts_server.py:335-352`）后 **38 ms** 返回
  - Codex 另抓三条阻塞项：`upstream` 未保证释放（改 `with` + `headers_sent` 标志防二次响应）/ 未拒绝 `Transfer-Encoding`（chunked body 会留脏数据）/ **早退响应不关连接**（未读完的 body 会污染下一个请求解析，请求走私形态）→ `_send_json(close=True)` 覆盖 404/401/429/400/413 全部早退路径
  - 活体回归全绿：正常转发 200 · 流式 4 块逐块到达 · `/health` 200 不含 key · 413 · chunked 400+`Connection: close` · 坏 JSON 400 · 404 · OPTIONS 204 · 非 ASCII token 401 不崩 · 限速 429 · 上游错误体 key 被 `[REDACTED]` · **客户端流式读一半掐断 ×3 后 Traceback 计数 0**
- ✅ **T10c 页面接入代理完成**（09-09，DeepSeek 六轮 + Codex 两轮 REJECT→ACCEPT）：`--llm-proxy`（要求同时给 `--tts-token`，否则 return 2——代理无鉴权即成开放中转）
  - 代理模式下：`settingsComplete()` 短路、`streamRequest` 走代理分支（`location.origin + LLM_PROXY`，发 `X-TTS-Token` **不发 Authorization**）、抽屉里服务商/接口地址/API Key 三项被 `removeChild` 移除。**HTML 结构一个字符没改**，全靠占位符注入
  - 不传 `--llm-proxy` 时逐字节兼容，儿子版零影响
  - **踩到的坑（都值得记）**：① 占位符只进 mapping 没进模板 → 映射有值但无插入点，代理模式静默失效 ② **两个占位符紧挨着时被正则 `__[A-Z_]+__` 贪婪吞成一个未知占位符**，两个都不替换、页面 JS 语法错误 → 改为不相邻布局（不动正则，全局影响太大）③ Codex 抓到代理分支位置太靠后：`var endpoint = settings.url` + `https?://` 校验先执行，而代理模式下 `settings.url` 为空 → **永远进不到代理分支**，"打开即可用"根本不成立 ④ Codex 抓到 `TTS_TOKEN` 未定义时代理分支抛同步 `ReferenceError` 且绕过清理路径
  - 那句 `/* ===== streamRequest（唯一改动…）===== */` 长注释被 DeepSeek 连改三轮，最后由 Claude 用脚本原样恢复（已声明，仅此一行文本）
- ✅ **cloudflared ingress 三路由就位**（09-09）：`^/v1/chat/completions$`→:8023（LLM 代理）/ `^/(tts|health|session)$`→:8022（TTS）/ 其余→:8021（爸爸站）。`tunnel ingress rule` 逐条验证匹配正确
  - 注意：**cloudflared 不做路径重写**，路径原样转发。故页面用 `/v1/chat/completions` 而非 `/llm/...`，免去改代理
- ✅ **T10d 端到端实测通过**（09-09，本地模拟 ingress，未经隧道）：真 DeepSeek key + tts_server + 8021 站 + `ingress_sim` 探针（模拟 cloudflared 三路由）
  - **抓到一个 Codex 两轮静态审查都没发现的致命 bug**：`llm_proxy` 流式响应**既无 `Content-Length` 也无 `Connection: close`**，HTTP/1.1 keep-alive 下客户端收到 `[DONE]` 后仍在等 → curl 实测 **30072 ms**（撞满 --max-time），页面永远卡在"正在输入"、发送按钮一直是"停止"。而代理自己的日志却是 `status=200 dur_ms=1784`，看起来一切正常。之前我用 `curl -N --max-time 15` 看到块与 `[DONE]` 就判"流式通过"，那其实是超时退出的假象
  - 修法：流式响应头加 `Connection: close` + `Cache-Control: no-cache` + `self.close_connection = True`。修后读完整个流 **1465 ms**
  - **完整链路验证**：页面（零凭据）→ 代理（持 key、强制 model、限速）→ DeepSeek → 分条 → TTS（wu 域）→ 语音条 → 会话日志
  - 真实回复（上海话、三条分发、各带语音条）：「还能哪能，老样子呀」「今朝呒没高烧，算是太平了」「[捂脸] 侬倒记得来问一声」——第三条带小埋怨，符合铁律 4「不做只会温柔的形象」
  - 会话落盘每条 `viewer=father`（**服务端认定**，非客户端自称）、`page=companion_father`、三条 `simulacrum_audio` 各自合成
  - 页面侧确认：**无「请配置接口」死态**、抽屉里服务商/接口地址/API Key 三项已移除、说明卡每次打开都出现
  - 测试会话已清理并重新 ingest（`deleted: sessions_father.json`），避免爸爸首次打开就看到测试对话的"上次对话卡"
  - 已知 404（非缺陷）：`favicon.ico`（T12c 主屏图标待办，**这就是用户反复看到的那个 404**）、`data/sessions_father.json`（首次对话前不存在，属预期）
- ✅ **T11 检索只取 sender=subject 完成**（09-09，DeepSeek 各一轮 + Codex 一轮 ACCEPT）：`build_companion_page.py` 与 `build_chat_page.py` 两份同样的 `retrieveSnippets` 都加过滤、删死数据 `isSubject` 字段与死代码排序行
  - **缺陷已量化实测**：真实分片 4779 条中 subject 仅 2492 条（52%），其余是建档者 1314 条 + 家庭群其他成员约 900 条。10 个查询下，**未修复版 56 条命中里 4 条来自他人**（`a26681743` 3 条、`wxid_ki6rrgtd96i812` 1 条），这些话会被标成「[档案检索 Tier-2] 她真实说过的话」喂给模型再以她的口吻复述
  - 修复后：companion.html 与 chat.html 各 54 条命中、**非 subject 0 条**
  - 验证方法：node 脚本按括号平衡从产出 HTML 中提取 `scoreText`/`extractTokens`/`retrieveSnippets`，喂真实分片跑查询后把命中文本回溯到原记录查 sender；另对两份产出提取全部 `<script>` 跑 `node --check`（本次主要语法风险是删字段后的尾逗号）
- ⚠️ **欠账**：`archive_dist/chat.html` 仍是未修复版本（对照组就是它）。离线档案是"二十年后还能打开"的那一份，**需重跑 `build_archive.py` 重打包**才能让修复进入 dist
- ✅ **T12a 大字说明卡完成**（09-09，DeepSeek 一轮 + Codex 一轮 ACCEPT）：`--intro-card` + `--intro-builder`（1–6 汉字校验）
  - **因用户裁决跳过当面知情说明，这张卡成为唯一告知渠道**：七条告知 + 「声音是合成的」+「我知道了」按钮，每次打开都显示（不写 localStorage），`removeChild` 移除（不用 `style.display`，避开 08-25 贴片事故）
  - 不传 `--intro-card` 时逐字节兼容，儿子版零影响（已实测）
  - **真机视口渲染验收**（Playwright iPhone 390×844）：全屏覆盖 390×844 / `position:fixed` / `z-index:9999` / 标题 26px·正文 20px·按钮 22px·按钮高 56px（均超 ≥18px 字、≥44px 触控要求）/ `elementFromPoint(中心)` 返回卡内 LI 证明真的挡住下层 / 点击后节点移除且输入框露出 / 重新导航后再次出现
  - 附带发现：`/health` 404 恰好证明 `ttsBase=location.origin` 生效（真实部署由 cloudflared ingress 路由到 8022）；`favicon.ico` 404 提醒 A1 主屏图标（#22 裁决 D1）仍是待办
- ⬜ T12b 老人 UX 其余项：抽屉锁定 / 错误文案人话化 /（~~TTS 周期重探~~、~~「她今天不在」离线页~~ 已由 T14-4 交付）/ Access session 过期时 fetch 收到 302 跳登录页而非 401 的降级
- ⬜ T12c A1 主屏 Web App：apple-touch-icon + manifest（#22 裁决 D1）
- ⬜ T13 `rhythm_dad.json` 按家庭群语料重算（家庭群中位 20 字 vs 私聊 15 字）
- 🔄 T14 运维自启（代码层全部完成并经 Codex ACCEPT；**剩部署与真重启验收=T14-6**。用户 09-09 裁决：自启方式取**开 Windows 自动登录**，已告知物理安全代价；token **加 --tokens-file**）
  - ✅ **T14-1 token 落盘**（DeepSeek 各 2 轮 + Codex 各 REJECT→ACCEPT）：`tts_server.py` +61/-3、`llm_proxy.py` +52/-3 新增 `--tokens-file`；错误不回显原值 / `utf-8-sig` / 空值 fail-closed / 两文件解析语义对齐。**实测生产进程命令行零 token**
  - ✅ **T14-2 `scripts/start_services.ps1`**（新建 1031 行，DeepSeek 9 轮 + Codex 3×REJECT→ACCEPT）：五服务编排 + 三模式（启动/-Status/-Stop）；三条件 skip、非匹配进程占端口 fail-closed 不杀、单实例 mutex、精确命令行匹配杀进程树、超时清理、日志时间戳保留 10 组、隧道每次重启以确保连接可确认
  - ⚠️ 隧道路径**未活体验证**（启 cloudflared = 开公网入口，需机主授权）；`-Status` 的 tunnel 仅进程存在检查，**不证明入口可用**
  - ✅ **T14-3 `scripts/register_startup_task.ps1`**（新建 303 行，DeepSeek 6 轮 + Codex 2×REJECT→ACCEPT）：注册器与任务运行器**同一文件**（`-Register`/`-Unregister`/`-Status`/`-Run`，杜绝两文件版本漂移）；登录触发 + 60s 延迟、`Interactive`+`Limited` 不存密码、`-Force` 原子替换、`ExecutionTimeLimit PT1H`、`IgnoreNew`。`-Run` 三次重试（120s 间隔），**exit 2 不重试、exit 3 不轻信**（改为跑 `-Status` 实测四服务全 `[ ok ]` 才报成功）。**端到端实测**：任务计划器触发 → `LastTaskResult: 0 (all services up)`；`-Run` 2.6–3.2s 返回
  - ✅ **T14-4 离线降级「她今天不在」四层**（DeepSeek 5 轮 + Codex REJECT→ACCEPT）：
    - L1/L2 `deploy/cloudflare-worker/dad-offline.js`（PC 关机/502 → 中文页，API 路径返 JSON，**自造响应带 `Cache-Control: no-store`**）**（09-10 已部署 v693b90d6；同日新增的出口缓存头版本待 `wrangler login` 后部署）**
    - L1'/L2' `people/mama_for_father/site/{offline.html,sw.js}`（用户自己断网 → SW 预缓存页；只拦 navigate，`/tts` 与 `/v1/chat/completions` **永不缓存重放**）
    - L3/L4 `build_companion_page.py` `--offline-fallback` + TTS 探活改重试（15s×24，覆盖 73s 冷启动）
    - **真浏览器实测**：SW 注册 scope `/` active → 停 :8021 → 显示「她今天不在」→ 恢复后自动跳回 companion.html；route-mock 造冷启动 → 16s 出提示、恢复 12s 出「她的声音准备好了。」；**儿子版默认参数产出零 SW 泄漏**（diff 仅重试改动）
    - ⚠️ 文案取**温情型**（用户 09-09 裁决），Codex 两轮独立指出拟人化风险，记为对铁律 2 的**显式覆盖**，复核日与 #24 三项对齐（2026-11-28）
  - ✅ **T14-5 `docs/ops-autologon.md`**（操作步骤，用户自行执行，Claude 全程不接触密码）：Autologon GUI（禁命令行传密码）+ **登录后自动锁屏任务**（把「物理接触即进桌面」降为「看到锁屏」，服务不受影响）+ ARSO 备选（不存密码但只覆盖补丁夜）+ 撤销与残余风险
  - 🔄 **T14-6 部署收尾**：
    - ✅ **重建爸爸站页面（2026-09-10）**：`build_companion_page.py --offline-fallback` 加 `--tts-origin same` / `--intro-builder 儿子`，token 从旧页面提取并与 `tokens.env` 的 `father:` 条校验一致后复用（全程不打印明文）。75592→76823 字节，与旧页 diff 只有两处（`probeTts` 返回 promise + `startTtsProbeLoop` 24×15s 重试、SW 注册 `/sw.js`）；十项结构探针 ALL PASS；儿子站 `people/mama/archive_out/companion.html` 字节未动
    - ✅ **L1'/L2' + L3 真浏览器实测（2026-09-10）**：页面自身注册 SW → scope `/` activated、预缓存 `/offline.html` → 停 :8021 → 显示「她今天不在」（四句逐字 + 截图人眼核对；有「再试一次」按钮证明命中缓存页而非 `inlineFallback()`）→ 恢复服务后自动跳回 companion.html；`pageerror` 0 条。本地 `/session` 404，档案零污染已核实
    - **踩坑记录（已写进 ops 文档）**：①原命令模板**漏了 `--tts-origin same`**，按文档照抄会让 ttsBase 变成 `https://dad.justmissingyou.com:8022`（该端口在 Cloudflare 上不存在）→ 爸爸完全没有声音；②原文档称 `--intro-builder` 反推不出来，实为构建期字符串替换，HTML 里可直接搜到；③**浏览器启发式缓存**：Python `http.server` 不发 `Cache-Control`，09-07 的 `no-cache` 只加在 data fetch 上、HTML 文档没有——重建后浏览器仍跑旧 HTML（栈回溯行号实锤），验收与爸爸设备都须强刷/加 `?cb=`
    - ✅ **部署 Cloudflare Worker（2026-09-10）**：走 wrangler 而非面板复制粘贴，配置入库 `deploy/cloudflare-worker/wrangler.toml`（`workers_dev=false`，只绑 `dad.justmissingyou.com/*`）。用户本人完成 `wrangler login` OAuth 授权（**scope 远超 Workers：含 ssl_certs/connectivity:admin/email_sending 等，建议用完 logout 或改最小权限 token**）。部署结果 `dad-offline` Version `693b90d6-ff26-43f4-8528-d5953ec13c79`，100% 流量，4.10 KiB，启动 7 ms。坑：`compatibility_date` 按 **UTC** 判定，本机 UTC+8 已 09-10 时填 09-10 被 API 拒（code 10021），改 09-09 通过
    - ✅ **Access 在 Worker 之前已实测确认**（此前仅推断）：未登录 curl `/companion.html` 返回 302 跳 cloudflareaccess 登录页，请求到不了 Worker → 离线页不对公众可见，符合设计
    - ✅ **L1 真实验收通过（2026-09-10）**：机主把自己邮箱加进 Access 策略（原 `allowed_emails` 只有爸爸一个，机主自己打不开站）后打开 `/companion.html`——隧道从未启动、源站真实不可达，正是 L1 故障态——**看到中文「她今天不在」而非英文 Error 1033**。`wrangler tail` 独立捕获 Worker 执行：`GET`/`HEAD /companion.html` 各两次 outcome `Ok`（02:14:25 与 02:15:50 两轮，间隔≈85s=离线页 60s 探针）。**这是文档里长期标注「至今没有真跑过」的那一层，现已关闭**
      - 附带验证一处易错设计：紧跟 GET 的 HEAD 是离线页自身探针，拿到 Worker 返回的 **503**（`buildOfflineResponse` 对非 API 路径返 503）→ `response.ok` 假 → 正确地留在原地。若兜底页写成 200，探针会误判恢复并把爸爸弹回打不开的页面
      - ⬜ **未验的另一面**：隧道起来后 Worker 对 `/tts`（音频）与 `/v1/chat/completions`（SSE 流式）的透明穿透。代码 `return await fetch(request)` 不缓冲 body，理论无碍但无实测，隧道首启后须专门确认
    - ⚠️ **Worker 是整条链的必经之地**：它若异常，爸爸的站整个不可用而不只是兜底失效。回滚 = `npx wrangler delete --config deploy\cloudflare-worker\wrangler.toml`（连路由一起删）
    - ✅ **隧道首次真启动（2026-09-10）**：4 条连接注册成功（hkg09/hkg13，http2）。**修掉一个从未被发现的致命错误**——`start_services.ps1` 把 `--config` 放在 `tunnel run <name>` 之后，cloudflared 报 `"tunnel run" accepts only one argument` 直接起不来；`--config` 是全局标志须前置。该路径此前只做静态审查。**教训：没有活体验证过的路径，不要安排在你不在场时第一次跑**（本轮临时把"先重启"改成"先启隧道"，正好躲过）
    - ✅ **端到端真机走通**（用户手机经隧道 + Access）：页面加载 / 说明卡 / SSE 流式逐字 / 语音条全部正常，Worker 对 `/tts` 与 `/v1/chat/completions` 的透明穿透**实测通过**
    - ⛔ **T14-5 自动登录：用户裁决跳过**。改为「重启后自己登录」；**服务不用手动起**——`ImissuStartServices` 是登录触发（60s 延迟、Enabled），登录即触发。已核实睡眠/休眠均为「从不」。代价=补丁夜重启到用户登录之间爸爸看到「她今天不在」（该层现已可用）
    - ⬜ **真重启验收**：该任务 `LastTaskResult = 267011`（`SCHED_S_TASK_HAS_NOT_RUN`），`-Register -Force` 重置过历史，**真重启将是其首次实跑，仍未验证**

### Phase 19：TTS 短句幻觉修复（2026-09-10 定根，**下回合第一件事**）— status: **根因已锁定，修法待 A/B 盲测**

> 现象：气泡「韫瑜，侬今朝哪能有空寻我讲话啦？」，语音是重复的「喔唷，喔唷」。用户已确认服务端 WAV 本身即如此（非播放/传输问题）。

- **根因在 CosyVoice 自己代码里**（`cosyvoice/cli/cosyvoice.py:94`）：`len(i) < 0.5 * len(prompt_text)` 即警告效果退化。我们的参考 `ref01_clip18` = **18.00 秒 / 90 字** → 警告线 45 字；而 8B-10 分条上限 30 字，**送进去的每一段都在警告区**
- **经验断点比警告线更低**：92 段统计中，所有离群点（>0.38 秒/字）**全部 ≤18 字**；22–38 字的段全部正常。真实的崖在 **~20 字**
- **提高分条上限（30→60）无效**（用户 09-10 提问，已答）：上限只影响**超限长行怎么切**，模型自己写出的 7 字短行不受影响，而翻车的全是短行。要拉长只能**合并**短行——但**她本人节律中位就是 17 字**，用长气泡迁就模型等于让她说话不像她，与铁律 2「尊重素材」冲突。**正确方向是把模型危险区往下压，不是把她的话往上拉**
- **wu 域比 mandarin 域差得多**（收工前补测）：wu 中位 0.453 秒/字、≤18 字短段翻车率 **86%**（14 中 12，n=18 噪声大）；mandarin 中位 0.277、27%（45 中 12，n=74）。**爸爸站正好用最不稳的那一档**。⛔ 不能因此改 mandarin——她跟爸爸说的就是上海话，铁律「尊重素材语言」挡住；此发现只用于**抬高本 Phase 优先级**（**2026-09-11 用户显式覆盖：爸爸站已改 mandarin**；本 Phase 对爸爸站的紧迫性下降，但 mandarin 短段仍 27% 翻车）
- ⬜ **修法一（主）**：加一条 ~12–16 字（3–4 秒）短参考并**按目标文本长度选参考**（危险线降到 ~7 字）。已从 99 条已校对转写筛出 **18 条 12–34 字候选**。⚠️ ref01–ref05 五条现有候选**全是 18 秒定长裁剪**，换哪条都一样，必须新切
- ⬜ **修法二（兜底）**：修好时长 QC。现有 `chars*0.32 + 2.0` 的**固定 +2.0 宽限在短句上完全压倒字数项**，24 条可疑只拦 4 条、漏 20 条；那句 16 字阈值 7.12s、实际 7.04s，**差 0.08s 溜过**。且重抽只比时长不看内容
- ⬜ **修法三（降级为可选）**：ASR 回读 CER 校验。仓库有现成配方（`gsv_pipeline.py` 用 funasr + `iic/SenseVoiceSmall`），但**对上海话的可靠性未验证**，可能误报连连并使每段延迟翻倍
- ⚠️ **必须先 A/B 盲测**：参考变短 = 音色信息变少，而音色是 M1 关口核心。现役为 SFT 微调模型、音色主要烘在权重里，判断风险不大，但**只能由用户耳朵裁决，不能由推理代替**。做法同当年选 epoch：同一批翻车文本 × 长/短参考 → 自包含 HTML 试听页 → SendUserFile

### Phase 20：运行期身份 + 聊天记录持久化（2026-09-10 用户立项）— status: **聊天记录持久化 ✅ 已上线（09-11）；运行期身份 待设计**

> 用户需求：reload 后聊天记录不丢（像微信）；**且同一站点上儿子与爸爸各自独立**。

- ✅ **聊天记录持久化 + 历史语音条（09-11，`36cbe32`）**：sessions 打开即加载，`replayHistory()` 回放全部保留会话（孤立发言跳过、不进模型上下文）；按段文本精确配对 `simulacrum_audio`，音频复制进 `sessions_data/<viewer>/audio/`，点击 fetch→Blob→复用 `replayBar`。**目前按站点隔离**，下面的身份方案落地前「同站点按人独立」仍未实现

- **前置缺陷（本轮暴露，比体验问题严重）**：`VIEWER` 是**构建期常量**，爸爸站写死 `'father'`。儿子在爸爸站说的话会被记成 viewer=father。本轮测试仅因用户勾了「本次对话不进记忆」才没进档案。**爸爸是唯一另一位 Tier-1 记忆确认人 → 属档案污染**
- **方向已定**：身份判定放**服务端**，用 Access 转发的 `Cf-Access-Jwt-Assertion` 头，而**不是**让页面 fetch `/cdn-cgi/access/get-identity` 后自述——后者只是把"写死的谎"换成"查过的话"，服务端依然在信客户端。`get-identity` 仅用于页面显示
- ⬜ **首要前置（未实测）**：确认 cloudflared 转发给源站的请求确实带 `Cf-Access-Jwt-Assertion`。需在 tts_server 上加一次性头部探针
- **存储：用户已裁决走服务端回放**（复用现有 `sessions/*.jsonl` + 按身份隔离的读接口）。爸爸的设备须在协议层拉不到儿子的对话
- 儿子站（:8020 无 Access）回落构建期默认值
- **09-11 实测污染规模**：father 名下 15 个会话 12 个是儿子测试（09-11 中午前爸爸根本登不进——OTP 未启用），其中 3 个进了爸爸的跨会话记忆 → ⏳ 待用户裁决 A（加入 `exclude.txt`）
- **09-11 发现**：儿子能在爸爸站看到爸爸的对话（白名单含机主邮箱 + 按站点读历史）；说明卡未告知「儿子能看到」→ ⏳ 待用户裁决 B
- 09-11 起儿子另有公网入口 son.（独立 Access 应用，见 Phase 23），测试应走 son 站
- ✅ **裁决 A 已执行（09-12）**：13 个儿子测试会话进 `exclude.txt` 并重摄入，爸爸历史只剩他自己 3 次
- ✅ **裁决 B：用户明确「不用处理」**——儿子能看到爸爸对话，维持现状（不加告知、不移邮箱、不做按人隔离）。**别再提议**
- ✅ 2026-09-12 用户确认无误：09-11 23:11（Windows 桌面 UA）与 09-12 11:27 爸爸站那次的归属判断都对，排除结果保持

### Phase 21：部署层站点清单（2026-09-10 用户立项）— status: **待设计**

> 用户需求：未来 people 下多个虚拟人 × 多个观看者站点，架构要模块化。

- **澄清：工具层早已 person-generic**（08-12 基线，`--person` + `relationship.json` + 参数化模板）。**写死的是部署层**：`start_services.ps1` 五服务端口常量、cloudflared 单 hostname ingress、单个 `wrangler.toml`、单份 `tokens.env`
- ⬜ 拟加一层站点清单（如 `deploy/sites.yaml`：person / viewer / port / hostname / lang / 关系配置），让上述四者全部由清单生成
- 排序建议：**排在 Phase 19、20 之后**——20 的接口形状会决定 21 的清单字段
- 09-11 起已有**两个公网站点**（dad. + son.）：`start_services.ps1` 六服务、ingress 两个 hostname、两个 Access 应用——都还是手写
- ⬜ T15 知情同意：大字一页 + 当面演示 + 日期写入 facets
- ⬜ T16 8A-2b b/d/e 欠账登记 + 三个月复核日（与 2026-11-28 对齐）

### Phase 22：爸爸站运维加固 + 刷新后历史回放（2026-09-10→11 通宵）— status: **complete（全部部署并验收）**

- ✅ **静态站缓存三层同治**（`55a6a24`）：`tools/static_server.py` 替掉 `python -m http.server`（no-cache + 304）；SW 后台预热；Worker 出口改写代码就位（⬜ 待 `wrangler login` 部署，已降为冗余）
- ✅ **502→424 语义冲突**（`4ce7c39`）：llm_proxy 上游失败改 424，响应不带上游 body；ingress 改 `127.0.0.1`
- ✅ **会话数据 viewer 隔离**（`d3d7fb4`）：爸爸站曾可直读 `data/sessions_owner.json`；迁至 `sessions_data/<viewer>/` + 爸爸站只联接 father 子目录；Codex 三轮
- ✅ **刷新后历史回放 + 历史语音条点播**（`36cbe32`）：见 Phase 20；Codex 页面 3 轮、数据层 6 轮（约 14 个 BLOCKER，五个是 Windows 大小写）
- ✅ 真 iPhone 实测（09-11）：暴露缺语音条（已修）与点击无声（研究中）→ 见 Phase 24；⬜ 被杀残留随机 `.tmp` 清理（NIT）

### Phase 23：儿子站公网入口 son.justmissingyou.com（2026-09-11 用户立项）— status: **complete（已上线；09-12 用户实测发现两 bug，均已修）**

- 用户裁决：只开陪伴页（不挂整个 :8020）/ 域名 son. / 方案 A（独立站点目录，边界靠目录联接不靠路由正则）
- ✅ Access 应用「son」（用户建，只放机主邮箱）→ ✅ DNS + 未登录全路径 302 → ✅ `people/mama_for_owner/site/` → ✅ `son-public` :8024（`start_services.ps1`，Codex REJECT→ACCEPT）→ ✅ ingress 2 条 → ✅ 隧道重启（09-11 12:53）
- ✅ 顺带：`register_startup_task.ps1` 兜底健康检查恒为 False 的旧 bug
- ✅ 用户手机实测（09-12）：登录通；发现「看不到任何历史」与「每站都要重填 key」两个问题 → 均已修（历史不再依赖 API key；构建期内置默认 key，Codex 三轮 ACCEPT）
- ✅ 修完后的手机复测（2026-09-12 用户确认：不配 key 就能看到历史、可直接发消息）
- 设计 `docs/superpowers/specs/2026-09-11-son-public-site-design.md`；运维 `docs/ops-son-public-site.md`

### Phase 24：历史回放真机问题（2026-09-11 真 iPhone 首测）— status: **缺语音条 ✅ 已修；点击无声 2026-09-12 用户复测报正常**

- ✅ 缺语音条：`/tts` 写音频记录也触发摄入（Codex 两轮 ACCEPT，真实流量验证）
- ✅ 点击无声：2026-09-12 用户复测「没问题」。⚠️ **未区分是哪一种**——若当时是「关掉标签重开后才出声」，那就是 H1（跨刷新粘连的 AudioContext），**问题会复发**；下次再遇到直接按 H1 修（每次播放前按状态 resume、假 running 时 suspend+resume、切后台主动挂起），不必再做判别
- 修法方向：H1 = 每次播放前按状态 resume、假 running 时 suspend+resume、切后台主动挂起，根治 = 声音不经 Web Audio（`<audio>` 直出 + 预算音量包络驱动口型）；H2 = 历史音频出 MP3 副本 + `replayBar` 失败不再静默复位

### Phase 17：VoiceStudio 能否取代本地 TTS（2026-09-08 用户立项）— status: **research complete**（09-08 收口）
> 用户指令："立项：研究下这个项目是否能取代我的本地 tts https://github.com/debpalash/VoiceStudio"
> 硬门槛（研究判据）：① 能否加载我们自训练的 CosyVoice2 全量 SFT e14 检查点（否则等于换掉她的声音）② 能否说上海话 / 支持 `<|wuyu|>` 类语言标记 ③ 是否全离线（云 TTS = 铁律 3 直接否决）；另需对照 `tools/tts_server.py` 现有能力（起音淡入 / 分句流水线 / token / sessions 日志 / 去抖摄入 / viewer 白名单）逐条评估重写成本
- ✅ 收口（09-08）→ `docs/research/voicestudio-vs-local-tts.md`。**结论=不能取代引擎层，服务层可借鉴不可搬**
- 决定性断点：它的 CosyVoice adapter 只接受**模型目录**（`OMNIVOICE_COSYVOICE_MODEL`），无注入外部 state_dict 的钩子；我们的音色是运行时 `llm.load_state_dict(filtered, strict=False)` 打上去的补丁（`tts_server.py:182-186`），按它的方式跑加载的是 WenetSpeech-Wu **基座不是她**；且 SFT 分支硬编码 `spks[0]` 无 speaker 入口、`LANG_TAGS` 无 `<|wuyu|>`、打包版今天没有受支持的 CosyVoice 运行时安装路径
- 两条伤档案的默认行为：**AudioSeal 隐形水印默认开**、**输出默认响度归一化到 −2.0 dBFS**（默认会改她声音的字节）
- **AGPL-3.0 与 F-乙 直接相关**：本机自用无义务，但 F-乙 要把服务开给爸爸访问，若服务层含其代码，§13 网络条款传染
- 可借鉴（零许可风险，只抄接口形状）：① `/ws/tts` 式流式 PCM16 ~200 ms 分块 + 句级并行 + `ttfa_ms`/`rtf`（对 F-乙 两人排队最有价值）② `/v1/audio/speech` OpenAI 兼容契约 ③ loopback 不鉴权 / 非 loopback 三道闸
- ⬜ 待用户裁决 P1（流式 + 首音延迟指标立项）/ P2（兼容端点）/ P3（记入 GENERALIZATION 作泛化线候选）——均非阻塞，推荐都做但排在 F-乙 之后
- ⚠️ 核实缺口：对抗校核 6 个 agent 因 `403 Request not allowed` 未执行，VoiceStudio 侧论断只经一轮调查（均带源码行号证据），动工程前需实机复核

### Phase 18：图片输入可行性（任务 #25，2026-09-08 用户立项）— status: **research complete**（09-08 收口）
> 用户指令："立项：研究文字以外，是否可以支持图片输入"
- ✅ workflow 四维调查 + 对抗校核（wf_19ce7bb8-888，12 agents 全部完成 0 失败）→ `docs/research/companion-image-input.md`
- **结论：「让她看照片」默认 NO-GO**——铁律 2.3 判定为纯沉浸增量（不产生任何档案条目）；**现有六条铁律没有一条挡得住**（铁律 1/2 只在"档案里没有"时触发，而模型看图时它自己就是信息源，于是 100% Tier-3 的视觉推断读起来像 Tier-1）
- 对 #24 爸爸场景额外风险：**污染 Tier-1 证人**（他是唯一另一位记忆确认人，模型先给一个编造的"这是 1998 年在杭州"，他之后的 Tier-1 确认已被 Tier-3 锚定——污染的是档案本身）
- 三条独立技术否决：①默认服务商 DeepSeek 的 `deepseek-v4-flash` **不支持图片**（只有 `deepseek-v4-flash-vision-exp` 能收图，其余 400 `This model does not support image`）②Anthropic 官方明写"cannot be used to name people in images and refuses to do so"，而核心场景正是"这是谁"③改动量最小约 15 处跨 4 文件，检索会失效（图片产出零 token → 检索块为空 → 与铁律 2 对撞），history 12 轮重放 base64 payload 爆炸
- 唯一"只增强档案不增加编造"的用法（§4）：**图片当时间锚不当画面**——人填日期（非模型猜）→ 按 ISO timestamp 检索她那几天真说过的话 → 图片根本不进 payload。零多模态、能进静态档案
- ⭐ **挖出两件正事**：**A 档案照片层是空的**（`media_index.json` 零 photo、983 条图片消息只剩「[图片]」占位符、raw/photos 仅 10 张且 EXIF 全空），而 **`tools/ingest_media.py`（773 行含 EXIF 提取）已写好从未跑过**、微信图片 md5 就在 `packed_info_data`、`collect_wechat_video.py` 已跑通同一条链——照片收集器基本是它的克隆，**推荐立项**；**B 两个既有缺陷**：`prompts/chat_system.zh.md:1` 对模型说"档案由消息、语音和照片构成"而照片不存在（**立即修**）、`companion.html` 压根不在 archive_dist（`build_archive.py` 白名单只有 avatar+chat 且扫尾会删白名单外文件）
- ⬜ 待用户裁决：图片输入 NO-GO 是否认可 / 时间锚用法是否做 / **A 补照片层是否立项** / B1 措辞立即修 / B2 companion 不进 dist 是欠账还是故意
- 校核推翻 1 条：「请求路径只有一处 isAnthropic 分支」错——`:883` 还有按 URL 正则注入的 `thinking:{type:'disabled'}`，且 isAnthropic 派生四处分歧；把改动量估成"只改一处"会显著低估

## 决策记录
- 2026-08-09 用户拍板 MVP 范围（本文件顶部指令）
- 语音层不等校对：31 条先行 + 45 条满血两步走（校对是用户异步动作）
- 2026-08-21 用户裁决：家人盲听 v2 移除，M1 以本人盲听关闭
- 2026-08-23 用户判死双帧口型架构（"这个技术有问题"）→ 立项 #17 渲染研究
- 2026-08-27 用户定稿 Phase 1 贴片（"先按照这些定稿"：W1/R1/嘟唇并入/B1）
- 2026-08-28 用户裁决"继续推进桌面陪伴"（上限形态"打开才在"，条件 a-f 硬规格）；同日裁决蕾咪方案甲先 + iPhone/Mac/PC 三平台硬要求
- 2026-08-29 用户否全身化，维持半身框
- 2026-09-01 用户定稿情绪贴片四情绪均 s5002；同日裁决移除四项待办（601 敏感复核 / persona Q1-Q13 / DeepSeek key 轮换 / 拟音词释义）
- 2026-09-02 用户立项 #22：iOS 专属 App 部署 + 0→1 建档 App 产品化研究（Phase 12）
- 2026-09-03 用户裁决 #22-a：A1 主屏 Web App 接受（8A-2b 先行）/ https 跳过 / A3′ 有声档案立项（Phase 13）/ A2 壳暂不做 / PC 常开手动拉起服务
- 2026-09-06 用户立项 #23（Phase 14）：把 09-04 晚与数字人的对话截图发给了爸爸，爸爸很触动 → 要把图中数字人的六段回复整段合成她的声音发给爸爸。**这是"家人向"的第一次实际使用，由用户本人决定（研究裁决的家人向默认 NO-GO 被用户在知情前提下针对此单次覆盖）**
- 2026-09-05 用户反馈（看 sessions 日志后）：默认发微信式语音条（点一下回味）+ 下方转写文字；回复过长不出声→每条 ≤30 字分条各自合成（先试试）→ 8B-10；#22-b 裁决 E1–E6 推迟
- 2026-09-01/02 用户提出多服务商抽屉、sessions 日志、TTS 剥括号、分句语音流水线+「正在输入」（均已实现，E2E 通过；真机完整验收待续）

- 2026-09-08 用户立项 #25 图片输入研究（Phase 18，同日收口 NO-GO + 挖出补照片层正事）
- 2026-09-08 T7 完成：`build_chat_context.py` 加 `--relationship` + 三占位符（DeepSeek 写 → Codex 两轮 REJECT→ACCEPT → 落盘；顺带修好 taboo_topics 从未进提示词的既有缺陷）
- 2026-09-08 用户裁决 #24 全部 19 个点并选定 F-乙 路线开工（详见 Phase 16 裁决表）；同日立项 Phase 17（VoiceStudio 评估）；追加指令：爸爸相关产物一律进 `people/mama_for_father/`，儿子视角部分零改动
- 2026-09-07：用户裁决清除"凯西"相关记录（第三方前配偶，数字人误当现任）：全删 174 条派生层记录（raw 不动）+ persona 引文名字改〔前儿媳〕+ 日志/导出涂改 + 暂不写"兔兔"Tier-1 卡。快照 `versions/pre_kaixi_scrub_20260907/`。执行见 progress 09-07 上午段。

- 2026-09-10 用户裁决：缓存三层全做（源站 + Worker + SW，不加版本自检）；502 语义冲突与 ingress IPv4 两个都修
- 2026-09-10 用户裁决：聊天记录回放顺序「隔离 → 文字回放 → 音频回放」；回放全部保留会话、孤立发言跳过、回放不进模型上下文
- 2026-09-10 用户裁决：Codex 额度用尽时等恢复再终审（不跳过铁律 1）；随后改用 `gpt-5.6-sol` 审核（astra 用量太重），删除 Claude Code 的 codex MCP 配置（codex 0.154.0 已移除 mcp-server）；CLAUDE.md 铁律 1 的 Codex 行保持原文不改
- 2026-09-11 用户裁决：儿子站公网入口——只开陪伴页、域名 son.、方案 A（独立站点目录）；用户自建 Access 应用「son」
- 2026-09-11 用户在 Zero Trust 启用 One-time PIN（爸爸站此前只有 Cloudflare 账号登录）
- 2026-09-11 用户裁决：爸爸站改普通话语域（**显式覆盖**「尊重素材语言」与 #24「语音 wu 域」，Claude 已提示她跟爸爸说上海话）
- 2026-09-11 提出、2026-09-12 用户裁决：**A = 排除**（13 个会话已进 `exclude.txt` 并重摄入）；**B = 不用处理**（儿子能看到爸爸对话，维持现状）
- 2026-09-12 用户指令：**更新 CLAUDE.md 铁律 1**（覆盖 09-10「Codex 行保持原文不改」）——审核 Codex `gpt-5.6-sol` 走 CLI，写码 DeepSeek `deepseek-flash`；并要求实测 `deepseek-v4.1-flash`（结论：不存在）
- 2026-09-12 用户要求：所有站「API key 填过一次就存住」→ 实现为构建期内置默认 key（key 明文进 HTML，用户知情）
- 2026-09-12 用户裁决：**写码通道换成 Opus 子代理**（`.claude/agents/coder.md`），`/deepseek` skill 与调用脚本删除、不保留为备选；审核仍为 Codex CLI。`DEEPSEEK_API_KEY` 只留聊天用途（llm_proxy + 儿子站页面内置 key）

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| DeepSeek 32k/60k 推理烧光正文 | 3+3 次 | 已解决（Phase 0，08-10）：根因=推理链烧光 token，deepseek_call.py 加 DEEPSEEK_NOTHINK=1（thinking:disabled）；流式与 max_tokens≥32000 为 08-04 既有实践、非本错修法 |
| 纸片人贴片 `style.display=''` 被类规则回落吃掉，从未渲染（08-25） | 1 | 显式 display='block' + computed style/截图 diff 验收铁律（findings） |
| Playwright 截图 DPR 1.5× 致像素 diff 假阴性（09-01） | 1 | CSS 坐标乘 DPR + 人眼对照图 |
| PowerShell 按 CommandLine 杀 tts_server 时杀掉自己（09-01） | 1 | 过滤加 Name='python.exe' |
| 缓存治理首版 `fetch(request, init)` 会降级 navigate、破坏 Access 302（09-10） | 1 | 改为普通 fetch(url) 预热 + cf 选项只给非导航的 /sw.js（Codex 抓） |
| 以为 503 是自己的 IPv4 改动引起（09-10） | 1 | 实测旧 http.server --bind 127.0.0.1 同样只绑 IPv4；真因是 502 语义冲突 |
| codex MCP 404 → 实为 Surfshark 拦 WebSocket + 模型名过时 + MCP 进程停在旧版（09-10） | 5 | Bypasser 加 node.exe；codex 0.154.0 移除 mcp-server，改走 CLI |
| DeepSeek 替换对臆造多行签名锚点（09-10） | 2 | 逐对统计出现次数定位；只修锚点，新增内容取自它自己的 OLD→NEW 差异 |
| 验收脚本从 offline.html 清 localStorage 与其自动跳转竞态（09-11） | 1 | 改在不会跳转的同源 JSON 页上清理 |
| 超长内联 Bash 命令（多重 heredoc + 引号）解析失败（09-11） | 1 | 改为 Write 工具写脚本文件后执行 |
| `Test-ServicesHealthy` 恒为 False：`Start-Process -PassThru` 未缓存 Handle，ExitCode 为 `$null`（09-11） | 1 | 两处 Start-Process 后缓存 Handle；AST 取函数隔离红/绿 |
| PowerShell `& python … \| Select-Object -First 1` 掐断进程，`$LASTEXITCODE` = -1（09-11） | 1 | 先完整接住输出再判退出码 |
| Git Bash 把中文 JSON 当参数传 curl → 服务端 400 invalid JSON（09-11） | 1 | 改用 Python urllib |
| 新 hostname 建 DNS 后本机仍 000：DNS 负缓存（09-11） | 1 | `curl --doh-url` 或 `ipconfig /flushdns` |
| 儿子站空 localStorage 时整页没有历史（09-12） | 1 | 历史渲染不再依赖 `settingsComplete()`；提示改为追加不清空 |
| 内置 key 被写进「当前」服务商档位，可能发到别家端点（09-12，Codex MAJOR） | 1 | 只写 `DEFAULT_PROFILE.provider` 档位 |
| 保护文件名 `chat.html` 比较区分大小写，Windows 上 `CHAT.HTML` 绕过（09-12，Codex MAJOR） | 1 | `basename().casefold()` 后比较 |
| Python 字符串里 `\a` 把文档路径写坏成 BEL 控制字符（09-12） | 2 | 用 `chr(92)` 拼反斜杠；写完读回并扫控制字符 |
