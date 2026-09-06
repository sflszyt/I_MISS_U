# 从 0 到 1 建档 App 产品化研究（任务 #22-b，2026-09-03）

> 用户原话："基于研究 a，目前从 0 到 1，能否做成 app 自动化？我想做成这样的一个产品：电脑用户直接将训练数据（聊天记录、语音、照片、视频等）拖入应用，应用全程引导用户进行配置以及审核（逃不掉的一些人工审核例如语音和卡通形象），最后产出 companion。"
> 定位：**构建端产品化**。form-factor.md 定的"构建端 = Claude Code skill，允许死"要重审；GENERALIZATION.md 五轴（对象/数据源/语音/人格维度/持续对话写回）是需求基线；a 的结论（消费端 = 静态档案 + 主屏 Web App，声音出不了 GPU）是前提。
> 方法：内部盘点（0→1 管线人机分工 33 项、伦理约束 39 项，workflow 完成）+ 主模型逐条外部补查（打包先例 / 数据导入现实 / 中国监管 / 同类产品）。研究文档由 Claude 直写。

---

## 0. 一句话结论

**能做，但要改一个字：不是"产出 companion 的自动化 App"，而是"产出档案的建档工作台"。** 管线 7 阶段约 30 步里，多数是确定性脚本，可以被 GUI 封装成"拖入 → 向导 → 闸门 → 编译"；用户说的"逃不掉的人工审核"恰好就是本项目的七道闸门，它们不是自动化的残余，而是产品本体。真正的边界有三条：**微信聊天记录永远不能被 App 自动取出**（铁律 3.4 + 管理员 + 扫码 + 第三方工具随时失效，用户必须自带导出文件）；**她的声音需要 4090 级 GPU 做 SFT**（普通显卡走 GPT-SoVITS 6–8 GB 档，无显卡只有文字档案）；**现在由 Claude 承担的判断力工作**（语音失败诊断、persona 起草与 13 问、贴片标定迭代、环境排障）无法写成固定流程——产品只能"固化配方 + 失败即止"，或内置一个以仓库工具为工具集的 agent。**给陌生人用的前提是把铁律 2 从文档变成不可绕过的功能**——这一步无论产品化与否，妈妈档自己也需要。建议：GO，但分期，先清工程债（项目本身就欠），受众先定"自己 + 少数人"。

---

## 1. 现状盘点：0→1 管线的人机分工（妈妈档实测）

| 阶段 | 步骤 | 自动化 | GPU | LLM | 人工闸门 | person-generic |
|---|---|---|---|---|---|---|
| S0 环境 | 5+ venv（cosyvoice/asr/comfy/gsv/chatlog-keeper）+ 权重（CosyVoice2-Wu、wenet u2++、Qwen-Image-Edit-2509 ≈28.6 GB、GPT-SoVITS ≈7.6 GB）+ ComfyUI + Rhubarb | 否（手工装） | — | — | — | 否：路径/Windows 专属/源码补丁未入库 |
| S1 素材 | 微信 DB key（chatlog-keeper `--method active`）→ 消息/语音 SILK/视频 → 照片 EXIF（`ingest_media.py`） | key 不可自动；其余脚本 | — | — | 无 | 否：`VIEWPOINT="justin"` 硬编码 4 处 |
| S2 解析 | `parse_wechat.py` → UIF 20923 条；敏感指认 `scrub_sensitive.py`（G4，601 疑似/14 条裁决）；`build_data_bundle.py` | 脚本 | — | — | **G4** 指认 | 半：config 手写 |
| S3 语音 | 参考选段（G1）→ 切段 + ASR（wenet u2++）→ 校对页（G2，117 条 8 页）→ 特征/parquet → 全量 SFT（15 epochs，17.5–21 GB 显存）→ epoch 耳测 + 盲听（G3，10+ 轮）→ tts_server | 切段/ASR/训练脚本在仓外 `~/wu-sft` | **必需** | — | **G1 G2 G3** | 否 |
| S3-alt | GPT-SoVITS 普/粤（`gsv_pipeline.py` + ASR CER 回读 QC） | 脚本 | 6–8 GB | 韵律标注 151k tokens | 3 次耳测 | 半 |
| S4 文字 | 节律 `build_rhythm.py` / 摘要 `extract_persona_digest.py`（确定性）→ **persona.md 起草（Claude 主动，180k tokens/11.5 min，46 判断+9 缺点+证据）**→ 13 问（G5）→ 记忆卡候选 150 → 闸门页（G6）→ 124 条 Tier-1 | 除起草外全确定性 | — | 起草必需 | **G5 G6** | 是（提示层） |
| S5 形象 | ComfyUI 候选（30+20 张）→ 拼图选择 → 表情/口型贴片烘焙 → viseme 时间轴 → avatar 页 | 脚本，但**贴片标定坐标手工、提示词迭代 6 轮跨 3 周** | 必需（≈21 GB 峰值） | — | **G7** | 否：STYLES 写死"妈妈" |
| S6 对话 | chat/companion 构建器；sessions Tier-3 | 脚本 | 运行时 | 运行时 BYOK | — | 是 |
| S7 档案 | `build_archive.py --verify`（sha256 离线核验） | 脚本 | — | — | — | 是 |

