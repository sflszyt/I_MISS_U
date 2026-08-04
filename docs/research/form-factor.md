# I_MISS_U 产品形态研究报告

> 研究日期:2026-08-04 · 研究问题:数字纪念档案项目应该做成什么形态(A. Claude Code skill / B. 独立本地软件 / C. 构建端 skill + 消费端自包含静态档案)

## «三行摘要»

1. **商业 grief tech 是「20年可打开性」的反面教材**:StoryFile 破产、Eternos 一年内放弃纪念赛道转型 Uare.ai、Eterni.me 从未上线即消亡——把档案托付给任何「运行时/平台/公司」都是在赌它的寿命,唯一穿越 20 年的载体是**开放格式的静态文件**(JPEG/MP4/Markdown/JSON + 静态 HTML)。
2. **推荐形态 C(混合)**:构建端用 Claude Code agent skill(参考 ex-skill 的 prompts+tools 结构,做导入/解析/persona 构建/审核闸门,skill 本身是「施工工具」不需要活 20 年);消费端产出**自包含本地静态 HTML 档案**,家人手机浏览器直接打开,零依赖、零安装。
3. **「档案 HTML 里嵌可选 BYOK 对话页」有成熟先例**(TypingMind 即纯静态 BYOK 应用,key 存 localStorage、请求直连 API):OpenAI 官方 API 允许浏览器 CORS、Anthropic 需 `anthropic-dangerous-direct-browser-access` 头;主要的坑是 `file://` 协议下部分 provider 拒绝 null origin、本地模型(Ollama/LM Studio)需手动开 CORS——建议档案附带一个单文件本地静态服务器脚本兜底。

---

## 1. 同类产品形态普查

### 1.1 总览表

| 产品 | 形态 | 商业模式 | 数据存储 | 现状(2026-08) |
|---|---|---|---|---|
| HereAfter AI | iOS/Android app + web(SaaS) | 订阅制,14 天试用 | 公司云端 | 存活,但为小团队,长期无融资消息 |
| StoryFile | SaaS(会话式视频录制+云托管播放) | ToB+ToC 收费录制 | 公司云端 | **2024-05 Chapter 11 破产**,欠用户退款 $15 万;2025 被 Key 7 收购后「重生」 |
| Replika | 手机 app(SaaS) | 订阅,$14M ARR,4000 万用户 | 公司云端 | 存活,但 2025 被意大利 DPA 以 GDPR 违规**罚款 500 万欧元**(隐私声明不透明、数据用途不明) |
| Eternos | SaaS 数字孪生平台(Human Life Model) | 订阅/分成 | 公司云端 | **2025-11 融资 $10.3M 后放弃纪念赛道,整体转型为个人 AI 助手 Uare.ai**——纪念用户被「pivot」 |
| Seance AI(AE Studio) | 纯 web SaaS,套 OpenAI API | 按次付费 | 公司云端 + OpenAI | 存活,但已退化为 AE Studio 的「定制开发案例」,非独立产品 |
| You, Only Virtual(YOV) | 手机 app + SaaS(Versona 聊天/语音/电话) | 订阅 | 公司云端 | 存活(Angel 轮,「Alive」),体量很小,学术论文已点名质疑其「永远」承诺 |
| 2Wai(HoloAvatar) | iOS app,3 分钟视频生成逝者数字人 | 订阅,$5M 种子轮 | 宣称端上处理,实际闭源不可验证 | 2025-11 beta 上线即遭大规模伦理抵制(「dystopian」「exploitative」) |
| Project December | 网页,按次付费($10)文本模拟 | 按次付费 | 服务端 | 半存活,作者个人维护,明确警告「后果自负」 |
| Eterni.me | 计划中的 SaaS(2014) | — | — | **从未真正上线,~4 万人排队注册后悄然消亡** |
| 国内「AI 复活亲人」(硅基智能、超级头脑等) | 定制服务/数字人 SaaS,单价 10 元~5 万+ | 一次性定制费 | 服务商手里 | 产业链存在但高度商品化、无长期托管承诺;硅基智能已将数字人平台开源(工具层开源、数据自持的先例) |
| MyHeritage Deep Nostalgia / DeepStory | 族谱 SaaS 的附加功能(照片动化) | 订阅引流 | 公司云端 | 存活,但属营销功能而非档案 |
| ex-skill(perkfly) | **Claude Code skill:纯 prompts(7) + tools(7 个解析器)** | 开源,无商业模式 | **全本地**,生成的 persona skill 存 `exes/` 目录(gitignored) | 存活(开源仓库) |

### 1.2 关键观察

