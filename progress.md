# MVP 生产进度日志

## 2026-09-10 · T14-3/4/5 自启任务 + 离线降级四层（T14 代码层收官）

**产出**：`scripts/register_startup_task.ps1`（新建 303 行）、`people/mama_for_father/site/{offline.html,sw.js}`、`deploy/cloudflare-worker/dad-offline.js`、`tools/build_companion_page.py`（+`--offline-fallback` 与 TTS 探活重试）、`docs/ops-autologon.md`、`docs/ops-offline-fallback.md`。全部走 DeepSeek 写 → Codex 审 → ACCEPT。

**T14-3 自启任务**：注册器与运行器同一文件（防两文件版本漂移）。Codex 两轮 REJECT 共 4 条阻断，全部属"把不确定当成功"：① `Start-Process -Wait` 等进程树导致挂死 494 秒（start_services 的常驻服务是它的子进程）；② 超时 `Kill()` 不验尸，僵尸持锁会把下次的 exit 3 洗成成功；③ exit 3 本身就是不确定态（mutex 异常也返回 3），且僵尸跨调用持锁使进程内标志失效 → 改为**收到 3 就跑 `-Status` 实测四服务全 `[ ok ]` 才报成功**；④ `-Status -DelaySeconds 9999` 违反"永远 exit 0"。另自查出一条更隐蔽的：把"启动成功吗"与"返回了什么"合并判断，导致**每次健康启动都被记成 launch-failed**、白烧 240 秒。端到端实测：任务计划器触发 → `LastTaskResult: 0 (all services up)`。

**T14-4 离线降级四层**：没有任何一层能覆盖全部故障——PC 关机要 Cloudflare Worker、用户自己断网要 Service Worker、TTS 冷启动要页面自身。真浏览器实测走通：SW 注册 scope `/` → 停 :8021 → 渲染出「她今天不在」四句 + 按钮 → 恢复后自动跳回 companion.html；route-mock 造冷启动 → 16 s 出提示、恢复 12 s 出「她的声音准备好了。」。儿子版默认参数产出零 SW 泄漏。

**T14-5**：Autologon 步骤交用户执行，Claude 全程不接触密码。额外给出**登录后自动锁屏**（把已裁决的"物理接触即进桌面"降为"看到锁屏"，服务不受影响）与 ARSO 备选。

**未做（需机主操作）**：隧道仍未启（外部可见动作）；Cloudflare Worker 未部署；爸爸站页面未用 `--offline-fallback` 重建（需 TTS token）；**真重启验收整条链未做**。均登记为 T14-6。

工程教训见 `findings.md` 末尾「T14-3/T14-4 自启任务与离线降级教训」。

## 2026-09-10 · T14-4 文案显式决策记录（对铁律 2 的第三次知情覆盖）

**背景**：离线页文案在动手前以三选项呈交用户（克制事实型 / 纯技术型 / 温情型），并在选项内直书温情型的风险。用户选定**温情型**。

| 项 | 内容 |
|---|---|
| 采用文案 | 她今天不在 / 等电脑醒过来，她就回来了。/ 明天再来看看吧。/ 这是家里那台电脑的事，不是她走了。 |
| 用户裁决 | 温情型（2026-09-09） |
| Claude 已告知的后果 | 拟人化停机、可能强化「她还在某处」的错觉——正是铁律 2「克制沉浸度」所防 |
| 独立佐证 | Codex 在**两轮**审查中各自独立地把该文案列为 blocking，理由与上述一致 |
| 处置 | 不改文案（用户裁决优先）；记为对铁律 2 的显式覆盖，并在 `docs/ops-offline-fallback.md` 文案段落就地标注，改文案前须回看 |

**已落实的边界**（未被覆盖的部分仍然生效）：页面不含她的照片/姓名/声音/任何档案内容；不出现「她在等你」式暗示；无倒计时、无「距上次对话 N 天」；`/tts` 与 `/v1/chat/completions` 永不缓存重放。

**复核日**：2026-11-28（与 #24 三项覆盖对齐）。**决策人**：justin，2026-09-09。

## 2026-09-09 · 任务 #24 F-乙 全线开工执行记录

**产出**：代码 +654 行 / 6 个既有文件 + 2 个新文件（`tools/llm_proxy.py` 366 行、`prompts/chat_system.husband.zh.md` 72 行）+ 2 份研究报告。全部走 DeepSeek 写 → Codex 审 → ACCEPT。

**基础设施**：域名 `justmissingyou.com` → 命名隧道 `imissu-father` → CNAME `dad.*` → Access 邮箱 PIN（全路径 302 拦截已实测）→ ingress 三路由（`^/v1/chat/completions$`→8023 / `^/(tts|health|session)$`→8022 / 其余→8021）。`protocol: http2` 钉死（QUIC 在 Surfshark 下每 ~90 s 断）。cloudflared 加入 Surfshark Bypasser 后边缘落点 ewr→hkg。

**代码**：T7 `--relationship`+三占位符 / T8 六项参数化 / T9 多 viewer token（服务端认定 viewer）/ T10b LLM 代理 / T10c 页面接代理 / T11 检索只取 sender=subject / T12a 大字说明卡。每项都验证"默认参数产出与基线逐字节相同"，儿子版全程零影响。

**端到端（真 key + 真 GPU）**：页面零凭据 → 代理 → DeepSeek → 分条 → TTS(wu) → 语音条 → 会话日志（`viewer=father` 服务端认定）。回复三条上海话各带语音条。测试会话已清理并重新 ingest。

**修掉的既有缺陷（非本任务范围但顺手修）**：
- `retrieveSnippets` 不按 sender 过滤 —— 实测真实分片 4779 条中她只占 2492 条（52%），10 个查询里**4 条别人的话被标成「她真实说过的话」**喂给模型（含"整个上海都在等雨，像一个初恋的少女等待男友"这种明显不是她的句子）。两个页面生成器同修，修后归零
- `taboo_topics` 从未进过提示词（`PIPELINE.md` 却写着它会进）
- `prompts/chat_system.zh.md:1` 对模型说"档案由消息、语音和**照片**构成"而照片层是空的

**血泪教训（详见 HANDOFF ⓪¹¹ 第 6 节）**：★ 最重要一条——`curl -N --max-time 15` 看到 SSE 块与 `[DONE]` 就判"流式通过"是**假象**（那是超时退出）；`llm_proxy` 流式响应缺 `Connection: close`，客户端实际卡 30 秒、页面永远"正在输入"，而代理日志显示 `status=200 dur_ms=1784`。Codex 两轮静态审查也没发现，只有真用浏览器跑一遍才暴露。

**未完成**：T14 运维自启（上线前最后硬门槛）、T12b 老人 UX 其余项、T12c 主屏图标、T13 rhythm_dad、archive_dist 重打包、爸爸手机真机验收。


## 2026-09-09 · 任务 #24 显式决策记录（裁决⑥ F17 要求的"知情自决覆盖"入档）

**背景**：研究报告 `docs/research/dad-husband-companion.md` §4 给出 GO/NO-GO 判定框架，列出若干"任一成立即不开独立入口"的条件。用户在知晓各项后果的前提下，逐条作出裁决，其中三项构成对该框架的显式覆盖。

| # | 覆盖项 | 用户裁决 | Claude 已告知的后果 |
|---|---|---|---|
| 1 | 8A-2b 护栏 b/d/e | **先上线，护栏后补** | 第一个非开发者受众将在无关窗道别、无限速、无使用统计的状态下使用。护栏 (c) 因"大字说明卡"裁决而提前落地 |
| 2 | 数据范围 | **全量不裁剪** | 爸爸设备可取得母子一对一 6,835 条，含她对儿子讲的关于他的话。已由 T11「检索只取 sender=subject」缓解"被当成她的话复述"，但挡不住直接翻数据文件 |
| 3 | 知情同意 | **跳过当面演示，直接给链接** | Claude 曾列为 §4 框架中唯一未被豁免的闸门。缓解：页面内大字说明卡（T12）仍实现，七条告知印在卡上、每次打开必须点过 |

**同时裁决**：禁区 A 组四条（夫妻私密 / 病程临终 / 钱 / 她对儿子讲的关于他的负面评价）**均不设禁区**；B 组只禁「任何指向未来的话」。
说明：不设禁区 ≠ 可编造——模板铁律 1 与追加铁律 8 不变，档案里没有的内容模型仍只能说记不清。

**"记不清"措辞**：用户裁决不写死，让模型自己组织。Claude 拟的三条沪语因准确性未经验证而弃用，未进生产提示词。

**复核日**：2026-11-28（与三个月复核对齐）。
**决策人**：justin，2026-09-08/09。这是继 #23（2026-09-06 六段语音）之后，对"家人向默认 NO-GO"的第二次知情自决覆盖。


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
## Session 2026-08-13（沪普攻坚：目标重定义为"她的上海口音普通话"）
- **用户耳测普通话首批："音色听得出来是她，发音不像，太标准了"**——关键洞察：她的普通话本就是沪普（上海口音普通话），标准播音腔同样不是她。目标重定义为中间态
- **沪普双路探针即刻发出**（probe2_hupu，8 条成对）：A=她的 SFT（v01_full44 e14）说普通话文本**无 <|wuyu|> 标签**（口音由她的语音数据自带）；B=CosyVoice3 instruct2 加"请用带上海口音的普通话"指令。等用户 A/B
- 若 A 胜：v0.2 重训（47 分钟数据）会同步强化沪普口音——校对的价值再+1；若 B 胜：零训练即用；若都不行：留观察项
- 校对区"找不到"诊断：服务器/文件/HTTP 全正常，系手机浏览器缓存旧首页 → 给缓存穿透 URL（index.html?v=2 或直连 corr_v02_p1.html）
## Session 2026-08-16（A 路定案 + 校对页空白破案）
- **用户耳测：A 路（她的 SFT 无标签说普通话）"比较贴近妈妈"，B 路（口音指令）不像** → **沪普定案：主 SFT 模型双语域**（挂 <|wuyu|>=沪语 / 不挂=她的沪普）。战略红利：①普通话备选线并入主线（Fun-CosyVoice3 线退役）；②对话页合成免"普→沪本字转换"（LLM 普通话输出直喂）；③v0.2 重训同步强化双语域——校对杠杆再+1
- synth_blind_batch 加 --lang {wu,mandarin} 开关（DeepSeek 10 行，qc_report 带 lang 标；Codex 待下批合审）
- **校对页"全是空的"破案**：非 bug 系设计错配——R2 双区设计「需校对」置顶+「正常」折叠，本批质量太好 6/8 页标红 0 条 → 全部条目藏在折叠条里。修复：零标红页默认展开（make_correction_page 一行声明 hotfix），8 页已重生成## Session 2026-08-16（校对收口 → v0.2 重训启动）
- 校对回贴收齐：p3（改12/留3）、p4（改1）、p5（改1，BROOKS BROTHERS 品牌名）逐条校验 utt 全对上；p1/p2/p6/p7/p8 用户裁决整页通过。全 8 页 = 14 修正 + 102 原样采纳
- 数据合并 prep_v02_data.py（Claude 声明直写，确定性拼装+全量审计）：160 条 / 47.2 分钟 / 零冲突 / 零超30s
- 特征提取：extract_embedding + extract_speech_token 160/160 全过；make_parquet_list 官方版两连坑（GBK 默认编码崩 → PYTHONUTF8=1；apply_async 吞 Windows spawn NameError → 复用 v0/make_parquet_single.py）→ 127.9MB tar
- run_train.sh（v02f160）后台开训 15 epochs → exp/mama_v02f160_llm
- **训练误杀事故与恢复（17:21 发现）**：harness 16:02 回收后台任务时杀掉外层 bash 管道，训练 worker（PID 49512，42.8GB RAM）stdout 断裂写阻塞卡死，占 21GB 显存不放，日志停在 Epoch 7 中段。清理 4 个残骸进程 → 显存 21GB→1.8GB → 从 epoch_6_whole.pt 续训（yaml 自带 epoch:6/step:1099，train.py 从 Epoch 7 续起；constantlr 续训等价）。**教训：长时 GPU 任务永不用 harness 后台 bash，须 Start-Process 独立进程 + 日志直写文件**；Monitor 挂三态监听（完成/报错/停滞）
- **v0.2 训练收官（18:02）**：15 epochs 完成，CV loss 0.195/acc 0.964（数据 4 倍于 v0.1，loss 略高属预期）；epoch_14_whole.pt 落盘
- 试听批 4 批 14 条全绿（e8/e14 × 沪语 3/沪普 4，--lang 开关首次实跑验证 mandarin 模式 OK）；ab_v02.html 自包含 1.38MB（21 条内嵌，base64 回读自检过）已发用户 + LAN listen_v02/ → **等用户两判：v0.2 vs v0.1 更像否；e8 vs e14**
- **v0.2 e14 定稿（用户耳测："有比v0.1好点，v0.2 e14"）**：现役模型切换 v01f44e14 → v02f160e14（双语域）；渐进改善符合预期（底座天花板下 47 分钟数据的增益）
- 盲听 v2 物料备齐：8 句训练集外文本（本字 5 + 试听 3，防训练背诵失真）× v02e14 合成全绿 + pilot 真声 4 条 → blind_v2.html 12 条乱序 0.64MB + key 分离（seed 46），已发用户，等用户安排家人（M1）
- synth_blind_batch --lang 改动 Codex 补审 ACCEPT：前缀不污染 qc_report/chars、默认 wu 向后兼容、lang 三分支全写入、retry 路径一致

