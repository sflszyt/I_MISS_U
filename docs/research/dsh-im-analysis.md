# dsh-im 拆解 + 把 persona 接入各 IM 平台（尤其微信）文字+语音研究（任务 #20）

> 立项：2026-08-29 用户指令"研究 xmanrui/dsh-im，作为桌面陪伴外的第二个副产品，把'调教好的'虚拟人物接入各平台（尤其微信）文字+语音聊天，卡通形象不需要"。
> 方法：workflow 11 代理（4 维并行 + 7 条载重论断对抗校核，含全源码逐文件读 + 联网核 iLink/封号/伦理先例）。克隆快照 scratchpad/dsh-im。
> 关联并更新：docs/research/messaging-channels.md（TG/WA/微信通道，个人号协议伪造已否决）、docs/research/wechat-ui-automation.md 第六节（任务 #16 微信 4.1.12.26 UIA NO-GO）、docs/research/desktop-companion.md（伦理三档）、GENERALIZATION.md（轴五 sessions）。

---

## 〇、两句话结论

**技术上有真进展也有真缺口**：dsh-im 是"连接层不是大脑"，它的微信走的是腾讯 **2026 官方 iLink/ClawBot 个人号 Bot 协议**——这是与我们已否决的 hook 灰产、以及任务 #16 UIA 都正交的**第三条微信路径，实质更新了我们之前"微信封死"的技术结论**。但它**不发原生语音条**（她的真声只能当文件发），接我们的 persona 也**不是即插即用**（要写一个冒充 DeepSeek Harness 的本机 shim）。

**而真正的决策是伦理的，不是技术的**：把"妈妈"放进**家人**的微信聊天列表 = 新增第三方受众（家人）+ 沉浸度最大 + 欺骗风险最高的配置——比桌面陪伴（只有你自己、无第三方）更进一步，**默认 NO-GO**；**自用**（绑你自己的号、仅自己模式，顺带落地轴五 sessions 采集）= 低风险可做。

---

## 一、dsh-im 是什么（校核 confirmed）

- **不是独立程序，是 DeepSeek Harness（dsh，deepseek-ai/deepseek-harness）的 Cordis 插件**。dsh 是 DeepSeek 官方开源的编码 agent 运行时（类比 Claude Code，含 session/workspace/工具调用/审批/模型路由/web UI）。dsh-im 把 9 个 IM 平台的消息经 RPC（`session.prompt` + 轮询 `session.history` 事件流）喂给 dsh，取回复。
- **它本身不做 LLM 推理**——纯连接层。渠道适配器与"大脑"之间有清晰接缝（每渠道注入 `HarnessClient` + 可配 `harnessBaseUrl`），所以大脑"可换"，但接缝是 Harness 的整套 RPC 契约（host/workspace/session/事件日志/WS mux），**不是简单的 chat completion 接口**。
- **各渠道接入手段**：官方 SDK（企微 `@wecom/aibot-node-sdk`、QQ 官方 bot、钉钉 stream、飞书）+ 平台 Bot API（Slack/TG/Discord）+ WhatsApp 走 Baileys（**非官方**设备关联）+ **微信个人号走 iLink 官方协议**。
- **许可 MIT**，微信适配器（weixin-api.mjs）近乎自包含可单独摘取。

## 二、微信 iLink：第三条路径（这是本研究最重要的新事实）

**校核 confirmed（多源实锤）**：dsh-im 的微信代码直连 `ilinkai.weixin.qq.com`（协议 2.4.6、扫码 `get_bot_qrcode`、35s 长轮询 `getupdates`、`sendmessage`、`context_token`）。iLink/ClawBot 是**腾讯 2026 年官方**为个人号首次开放的 Bot 协议（GitHub Tencent 组织 verified、npm `@tencent-weixin` 官方签名发布、官方《微信 ClawBot 使用条款》深圳南山）。

**它同时绕开了我们两条微信死路的死因**：
- 与任务 #16 UIA 正交：iLink 是服务端 HTTP/JSON，**完全不碰 Windows 客户端**——4.1.12.26 关掉的 Qt 无障碍桥接与它无关。
- 与 hook/iPad 灰产正交：是腾讯**自家官方端点**、有专项条款，非伪造注入。

**能力天然契合两条铁律**：reply-only + `context_token` 约 24h 过期 = **平台在协议层强制了"永不主动"**（比 TG/WA 更彻底）；它本就是"bot"实体、家人须扫码知情添加 = 天然落实"非本人标识 + 知情同意"。