**观察一:没有任何一家商业 grief tech 的形态能满足本项目约束。** 全部主流产品都是「公司云端存数据 + 订阅费维持服务」——隐私(约束①)和 20 年可打开性(约束②)天然不成立。学术界已有正式论文(ScienceDirect, 2026)点名质疑 Eternos/HereAfter/YOV 这类公司「让人永生」的承诺在平台关停、link rot、破产面前根本站不住。

**观察二:死亡/背叛方式不止「倒闭」一种。** 反面教材有四类:
- **破产**:StoryFile(欠退款、资产被拍卖,用户录制的「与逝者对话」视频命运取决于收购方);
- **转型(pivot)**:Eternos 拿到融资后整体转向个人 AI 助手——纪念档案用户不是被服务关停,而是被公司战略抛弃;
- **从未兑现**:Eterni.me 收了 4 万注册从未上线;
- **数据滥用**:Replika 被罚 500 万欧元,核心问题正是「用户数据被拿去训练模型、用途不透明」——这是把亲人数据交给任何 SaaS 的固有风险。

**观察三:ex-skill 验证了「构建端 skill」的可行性,但它只做了一半。** ex-skill(prompts+tools、全本地解析微信/iMessage/照片、生成 persona skill 文件)证明 Claude Code 是极好的**素材导入与 persona 构建**运行时;但它的**消费端也依赖 Claude 运行时**——生成物是一个 skill,只有会用 Claude Code 的人能「对话」,家人(约束③)完全无法使用,且 20 年后 Claude Code/skill 格式是否存在完全未知。这正是形态 A 的致命缺陷,也是形态 C 要补的那一半。

**观察四:2Wai 的舆论翻车提示「审核闸门」的价值。** 公众对「上传 3 分钟视频就自动生成逝者数字人」的反感,核心是失真与消费死者;本项目「档案优先于对话、人工审核闸门、纯自用」的定位恰好绕开了这些伦理雷区,应在形态上强化(对话页默认关闭、明确标注 AI 生成)。

---

## 2. 长期保存工具如何解决「永久」

| 方案 | 机制 | 对本项目的启示 |
|---|---|---|
| Permanent.org(非营利基金会) | 一次性付费进入**捐赠基金(endowment)**,用投资收益支付永续存储+格式迁移+完整性校验;章程承诺关停时用基金把档案迁往其他保存机构或交还用户 | 机构级「永久」的成本极高(需要基金会+基金收益);个人项目学不了机制,但可学两件事:**格式迁移**和**完整性校验**是长期保存的日常动作,不是一次性的 |
| Forever.com(商业公司) | 「终身+100 年」承诺,原理同样是预付费信托 | 承诺主体仍是一家公司——与 grief tech 同构的风险 |
| Immich / PhotoPrism(开源自托管) | Docker 自托管照片库;PhotoPrism 不移动原始文件、尊重既有目录结构 | 自托管**服务**也会腐烂(Docker 镜像、数据库 schema、依赖链);真正可长存的是它们背后**「原始文件+目录结构+EXIF」**这一层。启示:数据层必须独立于任何 viewer 存在 |
| 数字保存学界共识(如美国国会图书馆推荐格式) | 优先开放、无 DRM、广泛实现的格式:JPEG/PNG、MP4(H.264)、FLAC/WAV、纯文本/Markdown、JSON、PDF/A、静态 HTML | **本项目的「20 年答案」就在这里**:档案本体 = 文件系统目录 + 上述格式;HTML/浏览器是 30 年向后兼容记录最好的应用运行时(1996 年的网页今天仍能打开) |

**结论:分层是唯一正解。** `数据层(开放格式文件,必须活 20 年)` → `浏览层(自包含静态 HTML,大概率活 20 年,坏了可从数据层重新生成)` → `对话/工具层(skill、LLM、Live2D,允许死,随时可重建)`。任何把三层捆死在一起的形态(纯 app、纯 skill)都会让最短命的一层拖死整个档案。

---

## 3. 「档案 HTML 嵌 BYOK 对话页」的先例与坑

### 3.1 先例:这是一个已被验证的成熟模式

- **TypingMind**:最典型先例——**纯静态 web 应用、无后端**,用户填自己的 OpenAI/Anthropic/任意兼容 API key,key 存浏览器 localStorage(可选 AES 加密),请求由浏览器**直连** provider。官方 FAQ 明确:「整个应用是静态网站,我们没有后端可收集数据」。这证明「静态 HTML + BYOK + 直连 LLM API」在产品级规模上可行。
- **awesome-byok-apps**(GitHub 精选列表):BYOK 已成一个公认的应用类别,同类还有 Chatbot UI、big-AGI 等开源实现可直接参考代码。
- **OpenAI 官方 SDK** 提供 `dangerouslyAllowBrowser: true` 选项,`api.openai.com` 对浏览器请求返回宽松 CORS 头;**Anthropic SDK** 2024 年起支持浏览器直连(需请求头 `anthropic-dangerous-direct-browser-access: true`)。官方 SDK 层面已承认这个用法。

