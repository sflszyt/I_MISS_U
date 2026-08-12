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

## Session 2026-08-12（/clear 后恢复，4e 头像生成开工）
- 恢复要点：语音层 1e 已完（ab_final.html 上局域网，**阻塞等用户挑盲听版本**）；4e 环境 100% 就绪 → 本会话推进 4e
- ComfyUI 后台起服（run_nvidia_gpu 同款参数 + --disable-auto-launch，日志在便携包根 comfy_stdout/err.log），127.0.0.1:8188 就绪；GPU 空闲（1.75G/24G）
- 官方模板 image_qwen_image_edit_2509.json 在便携包 site-packages 内（新版包成 subgraph），已解出真实节点图并经 /object_info 核对入参名；本地无 Lightning LoRA → 走 20 步/cfg 4/shift 3 标准路径
- **探针成功（Claude 直写一次性探针，已声明，scratchpad/avatar_probe.py）**：单张照片→暖手绘卡通头像 70s（含首次模型加载），风格方向对、眼镜/发型/神态保留
- 生产脚本 gen_avatar_candidates.py 三轮闭环入库 tools/：DeepSeek v1 → Codex REJECT（3 BLOCKER：symlink/junction 越界+manifest 绕过检查 / interrupt 发 GET / 落盘异常未任务级兜底；2 MAJOR：--photos 递归放宽读面）→ DeepSeek v2 → Codex ACCEPT with fixes（剩 poll_history 兜底）→ DeepSeek v3 → diff 精确验证仅含该修复 + py_compile 过
- **用户 review 中插反馈（语音）**："full44 e14 好点，但开头 1s 内有奇怪的话，是垫进去的吗？"→ 探针实锤：6 条样本前 300ms 全部 0.000 纯静音（垫无声，清白），"话"在 300ms 后=模型起始幻觉；且 f44 e14 比 c27 e14 明显长（02 号 8.2s vs 5.4s），正文重音更晚 → 正文前多生成了低音量语音状内容
- 处理：/free 释放 ComfyUI 显存（21.3G→1.8G）→ synth_epoch_samples.py 重合成 f44 e14（新随机采样，tag v01f44r2，samples_rerun/）验证幻觉是随机还是固有；随机→重抽即可，固有→导出侧加起始能量截除或改推 e8
- **用户确认（2026-08-12）："干净了"** → 幻觉实锤随机，重抽即除；**盲听候选定稿 v01_full44 epoch14**；新增 1f 批量合成脚本待办（起始幻觉 QC：时长阈值+自动重抽）
- 4e 批量开跑：30 张（10 照 × 3 风格 × s1000）脱离进程生成中（日志 scratchpad/avatar_batch.log，Monitor 守完成）；dry-run 30 任务矩阵验证过；~70s/张
- make_contact_sheet.py 四轮闭环入库 tools/：DeepSeek v1 → Codex REJECT（布局/压缩循环/index 页/边界全有实缺；其中"90/93 行语法错误"一条经本机 py_compile+读行实证为 Codex 误报）→ 规格简化重写 v2（去 index 页/通用网格/压缩伪代码明确/纯 ASCII 标题）→ DeepSeek v2 → Codex REJECT（Windows 路径断言字符串前缀必炸 + 标注编号反查 IndexError）→ DeepSeek v3 修复 + Claude 声明 hotfix（删重复告警死代码）→ Codex 终审 ACCEPT with fixes（仅剩空源照硬失败）→ DeepSeek v4 修完 diff 验证。教训：**拼图布局类规格要给伪代码级细节，first-shot 质量与规格精细度强相关**
- **4e 批量收官**：30/30 全成功零失败（avg ~70s/张，最长 193s）；manifest.jsonl 30 行溯源齐；3 张风格拼图（281-314KB，1648×1380）自查渲染正确后已直发用户手机；两工具已提交（2fd781a / 44e294f）。运行环境注意：make_contact_sheet 需 Pillow，用 ComfyUI 内嵌 python 跑（系统 python 无 PIL）
- **用户挑风格（2026-08-12）："第一套风格的都不错" → warm 暖手绘方向定稿**；已启动 warm 加抽 seeds 1001/1002（20 张新图，PID 34096，日志 avatar_batch2.log，Monitor 守）→ 完成后拼 30 选 warm 大图发用户挑最终头像
- **1f 完成闭环入库 tools/synth_blind_batch.py**：spec 基于已验证 synth_epoch_samples.py 改造 → DeepSeek v1 → Codex ACCEPT with fixes（2 MAJOR：SKIP 在任务级 try 外+except 直写报告可断批 / 全超限 retries 多记 1；3 MINOR）→ DeepSeek v2 修复（diff+代码双验证：except 自算 elapsed、引用变量 try 顶部全初始化、retries=takes-1、SKIP schema 明确）+ Claude 声明 hotfix（check_sr 死变量）→ py_compile 过。**尚未实跑**（待盲听文本清单定稿后 GPU 实测）
- 4e 假警报教训：PS `Get-ChildItem -Filter` 不支持 `[12]` 字符类（FindFirstFile 语义），计数用 Where-Object 正则；warm 加抽批次正常（~55s/张）

