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

## Session 2026-08-12（同回合续 2：4e-集成 图片头像+口型动画闭环）
- 用户指令"先继续下回合" → 按 HANDOFF 顺序开工 4e-集成
- **关键发现**：定稿头像本身就是张嘴笑（露齿）→ 帧映射反转设计：canonical=静息帧、生成变体=说话帧（零工具约定改动）
- **说话帧生成**（复用上回合探针 avatar_probe.py，声明）：/free 释放显存（1.8→6.8GB）→ 3 种子实测：1001 背景跑偏、1003 眼翻白、**1002 完美一致**（仅嘴变 O 型）→ 定稿 persona/avatar_open.png + avatar_choice.json 加 open_frame 溯源块（含候选淘汰记录，用户可否决）
- **build_avatar_page.py 4e 扩展两轮闭环**：spec（图片模式+纯函数 mouthFrameFor+资产拷贝+SVG 回退+预览降采样）→ DeepSeek v1 → 自验发现 **JS 引用未定义常量 OPEN_THRESHOLD/FRAME_HOLD_MS（运行时必 ReferenceError，node --check 不报）** → 声明 hotfix 补 0.04/90 两行 → Codex R1 REJECT：**High #avatar 契约破坏**（图片模式无 id="avatar" 但共享 JS 到处 avatar.classList → TypeError；Codex 忠实 stub 执行抓到，我方 harness 对任意 id 返回元素太宽漏过）+ Medium 陈旧资产不清理；同时 Codex 用 125 条真实语音 RMS 分布验证 0.04 阈值合理（median 0.034，46.5% 窗口超阈）→ DeepSeek v2 修复（#avatar 包裹层恢复 + data/avatar reconcile 陈旧删除）→ Claude 改用**忠实 stub harness**（缺失 id 返回 null，avatar_harness2.js）双页全脚本执行干净 + 矩阵 7 场景全过 + 陈旧文件植入实测清理 → 死常量三行声明 hotfix → Codex R2 **ACCEPT 零发现**（自建含 rAF tick+play/pause 派发的更严 harness 复验）
- 工艺沉淀：**harness 的 DOM stub 必须忠实（缺失 id 返回 null）**——过宽的 Proxy stub 会把"元素不存在"类崩溃全部吞掉（本回合被 Codex 实锤教育）
- 产物：archive_out/avatar.html（图片双帧模式）+ avatar_preview.html 0.26MB + data/avatar/ 三资产；LAN 8020 在跑可直接体验；两帧图已发用户手机（说话帧可否决重抽）
- Phase 4 剩余：4c 合成语音入清单（等盲听定稿）、4d BYOK 对话页（Tier-3 禁陈述提示词，未开工）

