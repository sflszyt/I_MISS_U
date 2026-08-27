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
| **代码执行** | DeepSeek V4 Flash | API | 负责实际写代码（实现、修改、生成） |
| **审核验收** | Codex GPT-5.6 | MCP (`mcp__codex__codex`) | 负责代码审核（review）与验收（acceptance） |

1. **Claude 作为主模型**：理解需求、制定计划、编排工作流、分派任务、对最终结果负责。不亲自大批量写业务代码。
2. **DeepSeek V4 Flash 负责写代码**：所有实质性代码编写通过 `/deepseek` skill（`scripts/deepseek.ps1`）交给 DeepSeek。Claude 提供清晰的规格与验收标准。
3. **Codex GPT-5.6 负责审核验收**：DeepSeek 产出必须经 Codex（MCP）审查验收后才算完成。不通过则带反馈回炉 DeepSeek，循环至通过。

### 接入信息（已验证）

- **DeepSeek**：环境变量 `DEEPSEEK_API_KEY`（用户级，勿写进任何项目文件）；端点 `https://api.deepseek.com/chat/completions`（OpenAI 兼容）；模型 `deepseek-v4-flash`（写代码），`deepseek-v4-pro`（备用）。推理模型，`max_tokens` 必须给足（≥8000）。
- **Codex**：MCP 工具 `mcp__codex__codex`。

### 标准工作流

```
需求 → Claude：计划+拆解+编排 → DeepSeek：按规格写代码
     → Codex：审核+验收 → 未通过回炉 DeepSeek，循环至通过 → Claude：汇总交付
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
├── scripts/           # deepseek.ps1 等基础设施
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

**语音选型**（硬件：RTX 4090 24GB，无约束；2026-08-27 刷新）：**现役 = CosyVoice2-Wu 全量 SFT v0.2 e14 双语域**（`<|wuyu|>` 前缀=上海话 / 裸文本=她的沪普）；**普通话/粤语泛化 = GPT-SoVITS v2Pro**（普=沪语本字直喂微调，粤=零样本；`tools/gsv_pipeline.py` + ASR CER 回读 QC）。M1 已关口（用户本人盲听 v2：8 条骗过 7；家人盲听经用户 2026-08-21 裁决移除）。若跨方言掉音色，尊重素材语言——她说什么话就让她说什么话。不需要实时，离线批量生成。选型依据 `docs/research/tts-frontier-2026.md`。

**产品形态（已定：混合形态 C，2026-08-04 用户拍板）**：构建端 = Claude Code skill（素材导入/persona 构建/人工闸门/档案编译，允许死）；消费端 = 自包含静态 HTML 档案（数据层开放格式 + 浏览层静态 HTML + 可选 BYOK 对话页，裸 fetch 调任意 OpenAI 兼容端点，附本地静态服务器启动脚本）。原则："把需要智能的部分放在允许死的构建端，把需要活 20 年的部分做成不需要智能的静态文件。" 依据见 `docs/research/form-factor.md`。

## 里程碑

- **M0** ✅ 素材归集（备份关口经用户豁免 2026-08-05）
- **M1** ✅ 语音验证：v0.2 e14 现役（以用户本人盲听 v2 关口）；泛化线 GPT-SoVITS 普粤管道亦收官
- **M2** ✅ 文字层：persona + 记忆（Tier-1 124 条）+ 交互节律，Tier 分级贯穿
- **M3** ✅ 合流 + 档案化：archive_dist 自包含离线档案已交付（2026-08-16）
- **M4** 数字人层（进行中）：卡通形象（不做真人脸）✅ viseme 时间轴口型+眨眼+微摆（Phase 1，2026-08-27）；可选增强=talking-head 预渲染 MP4"特别版"
