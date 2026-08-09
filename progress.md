# MVP 生产进度日志

## Session 2026-08-09 深夜（重启恢复会话，MVP 立项）

- 会话恢复：B1 v0 SFT 端到端跑通（15 epochs，~/wu-sft/v0/exp/mama_v0_llm/）
- Codex 补审 B1 管线：REJECT（18/45 转写含噪声：14 条 U+FFFD + 4 条拉丁串）
- 分工违规取证并纠正（记忆 deepseek-division-enforcement.md）
- HANDOFF 已提交 3496327
- 校对页 spec 已写，DeepSeek 两轮调用失败（推理烧光正文）→ Phase 0 修复中
- 用户指令：修复 DeepSeek 后全力 MVP 四层

## Session 2026-08-10 凌晨（MVP 冲刺续）
- 校对页/试听页手机端过大打不开 → 全部瘦身重发（24kbps、校对 2 页×9 条、试听 3 页×1 组，0.4-0.5MB/页）
- 四工具入库（全部 DeepSeek 写 + Codex 多轮审至 ACCEPT）：build_data_bundle / build_rhythm / build_avatar_page / make_listen_page + make_correction_page
- 数据层+节律+卡通人页产物齐：archive_out/{data/(228MB), avatar.html, start_server.*}
- 等用户：①两页校对结果 ②三页试听 epoch 排序 ③avatar.html 本机浏览器体验反馈