## Session 2026-08-12 深夜（文字层全面开工 + 头像终选）
- **用户指令：同步推进文字层；泛化基线重申（anyone，MVP=mama）**→ 已写入 task_plan Phase 3 设计基线 + 记忆 i-miss-u-project-state
- **头像终选：04 s1001（用户拍板）**→ 固化 people/mama/persona/avatar.png + avatar_choice.json（溯源：源照/seed/prompt/model）。warm 加抽批次 20/20 成功（总 30 warm 候选，6 列大图发用户后即选定）。**下一步 4e-集成：build_avatar_page.py 支持图片头像+口型动画（DeepSeek 轮，未开工）**
- **Tool-1 extract_persona_digest.py 闭环入库**：DeepSeek×3 + Codex（REJECT：kw 抽样死循环+未降级 UnboundLocal → REJECT：kw 元素类型+池排序行序敏感 → ACCEPT with fixes：sender 必填缺失）+ Claude 声明 hotfix（sender 入必填）。**实跑通过：206KB digest**（random50/longest25/threads14/9 组关键词，全带 record_id）
- **Tool-2 extract_memory_candidates.py 闭环入库**：DeepSeek×4 + Codex（REJECT：duration_ms 类型炸+title str(dict)+candidate_id 碰撞+is_subject 宽松 → REJECT：UIF 入口解析未收紧 → ACCEPT → v4 配额增量审核中）。实跑：五信号 908 候选 → 配额 40/15/15/15/15+轮转补位 → 150 条（61/23/22/22/22），candidates.jsonl 已产
- **persona.md 起草已派 Claude 子代理**（后台，判断类工作留 Claude 家族）：读 digest+rhythm+relationship，铁律 2 全文约束（必写缺点冲突面/Tier-3 全标注/禁编造/逐论断带 record_id 证据），产物 people/mama/persona/persona.md + 待确认清单
- 配置直写（已声明）：tools/persona_keywords.zh.json（9 组通用中文+吴语特征关键词）、people/mama/persona/relationship.json（关系参数化落点，泛化架构第一实例）
- 文字层剩余：3d 闸门页 make_gate_page.py + apply 工具（下轮）、timeline.md 渲染（下轮）、persona 草稿等子代理回报
- **persona.md 草稿回报（子代理 180k tokens/11.5 分钟）**：306 行 10 节，46 条论断（语言 9/性格 8/关心 5/观点 6/**缺点冲突面 9**/幽默 4/健康期 5）逐条带 record_id 证据，Q1-Q13 待确认清单。主模型抽查头尾：Tier 纪律/DRAFT 声明/证据格式/两面性全达标。已直发用户手机
- 子代理三大发现：①**2024-02-09（数据最后一天）数字告别**——她集中交接全家密码/记账/抗癌药记录，**明文凭据在 UIF+archive_out/data 里（档案要发家人）**→ 已立敏感记录处理待办（task_plan Phase 3）；②她微信语音仅 76 条 0.8%（"文字召唤电话"型；注：克隆参考早已解决，55 分钟语音在库，此点不影响语音层）；③身份对应（郑韫瑜=爸爸/王铮=妈妈本人）系群聊生日链推断，Q1 最优先确认
- Tool-2 v4 配额增量 Codex ACCEPT with fixes（--quota 重复 kind 静默覆盖 + nan 绕过正数校验）→ Claude 声明 hotfix 两处守卫 → 实测 exit 2 + 真跑配额正常 → 提交 7f34bb4
- **会话收尾（用户远控指令）**：①persona 反馈"整理的很好（要看哭了）"；②答疑：persona 提炼只用文字消息，音频仅计数参与、视频未用（可选增强已记 HANDOFF）；③**敏感记录拍板：删除**（派生层全删/raw 不动/重跑下游），泛化为任意人物管线标准关卡 → 记忆 sensitive-data-cleanup.md；④HANDOFF ⓪ 全量重写 + README 里程碑刷新 → 推 GitHub → 用户清理上下文进下回合