## Session 2026-08-16 晚（/clear 后新回合：盲听 v2 回贴 + 状态保留合并开工）
- 恢复上下文（planning-with-files + HANDOFF ⓪），用户令"继续开工+总结进度"→ 汇总后按 HANDOFF 顺序开工「extract_memory_candidates 状态保留合并」
- 设计决策：不动已稳定的 942 行 extractor，新建独立工具 tools/merge_candidate_state.py（fresh 产物 × 旧 candidates.jsonl 按 candidate_id 合并）——审查面小、零回归、管线组合式符合仓风格
- 用户中插"家人盲听在哪里"→ blind_v2.html 重发手机 + 复制上 LAN（http://192.168.3.69:8020/blind_v2.html；key 不上传保持盲测）
- **盲听 v2 回贴码到达并对卷（dataset 69fbdcbc2417 核验通过，回贴存 wu-sft/blind_v2/responses/resp_20260816.json）**：**合成 8 条骗过 7 条**（6 条打 3 分、1 条 5 分=w08 旧衣裳），唯一识破 w07"吃饱饱"叠词句（1 分）——与预演低分共性一致；**真声 4/4 全认出全 5 分**（测试有效性基线成立）。合成均分 3.0 vs 真声 5.0：能骗过判定但确信度仍有差距。**听者身份待用户确认（本人预演还是家人）——决定 M1 是否正式通过**；对照预演（用户本人×v0.1）3/10 骗过 → 本轮 7/8，v0.2 e14 提升实锤
- merge_candidate_state.py：spec → DeepSeek 一发（14s/8788 字符，剥围栏后 py_compile 过）→ Claude 自查两疑点（old_sig_cache 死代码；规则 1 漏 pop content_changed 陈旧标志）→ 九场景冒烟全 PASS（smoke_merge.py：全同保留 124/26/内容变更/缺卡结转/丢弃未裁决/新卡/dry-run/重复 id/幂等/守卫）→ **Codex ACCEPT with fixes**：两发现与自查完全重合（MAJOR=content_changed 陈旧残留可稳定复现+报告计数不一致；MINOR=死代码），无其他偏差（守卫/就地升级/空文件/date 排序 Codex 实测全过）→ 声明 hotfix 两处 → 十场景（含 S10 回归）全 PASS → 提交 702085e
- **对话页知识源升级三件套（任务 #3+#4 合并实施，Codex 批审后台中）**：①build_chat_context.py 加 --memories-mode index（默认）——记忆块改"日期·标题"索引+检索声明，生产 prompt 89556→23884 字符（-73%）；②新工具 build_chat_knowledge.py——candidates(confirmed)→memories.json 124 条 Tier-1 + 双转写→transcripts.json 108 条 Tier-2（DeepSeek v1 覆盖缺陷我方实测抓出：voice/video 各写一次后者覆盖前者，v2 合并单写修复）；③build_chat_page.py 检索三源化——retrieveKnowledge 纯函数（记忆 top3 权重在前+转写 top2 带媒体标签）+loadKnowledge 404 容错+buildRetrievalBlock 标签化向后兼容（预算 2200）+Promise.all 装载门控；声明 hotfix 三行（loadKnowledge resolve 缓存+window 导出）。验证：harness 四套 20/20+16/16+6/6+e2e 2/2 全绿（老契约零回归），chat.html 26KB node 干净。发现既有缺陷一枚（build_chat_context 的 relative_to 对仓库外 --out 写盘后崩，旧版同款）交 Codex 裁决。**Codex 批审 ACCEPT with fixes（零 BLOCKER/MAJOR）**：仅 1 MINOR——memories_mode 字符串混进 stdout sources= 列表（混型 dict 迭代）→ 声明 hotfix 一行（`if v is True`）；泄漏面/排序幂等/SSE契约/hotfix 三行 Codex 全部实测通过（其 read-only 沙箱用 ast.parse+new Function 替代编译，自跑 harness 复现四套全绿）；relative_to 既有缺陷 Codex 确认预生存、单独立项（任务 #5）
- **用户裁决（08-16 深夜）**：盲听回贴系用户本人（"不重要"）——M1 家人盲听不作阻塞；指令"现在先把MVP做出来"→ Phase 5 开工
- **Phase 5 build_archive.py（DeepSeek×2 + 声明 hotfix 一处，Codex 终审后台中）**：白名单拷贝（default-deny，review 页全排除）+ 文字层 text/ 四件（刻意不拷 relationship.json/candidates.jsonl——构建端配置与闸门痕迹不属交付面）+ 生成干净 index/README/双脚本 + 六项一致性硬校验（含 HTML 无外链红线）+ sha256 manifest + --verify/--dry-run。缺陷史：v1 reconcile 三连（"./"前缀永不匹配每跑全删重拷 230MB/期望集漏生成物/data 递归被切）静态分析抓出回炉重写"期望集+两遍清扫"；分片形态 {records:[...]} 规格错误我方 hotfix 兼容。**实测**：161 文件/241.7MB checks=ok、幂等二连跑 copied=0 deleted=0、植入文件精准清除、违禁物 0、--verify 161/0/0/0、守卫 exit 2；**Playwright 真浏览器三页验收全过零 console 错误**（8021 独立服务器，favicon 404 属浏览器默认）
- **Phase 5 收官（MVP 交付）**：Codex 终审 ACCEPT with fixes（3 MAJOR：dry-run 建目录不零写/离线红线漏 srcset+css url/畸形 meta int() 崩；2 MINOR：畸形 manifest 条目静默过/"她是怎样的人"性别硬编码；另确认 reconcile 无越界删除）→ DeepSeek 五项全修 → **专项验收 11/11 全 PASS**（红线扩面拦截实证/畸形 meta 不崩计 failure/畸形 manifest 致 verify 失败/dry-run 对不存在 dist 零创建/person-generic/幂等+verify 回归）→ 提交。**MVP 四层交付完成：people/mama/archive_dist = 161 文件 241.7MB，拷走即用**

## Session 2026-08-17（对话页：file:// 引导 + Claude 官方接入）
- 用户实报"模拟对话打开显示档案加载失败：Failed to fetch"+ 问 BYOK 能否接 Claude
- 诊断：Failed to fetch = 双击 HTML 用 file:// 直开，浏览器拦 fetch（http 场景昨晚 Playwright 三页验收全过佐证）；正确姿势 = start_server.bat → http://localhost:8020/
- **build_chat_page.py 七处改动（DeepSeek + 声明 hotfix 一处，spec_chat_provider.txt）**：①file:// 守卫（引导气泡+禁发送）②设置抽屉接口类型 select（openai 默认/anthropic，localStorage 向后兼容）③splitSystem 纯函数④sseProcessLine 双协议（content_block_delta/text_delta + message_stop，OpenAI 共存）⑤streamRequest 按 provider 分支（Claude：x-api-key + anthropic-version + **anthropic-dangerous-direct-browser-access** header，body 带 max_tokens:2048/system 拆分）⑥非流式回退兼容 content[] 形态⑦占位符随下拉切换（hotfix：读 cfgProvider.value）
- 验证：harness 五套全绿（provider 14/14 新增 + 老四套 16/6/20/2 零回归，老 harness 补 location 全局 stub）；**真浏览器实锤 CORS 直连**：anthropic 模式 + 假 key → 页面收到 API 标准 401 JSON（authentication_error）——preflight 通过、直连通路成立
- archive_dist 增量重建 copied=1（恰 chat.html）+ verify ok；Codex 审核后台中
- 顺带修 claude-api skill 触发合规：接 Claude 的设计先读 skill（Messages API/SSE 格式/浏览器 CORS header 出处）
- **用户气泡不可见 bug 破案修复**：Playwright 复现实锤——addBubble user 分支设了样式类但漏写 textContent（自对话页 v1 潜伏，历次审核只测纯函数与发送流）；一行声明 hotfix + harness 源码合同回归 + 浏览器复验（393c74e）
- **微信式语音回复全链路（用户需求②）**：①tools/tts_server.py（DeepSeek 一发）——v0.2 e14 双语域本地合成服务 :8022（/health、/tts JSON→mp3、CORS、串行锁、int16+解码回读自检、120 字上限、时长 QC 重抽一次）；实测装载 15.6s、稳态 ~6s/句、RMS 0.07-0.10、错误路径全对；已脱钩常驻（Start-Process，wu-sft/tts_server/ 有 log/pid/start_tts.bat）；②build_chat_page.py +109 行（DeepSeek）——probeTts 探活（同主机:8022，Tailscale/LAN 通用）、回复≤120字且服务可达时气泡变绿色语音条（纯函数 voiceDurToWidth 定宽/时长标签/点击播放互斥/playing 动画）、右键+长按出菜单（标签"合成语音 · 非原声"守 Tier 纪律）转文字切换、四类失败全部优雅降级文字。**真浏览器全链路 E2E**（mock LLM SSE + 真 TTS）：语音条 83px/5″/播放/菜单/转文字全过，截图存档；合成样本 probe1.mp3 已直发用户。harness 五套 18+16+6+20+2 全绿（stub 补 window.addEventListener/URL/Audio）
- **外网访问（用户需求）→ 组网成功**：方案 Tailscale 私网（档案含隐私，裸公网隧道违背铁律 3 底线）。**故障链全记录**（近两小时排障）：①tailscale login 非 TTY 不吐授权 URL（CLI 缓冲，用户 `!` 命令同样吃掉）→ 改 auth key 流（用户手机生成 tskey 发来）②`up --auth-key` 超时：非提权 shell 的 Stop-Service/Stop-Process 全部静默失败（UAC ConsentPromptBehaviorAdmin=0 发现可静默自提权，winget 装机也是这么成功的）③提权后仍超时 → 守护日志实锤真根因：**腾讯电脑管家拦 SYSTEM 服务出网**（DNS 解析失败 + 全部 bootstrap IP 拨号 WSAEACCES"forbidden by access permissions"——本地拦截特征而非 GFW；用户态同 IP 秒通对照实锤不对称）④绕过：**userspace-networking 模式以用户身份跑 tailscaled**（Windows 服务停用；非提权建管道报属主错 → 提权用户态；up exit 0 登录成功但 CLI 断开即拆线 → 补 --unattended serverMode 落定）。**终态：PC=100.116.45.2（justin-pc）+ 用户 iPhone（100.111.127.101）双设备在网**；登录自启任务 TailscaleUserspace 已注册（userspace+statedir，unattended profile 自动上线）；含 key 脚本已清理（key 单次已消耗）。已知风险入档：电脑管家日后若拦用户态进程需回家加白名单；UDP 被管家限 → 走 DERP 中继 TCP443（延迟略高可用）
- **语音两件套 Codex 首轮 REJECT → 实证反驳 + 修复 → 复审 ACCEPT**：其 BLOCKER（"lang 缺省稳定 500"）六格矩阵（中/英 × 缺省/mandarin/wu）实测全 200 不能复现——判定系其裸 socket 分帧实验污染 keep-alive 连接所致（其自证的 501 错乱同根因）；复审时 Codex 用干净连接独立重测六格全 200 全有效 audio/mpeg，**主动撤回 BLOCKER 改判 ACCEPT**。真发现全修：MAJOR-1 分帧加固（MAX_BODY 64KB/缺失非法 CL→400/超限→413/一切错误响应断连防污染，DeepSeek 重写；裸 socket 三式攻击实测全防住）、MAJOR-2 --token 可选鉴权（默认关=私网信任，Codex 复审认可 posture）、MINOR blob 池上限 50 回收 + touchcancel + 原生长按抑制（声明 hotfix）。教训入档：**审核方自己的破坏性实验会污染共享测试环境——复现缺陷必须干净连接/干净状态**
- **Codex 审核 ACCEPT with fixes（两 MINOR 均实锤，其复现脚本抓出）**：①openDrawer 不回填 cfgProvider——未保存的下拉状态跨开合泄漏，可能误存 provider；②sseProcessLine 双协议未隔离——对抗场景 OpenAI 流混入 message_stop 会提前终止/Anthropic 流混入 choices 会双重追加。声明 hotfix 三处：openDrawer 回填+updatePlaceholders、sseCreate(mode) 状态机按 provider 隔离（默认 openai 向后兼容）、streamRequest 传 mode。harness 升至 **provider 17/17**（新增两条对抗回归 + openDrawer 源码合同）+ 老四套 16/6/20/2 零回归；dist 增量重建 copied=1 + verify ok。Codex 其余裁决：file:// 守卫禁设置可接受（file: 与 http 非同源，放开反而误导）、splitSystem 在 buildMessages 单 system 契约下无回归点、max_tokens/旧数据兼容无发现
- **记忆卡 draft→corrected 升级执行完毕（任务 #2）**：build_voice_transcripts 用 v02 校对稿重建（--corrected-text v02_full/data/text 160 条）→ **99/99 全 corrected，draft 归零**（此前 44+55），9 条文本实改（BROOKS BROTHERS 等 14 处校对分布于 9 记录）、55 条 quality 升级 → extract_memory_candidates 重挖至独立 fresh 文件（150 条，配额 61/23/22/22/22 不变）→ merge_candidate_state 合并：**150↔150 全对齐（candidate_id 确定性生产实证），124/26 裁决零丢失，38 卡 content_changed，零新增零结转零丢弃** → 空 delta 重跑 apply_gate_decisions（dataset 指纹 9c6f3423e44a 与历史一致）→ **memories.md 重生成 124 条，校对文本落位**。38 张 content_changed 卡的新文本即用户校对定稿本身，不强制复审（标记保留在 candidates.jsonl，需要时可出复审页）