### 但——校核 refuted 了"官方=可给家人用、值得升级为主选"（关键去魅）

对抗校核（引用我们任务 #16 已采信的 yage.ai 等）驳回了强论断，三处：
1. **它是"机主对自己 Agent 的控制回路"设计**——官方用例是账号主人扫码把**自己的**号变 bot 来控制自己的 agent，须"用户先发消息触发"。**家人作为第三方入站与一个 bot 聊天，这个拓扑无据**。
2. **dsh-im 是脱离官方 OpenColaw 客户端的直连**——属未授权独立客户端，"官方合规"打折扣。
3. **腾讯保留单方随时限流/拦截/终止权**，且明确"保留裁定你可接入哪些第三方 AI"——把 iLink 指向我们本地 persona 引擎**是否被允许存疑**；这是新的"二次丧失"向量（平台依赖，同桌面陪伴报告里 Grok/Replika 的教训）。

**"能不能绑定"其实很好查**（校核 refuted 了"须弃号探针"的说法）：这是个人号功能，微信 **设置 > 插件 > ClawBot** 扫码绑定，是**秒级 in-app 检查**——你自己打开微信看一眼有没有这个入口就知道你的号在不在灰度里，不用像 #16 那样备弃号。

**企业微信 aibot（另一条看似合规的路）= 对家人 NO-GO**（confirmed）：官方限死只能企业内部成员/内部群，外部及个人微信用户被平台直接拦截。承载不了"和家人的个人微信聊天"。

## 三、语音：dsh-im 不发原生语音条（校核 confirmed，逐文件核实）

- **入站友好**：iLink 把家人发的语音**已转成文本**（`voice_item.text`），我们不用做 ASR 就能拿到文本。
- **出站是缺口**：telegram/whatsapp 出站方法里**没有 sendVoice/audio**，wecom 只处理入站语音；全仓无出站语音路径。她的 CosyVoice 真声（:8022 出 MP3）**只能作为文件附件发**，显示为文件、**不是微信语音条气泡**——"她的声音"体验从"肌肉记忆级语音条"降级为"点开一个音频文件"。
- **要发原生语音条 = 自建工作量**，逐平台转码：TG/WA=ogg/opus、微信/QQ=SILK、企微=AMR。我们已有 pilk（SILK，silk_decode.py 用过，同库支持 encode）；**ffmpeg 便携版在盘状态待复核**（任务 #18 曾记 imageio-ffmpeg 在盘，本次代理未在 PATH 找到，动工前核）。

## 四、接入设计：把 mama 人格接进去要多少工（校核 unclear→方向成立但工作量被低估）

- **正确姿势**：persona/Tier 纪律/TTS/写回闸门**全留本机 Python 侧**，dsh-im 只当连接层。两条接法：
  - **shim（推荐）**：写一个本机 HTTP+WS 服务**冒充 DeepSeek Harness Host**，dsh-im 一行不改。但校核指出这**不是"一个 /reply 端点"那么轻**——要仿真 host.describe / workspace / session.create/prompt/history/cancel + 带 seq 的事件日志（turn/start → user/message 回显 promptRpcId → assistant/message → turn/end）+ WS mux 常开。工作量中等、边界清楚。
  - **摘适配器（最本地）**：只把 iLink 微信客户端（weixin-api.mjs，MIT，含登录状态机/AES 加解密/CDN 上传/context_token 分段这些踩过坑的成熟实现）摘进我们自有的 Python/Node 通道网关，不背整套 dsh 运行时（dsh 是重运行时，与"消费端 20 年免智能静态文件"取向冲突）。
- **禁用 dsh 方案 A（agentPreset 塞 persona）**：那会让大脑仍是 DeepSeek 云端 LLM 靠系统提示 roleplay——**无档案检索、无 Tier 分级会编造事实（违铁律②）+ persona/记忆流向云 API（违铁律③）**。只能当玩具级验证，档案不可接受。
- **dsh-im 的 AI Office 云中继必须禁用**（主动外连公网，违数据不出机），`harnessBaseUrl` 锁 127.0.0.1，审其出网。

**数据不出机核对**：任何"进真微信"方案，家人消息与回复本就全程过腾讯服务器——这与铁律③要防的"people/ 原始档案上传"是两回事。只要 persona/检索/TTS 在本地跑，离开本机的只是**当轮对话文本**（等同任何微信聊天）；她的 raw 素材永不上传。但须写入知情同意告知。

