# 交接文档（HANDOFF）

> 给下一个会话的 Claude（或未来的自己）。最后更新：**2026-08-21，Phase 6 转写策略终局定案（臂C/零样本粤语/refA）**。
> 读这份之前先读 `CLAUDE.md`（铁律），再读仓库根的 `task_plan.md` / `progress.md` / `findings.md`（MVP 计划与实时状态）。研究依据在 `docs/research/`。

> **📘 技术管道全景已成文：`docs/PIPELINE.md`**（2026-08-17）——七 Stage 全配方 + 七闸门清单 + 工程铁律 + **skill 化蓝图与泛化缺口清单**。用户确认初心 = 整套管道产品化为 Claude Code skill（形态 C 构建端），推进顺序见该文档 12.4。配套：`docs/GENERALIZATION.md`（五轴泛化 + 两纪元 sessions 架构）、`docs/research/messaging-channels.md`（TG/WA/微信通道研究）。

## ⓪⁶ 增补（2026-08-21：Phase 6 终局耳测定案，最先看这段）

1. **用户终局耳测三判落定（对照页 gsv_review.html，走 Tailscale 审核）**：①**普通话=臂C**（沪语本字直喂微调，g2p_char_map 拟音替换）②**粤语=零样本**（两臂微调与 zero-shot 听感无差"都差不多"，取零成本路径——泛化红利：粤语域无需任何训练）③**参考=refA 确认**（近普转写 20211229_115226_s03，音色最像；6a 遗留问题一并收口）。裁决已写入 `people/mama/voice/gsv_profile.json`（新增 defaults + decision_log 块；default_ref 维持不变）
2. **审核物料工艺**：复用已审 make_listen_page.py + Claude 直写 manifest（纯数据已声明，存 workdir/gsv_review_manifest.json 可重生成）→ archive_out/gsv_review.html（9 组 32 条 2.82MB，四方对照+QC 疑似红标+附加参考对照）；8020 服务器 Start-Process 脱钩重启（重启后曾掉线）；真浏览器验收仅 favicon 404（豁免同前例）
3. **6e ASR CER 回读 QC 当日收官 → Phase 6 全部完成**（DeepSeek×2 + Codex ACCEPT with fixes[3 MAJOR 2 MINOR 全实锤，含我方自查 3 项]→复核 ACCEPT）：引擎定 **SenseVoiceSmall（C:/Users/justin/venvs/asr，单模型 zh/yue，弃整合包 UniASR 粤语旧模型）**，模型已入 modelscope 缓存；gsv_pipeline synth 批后两轮回读（round1 全量 CER 判级 → round2 仅救"时长 PASS 且 CER 超标"者 seed+2000，采纳=更低 cer）+ 内部 `_asr` 子命令（跨 venv 子进程，PEOPLE_DIR 守卫 exit 2）；profile 新增 asr_qc 块（mama 已配）。冒烟名场面：r2 重抽 cer 0.5385 反而更差被正确拒收。**粤语零样本批的 QC 可直接单独调 `_asr` 子命令**（zero-shot 不走 synth；如需 zero-shot 子命令另立项）
4. **家人盲听 v2 已移除(2026-08-21 用户裁决）**：M1 以用户本人盲听 v2（8 条骗过 7，08-16）为最终依据关闭；blind_v2 物料不删但不再列待办、不再催办
5. 环境现场：api_v2 :9880 已重启常驻（PID 见 workdir/logs/api_v2_20260821.log）；8020 档案站 Start-Process 常驻；两者重启机器后都需手动再拉

### 下回合建议顺序（08-21 刷新，覆盖下方各旧版）

1. TG bot 通道网关（messaging-channels P1）或 VoxCPM2 A/B——按用户意愿
2. 零散：601 敏感疑似复核 / relative_to 小修 / 记音字还原（未立项待用户表态）/ 说话帧确认 / archive_dist 真机验收+分发备份

## ⓪⁺⁺⁺⁺⁺ 增补（2026-08-18 深夜：Phase 6 一日打穿——GPT-SoVITS 管道从零到工具入库，最先看这段）

1. **任务 #14 当日闭环到"等耳测"**：整合包 7.6GB 落地（~/gpt-sovits/GPT-SoVITS-v2pro-20250604，v2Pro 底模全在）→ api_v2 服务 :9880（workdir/tts_infer_v2pro.yaml，常驻）→ zero-shot 冒烟 16 条 → **两臂微调全链跑通**（臂 C=沪语本字直喂 mama_c_raw / 臂 A=全量普译 mama_a_man，各 s2 e8+s1 e15，~25 分钟/臂）→ 同题合成三批已发用户（zero-shot 8 / 臂 C 7 / 臂 A 6，与现役 v0.2 e14 同题 h01-h04 四方可比）。**等用户终局耳测三问：普通话哪批最像 / 粤语音色保持 / 臂C vs 臂A——直接定管道默认转写策略**
2. **tools/gsv_pipeline.py 闭环入库（3fd0e65）**：person-generic 五子命令 prepare/preprocess/train/synth/verify；**voice_profile 参数化首实例 people/mama/voice/gsv_profile.json**（含 g2p_char_map/arms/train/qc；gitignore 内，重建方法见 progress 08-18）。审核实录：DeepSeek 一发 → Codex REJECT 6 实锤（guard 先写后检/bert 对账 4 列按 2 列解析等）→ 回炉 → ACCEPT with fixes → 两 MINOR 声明 hotfix。CLI 配方 docs/research/gpt-sovits-cli-recipe.md（三大坑+全环境变量表，Explore 代理逐行核对）
3. **工程实锤三连（findings 详录）**：①G2P 破坏面——「覅」崩整条（13/160 静默丢）、「㑚/嗯」静默删字 → g2p_char_map 拟音替换（覅→表/㑚→拿/嗯→恩）；②1a bert 按文件名缓存不失效——文本变更须清 3-bert（工具已内建）；③抽卡实证——16 条冒烟 1 截断 + synth 实战 8 条重抽救回 3 条（时长/字数比 QC 有效；**ASR CER 回读还没做**，整合包 funasr 支持 -l zh/yue 可作质检器）
4. **语域标注资产**：workdir/register_annotation.jsonl（160 条 wu 90/mixed 57/mandarin 13 + 普译文本含记音字还原；子代理产出）。**记音字发现**：校对转写大量同音记音（雪小辈=血小板/带生=戴森/人名"亦添"多变体）——档案层潜在改进项，动校对稿需用户闸门，未立项
5. 环境注意：GPT-SoVITS runtime 是 embeddable python（_pth 隔离），users.pth 已重写为本机路径；api_v2 的 tts_infer yaml 会被服务回写（有状态）；tts_server(:8022 CosyVoice)/api_v2(:9880 GSV) 并存显存 ~8GB 常驻

### 下回合建议顺序（08-18 深夜刷新）

1. **等用户终局耳测**（三批样本在手机）→ 定默认转写策略 → 更新 gsv_profile arms 默认
2. ASR CER 回读 QC（gsv_pipeline synth 增强，funasr -l zh/yue）——抽卡自动淘汰闭环最后一块
3. 家人盲听 v2（旧待办，物料在手机）；粤语域若耳测过关可做正式验证批
4. 其余照旧：TG bot 通道网关 / VoxCPM2 A/B / 601 敏感疑似复核 / relative_to 小修

## ⓪⁺⁺⁺⁺ 增补（2026-08-18：TTS 前沿研究收口 + GPT-SoVITS 泛化管道立项，最先看这段）

1. **TTS 十维度研究已收口**（`docs/research/tts-frontier-2026.md`，commit e4d9e2f；12 研究代理 / 100+ 信息源，覆盖 VoxCPM2/IndexTTS2.5/GPT-SoVITS/dots.tts/Qwen3-TTS/Grok Voice + 沪语生态扫描）。**裁决：不换现役**——六候选全部不支持上海话克隆。要点速记：
   - **VoxCPM2 = 唯一值得 A/B 的候选**：预训练含吴语大类（六者唯一）+ 编码器原生 16kHz 输入（微信窄带是其设计工况）+ 克隆 SIM 开源第一梯队；但全量 SFT 需 ~40GB（4090 只能 LoRA r=32 ~20GB）、长文本官方自认偶发不稳、上海话质量零口碑
   - **Grok Voice 制度性排除**：活体同意验证（实时朗读校验短语 + 声纹比对）在产品设计上就拒绝逝者录音——反向印证本地开源权重是逝者档案唯一路径
   - **三大人工闸门结论**（维度 9）：产出人耳筛选**无任何模型可消除**；只有 zero-shot 能省转写校对+checkpoint 挑选，但所有候选 zero-shot 都不识上海话——"省人工"与"最像"对立 → **App 应做两档**（⚡快速档 zero-shot 分钟级验货 + 💎精修档微调全闸门）。**校对页/试听页/盲听页是产品核心组件，不是没自动化完的脚手架**
   - 沪语生态：SS 变体仍只有榜单数字无权重；Wu 系 checkpoint 自 2026-01 冻结（无升级目标也无威胁）；ASLP-lab 新出 **CN-MultiDialect-ASR**（2B 多方言 ASR）可作方言合成自动质检器候选；上海话转写校对负担是素材语言属性，换任何模型都省不掉
   - **Qwen3-TTS = 头号观察对象**：阿里 API 线有上海话预置音色（内部握有沪语数据），开源线无方言且云端复刻线不支持方言；若方言下放开源权重即成第一替代候选——每季度看一眼 QwenLM/Qwen3-TTS
2. **分语域选型定案（08-18 与用户对齐）**：上海话=现役 Wu-SFT（无竞争）；**沪普=现役 v0.2 e14 裸文本域已覆盖，不需要新模型**（双语域一次训练两语域正是其价值）；普通话泛化=**GPT-SoVITS v2Pro 微调主选**（6-8GB 显存门槛→产品化不绑 4090 / 工具链最成熟 / 官方明示 v2Pro 对平庸音质宽容而 v3/v4 不行），VoxCPM2 LoRA 为高配替代；粤语=**GPT-SoVITS 唯一音系级支持**（'yue' 语言代码、粤语音素 Y 前缀）。Fun-CosyVoice3 留位：唯一宣称单底座覆盖沪+粤+口音普通话（instruct 路线，克隆×方言兼容未证，A/B 时当第三组）
3. **★ 用户拍板（08-18）：下一会话开工任务 = 用 GPT-SoVITS 做一套泛化的普通话+粤语管道，以妈妈声音为首个验证对象**（任务 #14）。开工前设计要点：
   - 管道 **person-generic**（people/<slug>/ 布局 + voice_profile 参数化，对齐 GENERALIZATION 轴 3 选型矩阵）
   - 部署形态倾向 repo+CLI 而非 WebUI（tools/asr/funasr_asr.py、两阶段训练脚本均可命令行调用，利于管道化；整合包 GPT-SoVITS-v2pro-20250604 可作环境底座）
   - **首个待决问题=转写策略**：她 160 条语料的转写是上海话本字，GPT-SoVITS 无吴语 G2P——普通话域训练用"普通话近似转写"（报告口径：模型自学说话人发音习惯，口音自然带出）还是筛选她偏普通话的条目子集，需小实验定夺
   - 粤语域=验证管道的跨语言能力（微调她音色后合成 'yue' 文本），她本人无粤语素材，属产品能力验证而非她的档案需求
   - 铁律不变：管道代码 DeepSeek 写 + Codex 审；产出 A/B 对照现役 e14 普通话域（裸文本），盲听是唯一标准
   - 现成资产复用：processed/wechat_voice 125 条 WAV、99 条 corrected 转写、prep_v02 的 160 条清单（wu-sft/v02_full/data）；GPU 任务守 Start-Process 脱钩+Monitor 红线
4. 抽卡预警（研究实锤，开工时心里有数）：GPT-SoVITS 产出稳定性是其最大短板（"抽卡"是社区黑话），逐条筛选负担可能高于现役——管道里应内建 ASR 回读 CER 自动淘汰 + 人工尾筛，把抽卡降级为自动重试

### 下回合建议顺序（08-18 刷新，覆盖下方各旧版）

1. **GPT-SoVITS 泛化管道开工**（用户已拍板，上面第 3 点）
2. 等家人盲听 v2 结果（物料在用户手机，时机用户定）
3. VoxCPM2 A/B 盲听（zero-shot + LoRA 各出样，Fun-CosyVoice3 第三组，同题对照 v0.2 e14）——可与 1 并行或后置
4. TG bot 通道网关（messaging-channels P1，兼轴五 sessions 基建）
5. 零散：601 敏感疑似复核 / 说话帧 veto / 拟音词释义 / relative_to 小修（任务 #5）/ DeepSeek key 轮换（用户）

## ⓪⁺⁺⁺ 增补（2026-08-17 凌晨：对话页四连升级 + 远程访问，最先看这段）

1. **对话页新能力（全部 Codex 审 + 真浏览器 E2E）**：①file:// 直开引导（修"Failed to fetch"实报）②接口类型双模式——OpenAI 兼容（DeepSeek：`https://api.deepseek.com/chat/completions` + `deepseek-chat`）/ **Claude 官方**（`https://api.anthropic.com/v1/messages` + `anthropic-dangerous-direct-browser-access` 头，CORS 直连实测通；Max 订阅≠API 额度，需 console 充值）③**用户气泡漏渲染文本 bug 修复**（自 v1 潜伏）④**微信式语音回复**——tools/tts_server.py 本地合成服务 :8022（v0.2 e14，默认沪普；`wu-sft/tts_server/start_tts.bat` 一键启动，已常驻）+ 语音条 UI（点击播放/右键长按转文字/"合成语音·非原声"标签/≤120 字/四类失败降级文字）。审核插曲：Codex 首轮 REJECT 的 BLOCKER 被六格矩阵实证不能复现（其分帧实验污染自身连接），复审撤回改 ACCEPT；真发现（分帧加固/token 选项/blob 池/touchcancel）全修
2. **远程访问已通（Tailscale 私网）**：**手机任何网络访问 `http://100.116.45.2:8020/`** = 家里档案站全部页面（含语音对话，TTS 走同主机 8022）。架构：**userspace 模式用户态 tailscaled**（腾讯电脑管家拦 SYSTEM 服务出网 WSAEACCES，服务版已停用禁用；提权用户态 + --unattended）；登录自启任务 `TailscaleUserspace`；设备 justin-pc(100.116.45.2) + iphone182(100.111.127.101)。排障链与风险详见 progress 08-17 节（管家若日后拦用户态进程需回家白名单；UDP 受限走 DERP TCP 中继）
3. TTS 服务与 LAN http.server 均非开机自启（TTS 用 start_tts.bat、档案站用 archive_out/start_server.bat 手动起；后续可仿 TailscaleUserspace 注册计划任务）

## ⓪⁺⁺ MVP 已交付（2026-08-16 深夜收官，最先看这段）

**Phase 5 完成，MVP 四层全部交付**：`people/mama/archive_dist/` = **161 文件 / 241.7MB 自包含离线档案**，拷走即用（无网机器双击 start_server.bat → http://localhost:8020/）。内含：干净入口 index.html、卡通人（125 条原声）、BYOK 对话（三源检索：记忆 Tier-1/转写 Tier-2/消息 Tier-2）、text/ 文字层四件（persona/memories/timeline/rhythm）、README、archive_manifest.json（逐文件 sha256，`build_archive --verify` 对账）。工具 tools/build_archive.py（DeepSeek×3 + Codex ACCEPT with fixes 五项全修 + 专项验收 11/11 + Playwright 三页真浏览器验收零错误）。重跑幂等；review 页全剔；relationship.json/candidates.jsonl 刻意不入交付面。

用户裁决（08-16 深夜）：盲听 v2 回贴系**用户本人**（合成 7/8 骗过 vs v0.1 预演 3/10——版本提升实锤），M1 家人盲听"不重要"不阻塞交付；家人盲听物料保持可用（blind_v2.html 在手机+LAN，key 分离）。

下回合建议：①用户在别的机器/手机实测 archive_dist（真验收）②601 敏感疑似复核（交付面含 messages 分片，敏感疑似仍在数据层）③零散：说话帧 veto、拟音词释义、relative_to 小修（任务 #5）④档案分发方案（拷贝给爸爸等家人 + 双备份铁律执行）

## ⓪⁺ 增补（2026-08-16 深夜二回合，先看这段）

1. **盲听 v2 首份回贴已对卷（dataset 69fbdcbc2417）**：**合成 7/8 骗过**（6 条打 3 分、1 条 5 分），唯一识破 w07"吃饱饱"叠词句；**真声 4/4 全认出全 5 分**（有效性基线成立）。对照预演（用户本人×v0.1）3/10 → 本轮 7/8，v0.2 e14 提升实锤。**听者身份待用户确认（本人还是家人）——决定 M1 是否正式通过**。回贴存 `wu-sft/blind_v2/responses/resp_20260816.json`；盲听页已上 LAN（/blind_v2.html，key 未上传）
2. **tools/merge_candidate_state.py 闭环入库（702085e）**：状态保留合并——重挖记忆卡不再丢用户裁决（Codex ACCEPT with fixes；十场景冒烟含幂等/结转/守卫）
3. **记忆卡 corrected 升级完成**：voice_transcripts 99/99 全校对稿（draft 归零）→ 重挖+合并（150↔150 全对齐，124/26 裁决零丢失，38 卡 content_changed=新文本即校对定稿不强制复审）→ memories.md 重生成 124 条
4. **对话页知识源升级三件套（Codex 批审 ACCEPT with fixes，一行 hotfix 已修）**：①chat_context --memories-mode index 默认——system prompt 89.5k→23.9k 字符（记忆改索引）；②新工具 build_chat_knowledge.py → data/memories.json（124 Tier-1）+ data/transcripts.json（108 Tier-2，99 语音+9 视频）；③chat.html 检索三源混排（记忆 top3 优先带 [家人确认记忆 Tier-1] 标签、转写 top2 带媒体标签、404 容错、老契约零回归 harness 四套全绿）。原"转写进 bundle + chat 检索源扩展"待办一并落地
5. 新立项（低优先）：build_chat_context 仓库外 --out 的 relative_to 写盘后崩（预生存缺陷，Codex 确认非本轮引入）
6. 下回合看这里：①等盲听听者身份确认 + 更多家人样本 ②Phase 5 正式打包（工程侧当前无阻塞）③601 敏感疑似复核 ④零散：说话帧 veto/拟音词释义/relative_to 小修

## ⓪ 当前最热状态（2026-08-16 晚，先看这里）

**语音层到达稳定台阶：v0.2 e14 定稿为现役，双语域一个模型。** MVP 四层工具链全部闭环，剩用户现实动作（家人盲听）+ 文字层收尾工程。

### 本会话（08-16）拍板与产出

1. **现役语音模型 = `~/wu-sft/v02_full/exp/mama_v02f160_llm/epoch_14_whole.pt`**（用户耳测定稿："有比v0.1好点，v0.2 e14"）。**双语域用法（关键）**：合成文本挂 `<|wuyu|>` 前缀 = 上海话；裸文本直喂 = 她的沪普（上海口音普通话，A/B 耳测 A 路胜出定案）。v01_full44 e14 与 Fun-CosyVoice3 普通话线**双双退役**（后者并入主线，对话页合成不再需要"普→沪本字转换"——LLM 普通话输出可直喂）
2. **v0.2 训练闭环**：校对 8 页收口（用户回贴 14 处修正 + p1/2/6/7/8 整页通过）→ prep_v02_data.py 合并 **160 条 / 47.2 分钟**（v01 44 + 新转写 116，零冲突零超30s）→ 特征三件套 → 15 epochs（CV loss 0.195/acc 0.964）。中途遭 harness 误杀事故，从 e6 无损续训恢复（教训见下）
3. **盲听 v2 物料就绪（M1 关口）**：`~/wu-sft/blind_v2/blind_v2.html`（12 条乱序 = v0.2 e14 合成 8 句**训练集外**文本 + pilot 真声 4 条，0.64MB）+ `blind_v2.key.json` 答案卷分离。已发用户手机 → **等用户安排家人盲听——M1 唯一有效标准**
4. **synth_blind_batch `--lang {wu,mandarin}` 开关 Codex 补审 ACCEPT**（五项全过）；4 批 22 条实跑验证。双语域批量产线正式可用
5. 校对页"全是空的"破案：零标红页内容藏在「正常」折叠条里 → make_correction_page 零标红默认展开 hotfix，8 页重生成

### ⚠️ 本会话血泪教训（新增工艺红线）

- **长时 GPU 任务（训练/大批合成）永不用 harness 后台 bash**——会被任务回收误杀，且 worker 成孤儿后 stdout 断裂写阻塞**卡死占显存**（本次 21GB 挂了 80 分钟）。正确姿势：`Start-Process -WindowStyle Hidden` 启动独立 bash + 日志 `> file 2>&1` 直写 + Monitor 工具挂三态监听（完成 marker/日志报错 grep/mtime 停滞）。疑似死掉先 `Get-CimInstance Win32_Process` 按 WorkingSetSize 找僵尸，杀干净再重启。CosyVoice 续训：`--checkpoint epoch_N_whole.pt` 即可（同名 yaml 自带 epoch/step，自动从 N+1 续起）
- **官方 make_parquet_list.py 在 Windows 必挂两坑**：GBK 默认编码（`PYTHONUTF8=1` 解）+ apply_async 吞 spawn NameError（用 `~/wu-sft/v0/scripts/make_parquet_single.py` 单进程版）
- PowerShell 5.1 `Get-Content` 对无 BOM UTF-8 中文文件**行数统计不可靠**（GBK 误解码吞行）——文本处理一律 python -X utf8

### 下回合建议顺序

1. **等家人盲听结果（M1）**——物料已就绪，时机用户定；结果对卷 `blind_v2.key.json`
2. **extract_memory_candidates 状态保留合并**（DeepSeek 写 + Codex 审）——前置工程：现在重挖会清空用户已裁决的 150 条状态；做完才能用校对后 44 corrected 转写重挖记忆卡（draft→corrected 升级）
3. **build_chat_context 记忆块摘要/上限**——当前 system prompt ~9 万字对 BYOK 太重
4. 转写进 bundle + chat 检索源扩展（voice/video_transcripts.jsonl 已在 normalized/）
5. Phase 5 正式打包（剔除 review 页、无网机器验收）
6. 601 条敏感疑似人工复核（normalized/sensitive_scan_report.jsonl，闸门页已默认剔除）
7. 零散开放项：说话帧用户 veto（"还没看"）；@郑韫玉 typo 疑问；4 个拟音词释义（皮雪雪/交难受/铿钱/老麻球）；观察更强开源沪语 TTS（吴语生态 2026-02 起步）

### 环境现场（08-16 会话结束时）

- LAN 服务器常驻：`python -m http.server 8020`（archive_out，PID 3136），入口 http://192.168.3.69:8020/（手机缓存顽固时加 `?v=N`）
- 试听/盲听页：`listen_v02/ab_v02.html`（LAN）、`~/wu-sft/blind_v2/blind_v2.html`（已直发用户）
- 合成调用式：cosyvoice venv + `PYTHONPATH='C:/Users/justin/CosyVoice;...Matcha-TTS'` + `PYTHONUTF8=1`，`tools/synth_blind_batch.py --texts <jsonl> --exp-dir <exp> --epoch 14 --lang {wu,mandarin} --out-dir <dir>`
- ComfyUI 仍在后台（127.0.0.1:8188，占 ~1.7GB 显存）；DeepSeek 必带 `DEEPSEEK_NOTHINK=1`

## ⓪-旧 会话历史快照（2026-08-12/13，已被上文覆盖处以上文为准）

**MVP 四层齐头并进后的状态**。详细 phase 看 `task_plan.md`，一句话版：

- **语音层 90%**：模型定稿 **v0.1-full44 epoch14**（`~/wu-sft/v01_full44/exp/mama_v01f44_llm/`；起始幻觉=随机采样所致，重抽即除，用户已确认"干净了"）。`tools/synth_blind_batch.py` 已闭环入库（texts JSONL + 时长 QC 自动重抽 + qc_report）**但未实跑**。下一步：盲听文本清单定稿 → GPU 实跑 → 家人盲听（M1 关口，批次建议见 dialect-tts-maturity.md）
- **数据层 ✅**：`archive_out/data/` 228MB（但见下面敏感记录清理——2024 分片需重建）
- **文字层 90%（工具链全备，剩用户动作）**：digest/candidates/timeline/闸门页/apply 五工具全部闭环入库。**memories/timeline.md 已产**（68 月对账精确）；**gate_page.html（150 卡 192KB，6 条敏感默认剔除）已发用户手机**——用户逐卡 确认/改写/剔除 → 复制回贴码发回 → `python tools/apply_gate_decisions.py --person mama --decisions <存回贴码的文件>` 产 **memories/memories.md（Tier-1）**（支持多轮回贴、action pending 回撤、```json 围栏容忍）。**persona.md 草稿 306 行 46 论断已发用户**（全 Tier-3 + Q1-Q13 待确认，Q1 身份对应最优先）。3d 契约要点：回贴码=对 candidates.jsonl 初始状态的真 delta（dataset hash e17d30763dee 校验；候选文件重生成后 hash 会变，旧回贴码须 --allow-dataset-mismatch 或重发页面）
- **卡通人 90%（4e-集成完成 2026-08-12）**：头像 04 s1001（用户拍板）+ 说话帧 avatar_open.png（Qwen-Image-Edit seed1002，溯源在 avatar_choice.json open_frame 块，**用户可否决重抽**）。build_avatar_page.py 图片双帧模式闭环（Codex ACCEPT 零发现）：音量驱动双帧口型（mouthFrameFor 纯函数 0.04/90ms，阈值经真实语音 RMS 分布验证）+bob 弹动+SVG 回退（person-generic）+data/avatar reconcile。**体验：LAN http://192.168.3.69:8020/avatar.html（8020 常驻）**。剩：4c 合成语音入清单（等盲听）、4d BYOK 对话页（Tier-3 禁陈述提示词）
- **JS 产物 harness 定式（2026-08-12 二次教训固化）**：DOM stub 必须**忠实**——getElementById 对 HTML 中不存在的 id 返回 null（模板 scratchpad/avatar_harness2.js）；过宽的"任意 id 都给元素"stub 会吞掉全部空引用崩溃
- ✅ **敏感记录清理已闭环（2026-08-12）**：`tools/scrub_sensitive.py`（scan/apply/verify 三模式，person-generic）+ `tools/sensitive_patterns.json` 入库（DeepSeek×2 + Codex ACCEPT with fixes + 一行声明 hotfix）；2024-02-09 凭据批 **14 条已从全部派生层删除**（UIF 20923→20909），四下游全量重建，**verify residue=0**。审计清单 `people/mama/normalized/scrub_manifest.jsonl`（无正文）。⚠️ 两个尾巴：①日后重跑 parse_wechat 会重新引入这 14 条，须按 manifest 重新 apply；②删后全量扫描剩 **601 条疑似**（high 273/medium 50/low 278，报告 normalized/sensitive_scan_report.{jsonl,md}），供 3d 闸门页默认剔除 + 人工复核，**未经用户逐条确认前不得自动删**
- **persona 提炼数据边界（用户问过）**：persona/digest/rhythm 只用了**文字消息**；音频仅以计数参与（[语音]76/[通话]74 占位符统计），语音**内容**与视频完全未进 persona。可选增强（未立项）：99 条语音转写反哺口语语域、视频日期反哺记忆卡片
- ✅ **4d BYOK 对话页完成（2026-08-12）——MVP 四层工具链全部闭环**：`prompts/chat_system.zh.md`（六铁律模板）+ `tools/build_chat_context.py`（18074 字 system prompt，含 persona 全文+Tier 纪律+防伪造回退）+ `tools/build_chat_page.py`（chat.html 23KB：BYOK 设置/客户端检索 7 分片/真流式 SSE 纯函数状态机/永久非本人横幅）。Codex 三轮至 ACCEPT；测试三件套 harness（契约 16/SSE 6/e2e 2）沉淀 scratchpad。**体验：LAN http://192.168.3.69:8020/chat.html（⚙ 里填端点+模型+key）**；入口 index.html 已重排"档案体验"区
- **⓪-2 增补（2026-08-13 凌晨大跃进，先看这段）**：①**Tier-1 记忆册已诞生**——memories.md 134KB/124 条（用户 150 张全裁决：26 剔含全部敏感预标记，回贴码+文字指令"其他都是确认"补全式应用）；对话页 system prompt 已含真实记忆（9 万字，待加摘要上限）；②发音攻坚终局：本字改写/D 短句/D 长句三连耳测全负 + SS 变体未公开 → **CosyVoice2-Wu 公开权重天花板实锤、路线 D 关闭**，合成定位=短句场景，长内容播真声（观察项：留意更强开源沪语 TTS）；③她的 99 条语音 + 9 条视频音轨**全量文本化**（normalized/voice_transcripts.jsonl + video_transcripts.jsonl，44 corrected + 64 asr_draft），记忆卡带内容、转写进关键词挖掘；④v0.2 重训数据链全通（切段 101 段 / u2++ 转写零坏字符 / 校对 8 页上 LAN 首页）**等用户校对回贴**；⑤盲听预演成绩：合成 3/10 骗过（两条 5 分）、真声 4/4 全认出
- **下回合建议顺序**：①用户 v0.2 校对回贴 → parquet → 重训 → 试听 A/B ②校对完成后重挖记忆卡升级 draft→corrected（⚠️ 前置：extract_memory_candidates 加**状态保留合并**——现重挖会清空 150 个裁决）③build_chat_context 记忆块加摘要上限 ④转写进 bundle + chat 检索源扩展 ⑤persona Q2-Q13 后 Phase 5 正式打包（剔除 review 页、无网机器验收）⑥601 条敏感疑似复核
- **08-13 工艺沉淀**：音频产物必须解码回读（float32 事故实录见 findings）；同文件三轮回炉失败即停整文件重生成、换外科 hotfix（video_audio_prep 实践）；切段逻辑应抽共享模块（两脚本重复实现两次咬人，Codex 附议）
- **HTML 工具生成定式（2026-08-12 第三批教训固化）**：①模板一律 `r"""` raw 字符串 + `__X__`+.replace 插值（%格式化撞 CSS 百分号、非 raw 撞 JS \n 两个坑各炸过一次）；②页面 JS 的关键逻辑抽纯函数挂 window 供 harness 直测；③验收层级三级走全：node --check（语法）→ 忠实 stub 全脚本执行（空引用）→ e2e 驱动真实交互流（集成缺陷如假流式/fallback 丢块只有这层能抓）
- **审核工艺升级（2026-08-12 固化）**：凡产出含 JS 的页面，验收标准 = Node stub-DOM **实际执行**断言行为契约（harness 模板存 scratchpad/gate_harness.js，可复用），node --check 只算下限；Codex/查看器对 CJK 文件的"语法错误"类指控一律先 py_compile/json.load/node 实证（累计 3 次误报）
- **环境现场**：ComfyUI 可能还在后台跑（127.0.0.1:8188，起服命令见 progress 08-12 节；显存吃紧就 POST /free）；语音合成用 cosyvoice venv；DeepSeek 必带 `DEEPSEEK_NOTHINK=1`（写法：`$env:DEEPSEEK_NOTHINK="1"; python scripts/deepseek_call.py <spec> <out> 32000`，产物剥围栏+py_compile）
- **移动 review 定式**：HTML <1MB/页大按钮；音频逐条 MP3 直发（聊天渲染器不播内嵌音频）；图片拼图 SendUserFile 直发；选择题用 AskUserQuestion 按钮
- **本会话审核实录速览**（详见 progress.md）：五个工具 DeepSeek×2~4 轮 + Codex 多轮至通过；Codex 一次误报（"语法错误"经 py_compile 实证不存在）——**对 Codex 判定要抽查验证，不盲从**

## 一、项目一句话

为逝去的亲人建可传承数字档案（档案优先于对话，20 年后仍能打开）。首个对象：**mama**（已离开），**上海话为主辅普通话**，素材全数码、全用户（justin）视角。

## 二、已定决策（grill 会话拍板，勿重新讨论）

| 决策 | 结论 |
|---|---|
| 多人架构 | 方案 A：单仓库多人，`people/<slug>/`，工具/prompts 通用 |
| 产品形态 | **混合 C**（构建端 Claude skill + 消费端自包含静态 HTML + 可选 BYOK 对话页）✅ 用户已确认 |
| 语音选型（**2026-08-18 刷新**） | **现役：CosyVoice2-Wu-SFT 全量 SFT = v0.2 e14 双语域**（上海话 `<|wuyu|>` + 沪普裸文本）。十维度选型矩阵见 `docs/research/tts-frontier-2026.md`：普通话/粤语泛化=GPT-SoVITS v2Pro 主选（已拍板开工）· VoxCPM2=唯一沪语 A/B 候选 · Qwen3-TTS=方言开源化观察对象。**家人盲听是唯一标准**不变 |
| 微信导出（**已定案 2026-08-04**） | 用户微信实测 **4.1.11.24**。chatlog/chatlog-new 不支持 4.1.x（出局）。**采用混合方案**：①文字+图片→ `chatlog-keeper`（MIT，已在 4.1.11 取到 key 并缓存，`wechat`+`images` 命令）；②视频→ **直接复制** `xwechat_files/<wxid>/msg/video/**/*.mp4`（4.1 视频是明文 mp4，实测 387 个）；③语音→ **自研提取器**（SILK blob 在加密消息库内，需先探测表/字段，DeepSeek 写 Codex 审，pilk/silk→wav）。详见 `docs/research/wechat-media-extraction.md`。备选交叉验证：`LifeArchiveProject/WeChatDataAnalysis`（无协议、DMCA靶心，用完即弃）。chatlog-keeper 源码在 `installers/chatlog-keeper-0.2.0/`，已建 .venv 装好依赖 |
| 数据源架构 | 源适配器 → UIF 统一中间格式（`schema/uif.schema.json`）→ 下游只消费 UIF |
| 三条自我保护约束 | 已入 CLAUDE.md 铁律（Tier 分级+人工闸门 / 保留完整性 / 沉浸度克制） |
| 硬件 | RTX 4090 24GB + i9-14900KF + 64GB RAM，全本地无约束 |

## 三、Phase 1 已交付（全部经 DeepSeek 写 + Codex 三轮审核 ACCEPT）

- `CLAUDE.md` 三大铁律 · 仓库骨架 · `.gitignore`（people/ 隔离）
- `schema/uif.schema.json` + README（4 类记录：message/post/email/media_item；信封含 viewpoint/tier/provenance）
- `docs/research/wechat-export.md` · `docs/research/form-factor.md`
- `tools/ingest_media.py`（媒体清点+EXIF+报告）· `tools/silk_decode.py`（备用）· `tools/backup_check.py`（备份审计）
- `scripts/deepseek_call.py`（流式调用器，唯一可靠通道）

## 四、下一步（按序）

**微信导出与媒体提取的 RE 已全部跑通验证**（2026-08-05），完整配方见 `docs/research/wechat-media-extraction.md` 第三点五节。关键状态：
- 全量文字已导出 → `people/mama/raw/wechat/export_full/wechat_messages.json`（75万条；妈妈 laurawang001 6968 条）
- 语音 84/85、视频 13/25 已验证可提取（真实 60s 语音样本已解码到 `~/ck-decrypted/sample_mama_voice.wav`）
- 解密环境：key 在 `~/ck-data/secrets/`，db 镜像(已删shm)在 `~/ck-mirror`，明文库在 `~/ck-decrypted`，pysilk-mod 已装进 venv

**待建（DeepSeek 写 + Codex 审）**：
1. ~~`tools/extract_wechat_voice.py`（#11）~~ ✅ **已完成（2026-08-05，DeepSeek 两轮 + Codex 两轮审核 ACCEPT）**：实跑 5 会话共提取 **125 条 WAV（妈妈 99 条，总时长约 55 分钟）**，仅 1 条缺 blob（2021-12-22 一条，VoiceInfo 无行），0 解码失败 0 警告。产物：`processed/wechat_voice/<room>/` + `normalized/wechat_voice_manifest.jsonl`（UIF media_item，schema 校验通过，含 svr_id/chat_room/create_time_epoch/sender_wxid 关联键）+ `wechat_voice_report.md`。**运行须用 chatlog-keeper venv 的 python**（pysilk 在那里）：`installers\chatlog-keeper-0.2.0\.venv\Scripts\python.exe tools\extract_wechat_voice.py --person mama --db-dir ~\ck-decrypted`。原探测记录：sender 归属 = `Msg.real_sender_id` → 同 db `Name2Id` 表 rowid → wxid；Msg_<md5(room)> 分片散布在 message_0~6；VoiceInfo 在 media_0（3151 行全账号）+ media_1（1 行），列序 chat_name_id/create_time/local_id/svr_id/voice_data/data_index
2. ~~`tools/collect_wechat_video.py`（#12）~~ ✅ **已完成（2026-08-05，DeepSeek 三轮 + Codex 两轮 ACCEPT + 热修复确认）**：5 会话 540 条视频消息，**215 个 mp4 在本地并已采集入 `raw/wechat/video/<年-月>/`（1.91 GB，妈妈发的 9 个）**，其余 325 个未下载/CDN 过期。manifest `normalized/wechat_video_manifest.jsonl`（UIF media_item，schema 全过）。要点：raw 只新增不变量用 staging+os.link 硬链接原子落盘实现；微信源 mp4 带 ReadOnly 属性，staging 清理需 _force_unlink（chmod 后删）。运行：`python tools\collect_wechat_video.py --person mama --db-dir ~\ck-decrypted --video-dir ~\xwechat_files`
3. ~~`tools/parse_wechat.py`（#13）~~ ✅ **已完成（2026-08-05，DeepSeek 两轮 + Codex 三轮审核 ACCEPT）**：已产出 `people/mama/normalized/wechat_messages.uif.jsonl`（20923 条，妈妈 9386 条，jsonschema 全量校验通过，report 见同目录）。配置在 `people/mama/wechat_parse_config.json`（gitignore 内，重建时需按下述规格重写）。媒体 ref 由 #11/#12 后续按 chat_room+ts+sender_wxid 关联合并。**筛选规格（2026-08-05 核实后扩充，勿退回旧版）**：①一对一会话 `chat_room=laurawang001` 整段收录（6968 条，妈妈发 5048）；②**群聊补抓**——妈妈在 4 个群发过 4338 条（全部文字）：家庭群 `17586423176@chatroom`（她 3622/群 6981，成员仅她+justin+爸爸）、`25722082802@chatroom`（430）、`5030199976@chatroom`（147）、`3758229935@chatroom`（139），这些群的完整对话（含他人发言作为前后文）一并收录；③UIF 中 `chat_room` 区分语境（私聊/家庭群/亲友群），他人消息 sender 必须清晰标注，不得与妈妈本人的话混入 persona 语料
4. ~~**M0 收尾**~~ **备份关口已由用户明确豁免（2026-08-05："不要去管备份了，假设资料很安全"）**——backup_check/双备份不再阻塞后续里程碑，勿再催办。照片/家庭录像清点（ingest_media）仍待素材导入 raw 后进行
   - **新立项（2026-08-05，用户拍板）——数据源扩展**：
     - **微博（#14）**：两部分素材——①她自己微博账号的全部内容；②**用户（justin）微博下她的评论/回复**。适配器 `tools/parse_weibo.py` 输出 UIF post 记录（schema 已支持 author/comments）。前置：素材获取方式待研究（她的账号官方导出是否可行/网页存档抓取；justin 自己的微博可官方导出后筛她的评论），先由用户收集 raw → `people/mama/raw/weibo/`
     - **微信朋友圈（#15）**：她的朋友圈（含 justin 可见的点赞/评论互动）。适配器 `tools/parse_moments.py` 输出 UIF post 记录（source=wechat_moments）。前置：朋友圈数据在手机端，导出方式待研究（微信自带"个人信息导出"里朋友圈部分/手机备份工具），先由用户收集 raw → `people/mama/raw/moments/`
     - 两者共同点：先解决**素材到手**，adapter 都是纯解析（模式同 #13，DeepSeek 写 + Codex 审）
5. **M1 语音验证（进行中，2026-08-05 启动）**：
   - ✅ 素材普查：妈妈 99 条语音中 61 条 ≥15s（爱发 60s 长语音），参考素材充足
   - ✅ 候选试听：5 条最连续长语音切 18s 窗口发用户试听，**用户确认"音质可以"**（SILK 窄带可作克隆基底）
   - ✅ 参考固化：`people/mama/voice/reference/`（5 条 full + 5 条 clip18 + reference_manifest.json 含溯源/窗口偏移/sha256）
   - ✅ 环境搭建完成（2026-08-05）：CosyVoice 源码在 `C:\Users\justin\CosyVoice`，py3.10 venv 在 `C:\Users\justin\venvs\cosyvoice`（torch 2.3.1+cu121，cuda 可用），模型在 `C:\Users\justin\CosyVoice-models\Fun-CosyVoice3-0.5B`。装机坑：setuptools<81 约束修 whisper 构建、wget 需 --no-build-isolation 补装、prompt 传**文件路径**别传 load_wav 张量。冒烟脚本 `scratchpad/clone_smoke.py`（带参=zero-shot prompt_text 文件）。单句合成约 4-5s
   - ✅ 首轮 A/B（2026-08-05）：**用户判定音色"非常像妈妈"（关键 go 信号）**，但 instruct2 模式**发音不够地道**。已跑 zero-shot 版（prompt_text 用 ASR 草稿保守清理，非用户校对定稿）做对比，待用户听 zero-shot 是否改善发音
   - ✅ 二次研究（2026-08-05，workflow）：发音不地道判定为**工程问题非模型天花板**，最高杠杆三步=校对转写/吴语本字/换病中参考；完整调优指南与 VoxCPM2 备选触发条件见 `docs/research/cosyvoice3-deploy.md` 第五节
   - ✅ 5 条参考内容 ASR 识别（判健康期）：ref01(2022-07 设计花坛庭院,最日常) / ref02(聊买房) / ref03(2020-12 验血病中,当前主参考待换) / ref04(聊买房) / ref05(2021-11 失眠吃药)
   - ✅ 参考定稿：**ref01**（2022-07 健康期日常，用户从 5 条盲选，音色"非常像"）；转写已由用户校对（`voice/reference/ref01_transcript.txt`，上海话本字）
   - ✅ zero-shot 正路跑通（格式坑已解：源码 `llm.py:585` 确认 CosyVoice3 需 `指令<|endofprompt|>转写`；f0 崩溃因 tts_text split 出极短分句→改连贯长句）。但**用户判定 zero-shot 上海话发音仍不地道**，instruct2 也不地道 → CosyVoice3 上海话发音走不通
   - **决定（2026-08-07 用户）**：上海话**暂时保留 instruct2 版作为基线**（音色对、发音将就），存档于 `people/mama/voice/baseline_instruct2_20260807/`（配置见该目录 README + deploy 文档第六节）。音色链路已完全稳（最难部分成了）
   - ✅ **方言 TTS 深挖完成（08-07 首轮 + 08-08 补跑，报告 `docs/research/dialect-tts-maturity.md`）**。决定性发现：**CosyVoice2-Wu 全套权重已公开**（HF `ASLP-lab/WenetSpeech-Wu-Speech-Generation`，Apache-2.0 免申请，5 变体，SS 最佳 IMOS≈4.0，原生 zero-shot 克隆 + `<|wuyu|>` 标签，参考按 16kHz 加载窄带不吃亏）。路线修订：**B0**（Wu 底座 zero-shot，零训练）> B1（+她 55 分钟 AP-BWE 增强后本地 SFT，4090 可跑）> **D**（新增：沪语 TTS→Seed-VC timbre-only 换她音色，两段式绕开克隆×方言死结）> C（CosyVoice3 拼音标注只是字音补丁，音系天花板被本机 tokenizer 代码实锤）> A（退普通话，仅对照）。**工程红线：Wu 权重是 CosyVoice2 栈的 llm.pt，与 Fun-CosyVoice3 不通用**
   - ✅ B0 已跑（08-08，Wu 权重 5 变体全下载至 `C:\Users\justin\CosyVoice-models\WenetSpeech-Wu-Speech-Generation\`）：B0 zero-shot vs instruct2 基线 A/B 样本、instruct-prosody 韵律探针、语速探针（1.08/1.15 档）均已生成（存档 `~/wu-sft/v0/listen_archive/`）
   - ✅ **B1 v0 SFT 端到端跑通（08-09 深夜，重启电脑后本会话恢复）**：Wu ASR（Understanding whisper-medium + wenet attention_rescoring）转写妈妈 45 条 ≤30s 语音（8.2 分钟）→ embedding/speech_token → parquet → 4090 全量 SFT LLM 15 epoch（约 14 分钟，最终 train-cv loss 0.092/acc 0.989）。工作区已从临时 scratchpad 迁至 **`C:\Users\justin\wu-sft\v0\`**（数据/脚本/配置/启动脚本 run_train.sh/checkpoints epoch_0..14 约 30GB）
   - 训练三连坑（已修，勿再踩）：①backward OOM = 白天推理残留显存，重启即愈；②GBK 编码的 ds_stub 废稿经 PYTHONPATH 遮蔽 venv 内 ASCII 版 stub → SyntaxError（正版 stub 已装在 cosyvoice venv site-packages，勿加 PYTHONPATH）；③cv 阶段 `@torch.inference_mode()` 与 Windows gloo DDP `_sync_buffers` 冲突 → 已改 `@torch.no_grad()`（executor.py:146）。CosyVoice 未提交补丁两处：llm.py 梯度检查点（non-reentrant + use_cache=False）、executor.py cv 装饰器
   - ⚠️ **分工违规记录（08-09 用户查账指出）**：08-07~09 所有代码（探针/SFT 管线/源码补丁）均 Claude 直写，未走 DeepSeek/Codex，违反铁律 1。已送 Codex 补审，判定 **REJECT**：45 条转写中 **14 条含 U+FFFD 坏字符（26 处）**属不可接受监督噪声；extract_speech_token_cpu.py 对 >30s 音频静默空 token（本批未中招但属管线隐患）；cv==train 仅算冒烟。两处源码补丁 ACCEPT。**v0 checkpoints 只算管线冒烟产物，不作验收**
   - **下一步（按序）**：①14 条脏转写处理——生成 HTML 试听页供用户校对（或先剔除出 31 条干净版）→ 重建 parquet → v0.1 重训（DeepSeek 写清洗/重建脚本 + Codex 审，恢复分工）；②DeepSeek 修管线 blocker（空 token fail-fast、parquet 命名、accum_grad 奇数批 flush）；③v0/v0.1 checkpoint 逐 epoch 合成同文本样本（重点 epoch 2-5 防过拟合）→ 与 B0 zero-shot、instruct2 基线三方 A/B → 家人盲听（批次建议见 dialect-tts-maturity.md）
   - ASR 草稿环境：`C:\Users\justin\venvs\asr`（funasr+SenseVoiceSmall，CPU）；3号切片草稿在 `scratchpad/asr_draft_clip18.txt`
   - 环境事实：ffmpeg 不在 PATH；pysilk/numpy 在 chatlog-keeper venv；磁盘余 1.1TB

**注意 pysilk.decode 要传完整含 0x02 头的 blob（剥离会报 Not a valid silk_data）。**

## 五、工程注意事项（血泪教训，别再踩）

- **DeepSeek 调用**：只用 `python scripts/deepseek_call.py <spec> <out> 32000`。非流式会被网络掐断；<32k tokens 会被推理烧光正文；生成后 strip markdown 围栏 + `py_compile`；`scripts/deepseek.ps1` 勿用于含中文的文件（PS 5.1 响应解码乱码）
- **DEEPSEEK_API_KEY** 在用户级环境变量（Bash 工具进程可能不继承，可作第 4 参数传入）。⚠️ key 曾在对话明文出现，已提醒用户轮换
- **pilk**（silk_decode 依赖）在 Python 3.13 无 wheel——不阻塞（主路径 chatlog 直出 MP3），真需要时装 VS Build Tools 或用 py3.11
- **控制台中文乱码**是 GBK 代码页显示问题，文件都是 UTF-8，勿在脚本里强改 stdout 编码（Codex 建议保持现状）
- 审核循环战绩参考：Codex 第一轮抓过 3 个 blocker（--person 路径注入写 raw/），修复模式是 slug 正则 + resolve() 锚定校验——新工具写 spec 时直接把这两条要求写进去

## 六、用户待办（2026-08-21 刷新）

- ~~安排家人盲听~~ **已移除（2026-08-21 用户裁决）**——M1 以本人盲听 v2 关闭
- [ ] 说话帧确认（avatar_open.png，"还没看"，可否决重抽）
- [ ] DeepSeek API key 轮换（历史遗留，key 曾在对话明文出现）
- [ ] 4 个拟音词释义（皮雪雪/交难受/铿钱/老麻球）随手补
