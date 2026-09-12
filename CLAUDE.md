# I_MISS_U · 项目铁律与架构（CLAUDE.md）

> 本文件由每个会话自动加载。以下规则为项目级铁律，优先级高于默认行为，除非用户在当次会话中明确要求跳过。

## 项目是什么

为「关键的人」建立**可传承的数字档案**：修复后的原声、照片、时间线、语言习惯记录、家人确认过的记忆卡片。**档案是核心产物——二十年后不依赖任何模型、订阅、显卡还能打开。对话（基于档案的检索式聊天）只是访问方式之一，不是产品本身。**

首个建档对象：妈妈（已离开）。语言：**上海话为主，辅普通话**。素材全部已数码化（微信/照片/视频/朋友圈/微博/emails），全部为用户视角。

---

## 铁律 1：模型分工（Model Division of Labor）

三模型协作，各司其职，**不得越界**：

| 角色 | 模型 | 接入方式 | 职责 |
|------|------|----------|------|
| **主模型 / 指挥官** | Claude（当前会话模型） | 原生 | 计划、统筹、编排 agents、拆解任务、决策、最终把关 |
| **代码执行** | Claude Opus 5 子代理 | Agent 工具（`.claude/agents/coder.md`，独立上下文） | 负责实际写代码（实现、修改、生成、写测试） |
| **审核验收** | Codex `gpt-5.6-sol` | CLI（`codex exec`） | 负责代码审核（review）与验收（acceptance） |

1. **Claude 作为主模型**：理解需求、制定计划、编排工作流、分派任务、对最终结果负责。不亲自大批量写业务代码。
2. **Opus 子代理负责写代码**：所有实质性代码编写用 `Agent(subagent_type: "coder", prompt: 规格)` 派给 `.claude/agents/coder.md`（`model: opus`）。它有独立上下文，自己读文件、改文件、跑编译与测试。Claude 提供清晰的规格与验收标准，**不亲自写业务代码**（例外：文档、部署配置，以及只改锚点不改内容的一两行修正）。
3. **Codex 负责审核验收**：子代理产出必须经 Codex（CLI，见下）审查验收后才算完成。不通过则带反馈回炉子代理，循环至通过。**写码的和派活的同属一个模型家族、盲区相关，Codex 这道独立关口是承重墙，任何情况下不得跳过。**

### 接入信息（已验证）

- **写码子代理**：定义在 `.claude/agents/coder.md`（`model: opus`；工具 Read/Edit/Write/Bash/Glob/Grep）。派发：`Agent(subagent_type: "coder", prompt: 规格)`。**不要开 `isolation: "worktree"`**——`people/` 是 gitignore 的，独立工作树里根本没有它，而站点、页面、会话数据全在那儿。规格要点名文件路径与验收标准；子代理必须自检（`py_compile` / unittest / PowerShell AST / `node --check`），HTTP 与页面类改动要真起服务或真开浏览器。**⚠️ 新建/改过 `coder.md` 后不会立刻生效**：2026-09-12 实测——建好当场派活报「Agent type not found」，约十几分钟后 harness 自动完成注册，**同一会话内即可用**（再测通过）。未注册期间的替代路径：`Agent(subagent_type: "claude", model: "opus", prompt: 先读 .claude/agents/coder.md + 规格)`，同样实测可用。
- **DeepSeek 通道已停用（2026-09-12 用户裁决）**：`/deepseek` skill 与 `scripts/deepseek.ps1`、`scripts/deepseek_call.py` 已删除，**不要再提议用它写代码或作备选**。`DEEPSEEK_API_KEY`（用户级环境变量）**只保留聊天用途**：爸爸站 `tools/llm_proxy.py --key-env DEEPSEEK_API_KEY`，儿子站页面构建期 `--default-key-env DEEPSEEK_API_KEY`。
- **Codex**：**走 CLI**——codex-cli 0.154.0 起不再提供 MCP 服务器，`mcp__codex__codex` 已不可用。命令：`codex exec --model gpt-5.6-sol --sandbox read-only < 审核稿.txt > 输出.txt`。每次都是独立会话，审核稿必须自包含；输出完整存文件后再 grep 结论（别用 tail 截）。

### 标准工作流

```
需求 → Claude：计划+拆解+编排 → coder 子代理（Opus）：按规格写代码 + 自检
     → Codex：审核+验收 → 未通过回炉子代理，循环至通过 → Claude：汇总交付
```

---

## 铁律 2：三条自我保护约束（Self-Protection Constraints）