## 五、战略与伦理：这才是真正的裁决轴

**副产品定位质变**：桌面陪伴（任务 #18）里用户=开发者=唯一受众、自我同意即可。"接入 IM 与家人聊天"**新增受众=家人**——griefbot 伦理里的"哀悼者/继承人"，学界共识要求**数据供体/继承人/哀悼者三方知情同意**，且须"有意义地透明、明确标注为模拟、限成人不面向儿童"。

**最贴近的先例（反面直接对照）**：2025 中国 AI 复活服务泛滥期，一典型案例是用户要求"把去世母亲的微信聊天记录做成数字分身"，团队**以伦理底线拒绝**——这与本项目（妈妈+上海话+微信语料）几乎逐字同构。另有"每日与 AI 母亲对话 6 小时、拒绝社交"的过度沉浸案例，直接印证铁律①。

**关键判断**：把"妈妈"放进家人自己的微信聊天列表 = **持续在场 + 高拟真 + 可能未被清楚标注为模拟**，正撞 desktop-companion.md 已确立的三条边界（deadbot 应是 transitory use、反对 active presence、须标注模拟）。**它不新增任何档案内容，纯粹降低访问摩擦、扩大沉浸**——按铁律③"档案更完整还是只让对话更沉浸"，这是纯后者。故其默认答案应**至少和桌面陪伴一样保守，甚至更保守**。

## 六、go/no-go 裁决（分层）

| 形态 | 裁决 | 理由 |
|---|---|---|
| **自用**：iLink 或 TG 绑**你自己**的号、仅自己模式，当桌面陪伴"打开才在"的又一皮肤 + 顺带落地轴五 sessions 采集 | **有条件 GO（低风险）** | 无第三方、无新伦理面；网关=sessions 采集点，是真档案收益（对话正在白白流失） |
| **家人向**：把"妈妈"放进家人的微信聊天列表 | **默认 NO-GO** | 第三方受众、沉浸/欺骗最大化、比桌面陪伴更进一步；先例与学界共识都指向"先不做" |
| 家人向 + 全员知情同意闸门后 | **仅可重新评估，且仍劝阻常驻聊天列表形态** | 即便每位家人 opt-in、被告知 Tier-3 模拟、可随时拒绝、不面向儿童——"常驻可达"仍把唯一要克制的指标开到最大 |

**平台优先级（若做自用/验证）**：Telegram（官方 API、无封号、**原生语音条**、转码最顺）工程最干净，但国内家人不用；iLink 是唯一"家人可达 + 可能官方"，但伦理最险且开通/语音/本地大脑三处不确定；企业微信对家人 NO-GO；灰产 pad/web 仍否决。

## 七、若用户裁决推进，两个先验硬点（30 分钟级，用户可自查）

1. **你的号在不在 ClawBot 灰度里**：打开微信 **设置 > 插件**，看有没有 **ClawBot / 智能助手** 入口——秒级自查，有=iLink 路径对你活，没有=待腾讯放量。**这不用备弃号**（只是查你自己号有没有这个官方功能）。
2. **iLink 能不能发原生语音条**：协议层疑似支持（收发都走 CDN），但 dsh-im 未实现出站语音、官方文档发送能力未明列语音——**动工前须活体验证**，否则"她的真声"只能当文件送达，产品预期要下调。

## 八、可复用资产盘点（无论是否做家人向）

- **iLink 微信适配器**（weixin-api.mjs，MIT）：官方协议的成熟实现（登录状态机/AES 图文件加解密/CDN 上传重试/context_token/分段）——比我们从零照规范自建省一大截，且不背 dsh 运行时。
- **官方多平台 SDK 连接层**：messaging-channels.md 说要数周的那层，dsh-im 用官方 SDK 做完了（企微/QQ/钉钉/飞书）。
- **入站语音已转写**：家人发语音→我们直接拿文本，省 ASR。

## 附：结论确定性与溯源

11 代理 96 万 tokens，7 校核（6 confirmed/1 refuted/1 unclear，refuted 与 unclear 都已在正文吸收）。**最重要的更新**：iLink 是腾讯官方产品，实质更新 messaging-channels.md 与 wechat-ui-automation.md 的"微信封死"技术结论——但**技术门开一条缝 ≠ 家人向可做**，决策落回伦理面。iLink"官方"定性证据较强但部分源为开发者博客，动工前活体核验。全文溯源见 workflow journal（wf_26efff09-b58）+ scratchpad/dsh_digest.md。
