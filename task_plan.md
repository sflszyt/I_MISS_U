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
- ⚠️ **敏感记录处理（用户已拍板 2026-08-12：删除）**：2024-02-09 凭据交接批（账号密码/记账/抗癌药记录）从**全部派生层删除**——normalized UIF、archive_out/data 年度分片、memories/candidates.jsonl、persona_digest.json；**raw/ 保留不动**（铁律 1 只读且永不出机）。实现（下回合首要工程项，DeepSeek 写 + Codex 审）：清理工具走"凭据模式扫描 + 用户指认 record_id 清单"双通道 → 删除后重跑 bundle/candidates/digest 保证无残留 → 闸门页对疑似敏感候选默认剔除。**此步骤已泛化为任何人物管线的标准关卡**（记忆 sensitive-data-cleanup.md）
- 🔶 3c 两件：①tools/extract_memory_candidates.py（DeepSeek）——确定性信号挖候选：事件关键词簇（关键词表外置配置，通用非 mama 专用）/长消息/同日媒体爆发/≥30s 语音/年度首次，输出 memories/candidates.jsonl（Tier-2 带 source ids+日期+摘录）；②timeline.md 复用 archive_out/data/timeline 月度数据渲染人读版（Tier-2）
- 🔶 3d tools/make_gate_page.py（DeepSeek）——人工闸门移动页（沿 R2 定型模式：<1MB/大按钮/回贴码只含改动项/dataset hash 校验）：候选卡逐条 确认/改写/拒绝 → 回贴码 → apply 工具合并出 memories/memories.md（Tier-1）
- 完成标准：persona/ 与 memories/ 目录齐备，Tier 标注完整，闸门页可用

### Phase 4：卡通人（消费端）— status: 4a-4c complete（Codex ACCEPT），4d 未做
- ✅ tools/build_avatar_page.py（DeepSeek×5 轮 + Codex×3 轮）：archive_out/avatar.html（37KB）+ start_server.bat/.sh——SVG 卡通（圆脸眨眼腮红，非真人脸）+ AnalyserNode 音量驱动嘴型 + 600ms 静音伪驱动 fallback + 125 条原声播放列表（data/media/voice 相对路径）+ 续播守卫
- ⬜ 4c 合成语音入清单（等 v0.1 epoch 定稿后把 TTS 样本放 data/media/tts/）
- ⬜ 4d BYOK 对话页（Tier-3 禁陈述为事实的提示词）
- 🔶 4e 形象升级（2026-08-11 用户反馈"太卡通"）：**照片→风格化卡通头像**，全本地（铁律 3）。调研定稿 docs/research/photo-cartoon-avatar.md（首选 Qwen-Image-Edit-2509 Apache-2.0）；用户已放 10 张照片进 raw/photos/。**2026-08-12 进展**：ComfyUI 起服 + 官方 2509 管线探针 70s/张跑通；tools/gen_avatar_candidates.py 三轮闭环（DeepSeek×3 + Codex REJECT→ACCEPT with fixes→diff 验证）；30 张候选（10 照 × warm/watercolor/flat × s1000）批量生成中；拼图工具 make_contact_sheet.py Codex 审核中 → 拼图发手机挑选
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
