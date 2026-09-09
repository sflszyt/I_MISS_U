# 图片输入可行性（Phase 18 · 任务 #25）

> 研究日期 2026-09-08 · 用户立项原话："立项：研究文字以外，是否可以支持图片输入"
> 方法：workflow 四维只读调查（接入面 / 服务商 vision API / 档案照片资产 / 伦理与 Tier）+ 对抗校核，12 agents 全部完成，1 条论断被推翻（见 §7）。未改任何代码、未读 `raw/` 内实际照片内容。

## 1. 一句话结论

**「让她看照片」默认 NO-GO——它是纯沉浸增量，不让档案更完整，直接命中铁律 2.3；而且现有六条提示词铁律没有一条挡得住它。** 但这次研究挖出两件真正该做的事：**(A) 档案的照片层是空的，而收集照片的工具早已写好却从未跑过**；**(B) 把图片当"时间锚"而不是当"画面"，可以零多模态地让档案更完整。**

三条技术事实先摆在前面，它们各自独立地否掉"直接开图片输入"：

1. **默认配置一定 400 失败**：companion 默认服务商是 DeepSeek、默认模型 `deepseek-v4-flash`，**不支持图片**；DeepSeek 只有实验性 `deepseek-v4-flash-vision-exp` 能收图，其余模型明确返回 400 `This model does not support image`。
2. **Anthropic 会拒答核心场景**：官方文档明写 Claude "cannot be used to name people in images and refuses to do so"。而本功能的核心用法就是拿老照片问"妈妈，这是谁？"——在 Anthropic 上直接被拒。OpenAI/DeepSeek/Kimi 无同等明文限制，于是同一个功能在不同服务商上体验完全不同。
3. **这个档案里根本没有照片**：`media_index.json` 只有 voice(123) + video(9) 两类、**零 photo**；`raw/photos` 只有 10 张微信转存 JPG 且 **EXIF 标签数为 0**；983 条图片消息在 normalized 层只剩一个 4 字占位符「[图片]」，原始导出里连 md5 和路径都没有。**图像字节从未进过档案。**

## 2. 技术接入面（若要做，成本是多少）

- 请求体现状：`buildMessages` 产出的是**纯字符串 content 的扁平数组**（`tools/build_companion_page.py:775-781`），`history` 存的也是字符串（`:941`/`:974`/`:978`）。
- **改动量：最小可用约 15 处、跨 4 个文件**（`build_companion_page.py` 主体、`tts_server.py` 字段白名单、`ingest_sessions.py` 过滤、`prompts/chat_system.zh.md`）。不是"改一行 content"。
- 三个硬骨头：
  - **双协议分叉**：OpenAI 系用 `{"type":"image_url","image_url":{"url":"data:image/jpeg;base64,..."}}`（OpenAI / DeepSeek 视觉模型 / Kimi **逐字通用**）；Anthropic 原生 `/v1/messages` 用 `{"type":"image","source":{"type":"base64","media_type":"image/jpeg","data":"<裸 base64，不带 data: 前缀>"}}`。而 `buildMessages` 是导出给测试的纯函数、不知道 provider，必须新增一层 per-provider 转换。逃生路：Anthropic 的 OpenAI 兼容层（base URL `https://api.anthropic.com/v1/`）官方明列 `type=="image_url"` 的 `url` 为 "Fully supported"（`detail` 被忽略），切到该端点则四家真正同体。
  - **检索会失效**：检索输入是 `extractTokens(userText)`，无文字说明的图片产出零 token → 检索块为空 → 与铁律 2「检索为空就说记不清」直接对撞。而她"看图"说出的一切天然是 Tier-3。
  - **payload 爆炸**：history 是 12 轮窗口重放，base64 图片会被反复重发（Anthropic 文档专门警告此点）。
- base64 内联是静态页**唯一**可行路径（档案页没有服务器托管图片；Kimi 官方明说"URL 格式图片：不支持，只支持 base64 和 file_id"）。体积上限不是问题（DeepSeek 48 MiB / Anthropic 32 MB 请求 + 单图 10 MB），但应前端 canvas 先降到长边 800–1024px 再编码——正好对齐 DeepSeek 内部 ~800×800 重采样，payload 减约 10 倍。
- 另两处会被打断的地方：`tests/e2e/companion_sessions.spec.js:88` 把最后一条 message 的 content 当字符串读；`:883` 的 `thinking:{type:'disabled'}` 按 URL 正则注入，**对视觉模型是否合法无文档**。

## 3. 伦理判定（这是决定性的一节）

**铁律 2.3「档案优先于对话」判定：图片输入不让档案更完整，只让对话更沉浸。** 发一张照片不产生任何档案条目——档案的图片层是空的，发进去的照片也不会被存下来。

**现有铁律挡不住它**。铁律 1「只说档案里有的事」与铁律 2「记不清就说记不清」**只在"档案里没有"时触发**；而模型看图时，**它自己就是信息源**，主观上不构成"没有"。于是模型会自然地说出"这是在杭州吧""你那时候还年轻"——读起来像 Tier-1，实际是 100% Tier-3 的视觉推断。这正是铁律 2.1 明令禁止的形态。