## Session 2026-08-12（同回合续 3：4d BYOK 对话页收官，MVP 四层齐）
- 用户指令"先做出mvp 继续推进" → 开工最后一块纯工程拼图 4d
- **提示词模板 prompts/chat_system.zh.md（Claude 写，判断类）**：person-generic 六铁律——只说档案有的（事实源=Tier-1/2 标注+检索片段）/记不清就说记不清/Tier 标注纪律（Tier-3 只作语气参考）/保留缺点不美化/被问就承认是模拟不主动提/克制依赖（禁"我会一直在这里"）。占位符 8 个全来自 relationship.json+档案产物，零硬编码人物
- **build_chat_context.py 闭环**：渲染模板+rhythm 蒸馏（口头禅 top15/长度/时段/标点/语音习惯）+persona.md 全文嵌入（自带 Tier-3 DRAFT 声明随行）+缺 memories 防伪造回退文案+timeline 年度概要+message_shards 清单；占位符漂移守卫（v1 正确拦下我模板注释里的字面 {{占位符}}——模板 bug 我修）；18074 字 system prompt，零残留
- **build_chat_page.py 五轮闭环**：chat.html 23KB 自包含 BYOK（任意 OpenAI 兼容端点，key 只进 localStorage）+客户端检索（7 年度分片惰性并载，CJK 2-gram+拉丁词打分，top6 带日期"[档案检索 Tier-2]"）+真流式 SSE+永久"非本人"横幅。缺陷史全记：v1 esc 未定义→v2 %格式化撞 CSS 百分号（→定式：HTML 模板一律 __X__+replace）→v3 非 raw 模板 \n 变真换行+IIFE 罩纯函数（hotfix×2）→Codex R1 五实锤（分片 URL 双后缀检索全死/resp.text() 假流式/raw guard 弱/onerror 删整泡/context 输入绕守卫）→v4→R2 EOF 尾缓冲丢 delta（Codex Node 仿真）→v5 SSE 纯函数状态机→R3 新回归 fallback 只存首 chunk→声明 hotfix 累积→**ACCEPT**
- **测试工艺再升级：e2e harness**（事件处理器捕获+脚本化 reader 驱动真实 send 流）——正是能同时抓住"假流式"与"fallback 丢块"这类集成缺陷的层级；沉淀三件套 chat/sse/e2e harness 于 scratchpad。教训：stub 的 querySelector/parentNode 也要忠实接线，否则 e2e 报的是 harness 自己的伤
- 入口页 index.html 重排（直写声明）："档案体验"区（卡通人+对话）置顶，旧 review 区保留
- **Phase 5 合流预检**：archive_out 233MB 自包含盘点通过——能打开（index+7 分片+meta）/能听（125 原声+双帧卡通人）/能看（timeline+头像）/能聊（chat BYOK）。正式打包（并入 persona/memories 文字层、剔除 review 页）等用户 Tier-1 确认后做
- MVP 判定：**四层工具链全部闭环入库**。剩余全部为用户动作（回贴码/Q1-Q13/盲听文本）+ 等确认后的 Phase 5 打包

## Session 2026-08-12 晚（用户到家：Q1 确认 + 盲听实测 + 发音诊断）
- **Q1 用户确认**：郑韫瑜=爸爸、王铮=妈妈本人（升级为用户确认事实，persona.md 已标注；遗留 @郑韫玉 别字问题待答）；说话帧待用户在 LAN 看动画后定
- **盲听文本定稿**（用户"OK都可以"）：10 条全取自她真实文字消息（held-out，测泛化）+ 4 条真声锚点（避开 avatar 预览用过的 5 条）
- **1f 首次实跑 10/10 全绿**：零 QC 失败/零重抽/零起始幻觉标记，时长 2.5-8.3s——语音层完成标准两项齐
- **make_blind_page 事故与闭环**：v1 float32 直喂 lameenc → 14 段全噪音+低沉伪男声（连真声都坏，用户一耳抓出；node/泄漏/体积三关全过但没人"听"）→ 修 int16（复用 encode_mp3 成熟模式）+ 工具内解码回读自检 + Codex 三 Medium（file:// 剪贴板 catch 回退/全答完门控/异常包裹）→ 独立 roundtrip 14/14 零漂移后重发（e71b125）。教训入 findings：音频产物必须解码回读；"连真素材都坏→缺陷在打包层"
- **盲听预演成绩（用户本人，dataset b5bb1bf72a9e）**：总判对 11/14；**合成 3/10 骗过（两条 5 分"就是她"：早点回深圳/猫粮，一条 4 分：回视频电话）**；真声 4/4 全认出全 5 分（测试有效性基线成立）；合成均分 3.2。低分共性：拉丁拖长音/沪语字（好伐）/叠词（吃饱饱）/长道理句
- **用户定性（关键反馈）："音色很像，上海话的发音还是很奇怪"**——与 dialect-tts-maturity 预判一致：音色链路已成，卡在音系层
- **分布错位假说与实验（进行中）**：训练转写=浓密沪语本字（侬/㑚/伊/事体/辣辣/拨/额），盲听文本=纯普通话书面语 → 推理文本分布与训练分布错位。按她转写风格改写 5 条（b03 对照+四条低分）重合成（texts_wu.jsonl，wuv1 tag，5/5 零重抽），b/w 成对 MP3 已发用户耳测
- **发音升级阶梯（若本字改写不够）**：①满血重训——她全部 55 分钟（含 61 条 ≥15s 长语音切段）+ AP-BWE 增强 + MagicHub 4.19h 混合防遗忘（研究已给参数）；②路线 D——沪语原生 TTS→Seed-VC 换音色两段式；③底线（铁律）：尊重素材语言，档案核心=她的 55 分钟真声，合成只是增量能力