**汇总**：LLM API 在 0→1 中真正必需的只有两处（persona 起草；GSV 韵律标注），其余确定性。七道闸门的用户投入（妈妈档 08-04→08-16，指挥官 + 用户全职）：G1 1 轮、G2 8 页约 4 天、G3 约 10+ 轮耳测、G4 1 次、G5 13 问 1 天、G6 150 张 1 夜、G7 6 轮跨 3 周。**各闸门的墙钟分钟数从未记录**——产品化的用户负担估算需要一次计时实测。第二个建档对象从未跑过，person-generic 未经验证。

## 2. 自动化的三条边界

### 2.1 可全自动（GUI 封装即可）
S1b–e 抽取、S2 解析/打包、S3 切段/ASR/特征/训练/合成、S4a/b/e/f、S5a/d/e、S6、S7，以及**全部闸门页面**——校对页/试听页/盲听页/指认列表/问卷/记忆卡闸门/拼图/GIF 审核**已经是自包含 HTML**，App 内嵌只需把"LAN 传手机 → 回帖"换成"直接保存"。这是 b 最便宜的部分：形态 C 的两层分离已经把它铺好了。

### 2.2 闸门（不是障碍，是产品）
用户原话把"语音和卡通形象"列为逃不掉的人工审核，实测还有五道：敏感指认、转写校对、persona 判断确认、记忆卡闸门、参考选段。App 不能压缩人时，只能：① 让页面在 App 内直接保存；② 用自动 QC 先筛（tts-frontier 的 ASR CER 回读、SNR/时长/单说话人过滤）减少送到人眼前的条数；③ 把 G3a epoch 耳测改为"默认末 epoch + 可选对比"。**闸门变少 = 铁律 2 变弱**，这是产品设计的红线，不是优化空间。

### 2.3 判断力工作（现由 Claude 承担，无法写成流程）
- 语音：参考片段挑选、失败归因（route D、pad 截断探针、全量 vs 干净子集 A/B）——妈妈档 8 轮 A/B 才到 e14。
- 文字：persona 起草要"写缺点、写吵架、附 record_id 证据"，再设计 13 个问题让用户裁决。
- 形象：贴片坐标标定、提示词迭代、"自然度"判断、双帧体系判死（架构级发现）。
- 环境：harness 误杀训练、BOM、DDP、Tailscale/管家。
三条出路：**(i) 固化配方 + 失败即止**（默认参数、失败给诊断信息、不承诺修复）；**(ii) BYOK LLM 起草 + 硬校验**（缺点条数下限、每条判断必附证据、Tier 字段必填——把铁律 2 变成 schema 校验）；**(iii) 内置 agent 工作台**（Claude Agent SDK / OpenAI 兼容 agent，以仓库 CLI 为工具集，承担诊断）——这最接近"妈妈档实际是怎么做出来的"，但对陌生人的成本与可靠性未知。

### 2.4 永远不可自动化
- **微信取 key**：铁律 3.4 禁止自写解密；现实是管理员 PowerShell + 登录弹窗扫码 + 显式 data-root（memory wechat-key-extraction），且**工具随微信版本失效**（4.x 加密大改后留痕等需降级；WeChatMsg_2026 称已适配 4.0、依赖 PyWxDump、需管理员）。微信官方备份只能恢复回微信，不能导出文件。→ 产品唯一合规入口是"**用户自带导出文件**"（第三方工具的 JSON/CSV/SQLite/HTML），App 只做解析；这是 0→1 全流程最大的漏斗墙，任何"拖入即用"的宣传都不能覆盖它。
- **她的声音**：SFT 训练 17.5–21 GB 显存、15 epochs、事故前净耗时 15–50 分钟（未单独实测）。GPU 分档是硬事实：≥16 GB 走 SFT；6–8 GB 走 GPT-SoVITS（方言可能掉音色）；无 GPU 只有文字档案。**不提供云端 TTS**（铁律 3.2 精神：声音派生物不出本机）。

