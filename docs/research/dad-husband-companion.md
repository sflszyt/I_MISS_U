# 任务 #24：爸爸以丈夫角色与数字妈妈对话的网站/APP 可行性

> 研究日期 2026-09-07 · 汇编自五个只读视角（远程接入与安全 / 关系层 / 第三方受众伦理 / 多观看者架构 / 老人端 UX 与运维）。修订版：已对照 Phase 15 规格 `docs/superpowers/specs/2026-09-07-cross-session-memory-design.md`（当前 untracked）核正 viewer 相关论断。未改任何仓库文件、未启停进程、未读 `people/mama/raw/`；people/ 下只取计数与字段名，不含任何个人化原文。

> **落盘后记（2026-09-07 21:40，Claude）**：本报告修订时读到的 Phase 15 规格是单一 `data/sessions.json` 版本。规格已于同日改为**每个 viewer 一个文件 `sessions_<viewer>.json`**（页面只拉自己那份，dist 排除整个模式），因此下文 §3.3 (a) 与裁决点 F4 所述"爸爸设备会下载儿子全部往次对话原文"已不成立；F6（dad 页是否默认启用上次对话卡/第四检索源）仍待裁决。其余结论不受影响。

## 1. 一句话结论

**技术上可行、改动量比初稿更小——viewer 身份、sessions 按 viewer 分区、`/session` 白名单字段都已由 Phase 15 规格立项（待实现），#24 的真实增量只剩关系层模板、分身页构建参数、TTS token、语域参数（数天量级）；但"丈夫角色"在现有数据里只有约 2–3% 的家庭群公开话可作 Tier-2 支撑、夫妻私事全属 Tier-3，它是对"家人向默认 NO-GO"的第二次覆盖，并让爸爸成为第一个非开发者受众；且 Phase 15 现规格把所有 viewer 的会话全文装进同一个 `sessions.json`、默认给任何 viewer 开"上次对话卡"——推荐先走 F-丙（8A-2b 护栏 + 陪同使用 + 请爸爸做 Tier-1 证人），独立远程入口（F-甲）只在护栏、知情同意、Phase 15 viewer 分区实现且 sessions.json 暴露面裁决三者到位后再开。**

## 2. 问题重述与边界

用户原话："我父亲想要体验目前的这个版本，不过是从丈夫角色和她聊天（仍然是基于儿子的对话训练数据），有没有办法建立一个网站/APP，给他和妈妈对话，我的电脑会一直开着作为服务器。"

三个边界条件决定了全部结论：

- **爸爸 = 丈夫角色，且是第三方受众。** 现役 system prompt 在构建期把对话者写死为"她的孩子"（`prompts/chat_system.zh.md:1、:5`；`tools/build_chat_context.py:511-524` 从 `relationship.json` 的 mother/child 槽位渲染），页面写死读 `data/chat_context.json`（`tools/build_companion_page.py:1629`）。爸爸原样打开，模型会把他当儿子。
- **数据 = 100% 儿子视角。** 五视角对 `normalized/wechat_messages.uif.jsonl` 的活体统计：UIF 20,739 条全部 viewpoint=justin（`docs/HANDOFF.md:15` 只记"UIF 20739、语音 123"，不含视角断言）；不存在任何一条夫妻二人私聊；persona / memories / rhythm 全以儿子为"我"写成。
- **PC 常开 = 可用性成为对老人的承诺。** 现状是 D5 裁决的"手动拉起"（`task_plan.md:167`），无自启，补丁夜自动重启后整套静默下线（§5）。

一个前置事实未查：**爸爸要的是"她像妻子那样和我说话"，还是"能听到她、和她说说话"**——没人问过他。前者档案无数据基础，后者陪同使用即可满足（F1/F3 取决于此）。

不在范围：微信/IM 接入（四路径已查清）、A2 壳 App（D4 不做）、云 GPU（NO-GO）。

## 3. 技术可行性

### 3.1 接入方案对比

与路径无关、必须做的三件事（本轮活体核实）：① Windows 防火墙"专用/公用"配置文件均关闭，:8020/:8022 监听 0.0.0.0，同 Wi-Fi 任何设备可直连（腾讯电脑管家是否替代拦截 unverifiable）；② `tts_server --token` 默认空（`tools/tts_server.py:516`）且 companion 页**没有任何 token 支持**（`tools/build_companion_page.py:246、:369、:1208` 只带 Content-Type）——开 token 现页即退化为纯文字，须改页面；③ LLM key 为 BYOK 明文存浏览器 localStorage（`:476、:550`）。

