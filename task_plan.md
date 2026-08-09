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
- ⬜ 1c 管线加固（空token fail-fast / parquet 命名 / accum_grad flush / listen_page 两处 minor）→ 与 1e 合并做
- ⬜ 1e 用户校对回收后 45 条满血重训 v0.1-full
- 完成标准：有一版用户认可"可进盲听"的模型 + 批量合成脚本

### Phase 2：数据层 — status: pending
- 2a build_data_bundle：UIF 消息 + 语音/视频 manifest 合并为档案数据包（JSON，含 provenance/tier）
- 2b timeline 自动生成（Tier-2，按年月聚合，可溯源到消息 id）
- 完成标准：people/mama/archive_out/data/ 下自包含数据包，schema 校验通过

### Phase 3：文字层 — status: pending
- 3a rhythm.json：从 UIF 统计交互节律（消息长度/时段/表情/口头禅/回复间隔）
- 3b persona.md：从她的 9386 条消息萃取（含缺点与冲突面，禁止理想化）——LLM 辅助生成部分全部标 Tier-3 待确认
- 3c 记忆卡片候选 + timeline.md（Tier-2 可溯源）
- 3d 人工闸门页：候选卡片供用户逐条确认升 Tier-1
- 完成标准：persona/ 与 memories/ 目录齐备，Tier 标注完整，闸门页可用

### Phase 4：卡通人（消费端）— status: pending
- 4a 卡通形象：SVG 手绘风（不做真人脸），待机/说话两态
- 4b 音量驱动口型：Web Audio AnalyserRMS → 嘴型开合
- 4c 播放源：她的原声语音 + v0.1 合成语音
- 4d 可选 BYOK 对话（裸 fetch OpenAI 兼容端点，走档案检索式提示词，Tier-3 禁陈述为事实）
- 完成标准：单 HTML 双击可开，本地静态服务器脚本附带

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