## 3. 外部事实

### 3.1 桌面 ML 工具链打包已是解决过的问题
ComfyUI Desktop（推荐安装法，自动装 Python 3.13 + PyTorch CUDA + 依赖）与 Pinokio（一键脚本、Python/PyTorch/CUDA 版本选择、GPU 自动检测、多实例、comfy-cli 监管进程）证明"Electron 壳 + 托管 Python 环境 + 模型下载器"是成熟模式。我们的难点不在壳，在体量与债：5+ venv、≈40 GB 权重、ComfyUI + Rhubarb 外部二进制、仓外训练脚本、PS5.1/BOM/DDP 等 Windows 专属坑、CosyVoice 源码补丁未入库。

### 3.2 数据导入现实
- 微信：无官方文件导出；第三方工具（chatlog-keeper、WeChatMsg 系、PyWxDump）存续与版本适配是常态风险；4.1.x 取 key 需管理员 + 扫码。
- 照片/视频/语音文件：拖入可行（EXIF/UIF/SILK 转码已有）；微博/朋友圈/email 目前**无 parser**（12.3 缺口），一源一 parser 架构已定。
- 结论：产品的"拖入"只对文件型素材成立；聊天记录是"拖入导出件"。

### 3.3 中国监管（产品面向他人时生效；自用档案不发布则义务落在用户）
- 《人工智能生成合成内容标识办法》（2025-09-01 施行，配套强制国标）：显式标识（文字/声音/图形，用户可感知）+ 隐式标识（文件元数据）；平台上架核验。条文级细节（音频的语音/节奏提示位置、用户发布须主动声明、不得删改标识）**实施前对照原文**。
- 《互联网信息服务深度合成管理规定》：人脸/人声编辑须提示使用者取得被编辑者单独同意；被编辑者为逝者，取得有义务保护其肖像权的亲属同意。
- 《民法典》第 994 条：死者姓名、肖像、名誉、隐私受侵害，配偶、子女、父母有权请求承担民事责任（第 1023 条声音参照肖像权保护）；PIPL 第 49 条近亲属可行使权利。
- 《生成式人工智能服务管理暂行办法》适用于"向境内公众提供服务"——**本地 BYOK 桌面软件是否构成服务提供者/技术支持者是灰区**；产品应按就高原则自带显式声明 + 隐式元数据（与 Tier 标签同方向，成本低）。
- 对本项目：用户是子女，属第 994 条主体；对陌生用户，**G0 同意闸门**（活人本人 / 逝者近亲属确认）必须是产品功能。

### 3.4 同类产品与舆论
- StoryFile 2024 年 Chapter 11、重组并承诺"倒闭时家庭仍能拿回全部素材"——**平台依赖风险被市场验证，档案优先/本地优先是对的**。
- HereAfter AI、Eternos、Replika、Afterlife AI 持续运营；国内超级头脑一对一定制、硅基智能"数字永生"。
- 2Wai（2025-11）"和已故母亲的 HoloAvatar 聊天"广告 2200 万次观看，舆论定性"demonic / evil"，Black Mirror 对照——**"复活"叙事本身有毒**；产品文案禁用"复活/永生/再见到她"。
- 学术：O'Connor（*The Grieving Body*）——模拟妨碍与死亡和解；arXiv 2603.01017（26 名中国丧亲者：理想化、真假记忆混淆）——本项目铁律 2 的依据，对陌生用户同样成立。

## 4. "把关的人"：b 的核心问题

CLAUDE.md 铁律 2："用户既是开发者又是唯一用户，没有别人把关——**这三条规则就是把关的人**。"给陌生人用，规则必须变成**不可绕过的功能**。现状对照：