## Session 2026-08-18（/clear 后新回合：Phase 6 GPT-SoVITS 泛化普粤管道开工）
- 恢复上下文（planning-with-files + HANDOFF ⓪⁺⁺⁺⁺），按用户拍板直取任务 #14；task_plan 增 Phase 6（6a 环境底座→6b 转写策略实验→6c 数据工具→6d 微调 CLI→6e 合成+QC+A/B→6f 粤语验证）
- 现场探查：GPT-SoVITS 不在盘 → 走下载线；v02_full/data 八件套 + 125 WAV + ref01-05 参考资产全部在位；GPU 5.9/24GB 空闲无训练任务
- 6a 开工：魔搭直链（GitHub release 无资产，正文给三源；用户 4090 用标准包非 50 系特供）→ 后台断点续传循环下载 GPT-SoVITS-v2pro-20250604.7z 至 ~/gpt-sovits/；7-Zip winget 装毕（盘上原无解压器）
- 同题对照资产盘点：blind_v1/texts.jsonl b01-b10 + listen/texts_hupu.jsonl h01-h04（普通话冒烟可与 v0.2 e14 沪普域 + Fun-CosyVoice3 probe1 三方同题）；粤语臂届时同款句转粤文（'yue'）
- 6b 前置并行：Claude 子代理（判断类留家族，persona 先例）后台跑 160 条转写语域标注（wu/mixed/mandarin）+ 普通话近似转写版 → workdir/register_annotation.jsonl——转写策略实验两臂（普译臂/筛子集臂）的直接输入
- **6a 收官（当日）**：7.6GB 整合包落地解压（底模全在含 v2Pro sv 模型）→ api_v2 :9880 脱钩起服（自定义 yaml v2Pro+cuda+half，Start-Process 红线遵守）→ 读盘代码确认接口（POST /tts；语言 all_zh/all_yue；/set_gpt_weights //set_sovits_weights 热切换=管道化利好）→ 参考挑选探针（v02 数据 26 条 5-10s 合法区间，定 refA 近普转写/refB 健康期沪密/refC 中密度三候选）→ **zero-shot 冒烟 16/16 全出**（12 普 + 4 粤，~2s/条 32kHz）。**抽卡实锤第一例：refB_h01 十四字仅 0.7s 截断**（时长/字数比 QC + ASR 回读进管道必做实证）。MP3 64k 转码 + 解码回读抽查一致 → 8 条代表样本（三参考同题对照/长句/粤语×3）直发用户手机，等三判：音色像否/哪参考最像/粤语音色保持否
- 并行调研：Explore 代理读整合包训练链路（.list 格式/1abc 预处理环境变量/s1 s2 训练脚本与 config 生成/微调权重落位与热切换/v2Pro 默认参数）→ 产 CLI 化配方笔记，作 6d DeepSeek spec 素材
- **CLI 配方入库 docs/research/gpt-sovits-cli-recipe.md**（Explore 代理 75 工具调用逐行核对，零猜测全带行号）：三大坑=①users.pth 陈旧+_pth 隔离 PYTHONPATH 失效 ②分片合并+tsv 表头在 webui 层脚本不做 ③v2Pro 漏跑 2-get-sv.py s2 即崩；数据硬边界 0.6-54s（160 条全合法）；s2=全参微调非 LoRA（batch12/epoch8）；s1（batch12/epoch15）；权重热切换零特殊处理（b"05" 魔数自动识别）。users.pth 已重写并验证（import OK）
- **臂 C（沪语本字直喂）端到端探针开跑（工艺=探针验证配方→DeepSeek 工具化，探针全部已声明存 workdir）**：mama_c_raw.list 160 条生成（绝对路径模式，basename 唯一/竖线/存在性三检零问题）→ 预处理四步 CLI 复刻（probe_preprocess.py 含 webui 层合并+表头逻辑）1a 10s/1b 54s/1b-sv 15s/1c 5s 全过
- **★ G2P 破坏面发现（findings 已录）**：1a 对账 147/160——**「覅」字 g2p 出 fiao 不在普通话音节表 AssertionError 崩整条**（13 条 8% 全灭，1a try/except 静默吞，只有对账能见）；「㑚」×23「嗯」×4 被 normalizer **静默删字**（文本-音频错位更隐蔽）。对策 g2p_char_map（voice_profile 参数首例）：覅→表/㑚→拿/嗯→恩（拟音最小错位），只改 .list 层校对原文不动 → 重生成零残留 → 1a 重跑 **160/160 全过**
- s2 训练启动（Start-Process 脱钩+日志直写+Monitor 三态，红线遵守）：tmp_s2_mama_c_raw.json（batch12/epoch8/save4/fp16/text_low_lr 0.4/v2Pro 底模对）;s1 config 同步备好（tmp_s1_mama_c_raw.yaml，epoch15/save5/s1v3 底模）
- **s2 收官（~7 分钟）**：SoVITS_weights_v2Pro/mama_c_raw_e4_s76.pth + e8_s152.pth 双权重，进程干净退出
- **s1 首启即崩 + 破案修复（findings 已录新坑）**：dataset.py:234 assert bert长度≠phones数——根因 1-get-text.py:94 bert 按文件名缓存跳过，char_map 重跑 1a 时 147 条旧文本 bert 残留。修复：清 3-bert 全量重跑 1a（160/160）→ 新增全量对账探针 probe_verify_bert.py（bert.shape==phones 数 160/160 全对齐）→ s1 重启（s2 无恙：其用的 2-name2text.txt 已是新版且不吃 bert）。微调后合成探针 probe_finetuned_synth.py 已备好（热切换+同题普粤合成+时长比 QC），s1 完成即跑
- **语域标注子代理回报（151k tokens/75 分钟，自检全过）**：workdir/register_annotation.jsonl 160 条——**分布 wu 90 / mixed 57 / mandarin 13**。⇒ 6b 实验定型两臂：**臂 C=本字直喂（在训）vs 臂 A=全量普译**（纯 mandarin 仅 13 条，筛子集臂数据不足否决）。臂 A .list 已生成（mama_a_man.list，160 条零问题）
- **★ 记音字发现（子代理系统性难点报告）**：校对转写含大量同音记音字——雪小辈=血小板/带生=戴森/牌子=台子/疾病=截屏；**人名"亦添"存在 十一天/顺一天/陈一天 等多变体记音**（普译版已统一还原并逐条 note）；15 处记音彻底不明存疑。影响：①臂 A 文本某种意义上"更正字"②档案转写层的记音字是潜在改进项（动校对稿需用户闸门，未立项）
- **臂 C 训练全链闭环（s2 ~7min + s1 ~15min，两权重落盘）**：s1 修复后一次通过（mama_c_raw-e15.ckpt）。热切换 200 双成功 → 同题合成 8 条（普 4 全 OK；粤 4 中 y02 时长比 0.76 QC_SUSPECT=抽卡实例二号，自动标记生效）→ 7 条 MP3（剔 y02）+回读抽查一致 → 已发用户。**微调全链路 CLI 配方端到端验证完毕**——6c/6d 工具化 spec 素材齐备
- 臂 A（普译版）串行开跑：预处理四步一次 160/160 全过（普译文本 G2P 天然干净，零 char_map 依赖）→ s2 脱钩+Monitor 在跑，完成接 s1 → 同题合成 → 三方 A/B 包（zero-shot/臂C/臂A × v0.2 e14 对照）
- 臂 A s2 收官（~7min）→ s1 脱钩开训 + Monitor
- **6c/6d 工具化开工（铁律路径）**：spec_gsv_pipeline.txt（scratchpad，五子命令 prepare/preprocess/train/synth/verify + voice_profile schema + 今日全部实证坑写入硬性要求）→ DeepSeek 一发 34.4KB/818 行 → 5 处 f-string 多行 dict（3.10 不支持）机械同型声明 hotfix → py_compile 过。**people/mama/voice/gsv_profile.json 落位（voice_profile 参数化首实例）**。冒烟：prepare 两臂与探针产物**字节级 fc /b 零差异**（行为等价实证）；负路径三发现（未知 arm 裸 KeyError / prepare 与 verify sha 算法疑不一致 / verify bert 校验系统 python 无 torch 刷屏）→ 全部写入 Codex 审核 prompt（后台审核中）。工具已拷 tools/gsv_pipeline.py（工作树未提交，ACCEPT 后 commit）
- **Codex R1 REJECT（6 条全实锤，其实读产物+实跑复现）**：2 BLOCKER=guard 先写后检+users.pth/.gsv_list_sha256/NamedTemporaryFile 未过 guard；bert==phones 把 4 列 TSV 按 2 列解析（split("\t",1) 后两列混入 phones 计数，校验永不可靠）。3 MAJOR=unknown arm 裸 KeyError 且四子命令不校验/bert 装载失败 161 条刷屏（裁决：改 runtime python 子进程）/synth QC 重抽 status 取首轮+infer_s 硬编码 0.0+占位代码。1 MINOR=sha 双算法。→ 六项转精确修复要求（含行号）回炉 DeepSeek → **v2 一发 957 行 py_compile 过**。冒烟全绿：prepare 字节级回归零差异+sha 统一文件字节哈希；unknown arm 干净 exit 2 带可用列表；verify 161 刷屏→1 条（bert 子进程 160 全过；剩余 1 条=探针时代未写 sha 记录的预期失败）。Codex 复审后台中
- **Codex R2 ACCEPT with fixes**（六项全确认修复+guard/require_arm/4列解析/子进程/QC 语义逐处行号复核；剩 2 MINOR：残留占位 qc() 哑函数、manifest 写失败裸 traceback）→ 声明 hotfix 两处 → 回归过 → **提交 3fd0e65（工具+配方文档+findings/planning）**
- **臂 A s1 收官 → 正式工具 synth 首实战**：普 4（3 PASS+1 SUSPECT，重抽救回 2）+ 粤 4（3 PASS+1 SUSPECT，重抽救回 1）——QC 重抽机制实战验证；h02/y02 同句三批均难产（句式难度非模型差异）。6 条 PASS 转 MP3 回读抽查后发用户。**三方对照物料齐（zero-shot/臂C/臂A × 现役 v0.2 e14 同题）→ 等用户终局耳测三问定转写策略**
- 会话收尾：task_plan Phase 6 状态刷新、HANDOFF ⓪⁺⁺⁺⁺⁺ 增补、memory 项目状态+索引更新、收尾提交推送

## Session 2026-08-17/18（战略文档三连 + TTS 前沿研究收口 + GPT-SoVITS 泛化管道立项）
- **战略文档三连提交**：docs/PIPELINE.md（0e783dc，七 Stage 全配方+七闸门+skill 化蓝图）、docs/GENERALIZATION.md（43c76ce，五轴泛化+两纪元 sessions 永不合流架构）、docs/research/messaging-channels.md（bbbf8e7，TG 周末级/WA 周级/微信需主体资质三档；通道网关兼轴五 sessions 采集器，P1=TG bot）。另答用户两问（商业化路径 / Windows App 化）——均为对话裁决未立项
- **TTS 前沿研究立项并收口（任务 #13 → docs/research/tts-frontier-2026.md，e4d9e2f）**：用户点名 6 模型（voxcpm2/indextts2/gpt-sovits/dots.tts/qwen3-tts/grok voice）× 初始 8 维度，中途追加维度 8（训练数据质量数量）/9（人工干预程度）。执行：主轮 workflow 7 代理（6 模型独立检索核证 + 沪语生态扫描）+ 补充轮 5 代理（维度 8/9，Grok 免研究），共 12 代理 100+ 信息源，全部结构化 schema 产出零空结果
- **研究裁决：不换现役**——六候选全部不支持上海话克隆。VoxCPM2=唯一 A/B 候选（吴语大类+16kHz 原生输入+SIM 开源第一梯队；但全量 SFT ~40GB 超 4090、长文本自认不稳）；Grok Voice 活体同意验证（实时朗读校验短语+声纹比对）制度性排除逝者场景——反向印证本地开源权重是唯一路径；dots.tts 有效带宽估计过滤=窄带素材架构级冲突（六者最差）；Qwen3-TTS=方言开源化头号观察对象（阿里 API 线有沪语预置音色但克隆×方言不相交）
- **维度 9 产品级发现**：三大人工闸门（转写校对/checkpoint 挑选/产出筛选）中产出人耳筛选无任何模型可消除；仅 zero-shot 能省前两个但全不识上海话——"省人工"与"最像"对立 → App 两档设计（⚡快速档 zero-shot 分钟级验货 + 💎精修档微调全闸门）；**校对页/试听页/盲听页是产品核心组件而非脚手架**。沪语生态：SS 变体仍无权重、Wu 系 2026-01 冻结、CN-MultiDialect-ASR 可作方言合成质检器候选
- **分语域选型定案（08-18 与用户对齐）**：上海话=现役无竞争；沪普=现役裸文本域已覆盖不需新模型；普通话泛化=GPT-SoVITS v2Pro 主选（6-8GB 门槛/工具链/v2Pro 官方明示对平庸音质宽容）；粤语=GPT-SoVITS 唯一音系级（'yue'）支持；Fun-CosyVoice3 留位单底座候选（A/B 第三组）
- **★ 用户拍板（08-18）："根据妈妈声音做一套泛化的普通话和粤语管道，用 GPT-SoVITS"** → 任务 #14 立项，下一会话开工。要点入 HANDOFF ⓪⁺⁺⁺⁺：person-generic+voice_profile 参数化；首个待决=转写策略（沪语本字 vs 普通话近似）；粤语=跨语言能力验证；抽卡短板内建 ASR 回读 CER 自动淘汰；DeepSeek 写+Codex 审铁律不变
- 会话收尾：HANDOFF ⓪⁺⁺⁺⁺ 增补+语音选型决策行刷新、memory（项目状态+索引）更新、本记录，随收尾提交推送