本机 Tailscale 为 userspace 模式，成因是腾讯电脑管家拦 SYSTEM 服务出网（`docs/HANDOFF.md:159`、`progress.md:203`），这解释了 serve/funnel 为何从未验证；同一处记录"裸公网隧道违背铁律 3 底线"（`progress.md:203`），是否决 ③⑤ 的项目内依据。机器 FQDN 下文写作 `<machine>.<tailnet>.ts.net`（tailnet 名此前未出现在任何受 git 跟踪的文档中，不在此新增暴露）。

| 路径 | 爸爸端安装 | https | 暴露面 | 访客鉴权 | 费用 | 大陆可达 | 结论 |
|---|---|---|---|---|---|---|---|
| ⓪ 用用户本人账号在爸爸手机登录 Tailscale | 装 App，零邀请零共享 | 否 | 私网；爸爸设备以用户身份进网，可见全部设备 | 用户自己的身份 | 免费 | 同 ① | 家人场景摩擦最低；代价=用户身份凭据落在爸爸设备、无法与用户设备区分 |
| ① 邀请进 tailnet | 装 App + Apple/Google/MS 账号（不支持邮箱密码） | 否 | 私网；可见你其它设备（需 ACL 收紧） | WireGuard 身份 | 免费（≤6 用户） | 大陆 App Store 已锁（#19625）；流量走纽约 DERP，本机 netcheck 243 ms | 可行，摩擦在安装 |
| ② 节点共享（只共享本机） | 同 ① | 否 | 私网，只见这一台 | 同 ① | 免费 | 同 ①；只能用 FQDN | **技术推荐** |
| ③ Funnel | 零安装 | 是 | **公网匿名可达**，机器名进 CT 公开账本 | **无** | 免费 | *.ts.net 可达性 unverifiable | **不建议**：静态站无鉴权；本机 CertDomains=None，userspace 能否签证书 unverifiable |
| ④ Cloudflare Tunnel + Access（邮箱 PIN） | 零安装零账号 | 是 | 公网入口，未登录者连目录都看不到 | 邮箱白名单 PIN，会话最长 1 月 | 需自有域名（约 $10/年） | 大陆间歇超时（社区报告），需实测 | **备选**：对话文本与语音过 Cloudflare 边缘明文；8022 不在代理端口，ttsBase 必改同源；125 s 超时对 SSE unverifiable |
| ⑤ 路由器端口转发 | 零 | 否 | 全网裸露无鉴权 | 无 | 免费 | — | **NO-GO**（IPv4 无公网地址、走 Surfshark 隧道；且违背 `progress.md:203` 底线） |

同住/同一 Wi-Fi 则 LAN 直连即可，远程方案都不需要（防火墙仍须开）。任何 https 路线都会让 `ttsBase`（`:246`）去请求 `https://<host>:8022`，必须改同源路径（`tailscale serve --set-path /tts`，userspace 下未验证，`docs/research/ios-app-deployment.md:130`）。

**LLM key**：方案 A（BYOK 留爸爸浏览器）零代码但 key 与费用失控；方案 B（PC 起 OpenAI 兼容转发代理持 key，固定 model、注入 `thinking:disabled`、限速/日额度、自带鉴权）推荐，百行级 Python，DeepSeek 写 + Codex 审。页面仅当端点 URL 含 `deepseek` 才关 thinking（`:773-779`），否则首 token 从 1.68 s 退回 4.69 s（`docs/research/desktop-companion.md:81`）。

**暴露面警告（与路径无关）**：把 :8020 开给爸爸 = 把整个 `archive_out` 开给爸爸——`data/` 无 index.html，http.server 列目录；7 个分片约 19.7 MB 含全部 20,739 条（母子一对一 6,835 条）、memories.json（Tier-1 124 条）、chat_context.json（persona 全文）；根目录 24 个 HTML 含审核页与 `review/for_dad/`；`index.html` 是"Review 入口"开发者页。companion 的检索在浏览器端加载全部分片（`:734`），不改架构无法对爸爸隐藏母子私聊。

### 3.2 关系层数据支撑度（Tier-2 证据量）