| 约束 | 现状 | 产品化要求 |
|---|---|---|
| Tier-1/2/3 标签、非本人 banner、合成声明 | 已在代码 | 保留，不可关闭 |
| 记忆卡闸门（Tier-3 → Tier-1 须人工） | 已在 | 改为必经步骤，无"全部通过"按钮 |
| persona 缺点/吵架/让人难受处（禁理想化） | 仅提示词 + Claude 自律 | **硬校验**：缺点条数下限、每条判断附 record_id 证据，不满足不能编译 |
| 检索为空说"我记不太清了" | 提示词 | 运行时硬回退（已列 8A-2b 之外的文档项） |
| 关窗道别 / 空闲离场 / 节律限速 / 使用统计自见卡 | 8A-2b 未上 | companion 模块的**发布前置** |
| 同意：活人本人 / 逝者近亲属 | 文档（G0） | 向导第一步，记录到档案元数据 |
| 永不上传 / 本地优先 | 目录规则 | 设计：无云端、无遥测、无账号 |
| 不常驻、不推送 | 研究结论 | 设计：不提供 |
| 显式 + 隐式合成标识 | 显式有、隐式无 | 合成 WAV/MP3 写元数据 |
| 文案禁"复活" | 无 | 产品命名与向导文案 |

**这张表无论 b 做不做，妈妈档自己都需要**——它是 8A-2b 的超集。

## 5. 方案矩阵

| 方案 | 形态 | 自动化覆盖 | GPU | 判断力来源 | 伦理落地 | 工程量 | 结论 |
|---|---|---|---|---|---|---|---|
| **B0 维持形态 C** | Claude Code skill 构建端，技术用户 | 高（对会用 CLI 的人） | 4090 | Claude 会话 | 文档 + 自律 | 0 | 现路线；只服务"自己" |
| **B1 向导式工作台** | Tauri/Electron + uv 托管 Python + 内嵌闸门页 + 任务运行器 + 模型下载器 + GPU 分档 | 确定性步骤全覆盖 | 分档 | 固化配方 + BYOK 起草 + 硬校验 | 功能化（§4 全表） | 大 | **推荐起点** |
| **B2 agent 工作台** | B1 + 内置 agent（以仓库 CLI 为工具）承担诊断 | 同 B1 + 失败处理 | 分档 | agent | 同 B1 | 更大，可靠性未知 | 预留，第二阶段 |
| **B3 云端 SaaS** | 上传素材、云 GPU | 最高 | 无需 | 服务端 | 违铁律 3.2；StoryFile 先例 | — | **NO-GO** |

## 6. 工程量估计（推断，非实测）

以妈妈档为基准：0→1 用了 12 天（全职指挥官 + 用户 + 3 周形象迭代），产品化通常是 5–10×。分期：

- **P0 债清偿**（项目本身也欠，GENERALIZATION 五轴前置）：`VIEWPOINT` 硬编码 4 处、`synth_blind_batch`/`tts_server`/`build_visemes` 机器路径、`gen_avatar` STYLES、`~/wu-sft` 训练/切段/特征脚本入库、CosyVoice 源码补丁入库、`.bat` 手动启动→脚本化；**第二个建档对象端到端跑一遍**（含 G0）；各闸门计时实测。数周。
- **P1 B1 MVP**：拖入（文件型素材 + 导出件）→ 向导（G0 同意、对象/视角/关系配置）→ 任务运行器串现有 CLI → 闸门页内嵌保存 → `build_archive` 编译 + 离线核验。1–2 月。
- **P2 判断力层**：persona 起草 BYOK + 硬校验；自动 QC 前筛；失败即止的诊断信息；8A-2b 落地为 companion 发布前置。1–2 月。
- **P3 打包**：Electron/Tauri 壳、uv 环境、≈40 GB 模型下载器、GPU 检测分档、Windows 安装器。约 1 月。
- 面向公众另计：监管合规、支持、文案、形象素材的授权、发行渠道。

## 7. 与铁律的对照

- **档案优先**：产品"完成"的定义 = archive_dist 通过离线核验（sha256、无网可开）；companion 是护栏齐全后的**可选模块**，不是终点。用户原话"最后产出 companion"要改成"最后产出档案，companion 可选"。
- **沉浸克制**：产品不提供常驻/推送/云同步；分句流水线等沉浸增量在陌生用户侧须以 8A-2b 为前置。
- **数据安全**：raw 只读、本地优先、无遥测；不分发解密工具，只解析导出件。
- **模型分工**：B1 的代码由 DeepSeek 写、Codex 审；Claude 只做规格与编排（本文即规格前身）。

## 8. 建议

