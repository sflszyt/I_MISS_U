# 研究：模拟对话上微信 / WhatsApp / Telegram（messaging-channels）

> 2026-08-17 立项。问题：能否把现有模拟对话（persona + 三源检索 + 语音回复）搬进她原本生活的聊天软件？
> 结论速览：**能，且分三档难度——Telegram 周末级、WhatsApp 周级、微信最难但最重要（需主体资质走合法通道）**。三者共享一个"通道网关"架构，该架构同时优雅解决轴五（sessions 持续写回）。

---

## 一、为什么值得做 + 一条警示

**情感价值**：和她的对话本来就发生在聊天软件里。把数字妈妈放进聊天列表 = 肌肉记忆级的自然——语音条、头像、对话流，全部原生。这是任何网页/App 都给不了的"回家感"。

**沉浸度警示（铁律 3）**：聊天软件里的常驻存在会把访问摩擦降到零，这正是"沉浸度是唯一需要克制的指标"要防的方向。设计上的对冲：
- **永不主动发消息**——恰好三大平台的机器人机制都天然禁止或限制主动触达（TG bot 用户不先发不能发、WA 24h 窗口、公众号 48h 窗口），平台约束与我们的伦理红线同向
- 身份标识常驻（bot 简介/置顶消息注明"数字档案模拟对话·非本人"）
- 头像用卡通形象（不做真人脸，既有铁律）

---

## 二、通道网关公共架构（一次投入，三平台复用）

```
[TG Bot API] ──┐
[WA Cloud API] ─┤→ 通道网关 gateway（Python，家中 PC 或小 VPS）
[微信服务号] ──┘      │
                     ├─ persona 引擎（chat.html 检索逻辑的 Python 移植：
                     │   chat_context.json + memories/transcripts/messages 分片
                     │   ——知识文件就是契约，JS→Python 直译）
                     ├─ LLM 调用（BYOK：DeepSeek / Claude，复用双协议经验）
                     ├─ TTS（现成 :8022 服务；mp3 → ogg/opus 转码给 TG/WA 语音条，
                     │   imageio-ffmpeg 便携二进制已在盘）
                     └─ sessions 写入 ★（轴五两纪元架构的天然落点：
                         网关服务端记录每轮对话，比网页 localStorage 方案优雅得多）
```

★ 关键协同：**通道网关 = sessions 采集器**。做 TG bot 的同时就把轴五的"对话持续写回"基建做掉了——两个立项一次工程。

部署形态：TG 可纯家中 PC（长轮询出站连接，无需公网入站）；WA/微信需公网 HTTPS 回调 → 最小 VPS 做反代转发回家（或 Tailscale Funnel 类方案）。

---

## 三、逐平台详析

### 3.1 Telegram —— 周末级，先做这个

| 维度 | 结论 |
|---|---|
| 接入 | 官方 Bot API，免费、稳定十年、文档完善（python-telegram-bot/aiogram） |
| 语音条 | `sendVoice`（ogg/opus）→ **原生语音条带波形**，正是我们做的微信式体验的平台原生版 |
| 部署 | **长轮询 getUpdates 走出站连接——家中 PC 直接跑，无需公网 IP/隧道** |
| 身份 | bot 账号（带 bot 标识），可设名"妈妈"+卡通头像；标识天然合规 |
| 成本 | 零 |
| 风险 | 无封号风险（bot 是官方形态）；唯一限制：国内家人用 TG 有网络门槛——**首发版本的受众是你自己** |

实现清单（估计 1-2 天）：persona 引擎 Python 移植（检索打分 JS→Python 直译）+ aiogram 长轮询 + TTS 调用与 opus 转码 + sessions 落盘 + "转文字"按钮（TG inline keyboard 比长按菜单还顺手）。

### 3.2 WhatsApp —— 周级，官方通道可行