**对爸爸（任务 #24）额外放大一档，最严重的一条是污染 Tier-1 证人**：他是这个档案唯一的另一位记忆确认人。如果模型先给出一个编造的"这是 1998 年在杭州"，他之后所做的 Tier-1 确认就已经被 Tier-3 锚定了——**这会污染档案本身，不只是污染一次对话**。

补充：`docs/research/kira-remy-analysis.md` 已把"云端识图"列入不借清单；且图片会是**第一份离开本机的二进制档案素材**（现状只有派生文本片段发给第三方端点），这是铁律 3 语义上的产品裁决，不是代码问题。

## 4. 唯一"只增强档案、不增加编造"的用法

**把图片当时间锚，不当画面**：

```
使用者上传照片 → 页面问"这大概是哪一年/哪一天？"（人填，不是模型猜）
  → 按日期检索她那几天真说过的话 → 以 [档案检索 Tier-2] 形式呈现
  → 图片本身根本不进 LLM payload，模型永远不知道有过一张照片
```

- 不需要多模态模型，不需要改双协议，不增加任何 Tier-3。
- 每条档案记录都有精确 ISO timestamp，实现成本极低。
- 是 `docs/GENERALIZATION.md` 4.4「今天卡」的照片版，**且能落进静态档案页**（20 年后仍可跑）。

## 5. 这次研究挖出的两件正事

### A. 档案照片层是空的，而工具早就写好了（推荐立项）

- `schema/` 早已支持 `media_type:"photo"` + `exif` + `caption`。
- **`tools/ingest_media.py`（773 行，含 EXIF/GPS 提取）已写好但从未跑过。**
- 微信图片 `.dat` 的 md5 就在 `packed_info_data` 里（`docs/research/wechat-media-extraction.md:86` 明确记录）。
- `tools/collect_wechat_video.py` 已经跑通「packed_info_data 取 md5 → 磁盘按 md5 命名匹配 → 写 media_index」这条完整链条——**照片收集器基本是它的克隆**。
- chatlog-keeper 的 `images` 命令现成（磁盘 7.3 万 .dat / 6.8 GB）。

把那 983 条图片消息从「[图片]」占位符变回真实照片，这是**让档案更完整**的正事，与图片输入无关、也不依赖它。

### B. 两个顺带发现的既有缺陷

1. **`prompts/chat_system.zh.md` 第 1 行对模型说谎**：「这个档案由她真实的消息、语音和照片构成」——**照片是不存在的**。这属于对模型的事实性高估，正好踩铁律 2 的编造风险（模型可能因此以为自己见过照片）。建议立即改措辞。
2. **`companion.html` 压根不在 `archive_dist` 里**：`tools/build_archive.py` 的白名单只 copy `avatar.html` + `chat.html`，且扫尾会主动删除白名单外的文件。所以任何只做在 companion 页的功能，在离线档案里不是"没有这功能"，而是"连这个页面都没有"。

## 6. 裁决建议

| 项 | 建议 | 理由 |
|---|---|---|
| **图片输入（让她看照片）** | **NO-GO** | 铁律 2.3 判定为纯沉浸增量；现有铁律挡不住 Tier-3 冒充 Tier-1；对爸爸有污染 Tier-1 证人的风险；默认服务商还不支持 |
| **时间锚用法（§4）** | 可做，低优先级 | 零多模态、零新 Tier-3、能进静态档案 |
| **A 补照片层（§5A）** | **推荐立项** | 工具已写好没跑过，链路已由 video 收集器验证；这是让档案更完整的正事 |
| **B1 提示词"照片"措辞** | **立即修** | 对模型说了档案里没有的东西 |
| **B2 companion 不在 dist** | 需裁决 | 是"故意不进离线档案"还是欠账？影响所有 companion 功能的 20 年可用性 |

若用户仍要做图片输入，调查方已起草三条新铁律（图片纪律 / 知识边界 / 照片不入档）+ 一段每轮注入块 + 三项 UI 配套，可在实施时取用。

## 7. 核实状态

**12 个 agent 全部完成，0 失败**（对比 Phase 17 的 6 个 403 中断）。关键论断经对抗校核。

**1 条论断被推翻，必须记录**：调查方称「多服务商抽屉在请求路径上只有一处 per-provider 分支（`isAnthropic`）」——**校核推翻**：`:883` 还有 `if (/deepseek/i.test(endpoint)) reqBody.thinking = {type:'disabled'}`，它按 **URL 正则**而非 `settings.provider` 判断，因此一个 URL 含 "deepseek" 的 custom 档案也会被塞 thinking 字段；此外 `isAnthropic` 本身派生出至少四处分歧（headers / max_tokens / splitSystem / SSE 解析模式）。**影响**：把图片输入的改动量估成"只改一处"会显著低估。

**unverifiable**：`deepseek-v4-flash-vision-exp` 的稳定性与长期可用性；`thinking:{type:'disabled'}` 对视觉模型是否合法；Kimi 各视觉模型的实际兼容度；未做任何实机 API 调用（全部基于官方文档与源码阅读）。