1. **GO，定义改为"建档工作台"**（B1，预留 B2），产出 = 档案。
2. **先做 P0**——这是妈妈档 person-generic 承诺的兑现，不做 b 也该做；第二对象端到端是 b 的可行性实验。
3. **受众先定"自己 + 少数人"**；公开发行另开研究（监管条文核对、形象/声音授权、支持负担、"复活"舆论）。
4. **§4 表先于一切 UI**：把关功能不落地，不给任何第二个人用。
5. 微信入口按"自带导出件"设计，文案明示；不承诺"拖入即用"。
6. GPU 分档写进产品说明：无 4090 级显卡不承诺"她的声音"。

## 9. 待用户裁决

- **E1** 目标受众：自己 + 少数人 / 公开产品？（决定监管与发行研究是否立项）
- **E2** 接受"产出 = 档案，companion 为护栏后可选模块"的产品定义？
- **E3** GPU 分档策略（SFT / GPT-SoVITS / 仅文字），且**不提供云端 TTS**？
- **E4** P0 债清偿是否现在立项（与 8A-2b、A1、Phase 13 的排序）？
- **E5** 起点 B1 向导式，B2 agent 留第二阶段？
- **E6** 产品命名与文案禁"复活/永生"？

## 10. 未验证项

- 各闸门用户墙钟分钟数；SFT 无事故净耗时；ASR u2++ 是否必需 GPU。
- 第二个建档对象（含活人 G0）从未实跑；person-generic 未经验证。
- 标识办法条文级要求（音频显式标识位置、用户申报义务）与配套国标编号——实施前对照原文。
- 本地 BYOK 桌面软件在深度合成/生成式 AI 规章下的主体定性——需法律意见。
- BYOK LLM 起草 persona 在无 Claude 把关时的质量；agent 工作台对陌生人的成本。
- 微信第三方导出工具在未来版本/非管理员账户下的可用性。

## 11. 来源

**内部**：`docs/PIPELINE.md`（十、人工闸门总清单；十二、Skill 化蓝图 12.1–12.4；:292-303 缺口表）；`docs/GENERALIZATION.md`；`docs/research/form-factor.md`；`docs/research/tts-frontier-2026.md`（:224 闸门、:268 闸门页=产品、:282 GPU 分档）；`docs/research/ios-app-deployment.md`（a）；`tools/parse_wechat.py:238`、`ingest_media.py:439`、`collect_wechat_video.py:29`、`extract_wechat_voice.py:35`（VIEWPOINT）；`tools/synth_blind_batch.py:9-20`、`tts_server.py:19-25`、`build_visemes.py:22`（路径）；`tools/gen_avatar_candidates.py:19-22`；progress.md :64-67（persona 180k）、:119/:172（校对）、:176-177（训练误杀）、:264/:288/:365（贴片）；memory `wechat-key-extraction`、`long-gpu-jobs-detached`；CLAUDE.md 铁律 1–3。

**外部**：
- 打包先例：ComfyUI 安装法对比 https://www.alexanderharte.com/comfyui-installation-guide/ ；Pinokio ComfyUI 安装器（版本选择/GPU 检测/多实例）https://pinokio.co/posts/01ksbennpxyzbd5hb1x2c3zhxc ；https://beta.pinokio.co/posts/01kybzg9vvs222pggghmv7wm8p
- 数据导入：WeChatMsg_2026（支持 4.0，依赖 PyWxDump，需管理员）https://github.com/AwAcitizen/WeChatMsg_2026 ；4.x 加密大改与降级现实 https://zhuanlan.zhihu.com/p/2056372397859672167
- 监管：四部门发布《标识办法》 https://www.cac.gov.cn/2025-03/14/c_1743654685899683.htm ；9 月 1 日施行报道 https://www.news.cn/legal/20250901/a12108b0b10249e5bae4435269e40c91/c.html ；AI"复活"法律风险（深度合成规定第 14 条、民法典 994）https://www.jiemian.com/article/11006714.html ；https://news.qq.com/rain/a/20250403A017JO00
- 同类与舆论：StoryFile 破产重组与"fail-safe" https://www.cbsnews.com/news/ai-grief-bots-legacy-technology/ ；2Wai 反弹 https://www.forbes.com/sites/conormurray/2025/11/14/disney-channel-stars-ai-app-that-creates-avatars-of-dead-relatives-sparks-backlash/ ；https://decrypt.co/348707/demonic-ai-app-lets-users-talk-dead-loved-ones-faces-backlash ；grief-tech 综述（O'Connor）https://thenodmag.com/content/grief-tech-artificial-intelligence-chatbots ；学术框架 https://www.sciencedirect.com/science/article/pii/S2666659626000028 ；国内案例 https://blog.csdn.net/qq_67508379/article/details/136047888