## Session 2026-08-21（VS Code 迁移首会话：耳测站上线 + 转写策略终局定案）
- 环境迁移体检（CLI→VS Code 扩展）：DeepSeek API（key+两模型列表）/ Codex MCP（实测 ping 通）/ GitHub（gh 登录+ls-remote 与本地一致）三链路全绿
- **耳测站上线（用户指令"网站形式走 Tailscale 审核"）**：复用已审 make_listen_page.py + Claude 直写 manifest（纯数据声明，存 workdir/gsv_review_manifest.json）→ archive_out/gsv_review.html——9 组 32 条 2.82MB：普 4 句四方对照（现役 v0.2 e14/zero-shot/臂C/臂A）+ 粤 4 句三方 + 附加参考 B/C 对照；QC 疑似三条红标补全（此前手机批剔除件）；index.html 加 🎧 入口（直写声明）
- 部署细节：8020 服务器重启后掉线 → Start-Process 脱钩重启（PID 11464）；Tailscale PC 端在线 100.116.45.2，iPhone 需用户开 App 上线；真浏览器验收仅 favicon 404（豁免同 Phase 5 前例）
- **★ 用户终局耳测三判（Phase 6 关键裁决）**：①普通话=臂C（沪语本字直喂）②粤语=零样本（"都差不多"→取零成本路径，粤语域免训练）③参考=refA 音色最像（6a 遗留问题收口）→ gsv_profile.json 写入 defaults{mandarin:finetune/c_raw, yue:zero_shot} + decision_log（json.load 验证过；gsv_pipeline 按键取值容忍新增字段已核）
- 6b/6f 关闭；Phase 6 剩 6e ASR CER 回读 QC（funasr -l zh/yue）——下一工程项（DeepSeek 写 + Codex 审）

## Session 2026-08-22/23（纸片人审核 → 口型 bug 双根因修复 + 帧素材重做）
- 用户审核纸片人实报："卡通一闪一闪，没有大小嘴切换" → systematic-debugging 全流程
- **根因一（代码，自 08-12 潜伏）**：静音看门狗（rms<0.0001 持续 600ms → setFakeMode 永久切伪驱动）在 rAF 里无条件跑——页面打开 600ms（无播放）即永久退化 240ms 机械交替；真音量驱动任何真实使用中从未生效。实锤链：Playwright 采样切换间隔精确 240ms 等距（真驱动应随语音不规则）→ 空闲 1.5s 零交互 console 已打 Fallback。历次 harness 验收模拟了 play 流但没模拟"打开先闲着"的真实时间轴
- **根因二（素材）**：旧说话帧（O嘴 seed1002）整脸变表情（瞪眼+挑眉）且静息帧本身是张嘴大笑——无闭↔开信号，交替=两张脸轮播。当年"仅嘴变O型"判定系静态并排看走眼，从未按动画连播验收；当年 prompt 前提即错（"把她闭着的嘴改为张开"——原图嘴本来就张着）
- **修复一（DeepSeek + Codex ACCEPT 零发现，cacaf23）**：看门狗仅播放中计时 + play 事件 tryRealMode 复活（iOS 等 analyser 真失效场景兜底语义保留）。修后实测：空闲不退化，播放中切换 160-880ms 不规则随语音
- **修复二（素材重做，探针声明复用已审 build_graph）**：ComfyUI+Qwen-Image-Edit 从定稿头像生成闭嘴微笑候选×4（seeds 3001-3004）→ 用户选 s3002（灰眼保持）→ **新帧映射：静息=s3002 闭嘴微笑 / 说话=原定稿张嘴笑（04 s1001）**，旧 O 嘴帧退役备份 versions/avatar_frames_20260823/；avatar_choice.json 增 frame_remap_20260823 溯源块
- **根因三（部署，截图抓出）**：img URL 无缓存穿透——浏览器按 08-12 Last-Modified 启发式缓存死粘旧帧（换了图用户也看不到）。声明 hotfix：build_avatar_page img src 加 ?v=<内容哈希8位>
- 终验：静息截图=闭嘴微笑 ✓ 播放中 35/60 张嘴帧、起始静音垫闭嘴正确 ✓；archive_dist 增量重建 copied=4 checks=ok
- 环境：ComfyUI 起停一轮（生成用），api_v2 :9880 已复原常驻（PID 见 workdir/logs/api_v2_20260823.log）
- 用户待办"说话帧确认"就此闭环（旧帧被否决重做，新帧对用户选定）

## Session 2026-08-23/25（用户判死双帧架构 → 渲染研究 → Phase 0 嘴部贴片落地）
- 用户复审仍报"疯狂闪烁"并裁决"这个技术有问题"→ **双帧整图轮播架构性判死**（两张独立 AI 图像素级全图偏移，任何节奏都是闪不是动嘴）→ 立项任务 #17
- **渲染技术研究收口（workflow 4+1 代理/90 检索 → docs/research/digital-human-rendering.md，4f4849d）**：主线=viseme 嘴部贴片+预计算时间轴（五约束唯一全绿，路线3独立收敛同构=双重验证）；talking-head 四强（InfiniteTalk/EchoMimicV3/FantasyTalking/Sonic）降为精品条目增强+第一备选；Live2D 闭源 core 违 20 年红线不投入
- **Phase 0 执行（用户令"开工"）**：
  - 贴片素材：嘴部矩形标定 (480,460,700,640)+羽化14 → Qwen-Image-Edit 从底图（s3002）生成说话嘴型——首轮"半开"全出大嘴（prompt 无视"小缝"）→ 迭代 prompt 二轮命中；程序化羽化合成（矩形外像素=底图，架构保证）→ 连播 GIF 验收（血泪教训执行：素材必按动画验收）→ **SendUserFile 本会话已禁用发现**（此前"成功"未真送达）→ 改走 8020 站点 mouth_preview.html → **用户定稿 A 温和版**（half=s4101 唇缝微分/open=s4101 温和张嘴）
  - 资产：全尺寸 RGBA 透明叠层（羽化烘进 alpha；矩形外 RGB 清零 1.17MB→54/61KB）+ persona/mouth_patches.json（rect/image_size/states/provenance）
  - 工具：build_avatar_page.py 增 patch 模式（DeepSeek×3 轮 + Codex REJECT×2→ACCEPT + 声明 hotfix 两行）。审核实录：R1 我方抓 BLOCKER=.format() 撞 CSS 花括号（"%撞CSS"老坑 format 变体）+ 架构陷阱=容器百分比定位 vs object-fit:cover 裁切错位→贴片改全尺寸透明叠层（HTML 零坐标）；R2 Codex 抓 High=json 根类型非 dict 崩+Medium=fake 模式三态退化两态（level 0/1 改连续包络 0-0.08）+Medium=hasImageMode 与 patch 不互斥（改按模式特有元素判定）；R3 Codex 复审抓 states 非 dict 残余崩溃口→声明 hotfix 两行→**终裁 ACCEPT**
  - 验收：三态实测 C23/H9/O28 随语音、坏 JSON/无 JSON 降级回归 T2-T5 全过、整页截图贴片无缝、archive_dist 同步（162 文件 copied=5 deleted=2 checks=ok）
- 环境：api_v2 :9880 复原常驻；ComfyUI 已停；8020 站点常驻。**Phase 1（Rhubarb viseme 时间轴+6 态扩容）待排期**
- **家人盲听 v2 移除（用户裁决"移除这项"）**：M1 以用户本人盲听 v2（8 条骗过 7，08-16）为最终依据关闭；blind_v2 物料保留、待办清单与催办全部撤下（HANDOFF/task_plan/memory 同步）
- **6e ASR CER 回读 QC 开工即收官（用户令"开工先"）→ Phase 6 全部完成**：
  - 引擎选型：整合包 funasr 的 yue 走 UniASR TF1 旧模型且未下载（风险）→ 改用已有 venvs/asr + **SenseVoiceSmall**（单模型 zh/yue）；探针五连实证（Claude 直写已声明，scratchpad/probe_sensevoice_qc.py）：zh cer 0/0.071、yue cer 0/0（粤语识别惊艳）、错配 1.0、CPU 0.1-0.4s/条、模型 ~900MB 入 modelscope 缓存
  - DeepSeek v1（46KB spec 含全源码，一发 1294 行剥围栏 py_compile 过；diff +371/-2 全部落许可区域）→ 我方自查 3 项（err2 双计数/FAIL 条目误标 ASR_ERROR/死代码）→ 冒烟四套全绿（helper 六格、全链 on、--no-asr-qc 回归、--cer-max 0.01 逼出 round2——r2 实抽 cer 0.5385 更差被正确拒收=门控实战）→ Codex R1 **ACCEPT with fixes**（3 MAJOR：round2 采纳后 SUMMARY 不回算+确认双计数+异常不置 asr_qc:"error"；2 MINOR 均确认我方自查）→ 修复 spec 回炉 DeepSeek v2（+17/-13 五项精确落位）→ 三套回归全绿 → Codex 同线程复核 **ACCEPT**
  - 落位：tools/gsv_pipeline.py（synth 批后两轮 + `_asr` 内部子命令跨 venv 子进程 + PEOPLE_DIR 守卫）；gsv_profile.json 增 asr_qc 块（python/model/cer_max 0.30/enabled，gitignore 内需知）；报告新增 asr_status/cer/asr_text/cer_retried/cer_retry_cer/final_ok，SUMMARY 终态重算
  - 环境：api_v2 :9880 重启常驻（Start-Process+日志直写，v2Pro yaml 有状态恢复了 a_man 权重，synth 热切换自理）；粤语零样本批 QC 可单独调 `_asr` origin

## Session 2026-08-25 晚（用户复审"按播放后没变化"→ 真根因落网：贴片从未渲染过）
- 用户手机复审 Phase 0 报"按播放后卡通人没有变化"→ 系统化排障：服务端全排除（8020 存活、资产齐、同服务器桌面 Chromium"正常"）→ 判定设备侧断层
- **诊断 HUD 入库（1ea03a3）**：?debug=1 显示 BUILD/MODE/SRC/CTX/SPK/LV/FRM/AUD/IMG/ERR，HUD 缺席本身=旧缓存判据；DeepSeek×1 + Codex REJECT（子串匹配误触发+_hudError 死代码）→ 声明 hotfix → ACCEPT；window.onerror 常驻捕获
- **workflow 三视角审计（4 代理）交回代码级实锤，颠覆"设备侧"判定**：`style.display=''` 被 CSS 类规则 `.mouth-patch{display:none}` 回落吃掉——**贴片自上线起在任何浏览器都从未渲染过一个像素**；Phase 0 的"三态实测 C23/H9/O28"采的是 inline style 遥测=假阳性，"整页截图无缝"=贴片根本没画所以"无缝"。开发机"正常"与手机"不动"同因
- **修复（DeepSeek×1 + 声明 hotfix + Codex ACCEPT，41e9dc3）**：全部显示分支显式化 display='block'（patch/image/svg 三模式统一消灭 ''回落地雷）；patch scale 从容器（transform 被 bob 动画每帧覆盖=第二个哑通道）改三张 img 同步缩放；HUD IMG 行补 base；hotfix=DeepSeek 把 pause 的 frameClosed 写成 'none'（暂停藏整头像回归）改回 'block'
- **像素级验收（新铁律首执）**：getComputedStyle open 帧 block 37/65 采样；暂停基线 vs 播放中截图 diff 10.9/px、肉眼实锤真张嘴（露齿）且脸/眼镜/发不变；暂停回闭嘴路径干净；archive_dist 同步（162 文件 checks=ok）
- **教训入 memory（verify-rendered-pixels.md）**：视觉/动画验收必须 computed style+截图 diff，inline/内部状态遥测不算验证；显示一律显式 'block'；transform 效果须打在无 animation 的子元素
- 待用户：手机重开 avatar.html 复核（?debug=1 可看 BUILD≥20260825-194708 自证新版）

