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

## Session 2026-08-10（Phase R：移动 review 体验）
- 用户提出：手机远控场景下 review 回收方式要更方便 → 立项 Phase R（见 task_plan）
- R1（avatar 手机预览 <1MB 内嵌语音）+ R2（校对页回贴码只含改动项 + 大按钮剔除 + 底部固定操作条）两份 spec 已发 DeepSeek 并行生成
- R3：试听 epoch 排序改用聊天内 AskUserQuestion 按钮收集（无代码）
- 审核循环实录：R2 首版 dataset 三引号拼接产非法 JS（Claude 冒烟抓到）→ 修复轮；Codex 一审 R1 "ACCEPT with fixes"×4点 + R2 REJECT（回贴码无法标识45条全集）→ 各回炉；Codex 二审 R1 再抓 2 blocker（残留 sort_key 混排 / 替补乱序）→ fix4 → 终审双 ACCEPT
- 产物：tools/ 两工具入库；avatar_preview.html(0.18MB) + 校对页1_v2/2_v2(0.50/0.46MB) 已发用户手机；epoch 排序与 avatar 反馈改 AskUserQuestion 收集

## Session 2026-08-10（R4：手机音频通道修正）
- 用户实测：校对页无音频、avatar 预览播放无反应 → 实锤手机聊天 HTML 渲染器不播内嵌音频（8-08 教训重演，记忆已修正为铁律级）
- 音频全部改逐条 MP3 直发：校对 18 条（校对页N第M条_日期.mp3，与页内编号对应）+ 试听 12 条（文本×epoch）
- HTML 页降级为无声编辑面（改字/剔除/回贴码仍可用）；avatar 口型 demo 需电脑，待办无声演示模式/录屏

## Session 2026-08-11（局域网 review + 三项反馈全回收 + 4e 开工）
- 用户到家 → 起 LAN 服务器方案：archive_out 集中五页 + index.html 入口（Claude 直写纯链接页，已声明）+ 防火墙 8020（UAC 放行）+ 用户 `!` 起 start_server.bat → 手机浏览器 http://192.168.3.69:8020/ 全部可用（浏览器能播音频，聊天渲染器不能——通道定论不变）
- **试听反馈**：epoch14 最好但头尾被切 → 探针实锤合成导出无首尾缓冲（wav 0ms 即 RMS 0.05+），修复列入 1c
- **校对全回收**：两页回贴码存 ~/wu-sft/v0/corrections_page{1,2}.jsonl；apply_corrections.py（DeepSeek 写，Codex 审核中）合并 → **v01_full44/data/（44 条：17 替换+1 剔除+27 保留），指纹校验通过**，待 Codex ACCEPT 后走 1c+1e 重训
- **4e 卡通头像**：用户放了 10 张照片进 raw/photos/（只读）；调研定稿 docs/research/photo-cartoon-avatar.md：首选 Qwen-Image-Edit-2509 (Apache-2.0) + ComfyUI Portable，全本地；权重下载中（VPN 下 curl 反复 reset，已改断点续传循环，VAE 242MB 已完成）
- 会话中断插曲：API 403 → 用户 /login 恢复
- **1e 重训启动**：apply_corrections v2（Codex 两项 fix 已修，输出与 v1 逐字节一致）入库 tools/（f48a9ef）→ v01_full44 数据管线全通（44 embedding/44 token 0 空/parquet 21.5MB；坑：PS 写 utt2spk 带 BOM 崩 GBK 读，awk 重写）→ 训练进行中（epoch 9/15 时 loss 0.37/acc 0.93，显存 17.5G 正常）
- **4e 环境就绪**：三大权重断点续传全部下完（19.5G+8.9G+0.2G），ComfyUI Portable 解压至 ~/ComfyUI_portable，权重已入位 models/。下一步：起 ComfyUI 批量出头像候选
- 待办：synth 样本导出加首尾静音垫（epoch14 头尾截断修复）→ 训练完出样本前做