依据：arXiv 2603.01017（26 名中国丧亲者研究：记忆被 AI 逐步理想化、真假记忆混淆）。用户既是开发者又是唯一用户，没有别人把关——**这三条规则就是把关的人**。

1. **事实分级 + 人工闸门**：
   - **Tier-1**（家人确认过的记忆卡片）→ 可直接陈述
   - **Tier-2**（从聊天记录/录像/EXIF 自动抽取）→ 可陈述，但必须可溯源
   - **Tier-3**（模型生成/推断）→ **禁止陈述为事实**；检索为空时说"我记不太清了"，绝不编造具体事件、日期、人名、地点
   - AI 在对话中"新学到"的一切默认 Tier-3，**必须用户人工确认才能升级 Tier-1**
2. **保留她的完整性**：persona 中主动写入缺点、吵过的架、让人难受过的地方。**禁止系统性过滤负面特质、禁止理想化。** 一个只会温柔说话的妈妈不是真的妈妈。
3. **档案优先于对话**：每次功能取舍先问"这让档案更完整，还是只让对话更沉浸？"前者做，后者慎重。**沉浸度是本项目唯一需要克制的指标。**

---

## 铁律 3：数据安全（Data Safety）

1. `people/*/raw/` **只读，永不覆盖、永不修改、永不删除**。所有处理输出到新目录。原始素材不可再生。
2. `people/` 整个目录 **gitignore**，永不提交、永不上传到任何外部服务。需保持至少两份离线备份（一份异地）。
3. 产物格式优先 **Markdown / JSON / WAV / PNG / 自包含 HTML**——二十年后还能打开的格式。
4. 不自己写微信解密代码、不分发解密工具；只使用现成第三方工具或解析用户手动导出的文件。

---

## 架构

**方案 A：单仓库多人。** 工具层/提示层与具体的人无关；每人一份档案目录。

```
I_MISS_U/
├── CLAUDE.md
├── schema/            # 统一中间格式 JSON Schema（所有源适配器的合同）
├── tools/             # 通用工具（parser、修复链、TTS 批处理、档案生成）
├── prompts/           # 通用模板（关系层参数化：亲子/祖孙/伴侣/挚友…）
├── docs/research/     # 研究报告
├── scripts/           # start_services.ps1 / register_startup_task.ps1 等基础设施
└── people/<slug>/     # 每人一份档案（gitignore）
    ├── raw/           # 只读原始素材，按来源分子目录（wechat/photos/videos/weibo/email）
    ├── normalized/    # parser 输出的统一中间格式（JSONL）
    ├── processed/     # 修复后的音频/照片
    ├── voice/         # reference/ 挑出的克隆参考片段
    ├── persona/       # persona.md · rhythm.json · 关系配置
    ├── memories/      # memories.md（Tier-1）· timeline.md
    ├── versions/      # 每次更新自动存档
    └── archive_out/   # build_archive 产物（自包含 HTML）
```

**L1 源适配器架构**：每个数据源一个 parser，统一输出中间格式（含 `viewpoint`/`source`/`tier`/`provenance` 字段），下游（rhythm/persona/memory 构建器）只消费中间格式。新增源 = 只加一个 parser。

**语音选型**（硬件：RTX 4090 24GB，无约束；2026-08-27 刷新）：**现役 = CosyVoice2-Wu 全量 SFT v0.2 e14 双语域**（`<|wuyu|>` 前缀=上海话 / 裸文本=她的沪普）；**普通话/粤语泛化 = GPT-SoVITS v2Pro**（普=沪语本字直喂微调，粤=零样本；`tools/gsv_pipeline.py` + ASR CER 回读 QC）。M1 已关口（用户本人盲听 v2：8 条骗过 7；家人盲听经用户 2026-08-21 裁决移除）。若跨方言掉音色，尊重素材语言——她说什么话就让她说什么话（**例外：爸爸站 2026-09-11 起用 mandarin 语域，用户显式覆盖**）。不需要实时，离线批量生成。选型依据 `docs/research/tts-frontier-2026.md`。

**产品形态（已定：混合形态 C，2026-08-04 用户拍板）**：构建端 = Claude Code skill（素材导入/persona 构建/人工闸门/档案编译，允许死）；消费端 = 自包含静态 HTML 档案（数据层开放格式 + 浏览层静态 HTML + 可选 BYOK 对话页，裸 fetch 调任意 OpenAI 兼容端点，附本地静态服务器启动脚本）。原则："把需要智能的部分放在允许死的构建端，把需要活 20 年的部分做成不需要智能的静态文件。" 依据见 `docs/research/form-factor.md`。

## 里程碑