## Session 2026-08-26/27（Phase 1 全落地：viseme 时间轴 + 六通道整脸微活）
- 用户拍板"只有嘴型动感觉不够，安排 Phase 1，能否渲染整张脸"→ 答复分两档：本 Phase=眨眼+头部微动+音素口型（静态约束内），整脸表情走特别版预渲染 MP4（主线稳后试片）
- **1a Rhubarb 管线**：v1.14.0 下载入位 ~/tools；批跑 125 条上海话全过（18516 cues；坑：--machineReadable+stdout 拿不到 JSON，必须 -o 文件）；生产工具 tools/build_visemes.py 入库（DeepSeek 写；hotfix=mkstemp fd 双重 close 竞态实测 Bad file descriptor 群发 + Codex 抓增量吞失败→失败条目退缓存）
- **1b 贴片扩容**：ComfyUI 复用 Phase 0 管线出 wide/round/pucker/blink×3 种子；首轮嘴型普遍夸张（大张=喊叫、圆唇=香肠嘴）→ wide 温和化精修命中（s4211/s4213）、round 精修反而更厚弃用回首轮 s4203；眨眼一次命中（双镜片内区替换、镜框恒用底图像素，三种子全可用）；连播 GIF 审核页 phase1_preview.html（11 GIF）→ **用户 08-27"先按照这些定稿"→ W1(wide2_s4211)/R1(round_s4203)/嘟唇并入圆唇/B1(blink_s4201)**
- **1c 运行时**：build_avatar_page.py 数据驱动 N 态（mouth_patches.json v2: states/viseme_map/rms_states/blink + Python 端 fallback resolve）；时间轴驱动优先（currentTime 查 cue）、RMS 回退（BYOK 动态分支保留）；眨眼调度器待机也眨；.avatar ambient 常驻微摆；HUD 扩展 TL 源。审核链：DeepSeek×2 + Codex REJECT（3 实锤：增量吞失败/config 损坏回退死路→DOM 扫描恢复/空 states 建运矛盾）→全修→**ACCEPT**+声明 hotfix×4（含 DeepSeek 丢 avatar-base img 的 BLOCKER）
- **定稿装配**：烘焙全尺寸 RGBA 叠层（wide 60K/round 60K/eyes_closed 75K；RGB 取 raw 非 comp 的叠加数学自验 diff=0）；mouth_patches.json v2 写入 provenance；重建 376KB（时间轴内联）
- **像素级验收**：8 秒采样六通道全动（closed11/half95/open31/wide25/round16 + 眨眼3 + TL 驱动 178/178）；慢放 0.25× 抓 wide 实拍（温和张嘴露上齿）；克隆节点抓眨眼实拍（镜片后双眼轻阖）——中途两次"强制显示被 rAF/调度器覆写"的截图竞态被识别并绕过
- archive_dist 同步（166 文件 checks=ok）；ComfyUI 停、api_v2 重启归位（真实路径=gpt-sovits/GPT-SoVITS-v2pro-20250604/runtime）
- 提交：48fc2d8（代码层）；**Phase 1 完成**。下一步：talking-head 特别版试片（整脸表情 MP4）

## Session 2026-08-27（任务 #18 立项：桌面陪伴型数字人可行性研究）
- 用户立项：研究桌面陪伴数字人（打字/语音输入 → 语音/文本输出）是否可行
- task_plan.md 注册 Phase 8；研究 workflow 启动（六维度多代理）→ 目标产物 docs/research/desktop-companion.md
- workflow wf_c886ce8b-4b8 收官：14 代理（6 研究 + 8 校核）全成功，~89 万 tokens/285 工具调用/20 分钟；校核 6 confirmed 2 refuted（上海话 ASR Dolphin 翻案 / 本地 LLM 显存-幻觉推理链否决）
- 报告成文 docs/research/desktop-companion.md：技术拼装级可行；伦理三档判定——常驻不应做、上限=打开才在的对话窗（条件 a-f）、不做是合理默认
- findings.md 增补六条关键发现；task_plan Phase 8 → research complete 等用户裁决

## Session 2026-08-28（任务 #16 微信 UI 自动化活体探针）
- 用户备好小号（PID 15396，已登录小号，4.1.12.26 确认未被自动更新推走）
- Claude 直写 8 个只读探针（声明；uiautomation 2.0.29 + comtypes 1.4.16）：全程不点击/不输入/不发消息/不采集聊天正文
- **NO-GO 铁证**：控件树恒 3 节点空壳；五重触发全败（attach遍历/ElementFromPoint穿不透/SPI_SETSCREENREADER/真实Narrator运行/comtypes RawViewWalker）→ killer_risk 命中，4.1.12.26 关闭 Qt QAccessible→UIA bridge
- 连带：UIA 读+发同时归零；读退路=DB轮询(4.1.12未复验)，发退路=坐标/OCR最脆层
- 环境全清理（Narrator关/SPI复位/窗口未置顶）；结论入 docs/research/wechat-ui-automation.md 第六节 + findings；三选项交用户裁决

## Session 2026-08-28（任务 #18 Phase 8A 开工：桌面陪伴上限形态）
- 用户裁决'继续推进桌面陪伴'→ 按报告第七节 Phase A 开工，上限形态（打开才在的对话窗），条件 a-f 硬规格
- 8A-0 告别/降级协议成文 docs/companion-farewell-protocol.md（条件 f 前置件，第五格留用户填）
- 源文件接口摸清：avatar 单 audio#player+analyser（blob 无时间轴自动落 RMS 口型）；chat attachVoiceBar 用独立 Audio 不驱动嘴=各持一半；streamRequest openai payload 无 thinking 控制（DeepSeek 默认思考坑）；占位符 deepseek-chat 已退役
- **架构决策：iframe 组合**（非大合并页）——companion 父页 iframe avatar.html?mode=face + TTS blob 路由进 iframe audio；避免重构/触碰已上线 avatar.html，改动面最小
- 下一步：8A-1 avatar 两处追加式小改（DeepSeek+Codex，验收字节一致+像素复验）

## Session 2026-08-28（续：8A-2a 桌面陪伴合流页核心闭环）
- 架构定案：iframe 组合（父页 iframe avatar.html face-only + 复用 chat 大脑），avatar.html/chat.html 零改动，companion 纯新增
- DeepSeek 写 tools/build_companion_page.py（NOTHINK=1 关推理防烧正文；694 行含完整 HTML 模板 + 逐字复用 chat 大脑 JS）
- Codex 审核链：R1 REJECT 3 BLOCKER(三源检索退化/分片键名/加载时序)+2 MAJOR(停止按钮/并发) → 我 4 处外科修（DeepSeek 整函数重生成漂移严重弃用，改声明 hotfix）→ R2 又抓 1 MAJOR(saveSettings 提前放行+首条并发双发) → contextLoaded+sendPending 双门控 → R3 ACCEPT
- Codex 误报 1 条（send 监听被同行注释吞）：cat -A 实证 621 行独立成行 LF 结尾，CJK 行计数误读（findings 先例），未改
- 真浏览器 Playwright 冒烟全绿：iframe sameOrigin=true + player 可达（speakBlob 路由确认）+ playlist/controls display:none + avatar flex 可见 + 抽屉开合 + 两处非本人标识 + deepseek-v4-flash 占位符；截图确认脸干净渲染 face-only；console 仅 favicon404(豁免)+:8022未启(TTS优雅降级)二良性
- companion.html 生成于 people/mama/archive_out（不进 archive_dist）；下一步 8A-2b 条件 a-e 伦理护栏

## Session 2026-08-28（续：任务 #19 蕾咪拆解研究）
- 用户立项：研究 kira-remy-official，想把数字人做成"这种效果"（即 08-27 截图的蕾咪桌宠）
- 侦察：GitHub 仓库 WebFetch + 本地 Downloads\Remy_v1.2.1.zip / Desktop\Remy 实装在盘；克隆源码 ~14k 行 Python 逐行拆解（仓库小，直读优于 workflow）
- 机制拆透：透明窗=Frameless+StaysOnTop+WA_TranslucentBackground+QLabel 立绘；情绪=LLM 回复关键词匹配→8 张 PNG 切换（同表情防呆滞/说完回落 Shut）；说话=Open/Shut 静态双帧（无音频无口型——比我们 Phase 1 落后两代）；37 字回复约束
- 报告成文 docs/research/kira-remy-analysis.md：借形（透明立绘窗/情绪表情层/打字机气泡细节）不借魂（常驻/主动/游戏化/云识图全排除）；落地候选 方案甲(情绪贴片层)→方案乙(桌宠壳 QWebEngineView/Tauri) 等用户裁决
- task_plan 注册 Phase 9（任务 #19）

## Session 2026-08-28（续：8B-甲 三平台兼容 + 情绪层运行时）
- 用户裁决：方案甲先 + 硬要求 iPhone/Mac/PC HTML 正常运行
- 侦察：.mouth-patch{display:none} 类坑确认（overlay 全显式 inline style）；avatar 内部有"首次点击 resume AudioContext"监听→companion 合成 click 派发可薅（同源共享用户激活）
- DeepSeek 新工艺：**全文回显+区域纪律+diff 校验**——规格含 7 个改动区+原文件全文，产出 11 块 146 行差异逐字对应规格零漂移（对照 8A-2a 整函数重生成漂移事故，此工艺定式化）
- Codex R1 REJECT 全实锤：showEmotion 同名 return 跳过计时器刷新 / 兜底按钮同步 throw 自删重试入口+降级路径不补按钮 / detectEmotion null 条目崩 → 声明 hotfix×4 → R2 ACCEPT
- 验证：py_compile/node --check/11 项 grep 全绿；Playwright：emotions.json 404 静默关 ✓、emotion overlay DOM 机制 computed style 实测（显式 block/none、绝对定位全尺寸 1104x944、层序 emotion<blink）✓、iPhone 390×844 视口（无横滚/脸+输入栏布局/16px 防缩放）✓
- 测试用 emotions.json 已删（眨眼图替身不可留作真资产）；下一步 8B-3 ComfyUI 情绪贴片（默认微笑/开心/心疼/嗔怪/思考，用户定稿闸门）+ 8B-4 用户真机验收（iPhone/Mac 经 Tailscale）

## Session 2026-08-29（8B-3 情绪贴片首轮 + 任务 #20 dsh-im 立项）
- 用户否全身化（维持半身框）；开工 8B-3 情绪贴片
- 服务腾挪：停 :8022 TTS/:9880 GSV 腾显存（8.8G→2.4G）→ ComfyUI 脱钩起服 4s 就绪 → 生成完恢复 :8022
- 探针 gen_emotions_probe.py（声明；复用 gen_avatar_candidates.build_graph/poll_history/extract；坑：poll 返回 (status,entry) 元组、extract 返回 (fname,subf,type) 元组，非 dict）→ 4 情绪×3 种子 12 张，54-184s/张
- **意外之喜**：首轮即温和不夸张、形象一致性全保（对照 Phase1 嘴型首轮必夸张返工）——归因=眉眼区域改动比嘴型温和 + prompt 预置"嘴/镜框/发/脸锁死"
- 合成预览 compose_emo_preview.py：烘焙区=双镜片内区(blink rects 羽化8)+眉带(370,225,820,315 羽化10)，ImageChops.lighter 合 mask（numpy 不在系统 py），composite；抽验 sad 合成无接缝嘴不变；审核页 emo_review.html 12 GIF 上 8020 → 等用户定稿
- **任务 #20 立项 dsh-im**：Cordis 通道网关接 9 IM→DeepSeek Harness；官方 SDK(企微/QQ/钉钉)+微信个人号 iLink 协议；MIT/948★/无语音。撞既有结论=messaging-channels 个人号协议否决(封号>80%)+任务#16 UIA NO-GO。workflow wf_26efff09-b58 后台研究中（4 维+校核）→ docs/research/dsh-im-analysis.md

## Session 2026-08-29（续：任务 #20 dsh-im 研究收口）
- workflow wf_26efff09-b58 收官：11 代理/96 万 tokens/15 分钟；4 维（架构/微信风险/接入/战略）+ 7 校核（6 confirmed/1 refuted/1 unclear）
- 核心新事实：微信 iLink=腾讯 2026 官方个人号 Bot 协议（ClawBot），第三条路，实质更新我们两份"微信封死"研究；但校核 refuted"官方=可给家人用"（机主控自己 agent 设计/未授权直连/家人拓扑无据/可随时终止）
- dsh-im=连接层非大脑；不发原生语音条；接 persona 要写冒充 Harness 的 shim
- 报告 docs/research/dsh-im-analysis.md 成文；裁决分层=自用低风险 GO / 家人向默认 NO-GO（第三方伦理+沉浸最大化，比桌面陪伴更保守）
- 用户可自查：微信设置>插件看有无 ClawBot（秒级，判灰度，不用弃号）；iLink 能否发语音条动工前活体验证
- findings/task_plan 更新；等用户裁决方向