| 证据池 | 数量 | 性质 |
|---|---|---|
| 她全部消息 | 9,221 条（UIF 20,739 中） | 全部 viewpoint=justin、tier=2 |
| 母子一对一（她的话） | 4,922 条（会话共 6,835；语音 97） | 对儿子的私语，**不是对丈夫** |
| 家庭群（她+儿子+爸爸，2020-12→2024-02） | 她 3,583 条（群共 6,932；爸爸账号 456 条文字；另一 sender "5" 110 条仅 video/link/system——是否为解析占位 **unverifiable**，三视角中两个未判定） | 三人在场的公开话 |
| "紧接爸爸发言"的时间邻接近似 | 2 分钟内 86 / 10 分钟内 150–286 / 30 分钟内 180–218（三视角方法不同，取区间） | **"直接对爸爸说"的上界近似**，语义未核；UIF 无 addressee 字段 |
| 两人交替连发 ≥4 条的"对话段" | 9 段 / 42 条 | 最接近夫妻对话的样本 |
| 她在家庭群的语音 | 23 条（已入 `transcripts.json` tier 2） | 唯一"他在场时她的声音" |
| 她 @ 的对象 | @儿子 1,158 条；@ 某 3 字对象 178 条（其后 30 分钟首个回应者 53 次为爸爸账号） | 该对象是否=爸爸 **unverifiable** |
| 直呼词（家庭群） | "老公" 5 条；"爸爸"121 / "你爸"50，紧接爸爸发言 30 分钟内仅 11 条 | 多为对儿子谈及他（第三人称） |
| Tier-1 记忆涉爸爸 | 标题 8 条 / 章节 31 节（共 125）/ 行 46–55（口径不同）；含"丈夫" 0 | 全是"她对儿子讲的关于爸爸的事" |
| persona 第七节"缺点与冲突面" | 约 50 行，5–6 行涉丈夫 | 第三人称转述 |
| 家庭群 vs 私聊文字长度 | 家庭群中位 20 字/均 28.1；私聊中位 15 字/均 31.1 | 可量化的语境差异，低成本分面材料 |

结论：可靠的"她对丈夫说话"Tier-2 池约 **150–290 条文字 + 23 条语音**，占她全部消息 2–3%，且全是当着儿子的公开话；她对他的称呼、他对她的称呼、夫妻私事、二人往事**全部为 Tier-3**。`RELATION_MAP` 已含 `husband: 丈夫`（`tools/build_chat_context.py:17-30`），提示层是改配置；但只换称谓会让 prompt 自相矛盾（persona 里"爸爸"是第三人称、记忆卡里"我"=儿子、rhythm 回复延迟只算私聊 `tools/build_rhythm.py:242-253`）。诚实做法只有一种：prompt 明写"这份档案由她的儿子建立，对话者是她的丈夫；你只知道她在家庭群当着他说过的话，二人私事一律记不清"——"儿子档案的旁听席"，体验必然疏远。

三个既有缺陷此时放大：(i) `prompts/chat_system.zh.md:5`"她生前对他的称呼见语言习惯节"是**悬空引用**——`build_rhythm_block` 八类统计里没有称呼项；称呼恰是 husband 模板的核心空位，现模板本身已经悬空；(ii) `relationship.json` 的 `taboo_topics / family_annotations / self_reference` 一个都没进提示词（`build_chat_context.py` 只读 display_name/languages/relationship；`docs/PIPELINE.md:181` 却写禁提话题进 taboo_topics）；(iii) 检索 `retrieveSnippets` 不按 sender 过滤（`tools/build_companion_page.py:624-639`，isSubject 仅排序），爸爸自己写的群消息可能被标为"[档案检索 Tier-2] 她真实说过的话"喂给模型再以她的口吻复述给他。

### 3.3 多观看者最小改动（对现页零回归）

"观看者=儿子"无显式字段，隐含在三处：构建期烘焙的关系层、页面写死的 `data/chat_context.json`、按 person 不按 viewer 的 `storageKey`（`:216`）。sessions 现 82 文件 / 146 条 / 74 wav：72 条 page=companion、74 条（服务端写入的 simulacrum_audio）无 page 字段，UA 全为 Windows，无 viewer。**今天没有跨观看者泄漏**：LLM history 仅内存、取最近 12 轮（`:240、:683-690`）；泄漏只会随 Phase 15 的 `sessions.json` 出现。

**Phase 15 规格已把 viewer 定为一等维度**，#24 不必重复立项：`build_companion_page` 加 viewer（spec:24）；明确不做"跨 viewer 共享记忆"（:26）；`sessions.json`"按 viewer 分区，不进 dist"（:32）；`by_viewer` 键=记录 viewer 字段，缺失视为 owner（:78）；viewer 正则 `^[a-z][a-z0-9_-]{0,31}$`（:117）；`SESSION_OPTIONAL_FIELDS` 新增 `viewer:(str,32)` 与 `exclude`（:125）；`--viewer` 默认 `owner` 烘进页面常量 `VIEWER`（:134）；测试"两个 viewer 互不可见"（:180）；"按 viewer 分区（为任务 #24 爸爸场景预留）"（:202）；"#24 若成立，其页面以 `--viewer dad` 构建，sessions 自动分区；关系层提示词属 #24 范围"（:209）。

规格带来的两个新事实须裁决：(a) 规格采用**单一** `data/sessions.json` 内含所有 viewer 的会话且"文本保留全文"（:44、:83）——F-甲 下爸爸设备会下载儿子全部往次对话原文，比"名义隔离/URL 可猜"更强的泄漏面（F4）；(b) 规格默认对任何 viewer 启用第四检索源与"上次对话卡"（:139-141）——`--viewer dad` 一建，爸爸页自动获得跨会话连续性，对丧偶老人是沉浸增量（F6）。