- **M0** ✅ 素材归集（备份关口经用户豁免 2026-08-05）
- **M1** ✅ 语音验证：v0.2 e14 现役（以用户本人盲听 v2 关口）；泛化线 GPT-SoVITS 普粤管道亦收官
- **M2** ✅ 文字层：persona + 记忆（Tier-1 124 条）+ 交互节律，Tier 分级贯穿
- **M3** ✅ 合流 + 档案化：archive_dist 自包含离线档案已交付（2026-08-16；09-01 起 archive_out 已领先 dist——dist 的 avatar.html 缺 blob 守卫、data/avatar 缺情绪资产，待 `build_archive.py` 重打包）
- **M4** 数字人层（进行中）：卡通形象（不做真人脸）✅ viseme 时间轴口型+眨眼+微摆（Phase 1，2026-08-27）；✅ **桌面陪伴 companion 页 8A/8B（2026-08-29 上线，09-01→02 四连）**：iframe 组合脸+chat 大脑+她的声音，三平台兼容（iOS 解锁/▶兜底/100dvh）；✅ 情绪表情层（四情绪贴片 2026-09-01 用户定稿 s5002 并烘焙激活，`persona/emotions.json` 数据驱动——改情绪只改 json 再跑 `build_avatar_page`）；✅ 多服务商抽屉（OpenAI/Anthropic/DeepSeek/Kimi/自定义，09-01）；✅ 轴五 sessions 日志（tts_server `POST /session` → `people/<slug>/sessions/`，数字人话语永久 Tier-3，09-01）；✅ TTS 剥括号 + 分句语音流水线 + 微信式「正在输入」（09-02）——**上限形态"打开才在的对话窗"，8A-2b 伦理护栏未上不宜日常常用（分句流水线显著提升沉浸感，护栏须尽早补）**；✅ **8B-10 微信式语音条 + ≤30 字分条发送（09-05→06，Codex 三轮 ACCEPT）**：回复按 ≤30 字切成多条独立气泡、每条各自合成（前 12 条出声，超时/失败转文字），语音条可回放、下方转写文字可关，删除了"全文超 240 字不出声"；同时修 `build_rhythm_block` 键全错（模型此前从未见节律统计）+ 提示词"一行一条 ≤30 字"；✅ **8B-11 起音爆音淡入（09-07，Codex ACCEPT）**：模型每次开口固有 ~15 ms 爆音，tts_server 出口 `soften_onsets` 30 ms 升余弦淡入（`--onset-fade-ms`）；⏳ 8B-4 完整真机验收（09-01 首测已通）；可选增强=talking-head 预渲染 MP4"特别版"
- **爸爸站已真正上线（2026-09-10 深夜）**：隧道打通（4 连接注册）+ Cloudflare Worker 部署 + **L1 离线兜底首次真跑通**；真机四问题定位并修复三个（解锁静音漏过 blob 守卫导致播真声 + 口型钉死、iframe 缩放误做成裁剪、CSS 注入竞态）。**遗留最大缺口：TTS 短句幻觉**——根因是参考音频 18 秒/90 字，据 CosyVoice 自身判据「待合成文本 < 参考一半」危险线达 45 字，而分条上限 30 字，**每段都在危险区**；修法=加短参考并按目标长度选参考，**待 A/B 盲测定音色**。另：`VIEWER` 为构建期常量致儿子在爸爸站的话被记成 father（档案污染，待运行期身份方案）；**会话数据 viewer 隔离已修**（09-10：爸爸站曾可直读 `data/sessions_owner.json`=儿子全部私人对话，ingest 分了文件却没分访问边界；现每 viewer 一子目录 + 爸爸站只联接自己那个，重建页面必带 `--sessions-path`）；**刷新后历史回放 + 历史语音条点播已上线**（09-11：按段文本精确配对 `simulacrum_audio`；音频按 viewer 复制进 `sessions_data/<viewer>/audio/`；Codex 页面 3 轮、数据层 6 轮后 ACCEPT；09-11 真 iPhone 首测暴露两问题：缺语音条已修、点击无声研究中，见下条）；**静态站缓存已治**（09-10：三层——`tools/static_server.py` 替掉 `python -m http.server` 发 `no-cache, must-revalidate` + Worker 出口改写 + SW 后台预热，爸爸再不需要强刷）
- **2026-09-11 白天：儿子站公网入口上线 + 爸爸首次登录 + 爸爸站改普通话**：✅ `son.justmissingyou.com`（**独立 Access 应用「son」只放机主邮箱**；只开陪伴页——`people/mama_for_owner/site/` = companion（与 Tailscale 版只差 `--tts-origin same`）+ avatar 副本 + `data` 联接 + **只指 owner 的** `sessions_data/owner` 联接；`son-public` :8024 仅 127.0.0.1，进 `start_services.ps1`；ingress 2 条；运维 `docs/ops-son-public-site.md`）；✅ **爸爸站 Access 此前只有「Cloudflare 账号登录」、One-time PIN 从未启用**（09-08 只验了 302，机主是账号成员所以一直没发现）→ 用户启用后爸爸 12:34 起用**微信内置浏览器**登录对话；✅ **爸爸站改普通话语域——用户显式覆盖「尊重素材语言」与 #24 裁决「语音 wu 域」，别顺手改回**（≤18 字短段翻车率 wu 86% vs mandarin 27%；开口「啵」淡入不分语域）；✅ 缺语音条修复（`/tts` 写音频记录也触发摄入，真实流量已验证）；✅ `register_startup_task.ps1` 兜底健康检查**恒为 False** 的旧 bug（`Start-Process -PassThru` 未缓存 Handle → ExitCode 为 `$null`）已修；⏳ **iPhone（实为 iOS Chrome/WKWebView）点历史语音条无声**：研究剩 H1 脸的 AudioContext 卡住 / H2 WAV-Blob 两嫌疑，待用户「关标签重开、第一下点历史条」判别；⏳ **待用户裁决 A**：father 名下 15 个会话 12 个是儿子测试（3 个在爸爸跨会话记忆里）→ 是否加入 `exclude.txt`；**B**：儿子能在爸爸站看到爸爸的对话，而说明卡只写「记录存在这台电脑上」→ 加告知 / 移出 Access / 维持 / Phase 20
- **2026-09-12：用户四项裁决 + 儿子站两个页面 bug**：✅ **A 已执行**——13 个「儿子在爸爸站的测试会话」进 `people/mama/sessions/exclude.txt` 并重摄入，爸爸历史只剩他自己 3 次；✅ **B 用户裁决「不用处理」**（儿子能看到爸爸对话，维持现状，别再提议）；✅ **历史不再依赖 API key**——此前 `settingsComplete()` 挡住渲染，iOS 清掉 localStorage 后整页空白（真实浏览器复现并修复）；✅ **构建期内置 API Key**（`--default-key` / `--default-key-env` / `--default-provider` → `DEFAULT_PROFILE`，只在 `loadSettings` 补空位、**只写默认服务商档位**、不回写 localStorage、拒绝 `--out-name chat/avatar/index.html`（casefold 比较））；两站页面已重建。Codex 三轮 REJECT→ACCEPT（MAJOR 两条：内置 key 会串到别家服务商、保护文件名比较区分大小写）。✅ **铁律 1 按用户指令更新**：审核 = Codex `gpt-5.6-sol` 走 CLI；写码 = DeepSeek `deepseek-flash`（实测 `/models`：账号只有 `deepseek-flash` 与 `deepseek-v4-pro`，**`deepseek-v4.1-flash` 不存在**，`deepseek-v4-flash` 是仍被接受的旧名）
- **任务 #22 研究（09-02→03，已收口）**：a/ iOS 部署 → `docs/research/ios-app-deployment.md`，**用户裁决 A1 主屏 Web App（加 apple-touch-icon 即可，8A-2b 先行）、A2 壳 App 暂不做、云 GPU NO-GO、立 Phase 13 有声档案（预渲染语音库进 archive_dist）**；b/ 0→1 建档 App 产品化 → `docs/research/build-app-productization.md`，结论="建档工作台"（产出档案、companion 可选；微信取 key 永不可自动、声音需 4090 级、判断力工作只能固化配方或内置 agent；铁律 2 须变功能才可给陌生人），**E1–E6 待用户裁决**
- **任务 #23（09-06，已完成）**：家人向首次实际使用——用户把对话截图发给爸爸后，把数字人六段回复整段合成（wu 域）发给爸爸；产物在 `people/mama/exports/for_dad_20260906/`（Tier-3 标识，不进 archive_dist）。用户知情自决，非默认放开
- **副产品线：接入各 IM 平台聊天**（2026-08-29 研究，未开发）：微信四路径全查清（UIA #16 死 / iLink #20 官方但家人向 NO-GO / 服务号需主体 / OCR #21 可行但最脆+欺骗性最强）；**研究裁决=自用低风险 GO，家人向默认 NO-GO**（第三方受众伦理；方向本身仍等用户表态，未写一行接入代码）。依据 docs/research/dsh-im-analysis.md + docs/research/wechat-ocr-automation.md