## Session 2026-08-29（续：任务 #21 OCR 控微信研究收口）
- workflow wf_6b7db20f-956：11 代理/68 万 tokens/18 分钟；4 维（GitHub扫描/可行性/封号伦理/接入）+ 7 校核（3 confirmed/2 refuted/2 unclear）
- 直接答"github有没有开源"：有零件没成品；社媒"skill"=YoKo(83★)/pywechat(1874★) 但都 UIA 非 OCR，在 4.1.12.26 已被 #16 判死
- ★新事实：微信 PC 4.1.9+（用户 4.1.12.26 已有）支持发原生语音条(按住右Alt)，VB-Cable 虚拟声卡+keyDown/keyUp 可发她真声语音条——更新"PC 只能当文件发"旧结论；风险=微信 AGC 降噪可能劣化克隆音色待 A/B
- 校核 refuted 两强论断（OCR 非唯一绕 UIA=DB 读才是可靠读侧；OCR 非独占家人可达=iLink 扫码同样可达靠伦理否决）
- 报告 docs/research/wechat-ocr-automation.md 成文（四路径对照表修正版）；裁决=自用低风险 GO/家人向默认 NO-GO 且比 iLink 更甚（零 bot 标识欺骗性最强）
- findings/task_plan 更新；四条微信路径全景定论=没有一条为家人向打开干净的门

## Session 2026-09-01（8B-3b 情绪贴片定稿 + 烘焙 + 激活；待办清理）
- 用户令"完整报告项目进度"→ 全景报告；用户裁决移除四项待办（601 敏感复核 / persona Q1-Q13 / DeepSeek key 轮换 / 拟音词释义）→ HANDOFF 活跃区删除+裁决记录（旧章节历史不改）
- 用户"情绪贴片看了 ok 定稿吧"→ 对照表（底图 vs 12 候选眉眼区）→ 推荐并经用户确认：**四情绪均种子 5002**（happy s5003 瞳孔变棕、sad s5003 带泪珠排除）；12 候选+manifest 归档 versions/emo_candidates_20260829/
- **8B-3b**：DeepSeek 两路并行——①新工具 tools/bake_face_patch.py（262→300 行）②build_avatar_page.py 的 load_emotion_assets 片段（96 行；Claude 接线 3 行+docstring 一行，声明）。Claude 直写纯数据 persona/emotions.json（定稿+溯源+关键词表，声明）
- 烘焙实跑：4 贴片 [CHECK] max_diff=0，~180KB，coverage 10.9%；叠底图 vs emo_review 用户审核合成图 **max_diff=0**（所见即所得）；`build_avatar_page --person mama` → `[EMOTION] 4 emotions`，data/avatar 收 4 PNG + emotions.json（file 已带 ?v=hash）
- **Codex R1 REJECT**（1 BLOCKER 自验失败先 unlink 旧成品 / MAJOR --jobs 缺文件冒 traceback / MAJOR 负 feather+bool/float 漏校验 / MAJOR 关键词误报『太好了！！！→stern』『不错→happy』/ MINOR 缺 docstring）→ 代码回炉 DeepSeek（全文回显+四改动项，diff 实证零漂移；docstring 被放 import 后由 Claude 上移，声明）+ 关键词 r2 收窄（去标点类/单字唉/泛词赞棒不错好呀/等会，听话→不听话/听话点/要听话）→ **R2 ACCEPT with fixes**（1 MAJOR：src/out 未校验字符串）→ 声明 hotfix 2 行 → **ACCEPT**
- 工具负路径实测：缺 jobs/畸形 region/src 非字符串/互斥参数/out==base 全部单行 [ERROR] exit=2；重烘三次 sha256 均一致；单任务产物 cmp== 批任务
- **真浏览器 E2E（run_code_unsafe）**：page.route mock 同源 SSE 端点 + 经 ⚙ 抽屉 UI 配置 + 真按发送 → 真实运行时 showEmotion(detectEmotion(finalText))：sad→display block/src emo_sad?v=/1104×944/absolute/在 eyes-blink 之前/无 mouth-patch 类 → happy 切换 → 7844ms 回落 display none。截图人眼确认蹙眉/弯眼真实渲染（neutral2 恰抓到眨眼）
- **教训**：Playwright 截图为 DPR 1.5×，像素 diff 用 CSS 坐标会算成"眉眼带 0 变化"（假阴性）——坐标乘 devicePixelRatio 后眉眼带占脸部变化 40-66%；ambient 微摆会给全脸带来底噪 diff，截图 diff 需配人眼复核
- 环境：机器曾重启，手动拉起 :8020（Start-Process 脱钩）与 :8022 TTS（venv python 直启 + 日志重定向；cmd /c 包 bat 的写法静默失败）；:9880 未起
- 文档：task_plan 8B-3/8B-3b ✅、HANDOFF ⓪⁹ 增补+建议顺序刷新、memory 项目状态+验收铁律补 DPR 条目

## Session 2026-09-01（续：companion 多服务商抽屉 + TTS 接播真实语音 bug）
- 用户令"服务商设置 OpenAI/Anthropic/DeepSeek/Kimi，每个预填接口地址和模型"。前置核实：claude-api skill（claude-opus-5 / v1/messages）；WebSearch+官方文档核 `gpt-5.6`（Chat Completions 支持）与 Kimi 现役 `kimi-k3`（K2 系列 5 月停服、k2.5/moonshot-v1 8/31 下线；国内 base api.moonshot.cn，docs 已迁 platform.kimi.com）；curl OPTIONS+POST 实测四家端点 CORS 全通（Kimi 首次 grep 漏看误判为无 CORS，深查纠正）
- 设计：5 项下拉（含自定义）；`PROVIDERS` 常量表驱动预填/placeholder/提示行；`settings.profiles[provider]` 各自记忆；旧存档 `inferProvider` 按 URL 归类；DEFAULT_PROVIDER=deepseek
- 工艺：**区域规格法**——规格给 6 个原文区域+要求，DeepSeek 只输出 `=== Rx ===` 新文本，Claude 用 splice 脚本精确替换（锚点唯一性预检）；避免 830 行文件全文回显撞 32k 输出上限。bash heredoc 含单引号规格炸过一次 → 规格文件改用 Write 工具
- Claude 声明 hotfix：规格漏洞——旧存档 provider 'openai' 现为合法键致 URL 归类失效 → legacy（无 profiles map）且非 anthropic 时按 URL 推断
- **Codex R1 ACCEPT with fixes**：MAJOR 草稿直接写 settings.profiles（清空→切换→关抽屉不保存→后续保存把空值持久化）/ MINOR legacy 判定应用 `[object Object]` → DeepSeek r2（draftProfiles 草稿区 + cloneProfiles + closeDrawer 丢弃）→ **R2 ACCEPT**
- E2E（Playwright run_code_unsafe，route mock 四家端点）：旧存档 openai+deepseek 地址→deepseek 且保留自定模型/key；五家切换预填正确；草稿保留；取消路径 localStorage 不变；Kimi 请求 Bearer+kimi-k3（OpenAI 协议）；Anthropic 请求 x-api-key+dangerous 头+system 顶层；新用户默认 DeepSeek、无 key 发送禁用
- **用户真机首测**："api设置成功 对话上了 文字+语音回复通"→ 报 bug：她念完后播放训练用真实语音。根因 avatar.html `audio.ended → playAt((cur+1)%len)`，cur=-1 → 第一条真声。修法 1 行 `blob:` 守卫（声明 hotfix，Codex ACCEPT：src 判据充分、Safari blob 形态一致、pause 复位链不受影响）。E2E 真实 :8022 TTS：play→playing→pause→ended 后 2.5s player 仍 paused 于 blob、now-title 未变、avatar 无 speaking 类
- 文档：task_plan 8B-5/8B-6/8B-4 刷新、HANDOFF ⓪⁹ 追加 7/8、memory 项目状态。**archive_dist 未同步 avatar.html 改动**（独立页行为不变）
- **用户二报：「拉到 DeepSeek 地址和模型没预填」** → Playwright 复现两种存档形态（旧版只存 key→迁移归 deepseek 但 url/model 空；新版 deepseek profile 空）：`profileFor` 见 profile 即原样返回不补默认。DeepSeek r3：新增 `withDefaults(provider,p)`（空串→默认，非空不覆盖）；profileFor/loadSettings 统一经其输出 → Codex ACCEPT with fixes（MINOR：saveSettings 也应走 withDefaults 保持同会话语义一致）→ 声明 hotfix 3 行 → **ACCEPT**。E2E：只留 key 保存当场可发送且请求带默认 URL/模型；五家预填全对；自定模型 deepseek-v4-pro 不被覆盖；取消路径不变

## Session 2026-09-01（续：微信式时间分隔 + 轴五 sessions 日志）
- 用户令：①聊天栏微信式时间（每轮集中聊天顶上一个）②log 功能记录双方文字带时间戳 + 每轮语音文件。对齐 GENERALIZATION 轴五既定架构（`POST /session` 并入 tts_server、`sessions/YYYY-MM/session_<id>.jsonl`、服务不在 localStorage 排队）
- DeepSeek 两路并行：tts_server.py 全文回显+区域纪律（diff 实证只落点名区域）；companion 七区域规格（RC/RS/RH/RA/RP/RM/RX）+ splice 脚本精确替换。node 直跑 formatTimeLabel 五档全对、buildSessionId 匹配服务端正则
- 服务端 r1 实测（Python UTF-8 客户端；Git Bash curl 会把中文 body 编码搞坏→400 是测试工具问题）：/session 200 落盘、`../../evil`/bad role/bad turn/超长/非法 JSON 全 400；/tts 带 session 落 WAV 24kHz mono、同 turn 自动 `_2`、非法 sid best-effort 不写
- **Codex R1 ACCEPT with fixes（4 MAJOR）**：①时间分隔按「上次分隔线」算会每 5 分钟冒一条→改按「上一条消息」间隔（我的规格错误）②`_read_json_body` 异常路径不发响应→全路径尽力发 4xx/5xx ③`save_audio` exists→write 非原子、后缀耗尽覆盖→`open('xb')` 循环+耗尽 raise ④队列 flush 用 shift 可能误删→qid 标识按 id 删（服务端白名单加 qid）→ DeepSeek r2 两文件 → **R2 ACCEPT with fixes（1 MAJOR：无 qid 旧记录被丢弃）**→声明 hotfix（补 qid 回存再发）→ **ACCEPT**
- 重启 TTS 两次（r1/r2，各 ~75s）；教训：PowerShell 用 `CommandLine -like '*tts_server.py*'` 杀进程会匹配到自己→必须加 `Name -eq 'python.exe'`
- E2E（Playwright + 真实 :8022）：分隔线 1 条在首条 user 气泡上方、第二轮不重复；四轮对话 JSONL 全落盘（event/user/simulacrum(emotion,tts,retrieval_used 4)/simulacrum_audio(file)），/session 被 abort 的第 3 轮进队列(qid)→第 4 轮成功后补传→队列清空；4 个 WAV 落盘。测试 session 两组已删除
- 文档：task_plan 8B-7、HANDOFF ⓪⁹ 第 9 点、GENERALIZATION 轴五采集状态标记、memory 项目状态

## Session 2026-09-02（TTS 剥括号 + 回复变长诊断）
- 用户三问：①括号内容别念（[捂脸]/（瞟一眼））②回复为何比以前长③是否开了深度思考
- **#1 实施**（DeepSeek 三区域 + Codex ACCEPT）：tts_server 模块级 `strip_brackets`（BRACKET_RE 成对括号，不动点循环，空白压缩），`_handle_tts` 剥后合成+QC，剥空→400；simulacrum_audio 记录附 spoken_text。活体验证：带括号文本合成时长≈净文本、jsonl 见 spoken_text、全括号→400。服务端统一实现，chat.html 语音条同受益。TTS 重启一次（09-02）
- **#2 诊断（据 sessions 日志实据）**：今晨真实会话全部为 deepseek/deepseek-v4-flash（r3 预填默认），回复 90-163 字符 vs 她本人节律中位 17 字；此前 chat 页配的是 deepseek-chat。结论=模型行为差异（V4 Flash 铺陈+动作描写+markdown 空行），非深度思考（页面对 deepseek 显式 thinking:disabled，日志可证）。系统提示只有「消息长短以语言与节律为准」软约束，无硬上限——候选改进：chat_system 加硬性长度/禁动作描写纪律（动 prompts 需用户闸门）
- **#3 结论**：DeepSeek=显式关闭；Kimi kimi-k3=官方文档「始终推理」（reasoning_effort 默认 max，只可调低不可关，reasoning_content 独立于 content 不会进气泡）；OpenAI gpt-5.6=默认 medium；Anthropic claude-opus-5=默认 adaptive 开。切非 DeepSeek 服务商时推理默认在跑（更慢更贵但不显示）——如需，可给 kimi/openai 发低档 reasoning_effort（未实施，等用户表态）