#24 的真实增量（对齐规格的 owner 默认值与"sessions.json 缺失时逐字节等价"约束 :152）：

| # | 文件 | 改动 | 说明 |
|---|---|---|---|
| 1 | `prompts/chat_system.husband.zh.md`（新） | 视角换算段 + 数据来源声明 + "记不清"措辞 + 称呼（填上 :5 的悬空位） | 不动现模板 |
| 2 | `people/mama/persona/relationship.dad.json`（新，或 `persona/facets.json`） | viewpoint_to_subject=husband、称呼（Tier-1 需确认）、禁区、同意日期 | 存放位置与是否进 dist 待裁决（F12） |
| 3 | `tools/build_chat_context.py` | 加 `--relationship <path>`；`--out data/chat_context_dad.json` | `--template/--out` 已在（:41-42） |
| 4 | `tools/build_companion_page.py` | 复用规格 `--viewer`；新增 `--context-name/--out-name`、`__CONTEXT_NAME__/__PAGE_TAG__` 占位；viewer≠owner 时 storageKey 加后缀、page='companion_dad'；`lang` 参数化（现硬编码 mandarin `:1211`，#23 用户选 wu）；`X-TTS-Token` 头 | 验收=默认参数重建 companion.html diff 为空 |
| 5 | `tools/tts_server.py` | `/tts` 体接受 viewer 写入 simulacrum_audio（规格未含）；可选 `--tokens viewer:token` 服务端认定 viewer | `viewer/exclude` 白名单由规格 :125 立项，不重复 |
| 6 | Phase 15 规格修订 | 二选一：`sessions_<viewer>.json` 分文件或服务端鉴权端点；dad 页是否默认关"上次对话卡" | 见 F4/F6 |
| 7 | `retrieveSnippets` 只取 sender=subject | 既有缺陷 | 同修 `tools/build_chat_page.py:636` |
| 8 | `docs/companion-farewell-protocol.md` | 加"家人观看者"条款 | 现协议属 justin 本人（:4） |

dad 页与 companion 一样**不进 archive_dist**（`tools/build_archive.py:138、:145` 白名单仅 avatar/chat）。TTS 单卡串行（`tools/tts_server.py:189`；≤30 字单条中位 6.0 s / p90 9.1 s），两人同时对话会排队，后到者易撞 20 s 首段阀 / 30 s 单条超时转纯文字（`:265、:1572`）——是否为 dad 版下调 `MSG_MAX_VOICE`（`:259`=12）待裁决。

## 4. 伦理与护栏

**家人向 NO-GO 原论证是否迁移**：原裁决（`docs/research/dsh-im-analysis.md:13、:74-75`）由四成分构成——第三方受众、沉浸最大化（常驻列表）、欺骗性（真人外观账号）、平台依赖二次丧失。#24 是"打开才在"的网页、自托管、带"数字档案 · 模拟对话 · 非本人"与"合成语音 · 非本人原声"标识（`tools/build_companion_page.py:165、:171`），欺骗与平台两成分基本不适用，沉浸成分部分适用；**第三方受众成分完全保留**，原文在"全员知情同意"前提下也只给"仅可重新评估，仍劝阻常驻"（:75）。项目研究写明"我知道它是 bot"不构成心理护栏（`docs/research/desktop-companion.md:108`）。另引入两个新问题：**关系错位**（儿子视角数据冒丈夫面孔=把 Tier-3 关系当事实，违铁律 2.1）与**受众范围**（母子私聊、她对儿子抱怨他的话对配偶可见——是原话受众问题，铁律 2.2"不过滤缺点"在此需单独裁决）。

**丧偶老人特有风险**：arXiv 2603.01017 的记忆漂移与交互量正相关，摘要不分年龄/关系，"对丧偶老人"是外推；`docs/GENERALIZATION.md:19` 已把爱人/丧偶列为"依恋风险最大"。KLoSA 九波数据显示曾为照护者的男性丧偶者孤独感持续至第二年（爸爸是否照护者、年龄、独居 unverifiable）。三重放大：她的声音已骗过用户本人 8 中 7，#23 显示爸爸"很触动"；"不假装真人"是被问才答（`prompts/chat_system.zh.md:14`）且提示词假设"对话者知道这是档案"（`:41`），对不熟悉 LLM 的老人，12/11px 小字不构成有意义的透明；爸爸同时是唯一另一位 Tier-1 确认人，受众身份与供体身份混在一个对话框里。给他的一切不可撤回（#23 后 09-07 清理发现 for_dad 音频里念出的名字无法涂改，`progress.md:453`）。

