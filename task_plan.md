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

### Phase 1：语音层 — status: in_progress（1a/1b/1d 完成，等用户两项反馈）
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

### Phase 3：文字层 — status: in_progress（3a 完成，2026-08-12 全面开工）
- **设计基线（2026-08-12 用户重申）**：项目未来泛化到一切人物（父母/配偶/子女/朋友/anyone），MVP 基于 mama。**所有 Phase 3 工具必须 person-generic**：吃 `--person <slug>` + UIF，人物/关系特定内容全部进 `people/<slug>/persona/relationship.json` 配置与 prompts/ 参数化模板，工具代码零硬编码人名/关系
- ✅ 3a tools/build_rhythm.py（DeepSeek×3 轮 + Codex×3 轮 ACCEPT）：persona/rhythm.json + archive_out/data/rhythm.json——9386 条 subject 消息的长度/时段/连发/回复延迟/标点/口头禅23条/表情/语音习惯，精确 skip 计数
- ✅ 3b-① tools/extract_persona_digest.py 闭环入库（1afd573，DeepSeek×3 + Codex 三轮 + sender hotfix）；实跑产出 206KB persona_digest.json（分年样本/14 对话窗口/9 组关键词，全带 record_id）
- 🔶 3b-② persona.md 草稿完成（2026-08-12 深夜，Claude 子代理起草）：46 条论断 T01-T46 逐条带 record_id 证据 + 待确认清单 Q1-Q13，含"缺点与冲突面"9 条（铁律 2 达标），全文 Tier-3 标注 → **等用户逐条确认**（最优先 Q1 身份对应：郑韫瑜=爸爸/王铮=妈妈本人 系推断）
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
- 完成标准：persona/ 与 memories/ 目录齐备，Tier 标注完整，闸门页可用（✅ 工具链全备；剩余为用户动作：persona Q1-Q13 确认 + 闸门页回贴码 → apply 出 memories.md）

### Phase 4：卡通人（消费端）— status: complete（口型架构后续被 Phase 7 全面取代，见下）
- ✅ **4e-集成完成（2026-08-12，DeepSeek×2 + Codex REJECT→ACCEPT 零发现 + 两处声明 hotfix）**：build_avatar_page.py 图片头像模式——`persona/avatar.png`（静息帧=定稿笑容）+ `persona/avatar_open.png`（说话帧，Qwen-Image-Edit seed1002 生成，1001 背景跑偏/1003 眼翻白已淘汰，溯源入 avatar_choice.json open_frame 块）按音量双帧切换（纯函数 mouthFrameFor：0.04 阈值经 Codex 用 125 条真实语音 RMS 分布验证 + 90ms 帧保持 + 假驱动交替）+ bob 弹动；资产 reconcile 进 archive_out/data/avatar/（陈旧自动清理）；无头像人物回退 SVG（person-generic 保持）；预览页 Pillow 降采样内嵌 0.26MB
  - 审核实录：Codex R1 REJECT 抓 #avatar 契约破坏（图片模式 TypeError，我方 harness stub 过宽漏过）+ 陈旧资产不清理；R2 双方各自用"忠实 stub"（缺失 id 返回 null + rAF/play/pause 派发）执行双页全脚本干净 → ACCEPT。hotfix×2（声明）：JS 常量未定义补两行、Python 层死常量三行删除
  - 验证方式：LAN http://192.168.3.69:8020/avatar.html（8020 服务在跑）；两帧图已发用户手机（用户可否决说话帧，重抽即换）
- ✅ tools/build_avatar_page.py（DeepSeek×5 轮 + Codex×3 轮）：archive_out/avatar.html（37KB）+ start_server.bat/.sh——SVG 卡通（圆脸眨眼腮红，非真人脸）+ AnalyserNode 音量驱动嘴型 + 600ms 静音伪驱动 fallback + 125 条原声播放列表（data/media/voice 相对路径）+ 续播守卫
- ⬜ 4c 合成语音入清单（等 v0.1 epoch 定稿后把 TTS 样本放 data/media/tts/）
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