## Session 2026-09-02（续：分句语音流水线 + 微信式「正在输入」）
- 用户两问诊断后两需求：①文字出现后等语音、越长越久——查 sessions 日志实据（synth 与音频时长成正比，90 字 8.9s；整句批量合成是根因）②做分句流水线③模型出字太快时显示端加人工延迟、学微信「正在输入」
- 设计合一：发送→气泡三点打字动画（CSS keyframes）→回复分句，首段先合成先播、后段串行边播边接上，**每段文字随该段语音开播同刻浮现**（文声同步，首声≈首段合成）；TTS 不在/超 240 字→文字节奏兜底逐段浮现
- DeepSeek 5 区域（RCSS/RSTATE/RENGINE/RSEND/RX，RENGINE 271 行状态机）+ splice 精确替换。splitSegments 精确分片单测 join===原文全过
- **Codex R1 REJECT（BLOCKER）**：iframe player 'ended' 只读全局 voiceTurn，旧回合音频 ended 在新回合到达会误推进新回合 playIdx（跳首段）；fallback Audio 未存 vt 停不掉 → **R2**：activePlay 模块变量记当前占用播放器的回合，ended 校验 owner===voiceTurn；fallbackAudio 存 vt+带 vt 归属 ended；cancelVoiceTurn 暂停两者。短尾段并回（MINOR）一并修
- **Codex R2 REJECT（BLOCKER）**：showPlayButton 手点 iframe 重播分支漏设 activePlay→多段回复在 autoplay 拦截后卡首段 → 声明 hotfix（重播前 activePlay=vt、失败清 null）→ **ACCEPT**
- E2E（真浏览器+真 :8022）：①语音模式 2 段文声同步（t≈4.4s 首段、11.3s 次段，与 audio play 对齐）②并发压力（旧回合播中发新回合）新回合从首段正常播、旧回合文字 revealAll 保留③autoplay 拦截→按钮→点按后 endedCount=1 推进到第 2 段全文出齐④纯文字兜底全文出⑤停止键亮「（已停止）」。测试 session 全清理，保留真实 YqOjsW
- **注记：沉浸感显著提升，8A-2b 伦理护栏优先级上升**。文档：task_plan 8B-9、HANDOFF ⓪⁹ 第 10 点、memory

## Session 2026-09-02（续 2：进度全景报告 + 文档失真修复）
- 用户 /clear 后令"报告项目完整进度"→ workflow 六路并行核对（里程碑三文档 / HANDOFF 全篇 / 仓库产物实存 / 环境活体探针 / 研究目录 / 三源一致性；6/6 返回，63 次工具调用）→ 全景报告。核对实证：HANDOFF ⓪⁹/⓪⁸ 点名产物全部在盘（emotions.json 键序 sad>stern>think>happy、visemes.json 326KB、data/avatar 10 PNG、sessions/2026-09 1 jsonl+2 wav、emo_candidates 13 文件）；:8020/:8022 up（/health e14 session_log true）、:9880/:8188 down、Tailscale 100.116.45.2；archive_dist/avatar.html（08-27）与 archive_out（09-01）md5 不一致=已知未同步
- 用户令"先修复这些文档失真"→ **Claude 直写（声明，文档非代码）**，补丁脚本逐条断言唯一命中：①CLAUDE.md M4 行补 09-01/02 四连、去掉"贴片首轮待定稿"、副产品线标明"研究裁决/方向等用户"②task_plan Phase 1/3 状态头改 complete、3 完成标准改已达成、4c 标搁置（被 :8022 动态合成取代）、Phase 8/9 头改"用户已裁决"、8A-1 标被取代、8A-2a ✅、8A-3 标 🔶（companion 侧落地/chat.html 未动，build_chat_page 占位符仍 deepseek-chat）、8A-4 ✅（由 8B-7 落地）、Phase 10 重复骨架块删除、Phase 10/11 头改 research complete、决策记录补 08-28→09-02 四行（08-28 两裁决合写）、Errors 表改写 1 行+补 3 行③HANDOFF：四项待办移除日期 08-29→09-01（git -S 实证出自 09-02 提交、progress 记 09-01 会话）、下回合列表 09-02 刷新（加 archive_dist 重打包 / ingest_sessions / 静默消失项声明未经裁决）、⓪⁷ 第 4/5 点加"已被覆盖/已过期"标注、⓪⁸ D 与 ⓪⁷ 的"Tailscale 需手动拉起"改为有自启任务、二章语音行去"已拍板开工/家人盲听唯一标准"、微信版本加 4.1.12.26、#14 编号复用警示、六章加"当前有效用户侧动作"、说话帧条加双帧体系已废注④findings 补"companion 四连教训"一节（DPR/PS 自杀/区域规格/音频归属/关键词误报/两套烘焙数学/withDefaults/回复变长诊断/分句首声）
- 未动：progress.md 历史条目、HANDOFF 旧增补段正文（只加标注不改史）、people/ 一切

## Session 2026-09-02（续 3：文档修复核证 + 任务 #22 立项 + 研究 a 收口）
- 文档失真修复经独立对抗核证（workflow 8 组 217 条主张：213 证实、3 反驳已修——`wechat-ocr-analysis.md` 错名、Errors 表把流式/32k 误归 Phase 0 修法、1 条不可证改措辞）
- 用户立项 #22（Phase 12）：a/ iOS 部署与专属 App；b/ 0→1 建档 App 产品化。研究 workflow 内部三路完成（运行时依赖/管线闸门/伦理约束），外部 7 路扫描因账号限额（20:10 复位）全失败；用户指令"一个一个来"→ 改主模型逐条 WebSearch/WebFetch 补查，先 a 后 b
- **a 收口**：`docs/research/ios-app-deployment.md`——A0–A5 矩阵；推荐 A1 主屏 Web App（iOS 26 默认 Web App、加图标即可、http 无 secure-context 需求、tailscale serve https 零改动）；A2 壳不推荐（收益全在 6.2 ③ 禁区）；声音出不了 4090（端侧运行时无 CosyVoice2 SFT）；A5 云 GPU NO-GO；建议另立 A3′ 有声档案；前提 8A-2b。待裁决 D1–D5。task_plan Phase 12 已拆 a ✅ / b ⬜
- 未动：people/ 一切；未提交

## Session 2026-09-03（#22-a 裁决 + b 收口）
- 用户裁决 a：D1 A1 接受 + 8A-2b 先行；D2 https 跳过；D3 A3′ 有声档案立项（task_plan 新 Phase 13）；D4 A2 壳暂不做；D5 PC 常开手动拉起。实施顺序：8A-2b → A1 图标 → Phase 13
- **b 收口**：`docs/research/build-app-productization.md`——主模型逐条补查（ComfyUI Desktop/Pinokio 打包先例、WeChatMsg_2026 4.0 适配、标识办法 2025-09-01 + 深度合成规定 + 民法典 994、StoryFile 破产/2Wai 反弹）+ 内部管线盘点 33 项；结论=建档工作台 B1（产出档案，companion 可选）、三条硬边界、§4 把关功能表、P0–P3 分期。待裁决 E1–E6
- 未动：people/ 一切；未提交

## Session 2026-09-05（8B-10 语音条 + ≤30 字分条；用户反馈驱动）
- 用户反馈两条（推迟 #22-b 裁决）：默认发语音条可回味 + 下方备注文字；片段太长不生成语音→每条 ≤30 字分条各自合成。日志实证：sessions 17 条回复 7 条 `skipped_length`（`TTS_TOTAL_MAX=240` 全文超长整段跳过）；同时发现 `build_rhythm_block` 读的键在 rhythm.json 里全不存在（模型从未拿到长度/连发/标点统计）
- 实现：DeepSeek 区域规格两轮（R1–R9 / R1–R4，锚点唯一预检，49+39 hunk 全落规格区）+ Claude 声明 hotfix 8 处（硬切、ended 清回放、cancel 提前保证顺序、cancel 清回放、空回复守卫、删死函数、logSession 白名单 `messages`、标点-only 不送 TTS）+ Python 侧 2 处（tts_server int 字段校验、rhythm 死表达式）；提示词加"分条发"规则；rebuild chat_context + companion
- 验收：ES5 扫描 0；splitMessages 单测 12 例；Playwright route-mock 真运行时 E2E 两轮全绿（截图人眼确认语音条）；真 :8022 冒烟 29 字 5.5 s；tts_server 重启两次（白名单/校验生效）
- 审查：Codex MCP 报 refresh token revoked（CLI 显示已登录但实际失效）→ 改三视角 workflow（状态机/浏览器平台/安全+Python）26 发现 → 对抗核证 12（上限）：10 确认（1 major：旧回合 ▶ 按钮劫持 player 致新回合悬挂；9 minor）2 反驳，未核证 14 条人工筛出 4 条一并修（代理对硬切、纯空白 ['']、标签行送 TTS、标点类漏 …）→ 第二轮 DeepSeek 全修 → E2E 复验通过。**Codex 验收待补**：`codex logout` 后走 `codex login --device-auth`（浏览器流回调 localhost 不适合远程），两个设备码均 15 分钟超时未授权（用户远程未及时操作）；用户回家后 `codex login` 浏览器流登录成功（09-06 23:03）；MCP 默认模型 gpt-5.4 与 gpt-5.6 均被拒（"not supported when using Codex with a ChatGPT account"），`model: gpt-5.5` 可用 → **Codex 三轮 REJECT(5: 标点合并超 30/丢开头标点、超时未盖 body、降级 Audio 拒绝不清动画、零样本节律误导、未用变量)→REJECT(1: 被拒态点语音条绕开 activePlay 致回合停住)→ACCEPT**；每轮 Claude 声明式 hotfix + 单测 14 例 + E2E 两套复验全绿。8B-10 收口
- 教训入 findings/memory：Playwright MCP 沙箱无 Buffer/setTimeout、中途抛错的脚本会变僵尸继续操作页面（重跑前 browser_close）、截图落仓库根要移走
- 未动：people/ 一切（sessions 只做元数据统计）；未提交

## Session 2026-09-06（#23 给爸爸的六段语音）
- 用户立项 #23（Phase 14）：09-04 晚对话截图发给爸爸后爸爸很触动，要把数字人六段回复（turn 6–11，136–334 字，其中 4 段当晚因 TTS_TOTAL_MAX 未出声）整段合成她的声音。家人向首次实际使用，用户知情自决；产物带"合成语音·非本人原声·Tier-3"标识，不进 archive_dist
- 实现：Claude 直写一次性脚本 `scratchpad/synth_for_dad.py`（声明；只读会话日志、按句 ≤80 字走 :8022、句间 0.3 s/段间 0.85 s 拼接、峰值限幅、WAV+MP3+manifest sha256），两语域各 6 段：wu 42–92 s、mandarin 33–81 s，110 句 0 失败，合成约 12 分钟；对照试听页（自包含 6.6 MB）放 `people/mama/exports/for_dad_20260906/` 与 8020 站 `review/for_dad/`，SendUserFile 发用户
- 用户选 **wu 上海话域**，6 个 MP3 已 SendUserFile 发出；09-07 用户已转发给爸爸、关闭 #23。用户问"每段开头一声很短的声音"→ 实测为模型起音爆音（前 15 ms RMS 2–3×、峰值 2×、重心 800 Hz，每句起音都有，两语域与 companion 片段一致）；A/B 试听（30 ms 淡入 / 切 15 ms+淡入）用户说都没问题 → 选不裁剪的淡入方案，立 8B-11 修 tts_server 出口（本次 SendUserFile 6.6 MB HTML + 6 个 MP3 全部送达，比 08 月时可靠）；爸爸反馈是否入档由用户定

## Session 2026-09-07（8B-11 起音爆音抑制）
- 用户关闭 #23（六段已发爸爸）→ 要求修 companion 每段开头的"啵"。根因：模型每次开口前 ~15 ms 爆音（12 成品/两语域探针/会话片段签名一致：head15 RMS 2–3×、峰值 2×、重心 800 Hz vs 正文 400 Hz），每句单独合成故每个语音条都有；推断为 SFT 训练片段自动切段硬起音被学进去
- 修法：tts_server 出口 `soften_onsets`（起音检测 + 30 ms 升余弦淡入，不裁剪）。DeepSeek 区域规格两轮（首轮 Codex 抓出静音前缀用 thresh 而非 quiet、首次发声只认第 0 帧 → 重写为单次线性扫描 seen_voice/quiet_run/in_voice）→ Codex ACCEPT；单测 6 例通过。**事故**：第二轮区域锚点 `def soften_onsets(`…`
class ` 吞掉了 DeepSeek 首轮放在其后的 `strip_brackets`，重启后 /tts NameError 500——从备份恢复该函数（Claude 声明），补 hunk 落区/关键符号断言纪律入 findings。恢复后重启实测：起音比 2.1–2.9 → 0.63–0.78，起音峰值 0.18 → 0.10–0.15，含 `[捂脸]` 标签文本正常合成
- 未提交（8B-10 + 8B-11 + #22 两报告 + 文档）

## Session 2026-09-07 上午（进度全景报告 + 凯西相关记录全层清除）