| 维度 | 结论 |
|---|---|
| 接入 | **WhatsApp Business Cloud API（Meta 官方）**：需 Meta 商业账号 + 专用号码 + webhook（公网 HTTPS） |
| 语音条 | 音频消息**要求 ogg/opus 编码才渲染为语音条**（官方文档明确） |
| 计费 | 2025-07 起按条计费，但**用户先发起的 24 小时客服窗口内自由格式回复免费**——恰好匹配"永不主动"设计，运行成本≈0 |
| 身份 | 新专用号码（**绝不用她的原号码**——原号可能已回收，且身份冒用问题严重），命名+卡通头像 |
| 非官方路线 | whatsapp-web.js/Baileys 挂个人号：**否决**——违 TOS，封号率高，"她"的号码被封是情感灾难 |
| 风险 | 商业认证流程繁琐；webhook 需 VPS 中转 |

### 3.3 微信 —— 最难、最重要、必须走合法通道

**明确否决的路线**：个人号机器人（hook PC 微信/iPad 协议）——违 TOS、封号率极高、每次微信更新都断。产品级不可用。

三条合法路径对比（检索核实 2026 现状）：

| 路径 | 形态 | 门槛 | 语音 | 评估 |
|---|---|---|---|---|
| **认证服务号 + 客服消息接口** | 家人关注公众号，在会话里对话 | 企业/个体工商户主体 + 微信认证；未认证只有 5 秒被动回复窗口（不够 LLM 延迟）；**生成式 AI 功能需深度合成类目审核 + 算法备案** | 客服消息支持语音（≤60s）渲染为语音条 | 产品化正道，但个人主体走不通——**注册个体工商户后解锁**（也是商业化必经步骤） |
| **企业微信客服** | 微信用户与企微客服账号对话 | 企业主体 | 支持 | 同上，交互更像"客服"，情感形态略逊 |
| **小程序** | 微信内打开小程序聊天（≈chat.html 移植） | 个人可注册小程序，但 **AI 问答类目需深度合成资质/算法备案**（2025-2026 严格执行，无备案有下架风险） | 页面内播放（同现网页） | "在微信里"但不在聊天列表——情感价值半程；合规负担与服务号相当 |

**微信结论**：家庭私用短期内没有合法的"聊天列表级"方案；产品化路径 = 注册个体工商户 → 认证服务号 → 深度合成备案（云开发平台有辅助生成备案材料的通道）→ 客服消息接口。这条链和商业化第二阶段（工作室）的主体需求重合——**一次注册，两处受益**。

---

## 四、合规分级

- **家庭私用**（当前）：TG bot 仅自己用，风险≈0；标识照做（bot 简介声明）
- **对外产品**：中国《深度合成管理规定》要求显著标识 + 逝者近亲属同意 + 算法备案（服务号/小程序审核会实际卡这个）；海外 WA 侧遵守 Meta 商业政策即可。我们的 Tier 纪律/非本人标识/同意闸门是现成的合规资产

---

## 五、落地计划

| 阶段 | 内容 | 规模 |
|---|---|---|
| P1 | **TG bot + 通道网关 + persona 引擎 Python 移植 + sessions 落盘**（轴五基建同步完成） | 1-2 天 |
| P2 | 网关抽象定型（channel adapter 接口），WA Cloud API 接入（含 VPS 中转 + opus 转码复用） | 3-5 天 |
| P3 | 微信：随商业化主体注册解锁服务号路径；此前家人用 Tailscale 网页版过渡 | 依主体进度 |

**P1 建议立即排期**——它同时是：三平台的公共地基、轴五 sessions 架构的落地、以及你自己每天可用的产品形态升级。

---

## Sources

- [Meta for Developers — Audio messages（ogg/opus 语音条要求）](https://developers.facebook.com/documentation/business-messaging/whatsapp/messages/audio-messages)
- [WhatsApp API Pricing Explained (2026) | Authgear](https://www.authgear.com/post/whatsapp-api-pricing/)
- [WhatsApp Business API Pricing 2026 | EngageLab](https://www.engagelab.com/blog/whatsapp-business-api-pricing)
- [2026最新！把AI智能体接入微信的5种方案 | CSDN](https://blog.csdn.net/kilohester/article/details/161430731)
- [微信小程序AI功能上架完全指南：资质要求和审核攻略 | Apiyi](https://help.apiyi.com/wechat-mini-program-ai-requirements-guide.html)
- [小程序深度合成审核资质与微信云开发 | 微信开放社区](https://developers.weixin.qq.com/community/develop/article/doc/000c00504302d0319f336ab6a6b013)

*2026-08-17 首版。*