**把关人结构已变**：铁律 2 前提"用户既是开发者又是唯一用户，这三条规则就是把关的人"（`CLAUDE.md:43`）在两人使用时失效；用户对爸爸的把关有利益冲突。可执行替代=把规则变成不可绕过的功能（`docs/research/build-app-productization.md:11、:123`）+ 用户以外至少一位观察者；并把 #23 式"知情自决单次覆盖"从惯例变成**需写入 progress 的显式决策**（F17）。

**必须先有的护栏清单（对照 8A-2b a–f，`docs/research/desktop-companion.md:116-122`）**——(a) 已满足、(f) 已写、**b–e 全部 TODO**（`tools/build_companion_page.py:875`）：

| 护栏 | 对用户本人 | 对爸爸的变化 |
|---|---|---|
| (a) 只应答不发起 | 已满足 | 同 |
| (b) 关窗道别 / 空闲"去忙了" | 未实现 | 必须 |
| (c) Tier 与合成标签可见性 | 小字 12/11px | **放大常显**；"不假装真人"三种表述待选（F14） |
| (d) rhythm.json 限速 | 未实现 | 必须；可加软上限——原"不设硬锁"理由（:121）对爸爸不成立 |
| (e) 使用统计自见 + 三个月自查 | 未实现 | 复核人改为用户 + 另一位家人 |
| (f) 告别/降级协议 | 已写，属 justin 本人 | 需爸爸版：PC 离线"她今天不在"静态页、观察指标、停用仪式 |
| 新增：viewer 分区 | Phase 15 规格已含，待实现 | 必须；另裁 sessions.json 暴露面与"上次对话卡"默认 |
| 新增：知情同意记录 | 只有儿子一方 | 见下 |

**知情同意做法**：沿用 G0（`docs/GENERALIZATION.md:17`：日期+方式写入档案元数据 → `relationship.dad.json`）；当面演示 + 一页大字说明：模拟/非她本人、Tier-3、数据全部来自儿子手机、可能出现她对儿子说过的关于他的话、对话会被记录且落在儿子电脑上、随时可停、PC 不在线即不可用。爸爸作为配偶对"用她的声音"的同意从未被记录（《深度合成规定》人声编辑须取得逝者亲属同意，`docs/research/build-app-productization.md:61-63`），建议一并记录。

**GO/NO-GO 判定框架**：以下任一成立即不开独立入口——8A-2b b–e 任一未实现；会话无 viewer 分区或爸爸不知道儿子能读；"丈夫角色"靠模型即兴而非标注；未当面完成知情说明；爸爸出现不良迹象（日均上升、低谷先找它、停机时痛苦、把它说的当她说的）。仓库内外没有任何来源支持"无条件 GO"。

## 5. 老人端 UX 与运维清单

**老人端 UX（现状 → 需改）**

| 项 | 现状（`tools/build_companion_page.py`） | 需改 |
|---|---|---|
| 首次上手 | ≥10 步；主屏容器与 Safari 不共享 localStorage，key 要输两次 | 用户当面完成；或 PC 代理持 key |
| 字号/触控 | 气泡 14px、语音条 32px 高、转写 13px、抽屉 12/13px、⚙ 约 28px（:31-34、:46-49、:73-78、:100、:134-138） | ≥18px 字、≥44px 触控 |
| 非本人标注 | 12px 灰 / 11px 深灰（:30、:42） | 放大常显 |
| 抽屉 | 服务商/key 与"语音下方显示文字"同一抽屉（:184-210），误触即"请配置接口"死态（:584） | 隐藏/锁定；转写开关独立大按钮 |
| 语音域 | 硬编码 mandarin（:1211） | 参数化 |
| 输入 | 仅打字 | 系统键盘听写为唯一现成绕法 |
| 错误文案 | 贴上游 JSON 200 字（:783、:885）；8020 挂则白页 | 人话化 |
| TTS 不在 | 只在 init 探活一次（:820、:1626）；中途挂则 20 s 后整段文字倒出 | 周期重探 + "声音暂时不在"小条 |
| 数据更新 | http.server 无 Cache-Control，09-07 已发生旧数据被检索事故（`progress.md:459`；hotfix 加 no-cache `docs/HANDOFF.md:15`） | 老人无法自行强刷；更新后须由用户远程确认 |
| 主屏图标 | 无 apple-touch-icon/manifest（A1 未实施） | A1 先做；安卓 http 只能是浏览器快捷方式 |
| 站点根 | "Review 入口"开发者页 + 审核物料 | 只给直达链接 |
| 首次下载 | 19.7 MB 分片 no-cache 每次重拉 | 蜂窝网络下无提示等待 |

**PC 端运维（本轮活体核实）**