## Session 2026-08-12（/clear 后新回合：敏感记录清理关卡闭环）
- 恢复上下文（planning-with-files + HANDOFF ⓪），按"下回合建议顺序"直取首要工程项：敏感记录清理工具
- 侦察（Claude 探针，已声明）：2024-02-09 批共 14 条（13 subject + 1 viewpoint_owner；text 7/link 4/image 3；4 条长文本 827/806/5790/4167 字为凭据主体）；扩散 = UIF 14、messages_2024.json 14、digest 4、candidates 4、media_index 0、persona.md 0（仅前缀引用）。删除清单定稿全 14 条（整批交接会话，链接 URL 或含文档 token；派生层删除可从 raw 重建）
- **tools/scrub_sensitive.py + tools/sensitive_patterns.json 闭环入库**：spec（scan/apply/verify 三模式、raw guard 单点、字节级保留、manifest 无正文、原子替换）→ DeepSeek v1（29s 一发成型）→ Codex REJECT（9 条：其中 2 条"py 语法错误/JSON 未闭合"BLOCKER 经 py_compile+json.load 双实证为误报——Codex 读 CJK 文件误判第二次发生；7 条真实：--patterns/--ids-file 未过 raw guard×2、rel_posix 越界 ValueError、dry-run 按唯一 id 计数、scrub 数据文件按名排除可被 symlink 绕过×2、record_id 大小写折叠）→ DeepSeek v2 全修（diff 逐条核对无越界改动）→ 冒烟全绿（dry-run 14 条精确；scan 21263 条命中 607；删前 verify residue=36 与侦察互证）→ Codex 复审 ACCEPT with fixes（7 修复全确认+2 误报自认撤回；仅剩 load_ids_file 一处 .lower()）→ Claude 声明 hotfix 一行
- **实删执行**：apply 14 条（UIF 20923→20909，scrub_manifest.jsonl 落盘、无正文）→ 重跑 build_data_bundle（messages=20909，227.76MB）/build_rhythm/extract_persona_digest（204.7KB）/extract_memory_candidates（150 条，配额 61/23/22/22/22 不变）→ **verify ids=14 files=32 residue=0** → 删后重扫 601 条疑似（high 273/medium 50/low 278）存 sensitive_scan_report.{jsonl,md} 供 3d 闸门页默认剔除 + 后续人工复核
- 注意事项落档：日后重跑 parse_wechat 会把 14 条重新引入 UIF，须按 scrub_manifest.jsonl 重新 apply（已写 task_plan + HANDOFF）

## Session 2026-08-12（同回合续：3c/3d 文字层工具链收官）
- **3d 双工具闭环**：make_gate_page.py + apply_gate_decisions.py（共享回贴码契约 v1）。历程：spec 双份（契约共写防漂移）→ DeepSeek v1 双生成 → 冒烟（页面 150 卡 178KB node --check 过；apply scratch 副本全链路：3 决定精确改行/幂等/坏 id 写前中止/dry-run 零写盘）→ Codex 联审 REJECT 9 条（1 条"JS 坏字面量"BLOCKER 被 node --check 权威推翻=第三次 CJK 误报；1 条"kind_label} 字面量"被实物输出推翻；7 条真实：**delta 契约缺口（已决定卡翻回待定无法回传）**/excerpt 展开双转义/敏感配置 schema 失配 silent []/```json 围栏/dry-run 语义/相对路径）→ 契约修订（decisions=对初始状态的真 delta + 新 action "pending" 显式回撤）→ DeepSeek v2 双修 → 扩展冒烟五场景全绿 → Codex 复审仍 REJECT：**用 Node stub-DOM 实际执行页面 JS 抓到 High 实锤**（effectiveTitle 回退基础 title 参与比较 → 未动卡全量导出）+ Medium（预标记烤进 initial）→ v3 spec 要求抽纯函数 computeDecisions() 使契约可测 → DeepSeek v3 → **Claude 同法 Node harness 七场景矩阵全绿**（scratchpad/gate_harness.js）→ Codex 终审 **ACCEPT 零发现**（自行重跑 harness 复现全部结果）
- **3c-② render_timeline.py 闭环**：DeepSeek v1 留占位残桩（NameError）→ v2 修 → 实跑 68 月（头部对账 20909/9373 与清理后 UIF 精确一致，2024-03 起"本人 0"）→ Codex REJECT（gap 锚定=缺口前月而非起始月/ASCII/死代码）→ v3 修 → 合成缺月用例（2024-12+2025-03 → "2025-01 起连续 2 个月无记录"落 2025 表后）验证 → memories/timeline.md 已产
- 死代码清理（Codex Low，Claude 声明 hotfix）：apply MAX_ISO/changed_count、timeline idx
- **闸门页敏感预标记校准（重要设计决策）**：source 元数据命中全废（svr_id/文件名长数字撞 card_number，voice 候选 22/22 全误报）→ 改为只扫**将进入 memories.md 的可见文本**（title+excerpts），150 卡中 5 high+1 medium=6 条默认剔除（全是"账号"类对话性提及，用户可翻回）
- 工艺沉淀：①审核 JS 产物的标准从"node --check 语法"升级为"stub-DOM 实际执行断言契约"（Codex 先做，Claude 跟进复用）；②Grep/查看器显示层也会把 `//` 渲染成 `\`——py repr 才是字节仲裁；③共享契约的成对工具必须联审抓两端不一致
- 产物：gate_page.html（192KB，150 卡）+ timeline.md 发用户手机；**等用户回贴码** → python tools/apply_gate_decisions.py --person mama --decisions <回贴码文件> 产 memories.md（Tier-1）