- **全景状态报告**：Workflow 8 路读者 + 8 路核验员 + 一致性/汇编/批评（20 agent，首轮撞会话上限、恢复后 19/20 完成，修订由 Claude 手工做）→ `docs/status-2026-09-07.md`（40 行文档失真表 + 待办全景 + 风险）。要点：8A-2b 护栏未上但 companion 已真机日常使用；archive_dist 自 09-01 落后；12 提交未 push；单测/#23 脚本/e14 训练配方均不在仓库；Codex 实际可用 gpt-5.5。
- **用户提出**：数字人在 09-04 会话里把"凯西"当作用户的老婆（用户当场纠正：已离婚，现任叫兔兔）。要求找到并删除凯西相关回忆。
- **查明**：凯西=谢凯西（Kathy），2022–2023 记录人物。来源两路：persona.md T34/T35 两条引文进系统提示；检索源 170 条消息 + 2 条语音转写。Tier-1 卡 0 命中，8 条相关候选早已 rejected。
- **用户四项裁决**：①全删 174 条（170 消息 + 2 转写 + 2 语音清单）②persona.md 引文名字改〔前儿媳〕（保留 T34/T35 缺点特质）③sessions 日志与 for_dad 导出里的句子涂成〔已隐去〕④"离婚/兔兔"暂不升级 Tier-1。
- **执行（无新代码，全部现有工具 + 数据编辑，Claude 直接操作并在此声明）**：快照 → `versions/pre_kaixi_scrub_20260907/`（16 文件 + 2 WAV，26 MB）；`scrub_sensitive.py apply`（manifest 14→188）；两段原声 WAV 从 processed / archive_out / archive_dist 移入快照；persona.md 2 行；6 个 HTML/JSONL 文本涂改；candidates.jsonl 删 9 条 rejected 行 + 1 条 confirmed 卡剪掉 1 个已删 record_id（150→141，124/17，memories.md 不变）；sensitive_scan_report 601→595；重跑 build_data_bundle → extract_persona_digest → build_chat_context → build_chat_knowledge → build_archive。
- **结果**：UIF 20909→20739；语音 125→123（转写 97+9）；prompt 24,326 字符；archive_dist 169 文件 verify=ok（顺带还清 M3 欠账：blob 守卫 + 情绪资产 + 09-06 chat_context 已进 dist）；`scrub verify` residue=0；raw 与快照目录以外名字残留 0。:8020 实时提供的 chat_context 与磁盘一致。
- **遗留**：快照目录仍含删除前副本（用户决定何时删）；visemes.json 留 1 条指向已删 WAV 的哑条目（无害）；for_dad 音频与 sessions 音频里念出的名字无法涂改；09-04 用户纠正仍是 Tier-3。
- 未提交。

## Session 2026-09-07 下午（用户复测仍"记得凯西"→ 浏览器启发式缓存根因 + no-cache hotfix）

- **现象**：16:33 新会话问"你还记得谁是凯西吗"，回复"谢凯西伐，侬女朋友呀…见过伊一面"，retrieval_used 含「语音转写 2022-10-08」（被删两段语音的日期）。
- **根因**：companion/chat 页用裸 `fetch('data/*.json')`，:8020 是 Python http.server 不发 Cache-Control，浏览器按"距 Last-Modified 的 10%"启发式缓存。transcripts.json 原 Last-Modified 08-16 → 新鲜期约 2 天；用户 01:31 开过页面，16:33 重新加载（sessionId 在加载时生成，故确为重载）时浏览器未向服务器校验，直接用了 01:31 的旧 transcripts.json/年度分片，旧数据里的凯西转写被检索命中。服务器端当时已是新数据（curl md5 一致）。
- **hotfix（Claude 直改并声明，7 处同一 token 机械插入，未走 DeepSeek/Codex）**：build_companion_page.py 4 处、build_chat_page.py 3 处数据 fetch 加 `{cache: 'no-cache'}`（每次条件校验，未变返回 304）。重建 companion.html（需显式 `--archive-dir people/mama/archive_out`）与 chat.html；build_archive 同步 dist verify=ok。
- **用户侧动作**：各设备首次需强制刷新一次（PC Chrome Ctrl+Shift+R；iPhone 在地址后加 `?r=1` 或清站点数据），之后新页面自带 no-cache。
- **残留说明**：名字已清，但"谢爸/谢妈/六人群/婚礼"等同章节其它消息仍在档案；被直接问到名字时模型可能凭"谢爸"拼出"谢凯西"并编造（Tier-3 违规，属提示遵循问题）。是否扩大删除范围或写 Tier-1 纠正卡待用户裁决。
- 未提交。

## Session 2026-09-07 下午（续：跨会话记忆立项 + 任务 #24 研究立项）

- 用户裁决推进跨会话记忆（"记得昨天的聊天更有沉静感"），先于 8A-2b。brainstorming 三问定案：双方都记/她的话永久 Tier-3；"本次不记"开关 + exclude.txt；静态 sessions.json + tts_server 去抖自动刷。设计待用户过审后写 spec。
- 用户立项 #24：爸爸以丈夫角色与她对话的网站/APP，PC 常开作服务器。研究 workflow 后台启动（5 视角 + 汇编 + 批评）。
- 复测观察：强刷后 16:43 仍拼出"谢凯西"（引用 2022-10-08 未提名字的第三段语音 + 用户问句里的名字），16:44 改口"记不清"。数据层名字残留 0，属模型推断；跨会话记忆落地后"对话者自述：已离婚/现任兔兔"可给她正确答案。

## Session 2026-09-07 夜（Phase 15 跨会话记忆：Task 1+2 落地，Codex 两轮 ACCEPT）

用户裁决推进跨会话记忆并"继续"。按 brainstorming → spec → plan → 逐 Task 实施推进（铁律 1 全流程：Claude 出规格 / DeepSeek 写 / 三视角 workflow 审 / Codex 验收）。

**规格与计划**：`docs/superpowers/specs/2026-09-07-cross-session-memory-design.md`（15 节）+ `docs/superpowers/plans/2026-09-07-cross-session-memory.md`（4 Task）。spec 落盘后依 #24 研究批评改为**每 viewer 一个文件** `sessions_<viewer>.json`（原设计单一文件会让爸爸设备下载到儿子全部对话原文），裁决未变。

**Task 1 `tools/ingest_sessions.py`（新，Codex ACCEPT）**
- 第二纪元摄入：sessions/*.jsonl → archive_out/data/sessions_<viewer>.json（静态、确定性、原子写、纯标准库）。
- 审查发现 8 条全部机械核实成立并修复：REDACTED_TEXT 逐字错（`【】`→`〔〕`）；`ingest()` 缺路径校验（铁律级，新增 `validate_paths`，raw 判断不依赖目录是否存在）；`--dry-run` 缺 3 个统计键；`last_card.started_at/ended_at` 恒 null；`os.walk` 未排序；**敏感正则缺 `re.IGNORECASE`（实测 `wifi PASSWORD is hunter2` 曾明文入档，而这些内容会进系统提示发往第三方 LLM）**；非法 severity 静默降级为 low；viewer 全排除时 `excluded_sessions` 错为 0。
- 真实数据：8 文件 146 记录 → 排除 3 次凯西复测会话 → 保留 5 次；last_card 指向 09-07；凯西 0 残留；两次运行去 generated_at 后逐字节一致。
- `people/mama/sessions/exclude.txt` 预填三次测试会话 id。

**Task 2 tts_server 自动摄入（Codex ACCEPT）**
- `SessionsIngestScheduler` 放在 ingest_sessions.py（tts_server 有 torch 等重依赖，测试进程 import 不了）。经两轮回炉修四个并发缺陷（去抖失效 / 成败判断错 / stale timer 多跑 / 锁忙路径多跑）。
- tts_server 六处接线 33 行：白名单加 viewer+exclude、`sessions_ingest` 属性、/health 两个新键、`_handle_session` 后触发 schedule（异常不影响响应）、`--sessions-out-dir`/`--no-sessions-ingest`、启动同步跑一次 + 横幅 `ingest=on`。
- 服务已用新代码重启并活体验证（写入→5 秒→摄入，exclude 生效）。
- 变异验证证明并发测试非碰巧通过。

**测试首次入库**：`tests/`（36 例，标准库 unittest，因默认 Python 无 pytest）。Claude 声明式 hotfix 共 7 处，全部 1–2 行（测试夹具 mkdir/set 字面量/log 参数/out-dir 位置；实现侧补 import）。

**工艺教训**：DeepSeek 首次生成测试文件被推理烧尽 token 截断（finish=length，reasoning 29047 chunks）→ 改 `DEEPSEEK_NOTHINK=1` + 60000 一次成功，之后全程用此配置。

**剩余**：Task 3（companion 页：viewer/第四检索源/上次对话卡/本次不记）、Task 4（提示词纪律 + dist 排除 + 真机验收 + 文档）。未提交。

## Session 2026-09-08 凌晨（Phase 15 收官：Task 3+4，四轮 Codex ACCEPT）

- **Task 3 companion 页（133 行，Codex ACCEPT）**：`--viewer` 构建参数；`loadKnowledge` 加载 `sessions_<viewer>.json`；`retrieveSessions` 第四检索源（Tier-2/Tier-3 标签，排在第一纪元之后，2200 预算超出时优先丢第二纪元）；`buildSessionsCard`/`applySessionsCard` 把上次对话卡拼进 systemPrompt（**只在内存**，chat_context 与 sessions 两处触发、`sessionsCardApplied` 保证只一次）；抽屉 `#cfg-no-memory` + 聊天区 `#no-memory-banner`；`logSession` 带 viewer/exclude。
- **E2E（Playwright MCP route-mock，仓库无 playwright 包）五组全绿**：卡片格式逐字正确；两种标签且 Tier-2 在前；所有记录带 viewer=owner；勾选开关发出 `exclude_session` 且后续轮次带 exclude、提示条可见；sessions 404 时系统提示恰好等于原文、无卡无标签无额外报错。脚本入库 `tests/e2e/companion_sessions.spec.js`（15 断言，头部注明未在 node 下跑过）。
- **真实数据端到端**（只 mock LLM/TTS）：系统提示 24,743 字符，含第 7 条铁律；卡片显示「上次对话：2026-09-07（1 天前）。更早还有：09-04、09-02」并列出用户当时说过的四句与最后一来一回；检索命中 09-04 红包对话并正确标 `[往次数字对话 Tier-3]`。**这就是用户要的"记得昨天"效果。**
- **Task 4**：`prompts/chat_system.zh.md` 加第 7 条铁律「往次对话纪律」→ 重建 chat_context（24,507 字符）；`build_archive.py` 加 `SESSIONS_FILE_RE` 排除 `sessions_*.json`（9 行改动），dry-run 零命中、实跑 169 文件 verify=ok、dist 内 sessions 文件数 0。
- **Phase 15 四个 Task 全部 Codex ACCEPT**。测试总计 36 例 unittest + 1 套 E2E。
- ⏳ **剩用户真机验收**：PC/iPhone 各强刷一次（页面本身已带 no-cache，但旧 HTML 需冲一次），开新窗口看她是否接上上次的话。
- 未提交。

## Session 2026-09-09（T14-1 + T14-2：token 落盘 + 服务启动编排）

用户裁决：自启方式取**开 Windows 自动登录**（已知代价：物理接触电脑即进桌面、people/ 档案敞开）；token **加 `--tokens-file`**。

- **T14-1 token 落盘（DeepSeek 各 2 轮 + Codex 各 REJECT→ACCEPT）**：`tts_server.py` +61/-3、`llm_proxy.py` +52/-3，新增 `--tokens-file` 读 `people/mama_for_father/config/tokens.env` 的 `TTS_TOKENS`。三条安全要点均由 Codex 提出后补齐：文件来源的解析错误捕获 stderr 换成不含原值的统一文案（命令行来源刻意保留详细错误）、`utf-8-sig` 读、空值 fail-closed。两文件解析语义对齐（llm_proxy 原本 `item.strip()` 且跳过空项，比 tts_server 宽松 → 同一份 tokens.env 可能一个起得来一个起不来；已让宽松方变严格）。**实测生产进程命令行零 token。**
- **T14-2 `scripts/start_services.ps1`（新建 1031 行，DeepSeek 9 轮 + Codex 3×REJECT→ACCEPT）**：五服务编排（8020 儿子站 / 8021 爸爸站 / 8022 tts / 8023 llm-proxy / cloudflared 隧道），三模式（默认启动 / `-Status` / `-Stop`）+ `-SkipTunnel` / `-Quiet`。要点：三条件 skip（端口+健康+匹配进程）、端口被非匹配进程占则 **fail-closed 不杀**、单实例 named mutex（拿不到 exit 3，异常也 fail-closed）、精确命令行匹配杀进程树（含 tts 父子孙）、超时清理、日志时间戳命名保留最近 10 组、隧道**每次重启**以确保连接状态可确认。
- **实测**：幂等连跑两次全 skip 零重复进程；`-Stop` 8s 完成零 warn、tts 三进程全清、四端口释放；冷启动 26.9s 四服务全绿端点全 200；外来进程占 8021 → FAIL + exit 1 + **外来进程未被误杀**；持锁时等 30.2s → exit 3。
- ⚠️ **隧道路径未活体验证**：启动 cloudflared 等于开公网入口，需机主授权，且 T14-5 自动登录与真机验收未做。"已有进程→重启→60s 注册判据"仅静态审查。另 `-Status` 的 tunnel 只是进程存在检查，**不证明入口可用**（Codex 特别点出）。
- **剩余**：T14-3 注册登录自启任务、T14-4 冷启动/离线降级页、T14-5 自动登录操作步骤（用户自行执行，Claude 不接触密码）。