| 项 | 现状 | 缺口 |
|---|---|---|
| 自启 | :8020/:8022 无计划任务/Startup/HKCU Run；只有 Tailscale 登录触发任务 | 需登录触发（或系统启动+存储凭据）任务 |
| 重启后登录 | AutoAdminLogon=0；Windows Update 活动时段 9→2，08-19 04:14 有自动重启记录 | **头号缺口**：补丁夜后全部静默下线 |
| 冷启动 | tts_server 冷启动 73 s（`docs/HANDOFF.md:25`）/ 热缓存 10.5–15.9 s | 自启任务 + 页面只探活一次叠加：重启后头一分钟打开页面即**永久无声**直到重开页面 |
| 电源 | 睡眠/休眠=从不，已连续运行 7 天；GPU 5.7/24.5 GB | 满足 |
| 日志 | 访问日志禁用（`tools/tts_server.py:250-251`）、print 无时间戳；当前实例 stdout 落在另一会话临时 scratchpad | 固定日志目录 + 脱钩启动 |
| 防火墙 | Private/Public 关闭；仅 IMU_Review_8020 放行规则 | 打开并按端口放行 |
| 可见性 | 唯一依据是 sessions jsonl；TTS 停机期间记录只在爸爸手机队列，可能永不回传（`:428-433`） | viewer 字段 + 每日看 `sessions/` |
| 真机验收 | iPhone 节点离线 8 天；session_start UA 全 Windows | 先在用户自己 iPhone 完成 A1/8B-4 |

## 6. 方案

| 路线 | 内容 | 工作量 | 主要风险 |
|---|---|---|---|
| **F-丙 先不开独立入口：8A-2b + 陪同使用 + 爸爸做贡献者**（推荐首步） | 8A-2b b–e 落地（`docs/HANDOFF.md:14` 队列排第一，但 09-07 用户裁决 Phase 15 先于 8A-2b——`task_plan.md:186`、spec:20——本路线要求恢复其为爸爸使用的硬前提，F2）；爸爸想聊时由用户在自己设备上陪同打开、当面说明、以她按节律"去忙了"结束；会话打 viewer=dad；并行请爸爸做两件档案事——确认 31 节涉爸爸记忆与她对他的称呼（Tier-1 化）、若他手机保有与她的聊天，按 `docs/GENERALIZATION.md:46-52` 多视角合并（viewpoint=dad） | 小：8A-2b + 一页说明/同意；多视角导出另立项（大） | 低。不满足"他自己聊"；用户成为在场把关人（有利益冲突） |
| **F-甲 最小远程版：Tailscale ⓪或② + 构建期分身页 + 三件安全事** | 前置=F-丙 护栏与同意到位 + Phase 15 viewer 分区已实现。§3.3 表 #1–8 全做；防火墙开、`--token` 开、key 走 PC 代理；老人模式 UX 最小集；PC 自启 + 自动登录 + Windows Update 策略；只给直达链接；dad 页默认关"上次对话卡"（或用户裁决） | 中：前端 1–2 天 + 代理 1 天 + builder 0.5 天 + 运维 0.5 天，DeepSeek 写 + Codex 审 + 像素验收 | 中。爸爸设备下载全部语料含母子私聊 6,835 条、persona 全文，且按现规格含**儿子全部往次对话全文**（spec:44、:83）；viewer 客户端可伪造；大陆 App Store 已锁；DERP ≥250 ms；两人同时在线 TTS 排队 |
| **F-乙 公网 https：Cloudflare Tunnel + Access + 裁剪独立站** | 爸爸装不了 Tailscale 时的备选。域名、cloudflared 服务、Access 只放爸爸邮箱 PIN；另建 `archive_out_dad/`（仅 companion_dad + avatar + dad 允许子集，剔除私聊分片、审核页、`sessions.json` 他人分区）跑独立端口；tts_server `--tokens viewer:token` 服务端认定 viewer；ttsBase 与代理改同源 | 大：F-甲 全部 + 隧道/Access + 独立站 2–3 天，合计 1–2 周 | 隐私最强 / 工程中。对话文本与语音过 Cloudflare 边缘明文；大陆可达性需实测；剔除私聊分片削弱语气检索；两套静态目录同步重建 |

否决：③ Funnel（访客零鉴权 + CT 公开机器名）、⑤ 端口转发（`progress.md:203` 底线）。

## 7. 待用户裁决点 F1–F18