## Session 2026-08-12 深夜（发音攻坚：v0.2 满血重训开工 + 路线 D 并行立项）
- **A/B 结论（用户耳测）：w 本字版一样怪 → 分布错位假说部分证伪**（文本转换非主因），用户拍板"直接跳 1"，随后指令"立项同时尝试路线D"
- **数据盘点**：她本人 99 条 47.2 分钟——≤30s 59 条 13.1 分（现役仅 44 条 8.2 分），>30s 40 条 34.1 分闲置（26 条为 45-60s 长消息）
- **切段工具闭环**（segment_long_voice.py，DeepSeek 一发成型，存 wu-sft/v02_full/scripts/）：能量谷切割 40 长条 → 101 段（4.7-27.9s，对账零误差，切点能量 0.57×全曲均值），全池 160 条 47.2 分
- **Wu ASR 链路复原**：Understanding 模型盘上已失（HF 缓存被清）→ 重下 39 文件 1.16GB；whisper yaml 缺解码字段 → 改用 **u2++**（自带 dict，attention_rescoring 本装）；排坑两枚：发布 yaml 缺 input_dim/output_dim（补 80/5949）、PS Set-Content BOM 再踩（findings 老坑，无 BOM 重写）
- **全量转写 117 条质量惊艳：零 U+FFFD**（v0 时代 14 条坏字符的元凶实为 whisper BPE；u2++ 字级模型根除）、零空转写、仅 2 条 <unk>、平均 81.6 字
- **校对页 8 页上 LAN**（corr_v02_p1-8.html，15 条/页 24kbps 内嵌，工具自动标红仅 6 条）；index.html 加 v0.2 区块。**等用户分页回贴（大头用户动作，可跨多晚）** → 合并 → parquet → v0.2 重训
- **路线 D 立项与探针**：公开原生沪语样本全灭（HF 模型仓库无音频/数据集仓库仅 README/demo 页与 GitHub 404）→ 用户拍板用自己的语音做原生 prompt → 58.3s 切 24.7s（静音谷 0.0004）+ ASR 转写 → **Wu-SFT 底座 × 用户原生音零样本 4 条探针已发用户**（d00 官方示例句=模型主场上限）。**等用户"发音地道吗"耳测——此判定决定 D 生死与底座天花板结论**
- 环境注：wenet 无需安装，PYTHONPATH=C:\Users\justin\wenet + cosyvoice venv 即可；u2++ 解码 yaml 存 v02_full/asr_input/u2pp_decode.yaml