### Phase 8：桌面陪伴型数字人可行性研究（任务 #18，2026-08-27 用户立项）— status: **research complete，等用户裁决 go/no-go**
> 用户指令："研究是否可以构建桌面陪伴型数字人，用户利用打字或语音与他/她进行交互，她返回语音或文本"
- ✅ 研究执行（workflow wf_c886ce8b-4b8：6 维并行 + 8 条载重论断对抗校核，6 confirmed/2 refuted，含 4 组本机实测探针——CosyVoice 流式首包 2.2-4.4s / GSV 流式 ~1.07s / SenseVoice 0.1-0.4s / Rhubarb 每句 +1.1s）
- ✅ 报告成文 `docs/research/desktop-companion.md`：**技术=拼装级可行**（三积木全在库，缺口只是合流页+壳+语音输入；avatar RMS 分支与 chat TTS 语音条"各持一半"，blob 接 analyser 即通）；壳选型两轨（轨0 Edge --app 零代码 / 轨1 Tauri v2）；对话层 BYOK DeepSeek 主线（thinking:disabled 一行修正）；**伦理三档判定：常驻桌宠不应做 / 上限形态="打开才在的档案对话窗口"（条件 a-f：只应答/关窗道别/Tier 标签不减配/真实节律限速/使用统计自见+三月自查/预写告别协议）/ "维持现状不做"是合理默认**
- 校核两翻案入 findings：上海话本地 ASR 存在（Dolphin zh-SHANGHAI，待实测）；"本地 LLM 只能 8-14B"推理链不成立
- ✅ **用户裁决（2026-08-28）："继续推进桌面陪伴"** → 按报告第七节 Phase A 开工，上限形态（打开才在的对话窗），条件 a-f 全部为硬规格；常驻/托盘/自启/主动搭话永久排除
- **架构决策（2026-08-28）：iframe 组合，非大合并页**。companion.html `<iframe>` 内嵌现有 avatar.html（face-only），父页放对话 UI，TTS blob 喂给 iframe 的 audio#player（匹配不到时间轴→RMS 口型）。理由=避免重构 1941 行、避免触碰已像素验收上线的 avatar.html；avatar 仅两处追加式默认不变小改。同源 iframe 直接 contentWindow 存取
- **Phase 8A 开工清单（2026-08-28）**：
  - ✅ 8A-0 告别/降级协议 docs/companion-farewell-protocol.md（条件 f，Claude 起草用户可改；第五格留用户填）
  - ⬜ 8A-1 build_avatar_page.py 两处追加式小改（DeepSeek+Codex）：①face-only 显示模式（?mode=face 隐藏播放列表 chrome 只留脸）②接收外部音频（postMessage/或父页直接设 audio#player.src 播 TTS blob 触发 RMS 口型）。**验收=无参数/无消息时 avatar.html 重建字节级一致 + 像素级口型复验**
  - 🔶 8A-2a **核心闭环完成**（2026-08-28，DeepSeek 写 + Codex REJECT→REJECT→ACCEPT + 声明 hotfix）：tools/build_companion_page.py 入库；companion.html（父页 iframe avatar.html face-only + 复用 chat 三源检索/SSE 双协议/buildMessages/TTS → blob 路由进 iframe audio#player 触发 RMS 口型）。Codex 两轮抓 3 BLOCKER（三源检索退化/分片键名 data.shards→message_shards/加载时序无门控）+ 2 MAJOR（停止按钮禁用/saveSettings 提前放行与并发双发）；DeepSeek 整函数重生成漂移严重（标识符全猜错）→ 改外科式声明 hotfix + contextLoaded/sendPending 双门控（比 chat.html 更严）→ ACCEPT。Codex 误报 1 条（send 监听被注释吞，cat -A 实证独立成行）。**真浏览器冒烟全绿**：iframe 同源可存取+player 可达+chrome 隐藏脸可见+抽屉+两处非本人标识+deepseek-v4-flash 占位符（console 仅 favicon404+TTS未启二良性）。thinking:disabled(仅 deepseek 端点)+占位符修正一并落地（8A-3 折入）
  - ⬜ 8A-2b 条件 a-e 伦理护栏：关窗道别语（取 rhythm/语料 Tier-2）+ 空闲「去忙了」离场 + rhythm.json 真实节律限速 + 使用统计自见卡（首页/三月自查）；另修 contextLoaded 混用「未加载/已失败」两义的非阻塞瑕疵
  - ⬜ 8A-3 chat 构建器两处小修（payload 加 thinking:{type:disabled} 仅 endpoint 含 deepseek 时 + 占位符 deepseek-chat→deepseek-v4-flash；companion 与 chat.html 同源共享，一并修）
  - ⬜ 8A-4 轴五 sessions 采集：tts_server.py 加 POST /session → people/<slug>/sessions/*.jsonl（第二纪元，数字人话语永久 Tier-3）
  - ⬜ 8A-5 壳=Edge --app 快捷方式（刻意不自启不置顶）+ Playwright 真浏览器验收 + 像素级口型验收 + 用户真机验收

### Phase 9：蕾咪桌宠效果研究（任务 #19，2026-08-28 用户立项）— status: **research complete，等用户裁决 8B 方向**
> 用户指令："立项研究 kira-remy-official，我想把数字人做成这种效果"
- ✅ 仓库全量克隆逐行拆解（~14k 行 Python）+ 本地 v1.2.1 实装对照 → `docs/research/kira-remy-analysis.md`
- 核心发现：**"效果"=透明无边框桌宠立绘窗+情绪表情立绘切换+打字机气泡**；技术栈仅 PyQt5+8 张 PNG（无 Live2D/无语音/口型仅 Open-Shut 双帧）；完全开源可二创，无 20 年红线冲突
- 对照判定：口型/语音/人格/记忆四项我们领先；**要补的只有情绪表情资产 + 桌宠壳形态**
- 落地候选（等裁决）：**方案甲**=companion 页内补情绪表情层（ComfyUI 情绪贴片 4-6 个+用户定稿闸门+关键词驱动，资产两形态通用）→ **方案乙**=桌宠壳（PyQt5 QWebEngineView 透明窗装我们 HTML 运行时 / Tauri v2；仍守"打开才在"：无托盘无自启关窗道别）；推荐甲→乙
- 借形不借魂：蕾咪的常驻/主动搭话/游戏化/恋人模式/云识图全部排除（条件 a-f 与铁律 3）

## 决策记录
- 2026-08-09 用户拍板 MVP 范围（本文件顶部指令）
- 语音层不等校对：31 条先行 + 45 条满血两步走（校对是用户异步动作）
- 2026-08-21 用户裁决：家人盲听 v2 移除，M1 以本人盲听关闭
- 2026-08-23 用户判死双帧口型架构（"这个技术有问题"）→ 立项 #17 渲染研究
- 2026-08-27 用户定稿 Phase 1 贴片（"先按照这些定稿"：W1/R1/嘟唇并入/B1）

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| DeepSeek 32k/60k 推理烧光正文 | 3+3 次 | Phase 0 处理中：参数探测 + spec 拆小 |