- **F0 前置事实**：先问爸爸要的是"像妻子那样和我说话"还是"能听到她、说说话"——推荐先问，决定 F-丙 是否已够。
- **F1 受众**：是否对爸爸第二次覆盖"家人向默认 NO-GO"并开独立入口——推荐：先 F-丙，护栏/同意/Phase 15 分区到位后再评估 F-甲。
- **F2 排序**：8A-2b 是否恢复为爸爸使用的硬前提——与 09-07 "Phase 15 先于 8A-2b"（`task_plan.md:186`、spec:20）冲突；推荐：是。
- **F3 关系层**：A 诚实标注（儿子建档、对话者是她的丈夫、私事记不清）/ B 用 150–290 条邻接语料伪造"丈夫面孔"/ C 等多视角数据——推荐 A。
- **F4 数据可见范围与 sessions.json 形态**：是否接受爸爸设备下载全部语料 + 单一 `sessions.json` 内儿子往次对话全文（spec:44、:83）——推荐：在 Phase 15 规格改为 `sessions_<viewer>.json` 分文件（最低）或服务端鉴权端点；不接受语料下载则 F-乙 裁剪站；接受则须明示并修检索 sender=subject。
- **F5 sessions 记录与 Tier**：爸爸会话 ①全记 ②默认不记 user 文本、只记计数与她的回复 ③爸爸自选——推荐 ②；无论哪项明示"记录落在儿子电脑上"；爸爸话语在第二纪元标为"Tier-2 家人证言"，独立于"用户话语=Tier-2"（`docs/GENERALIZATION.md:145` 语义对爸爸不成立）——推荐是。
- **F6 dad 页跨会话连续性**：规格默认对任何 viewer 启用第四检索源与"上次对话卡"（spec:139-141）——推荐 dad 页默认关（沉浸增量，`GENERALIZATION.md:19` 依恋风险最大），或 F5 ② 下仅保留她的回复。
- **F7 接入路径**：⓪ 用户账号登录 vs ② 节点共享 vs ④ Cloudflare——推荐 ②；同住则 LAN；⓪ 仅在爸爸无可用身份账号且用户接受凭据落在其设备时。
- **F8 三件安全事**：现在就开防火墙、`--token` + 页面 X-TTS-Token、key 走 PC 代理——推荐全做。
- **F9 语音**：是否给语音、语域 wu 还是 mandarin、是否为 dad 版下调 `MSG_MAX_VOICE`（TTS 排队）——推荐给、wu、下调至 6 待实测。
- **F10 冲突面**：persona 第七节 5–6 行涉丈夫内容与 Tier-1 涉爸爸记忆逐条裁决——推荐原则"保留脾气特质、不主动转述她对儿子讲的关于他的负面话、被问不否认、不编造吵架事件"。
- **F11 禁区与措辞**：`relationship.json` 现有 taboo_topics 1 条是否沿用、新增哪些（夫妻私密/病程末期/财务等）；"记不清"措辞用她口吻写几条供认可——推荐用户列清单、DeepSeek 起草措辞、用户逐条认可。
- **F12 facets 存放**：扩展 `relationship.json` vs 新建 `persona/facets.json`（`GENERALIZATION.md:104` 设想后者）；是否与 relationship.json 一样不进 archive_dist（`docs/PIPELINE.md:222`）——推荐新建 facets.json、不进 dist。
- **F13 rhythm**：dad 版剔除私聊 reply_latency 行、标注来源，还是按家庭群重算 `rhythm_dad.json`（`build_rhythm.py:242-253` 只算私聊；家庭群中位 20 字 vs 私聊 15 字）——推荐重算，低成本 Tier-2 分面材料。
- **F14 "不假装真人"对老人的表述**：①现状被问才答 + 小字 ②每次打开大字说明卡 ③首轮由她合成声自述是模拟——推荐 ②，③ 由用户听感决定。
- **F15 知情同意形式**：当面演示 + 大字一页 + 日期写入 `relationship.dad.json`（G0）；同时记录他作为配偶对声音使用的同意——推荐是。
- **F16 爸爸作为贡献者**：请他做 Tier-1 确认人并导出他手机里的聊天——推荐是，铁律 2.3 下唯一"让档案更完整"的项。
- **F17 覆盖决策显式化**：把 #23 式"知情自决单次覆盖 NO-GO"写入 progress 为显式决策（含日期、范围、复核日）——推荐是。
- **F18 运维与协议**：为爸爸推翻 D5（自启 + 自动登录 + Update 策略）；先完成用户自己 iPhone 的 A1/8B-4；另立爸爸版告别/降级协议；复核人=用户 + 另一位家人；三个月复核与 2026-11-28 对齐——推荐：若开独立入口则全部必须。

## 8. 与现有裁决的关系