### 3.2 坑(按严重程度)

1. **`file://` 协议的 origin 问题**:双击打开本地 HTML 时 Origin 为 `null`。OpenAI 等返回 `Access-Control-Allow-Origin: *` 的 API 仍可用,但**部分 OpenAI 兼容网关/中转会拒绝 null origin**(Gemini 的 OpenAI 兼容层就出过 CORS 问题)。**对策**:档案内附一个零依赖启动脚本(如 `python -m http.server` 包装或单文件 exe),把档案跑在 `http://localhost` 下;对话页做 CORS 失败的友好降级提示。
2. **本地模型的 CORS**:Ollama 默认拒绝浏览器跨域(需设 `OLLAMA_ORIGINS`),LM Studio 需勾选启用 CORS。文档里要写清楚。
3. **API key 安全**:BYOK 场景下 key 是用户自己的,不存在「泄露开发者的 key」问题;真正的风险是 key 躺在 localStorage 里被同机恶意页面/家人误操作暴露。**对策**(抄 TypingMind):key 只存本地、可选口令加密、页面不引入任何第三方脚本(自包含档案天然满足)、给家人的档案副本可以干脆不含 key(对话页留空,填了才可用)。
4. **SDK 自定义头问题**:openai-js 等 SDK 会加 `x-stainless-*` 头,部分兼容网关的 CORS 白名单不含这些头导致 preflight 失败。**对策**:对话页不用 SDK,直接 `fetch` 裸调 `/v1/chat/completions`——顺带把「模型无关」(约束④)做到最彻底。
5. **流式输出**:SSE 在纯前端 `fetch` + ReadableStream 下可用,无额外坑。
6. **长上下文检索**:纯前端做档案检索式对话,需要把检索索引(如预计算的 embedding 或纯文本倒排索引)也静态化打包进档案——构建端 skill 生成、消费端 JS 加载,技术上完全可行(几 MB 级 JSON)。

---

## 4. 三形态对比打分

打分:✔ 满足 / △ 部分满足 / ✘ 不满足

| 约束 | A. 纯 Claude skill(ex-skill 式) | B. 独立本地软件/平台 | C. 混合(skill 构建 + 静态 HTML 消费) |
|---|---|---|---|
| ① 隐私(数据不上云) | △ 数据本地,但对话时档案内容必然进入 Claude API 上下文;绑死 Anthropic 一家 | ✔ 完全本地可控 | ✔ 数据层纯本地;构建期送入 Claude 的内容可控可审;消费端零外联(对话为可选项且用户自选 API) |
| ② 20 年可打开 | ✘ 赌 Claude Code、skill 格式、Anthropic 三者都活 20 年 | ✘ Electron/依赖链/数据库 schema 10 年内必腐烂,需持续维护 | ✔ 数据层开放格式 + 静态 HTML;viewer 坏了可由数据层再生成 |
| ③ 家人(非技术、手机)可浏览 | ✘ 家人不可能用 Claude Code | △ 需装 app 或连你家服务器(HTTPS/内网穿透都是负担) | ✔ 发一个文件夹/一个 HTML,手机浏览器直接开 |
| ④ 对话模型无关 | ✘ 绑死 Claude 运行时 | ✔ 自配 API key | ✔ 裸 fetch 调任意 OpenAI 兼容端点(含本地 Ollama/vLLM,4090 可跑) |
| ⑤ Live2D + TTS 扩展 | ✘ 终端形态无法承载 | ✔ 可做,但加重软件维护负担 | ✔ Live2D 有纯前端方案(pixi-live2d-display),TTS 可 API 实时或构建期预生成音频落盘(预生成的音频本身也成为档案资产) |
| 开发/维护成本(参考项) | 低 | **高**(打包、更新、跨端) | 中(skill 迭代快;HTML 模板一次成型) |
| 未来开源工具层 | ✔ 天然可开源 | △ 开源整个 app 维护重 | ✔ skill + HTML 模板开源,数据不含在内(与 ex-skill 同构) |

**A 得 0.5/5,B 得 2.5/5,C 得 5/5。**

---

## 5. 推荐:形态 C(混合),并给出结构建议

**明确推荐 C**,理由浓缩为一句话:**把「需要智能的部分」放在允许死的构建端,把「需要活 20 年的部分」做成不需要智能的静态文件。**