## Session 2026-08-13 凌晨（路线 D 死刑 + 天花板实锤 + 预期重校）
- 长句探针第二批（97-123 字，取自她真实转写轻度断句清理）→ 用户判定"**D路线拉胯的不行**"
- 关键查证：**SS 变体（论文最优 IMOS 4.37）未公开发布**——HF 仓库仅 CPT/SFT/instruct×2+底座；探针用的 SFT 已是公开最强 → **CosyVoice2-Wu 公开权重长句音系天花板实锤，路线 D 关闭**（无更好本地沪语源 TTS 可用；商用云此前调研亦无产品化）
- v0 训练底座查证：v0/v0.1 均从 Wu-SFT llm.pt 起训（run_train.sh 注释实锤）——v0.2 无换底座升级空间
- **预期重校（依铁律"尊重素材语言"）**：v0.2 重训继续（她的数据把发音往本人拉，渐进改善），但长句地道度受底座压制；合成定位=短句场景（卡通人/对话页短回复），长内容播真声；**117 条全量转写是独立档案资产**（进 bundle 可检索，不系于 TTS 成败）
- 观察项入 HANDOFF：吴语 TTS 生态 2026-02 才起步，留意 SS 权重放出或更强开源沪语模型
## Session 2026-08-13 凌晨（语音/视频记忆卡文本化——用户提问当场落地）
- 用户问"记忆卡能否把语音视频总结成文字"→ 当场三件套落地（闸门页恰好未开始做，无草稿冲突，用户确认后重生成）
- **build_voice_transcripts.py 入库（person-generic 合并器）**：段级 ASR+校对稿（校对优先）按 start_s 排序聚合回原始条目，联 manifest 元数据；语音跑出 **99/99 全文本化**（44 corrected + 55 asr_draft，26 条非本人未转写）；--media-kind 复用跑视频。DeepSeek v1 守卫双向写反（禁仓库外+放行 raw）→ 声明 hotfix 改为仅禁 raw 树
- **video_audio_prep.py 入库（工作区）**：imageio-ffmpeg 便携二进制抽音轨（9/9 全有音轨共 5.1 分钟）→ 同契约能量切段（16 池条目全 11-26s）→ u2++ ASR 16/16 → video_transcripts.jsonl（她的 9 条视频音轨全文本化；质量混合符合预期，闸门逐条判）。已知瑕疵：stdout 汇总计数自相矛盾（manifest 本体一致），入 Codex 批审
- **extract_memory_candidates transcripts-v1 扩展**：①回填——22/22 voice_long 卡带她说的话（标题即内容首句）、media_burst 语音/视频摘录带文本；②**转写进 keyword_event 挖掘语料**（keyword 池 418→427，5 张关键词卡长出语音/视频摘录）；③has_asr_draft 顶层标记 37 张（闸门页忽略未知字段安全）。Tier-2 纪律：全部标注 transcript_corrected/asr_draft 来源
- **闸门页 v2 已发用户**（150 卡 229KB，敏感预标记 10 张——语音可见文本进了扫描面）；旧页作废。用户校对 v0.2 转写完成后重挖一轮升级 draft→corrected
- 视频画面内容描述（视觉模型）定为 MVP 后增强项
- Codex 四工具批审后台进行（含 stdout 计数瑕疵与 hotfix 复核）
## Session 2026-08-13 凌晨（Tier-1 记忆册诞生 + 四工具修复轮）
- **Codex 批审 6 条全实锤**（1 High 潜伏未触发：全缺失段落клип误标 mixed；2 Medium：media 标签靠 chat_room 推断错标/缺 raw 守卫；video prep 切段算法偏离契约+相对路径风险+stdout 计数）——已核对**今晚已交付产物零污染**（mixed=0/路径全绝对/media 字段页面不渲染）→ DeepSeek 三工具修复轮 → 重跑全链零回归（视频重切段+ASR 重跑对齐新边界）
- **用户回贴码到达（150 张全裁决）**：26 剔除（含全部 10 张敏感预标记）+ 文字指令"其他都是确认"→ 按 delta 契约补全 124 张确认文件（hash 9c6f3423e44a 双向验证）→ apply：**confirmed=124 rejected=26 pending=0 confirmed_flagged=0 → memories/memories.md 134KB/124 条 Tier-1 诞生**
- **对话页升级**：build_chat_context 重跑，sources 首次含 memories——system prompt 1.8 万→9 万字（记忆全文嵌入）。待办：memories_block 加摘要/上限（9 万字对 BYOK 调用偏重）
- **管线新缺口立项**：extract_memory_candidates 重生成会清空 status——需"状态保留合并"能力（下轮与校对升级重挖一起做）
- Phase 3 完成标准实质达成：persona/（草稿待 Q2-Q13）+ memories/（Tier-1 记忆册+timeline）齐备
## Session 2026-08-13 凌晨（修复轮终审收口）
- Codex 复审：build_voice_transcripts / extract_memory_candidates 两修复确认通过；video_audio_prep 剩一条 Medium（缺 min_seg 钳位+三 CLI 守卫）→ DeepSeek v3 回炉**反而打碎直通逻辑**（全部 16 条误标 segmented=true）→ **三振协议触发：停整文件重生成，Claude 外科 hotfix**（单元组→直通分支恢复，声明）→ 重建生产视频池（passthrough=6/segmented=3/segments=10 与 Codex 预测精确一致，manifest 本体验证通过）→ 新边界重跑 ASR + 重建 video_transcripts 全链对齐
- HANDOFF ⓪-2 增补 + 下回合顺序刷新（状态保留合并列为重挖前置）
## Session 2026-08-13（persona Q2-Q13 聊天内全量裁决）
- 用户指令"这里问我吧"→ AskUserQuestion 三批 12 问全部落定：
  - **事实升 Tier-1**：Q2 生日 1 月 10 日；Q3 癌种=乳腺癌（写入健康期章节）；Q4 太平系保险任职照写
  - **重论断全保留**：Q6 T30"用病和眼泪表达失望"保留原样（定性公允、生日长信留档）；Q7 T34"说教与钻空并存"保留定性；Q8 T36"单线运作"成立保留——完整性铁律用户亲手执行
  - **删除**：Q9 2023 婚姻纠纷**全部移除**（T27/T37 相关引文已删，正文无事件展开；taboo_topics 入 relationship.json 对话层禁提；派生层延伸清理待另定）；Q10 T22"数字告别"整条删除
  - **语言层**：Q12 姆妈=口语/妈妈=文字分场景（入 relationship.json self_reference）；Q13 赞咯/一天世界/很残过全进词表（confirmed_catchphrases）
  - **待用户文字补充**：Q5 人名关系标注、Q11 沪语释义