- **D1–D5（`task_plan.md:167`）**：D1 A1 与"8A-2b 先行"直接沿用；D2 "https 跳过"在 Tailscale 下仍成立，走 F-乙 则需重开；D4 不受影响；**D5 "手动拉起"与"给爸爸用"不兼容**（F18）。ios 研究把"受众只有用户本人，Tailscale 私网"列为 A1 安全前提（`docs/research/ios-app-deployment.md:95`），#24 正是撤销这一前提。
- **E1 受众问题（`docs/research/build-app-productization.md`，待裁决）**：#24 是 E1 的具体实例——第一个"少数人"；"把铁律 2 从文档变功能是给任何第二个人用的前提"（:11、:123）直接约束本任务。
- **家人向默认 NO-GO（`dsh-im-analysis.md:74-75`）**：命中"第三方受众"成分，不命中"常驻/欺骗"成分；§4 判定框架即原文"全员知情同意后重新评估"的内容。
- **#23（09-06）**：已是用户知情下对 NO-GO 的单次覆盖（`docs/status-2026-09-07.md:177`）；爸爸对六段语音的反馈尚未入档（:105），应先于 #24 决策；F17 要求此类覆盖今后显式入档。
- **Phase 15 跨会话记忆（`task_plan.md:186`，规格已落盘未提交）**：规格已含 viewer 分区、`--viewer` 默认 owner、两 viewer 互不可见测试、对 #24 的预留（spec:32、:78、:134、:180、:202、:209），#24 复用而非重立；本报告新增的修订请求只有两条——单文件全文暴露面（F4）与 dad 页"上次对话卡"默认（F6）。规格 :20 记"用户决定先于 8A-2b"，与 F2 冲突需用户重裁。
- **GENERALIZATION 轴四 facets（`docs/GENERALIZATION.md:100-104`）**：设计已预留"以某人的面孔对话"，但明言多视角导入后才完整成立；F-丙 的多视角导出正是其数据前提。

## 9. 来源与核实状态

**汇编者本轮复核（只读，2026-09-07，工作树）**：`docs/superpowers/specs/2026-09-07-cross-session-memory-design.md:20、:24、:26、:32、:44、:78、:83、:117、:125、:134、:139-141、:152、:180、:202、:209`（全部逐行核对）；`tools/build_companion_page.py:165、:171、:216、:240、:246、:259、:265、:683-690、:820、:875、:1211、:1626、:1629、:1696`；`tools/tts_server.py:34、:189、:256、:516`；`tools/build_archive.py:138、:145`；`prompts/chat_system.zh.md:41`（"对话者知道这是档案"，初稿误引 :38）；`docs/research/build-app-productization.md:84`（同意闸门行，初稿误引 :85）；`task_plan.md:186、:189-190`（产出路径在 :190）；`docs/HANDOFF.md:14、:15、:25、:159`；`progress.md:203、:459`；`docs/status-2026-09-07.md:105、:112、:175、:177`。

**版本状态提示**：`git status` 显示 `docs/status-2026-09-07.md` 与 `docs/superpowers/` 为 untracked，`docs/HANDOFF.md`、`progress.md`、`task_plan.md`、`tools/build_chat_page.py`、`tools/build_companion_page.py` 有未提交改动（companion 为 :740/:751/:1629/:1643 四处单行 no-cache hotfix，行号未移位）。本文行号以工作树为准；汇编入库时应确认上述文件随本报告一并提交，否则引用悬空。

**五视角活体探针（一手命令输出，未二次复核）**：防火墙/网络配置文件/netstat/计划任务/注册表/事件日志/powercfg/nvidia-smi；`tailscale status/netcheck/serve status`；UIF 计数与时间邻接统计（三视角口径不一，已取区间）；tts_server 日志时长统计；sessions 146 条字段统计（page 72/无 page 74）。

**外部文档（五视角 WebFetch，未复核）**：Tailscale Funnel/Sharing/HTTPS/SSO/pricing KB 与 GitHub #12788/#19625/#10136；Cloudflare Access/ports/524/trycloudflare 文档；arXiv 2603.01017 摘要；KLoSA（OUP Innovate Aging igaf035）；Cambridge 2024 deadbot 新闻页与 Hollanek & Nowaczyk-Basińska 2024。

**unverifiable（须实测或用户口头确认）**：爸爸的设备/系统/账号/所在地/是否同住/是否照护者/是否保有与她的聊天/他想要的是什么；家庭群 @ 的 3 字对象与家庭群第三发送者账号是否=爸爸（仅由 `HANDOFF.md:269` 群成员推断）；sender "5" 110 条的性质；"她直接对爸爸说的条数"（UIF 无 addressee，只有 150–290 的邻接近似）；Windows 提权 userspace 下 `tailscale serve/funnel` 能否签证书；*.ts.net 与 Cloudflare Access 从爸爸 ISP 的可达性；Cloudflare 125 s 超时对 SSE 的计时方式；iOS 26 对 http 站"作为 Web App 打开"的行为；腾讯电脑管家是否替代拦截 :8020/:8022；DeepSeek 同账号能否开第二把 key；ScienceDirect S1876201826001401（403）；爸爸对 #23 六段语音的反馈；ARSO 状态。

**产出位置**：`task_plan.md:190` 已指定 `docs/research/dad-husband-companion.md`；本文为正文，落盘由主会话执行（本汇编未写任何文件）。