- 构建端(Claude Code agent skill,参考 ex-skill 的 prompts+tools 三层结构):素材导入(微信/照片/视频解析)、时间线与记忆卡片生成、persona 构建、**人工审核闸门**(每张记忆卡片、每条 persona 事实须经确认才进档案)、档案编译(生成静态 HTML + 检索索引 + 可选预生成 TTS 音频)。skill 是施工队,工程结束即可退场,Claude Code 死了换任何 agent 运行时重写皆可。
- 消费端(自包含静态档案):目录结构 = 原始媒体(开放格式)+ `data/*.json`(时间线/卡片/persona)+ `index.html`(浏览)+ `chat.html`(可选 BYOK 对话页,默认无 key 不可用)+ 一个本地静态服务器启动脚本。给家人的副本可裁剪(不含对话页或不含某些素材)。
- 长期维护动作(向 Permanent.org 学习):每隔几年做一次**格式健康检查与迁移**(如 H.264→当时主流格式)、校验和验证——把这写进 skill 作为一个命令。

### 反面教材备忘(写进项目 README 的理由陈述)

> StoryFile 破产时,用户为逝者录制的对话视频躺在待拍卖的服务器上;Eternos 的纪念用户在公司拿到 $10.3M 后被转型抛下;Replika 因拿用户数据训练模型被罚 500 万欧元。I_MISS_U 的档案不托付给任何公司、任何运行时、任何订阅——它只是你硬盘上一个 20 年后仍能双击打开的文件夹。

---

## 6. 来源

- StoryFile 破产:https://aibusiness.com/verticals/startup-behind-ai-william-shatner-files-for-bankruptcy · https://westfaironline.com/courts/white-plains-bankruptcy-interrupts-talk-with-the-dead/ · https://www.storyfile.com/news/key7-purchase · https://www.avinteractive.com/territories-news/us-canada/conversational-ai-video-pioneer-emerges-from-chapter-11-03-03-2025/
- Eternos 转型 Uare.ai:https://techcrunch.com/2025/11/11/immortality-startup-eternos-pivots-to-a-personal-ai-that-sounds-like-you/ · https://theaiinsider.tech/2025/11/29/liveperson-founder-rebrands-eternos-as-uare-ai-and-raises-10-3m-to-build-personal-ai-models-based-on-human-life-stories/
- HereAfter AI:https://apps.apple.com/us/app/hereafter-ai/id1626176069 · https://aichief.com/ai-productivity-tools/hereafter-ai/
- Replika GDPR 罚款与业务数据:https://www.edpb.europa.eu/news/national-news/2025/ai-italian-supervisory-authority-fines-company-behind-chatbot-replika_en · https://www.aicompanionpick.com/replika-user-base-2026 · https://en.wikipedia.org/wiki/Replika
- Seance AI:https://www.ae.studio/seanceai/about · https://futurism.com/ai-seance
- YOV 及学术质疑:https://www.myyov.com/ · https://www.cbinsights.com/company/yov · https://www.sciencedirect.com/science/article/pii/S2666659626000028
- 2Wai 争议:https://www.forbes.com/sites/conormurray/2025/11/14/disney-channel-stars-ai-app-that-creates-avatars-of-dead-relatives-sparks-backlash/ · https://decrypt.co/348707/demonic-ai-app-lets-users-talk-dead-loved-ones-faces-backlash
- Project December / Eterni.me:https://theconversation.com/deadbots-can-speak-for-you-after-your-death-is-that-ethical-182076 · https://www.rollingstone.com/tv-movies/tv-movie-reviews/eternal-you-doc-sundance-ai-digital-afterlife-death-chatgpt-technology-1234950589/
- 国内 AI 复活亲人产业:https://finance.sina.cn/2024-04-08/detail-inarchuw3285888.d.html · https://t.qianzhan.com/caijing/detail/240304-718de22f.html · https://tech.china.com/articles/20251103/202511031758412.html
- ex-skill:https://github.com/perkfly/ex-skill
- Permanent.org 捐赠基金机制:https://www.permanent.org/blog/how-our-endowment-works/ · https://www.permanent.org/why-permanent/ · Forever.com:https://www.forever.com/
- 自托管照片库:https://blog.elest.io/immich-vs-photoprism-which-self-hosted-photo-manager-for-your-family/ · https://homenode.tech/best-self-hosted-photo-manager-2026/
- BYOK 静态前端先例与 CORS:https://docs.typingmind.com/general-faqs · https://www.typingmind.com/privacy · https://github.com/typingmind/typingmind · https://github.com/yatsyk/awesome-byok-apps · https://github.com/anthropics/anthropic-sdk-typescript/issues/248 · https://discuss.ai.google.dev/t/gemini-api-cors-error-with-openai-compatability/58619 · https://community.openai.com/t/how-to-properly-proxy-chatgpt-calls-get-around-cors-errors/580179