- persona.md 头部 DRAFT 声明改为"用户裁决状态"；relationship.json 增 confirmed_facts/self_reference/confirmed_catchphrases/taboo_topics；chat_context 重建（8.9 万字，裁决后 persona 生效）
## Session 2026-08-13（Q5/Q11 文字补充落档）
- Q5：「嬢嬢」称呼者均为爸爸的姐姐（justin 姑妈）→ persona.md + relationship.json family_annotations；其余人名维持不提及
- Q11 三条释义（Tier-1）：侬盐才介来三了=你现在这么厉害了；臭哄哄咯宁臭哄哄咯添（**添=对儿子的称呼**）忒过浴了伐=洗过澡了吗；哈腻心=好恶心 → relationship.json dialect_glossary；皮雪雪/交难受/铿钱/老麻球维持拟音待释义
- chat_context 重建；Q1-Q13 至此全部收口（仅剩零散人名与四个拟音词开放）
## Session 2026-08-13 上午（普通话备选线开通 + Q9 范围定案）
- **用户裁决：Q9 婚姻纠纷原始记录不删**——数据层保留，仅 persona/对话层不提（raw 恒不动）；已闭环
- 用户指令"开通一条线做普通话版本"→ **普通话备选线当场首跑**：零新装（Fun-CosyVoice3 在盘 + ref01 + 08-05 验证过的 AutoModel/instruct2 调用式，基线 README 复现配置）；探针 13 条（盲听同 10 句 instruct2 + b01/06/09 zero-shot 模式对照，300ms 首尾垫 + int16 MP3）一发全成，已发用户
- 定位（若耳测过关）：普通话线接管长句合成场景（模型主场发音自然），沪语 v0.2 专攻短句；两线共用 ref01 音色链
- 用户计划：今晚审 v0.2 校对 8 页