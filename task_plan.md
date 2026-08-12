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
- 完成标准：有一版用户认可"可进盲听"的模型（✅ full44 e14）+ 批量合成脚本（1f）

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
- ✅ 3c 两件全完成：①tools/extract_memory_candidates.py 闭环入库（7f34bb4，150 条候选）；②tools/render_timeline.py 闭环入库（2026-08-12，DeepSeek×3 + Codex REJECT→ACCEPT：gap 锚定月修正/ASCII 路径/死代码清理，合成缺月用例验证）→ **memories/timeline.md 已产**（68 月无缺口，头部对账 20909/9373 与清理后 UIF 精确一致）
- ✅ 3d 闸门页+apply 双工具闭环入库（2026-08-12，Codex 三轮 REJECT→REJECT→**ACCEPT 零发现**）：tools/make_gate_page.py（150 卡 192KB 自包含移动页，敏感可见文本预标记 6 条默认剔除，localStorage 草稿，回贴码 delta 契约）+ tools/apply_gate_decisions.py（多文件 later-wins 合并、```json 围栏容忍、action confirm/reject/pending 三态、敏感复检 confirmed_flagged、幂等重生成 memories.md Tier-1）。**审核升级：Codex 与 Claude 双方均用 Node stub-DOM 实际执行页面 JS 验证契约七场景矩阵**（工具 harness 存 scratchpad/gate_harness.js，抓到 v2 的"未动卡片全量导出"High 实锤）→ **gate_page.html 已发用户手机，等回贴码** → apply 后产 memories/memories.md（Tier-1）
- 完成标准：persona/ 与 memories/ 目录齐备，Tier 标注完整，闸门页可用（✅ 工具链全备；剩余为用户动作：persona Q1-Q13 确认 + 闸门页回贴码 → apply 出 memories.md）

### Phase 4：卡通人（消费端）— status: 4e-集成 complete（2026-08-12），剩 4c（等盲听）/4d
- ✅ **4e-集成完成（2026-08-12，DeepSeek×2 + Codex REJECT→ACCEPT 零发现 + 两处声明 hotfix）**：build_avatar_page.py 图片头像模式——`persona/avatar.png`（静息帧=定稿笑容）+ `persona/avatar_open.png`（说话帧，Qwen-Image-Edit seed1002 生成，1001 背景跑偏/1003 眼翻白已淘汰，溯源入 avatar_choice.json open_frame 块）按音量双帧切换（纯函数 mouthFrameFor：0.04 阈值经 Codex 用 125 条真实语音 RMS 分布验证 + 90ms 帧保持 + 假驱动交替）+ bob 弹动；资产 reconcile 进 archive_out/data/avatar/（陈旧自动清理）；无头像人物回退 SVG（person-generic 保持）；预览页 Pillow 降采样内嵌 0.26MB
  - 审核实录：Codex R1 REJECT 抓 #avatar 契约破坏（图片模式 TypeError，我方 harness stub 过宽漏过）+ 陈旧资产不清理；R2 双方各自用"忠实 stub"（缺失 id 返回 null + rAF/play/pause 派发）执行双页全脚本干净 → ACCEPT。hotfix×2（声明）：JS 常量未定义补两行、Python 层死常量三行删除
  - 验证方式：LAN http://192.168.3.69:8020/avatar.html（8020 服务在跑）；两帧图已发用户手机（用户可否决说话帧，重抽即换）
- ✅ tools/build_avatar_page.py（DeepSeek×5 轮 + Codex×3 轮）：archive_out/avatar.html（37KB）+ start_server.bat/.sh——SVG 卡通（圆脸眨眼腮红，非真人脸）+ AnalyserNode 音量驱动嘴型 + 600ms 静音伪驱动 fallback + 125 条原声播放列表（data/media/voice 相对路径）+ 续播守卫
- ⬜ 4c 合成语音入清单（等 v0.1 epoch 定稿后把 TTS 样本放 data/media/tts/）
- ⬜ 4d BYOK 对话页（Tier-3 禁陈述为事实的提示词）
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

### Phase 5：合流交付 — status: pending
- build_archive：数据层+文字层+语音样本+卡通人页打包为自包含档案目录
- 完成标准：整个 archive_out 拷走后在无网机器可打开

## 决策记录
- 2026-08-09 用户拍板 MVP 范围（本文件顶部指令）
- 语音层不等校对：31 条先行 + 45 条满血两步走（校对是用户异步动作）

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| DeepSeek 32k/60k 推理烧光正文 | 3+3 次 | Phase 0 处理中：参数探测 + spec 拆小 |
