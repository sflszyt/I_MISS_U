# 交接文档（HANDOFF）

> 给下一个会话的 Claude（或未来的自己）。最后更新：**2026-09-09，T14-1/T14-2 完成（token 落盘 + 服务启动编排，见 ⓪¹²）**。上一版：2026-09-07，提交前全量刷新：#22 研究 a/b 收口（a 已裁决）+ 8B-10 语音条分条 + 8B-11 起音淡入 + #23 给爸爸六段语音**。最先看 ⓪¹⁰。（09-02 后补：进度全景核对（workflow 六路，输出未落盘）后修文档失真——四项待办移除日期更正为 09-01、⓪⁷/二章/六章过期陈述加标注、下回合列表 09-02 刷新）。
> 读这份之前先读 `CLAUDE.md`（铁律），再读仓库根的 `task_plan.md` / `progress.md` / `findings.md`（MVP 计划与实时状态）。研究依据在 `docs/research/`。

## ⓪¹² 增补（2026-09-09：T14-1/T14-2 完成——token 落盘 + 服务启动编排，最先看这段）

> 一句话：**重启后先把服务拉起来这件事，代码层已就绪并通过验收；但还没接上开机自启，也没碰隧道。**用户本会话裁决：自启方式取**开 Windows 自动登录**（已告知代价：物理接触电脑即进桌面、people/ 档案敞开）；token **加 `--tokens-file`**。

### 1. 已交付

| 文件 | 改动 | 验收 |
|---|---|---|
| `tools/tts_server.py` | `--tokens-file`，+61/-3 | DeepSeek 2 轮 → Codex REJECT→**ACCEPT** |
| `tools/llm_proxy.py` | `--tokens-file`，+52/-3 | DeepSeek 2 轮 → Codex REJECT→**ACCEPT** |
| `scripts/start_services.ps1` | 新建 1031 行 | DeepSeek 9 轮 → Codex 3×REJECT→**ACCEPT** |

**安全目标已落地**：现在跑着的 tts/llm_proxy 命令行只有 `--tokens-file <路径>`，实测零 token 明文（之前 token 同时暴露在进程命令行与即将创建的计划任务 XML 中）。

### 2. start_services.ps1 怎么用

```
scripts\start_services.ps1                启动全部（幂等，已跑的跳过）
scripts\start_services.ps1 -Status        只看状态，永远 exit 0
scripts\start_services.ps1 -Stop          停全部（逆序，含 tts 父子孙进程树）
scripts\start_services.ps1 -SkipTunnel    不碰隧道（本地测试用）
```

退出码：0 全就绪 / 1 有服务失败 / 2 前置路径检查不过 / 3 拿不到单实例锁。日志在 `logs/<name>.<yyyyMMdd-HHmmss>.{out,err}.log`（保留最近 10 组）+ `logs/start_services.log`。

### 3. 两个必须知道的缺口

1. **隧道路径没真跑过**。启 cloudflared 等于开公网入口，属外部可见动作，未经机主授权不做；且 T14-5 自动登录与真机验收都没做。所以「已有进程→重启→60s 注册判据」这条链只有静态审查。
2. **`-Status` 里的 tunnel 只是进程存在检查**，不证明已连上（Codex 特别点出）。运维时按 "process running" 理解，别当成「入口可用」。

另：tunnel 现在**每次 start 都重启**（为确保连接状态可确认），是刻意牺牲幂等换可靠性。

### 4. 下回合接着做

1. **T14-3 注册登录自启任务**（计划任务或启动文件夹，配合已裁决的自动登录）
2. **T14-4 冷启动/离线降级页**「她今天不在」
3. **T14-5 自动登录操作步骤**——用 Sysinternals Autologon（存 LSA secrets）而非直写注册表 `DefaultPassword` 明文；**Claude 不接触密码，步骤交用户自行执行**。现 ActiveHours 9→2，重启窗口=凌晨 2-9 点
4. 然后才是 T12b 老人 UX / T12c 主屏图标 / T13 rhythm_dad / archive_dist 重打包 / 爸爸真机验收

### 5. 环境现场（本会话结束时）

- **在跑**：:8020 儿子站、:8021 爸爸站、:8022 tts（e14，`--tokens-file`）、:8023 llm-proxy（持真 key，`--tokens-file`）——四者均由 `start_services.ps1` 拉起
- **未跑**：cloudflared 隧道
- 工程教训见 `findings.md` 末尾「T14 运维自启教训」（PowerShell 单元素数组展开、判重写错方向=死循环、区域规格 vs 全文回显分界线等）

## ⓪¹¹ 增补（2026-09-08→09：任务 #24 走 F-乙 全线开工，端到端跑通，最先看这段）

> 一句话：**爸爸以丈夫角色对话的独立入口，从"研究报告"变成"端到端能聊的东西"**。域名 → Cloudflare 隧道 → Access → 三路由 → 独立站 + LLM 代理 + TTS token + 说明卡，全链路已用真 key + 真 GPU 跑通。**尚未上线**（隧道未启、代理未常驻），差 T14 运维自启与真机验收。

### 1. 用户一次性裁决 19 项（09-08），选定 F-乙

`docs/research/dad-husband-companion.md` 的 F0–F18 全部拍板，完整表格见 `task_plan.md` Phase 16。**三项构成对 §4 GO/NO-GO 框架的显式覆盖**（已按裁决⑥写入 `progress.md` 作为显式决策，含复核日 2026-11-28）：

| 覆盖项 | 裁决 | 已告知的后果 |
|---|---|---|
| 8A-2b 护栏 b/d/e | **先上线，护栏后补** | 第一个非开发者受众将在无关窗道别/无限速/无使用统计下使用；(c) 因大字说明卡裁决而提前落地 |
| 数据范围 | **全量不裁剪** | 爸爸设备可取得母子一对一 6,835 条；T11 检索修复缓解"被当成她的话复述"，挡不住直接翻数据文件 |
| 知情同意 | **跳过当面演示，直接给链接** | 曾是唯一未被豁免的闸门。缓解：页面内大字说明卡仍实现，七条告知每次打开必须点过 |

其余关键裁决：关系层 **A 诚实标注**；语音 **wu 域 + MSG_MAX_VOICE 12**；会话**全记**含爸爸原话；**上次对话卡开**；禁区**只禁"任何指向未来的话"**（A 组四条"都讲没事"——注意**不设禁区 ≠ 可编造**，铁律 1 与追加铁律 8 不变）；"记不清"措辞**不写死**（Claude 拟的三条未验证沪语已弃用）。

### 2. 两个新研究（都 NO-GO，但各挖出一件正事）

- **Phase 17 VoiceStudio**（`docs/research/voicestudio-vs-local-tts.md`）：**不能取代引擎层**。它的 CosyVoice adapter 只接受**模型目录**（`OMNIVOICE_COSYVOICE_MODEL`），无注入外部 state_dict 的钩子；我们的音色是运行时 `llm.load_state_dict(filtered, strict=False)` 打上去的补丁 → 按它的方式跑加载的是 WenetSpeech-Wu **基座不是她**。另有 SFT 分支硬编码 `spks[0]`、`LANG_TAGS` 无 `<|wuyu|>`、打包版无 CosyVoice 运行时安装路径。两条伤档案的默认行为：**AudioSeal 水印默认开**、**输出归一化到 −2.0 dBFS**。**AGPL-3.0 与 F-乙 直接相关**（服务开给他人访问会传染服务层）。可借鉴：`/ws/tts` 流式思路、`/v1/audio/speech` 契约、loopback 不鉴权三道闸。
- **Phase 18 图片输入**（`docs/research/companion-image-input.md`）：**默认 NO-GO**。铁律 2.3 判定为纯沉浸增量（发照片不产生任何档案条目）；**现有六条铁律没有一条挡得住**——铁律 1/2 只在"档案里没有"时触发，而模型看图时它自己就是信息源。对爸爸额外风险=**污染 Tier-1 证人**（模型先编"这是 1998 年在杭州"，他之后的确认已被 Tier-3 锚定）。技术上还有三条独立否决（DeepSeek 默认模型不支持图片、Anthropic 明写拒绝指认图中人物、改动约 15 处且检索会失效）。**挖出的正事：档案照片层是空的**——`media_index.json` 零 photo、983 条图片消息只剩「[图片]」占位符，而 `tools/ingest_media.py`（773 行含 EXIF 提取）**已写好从未跑过**、微信图片 md5 就在 `packed_info_data`、`collect_wechat_video.py` 已跑通同一条链。**另发现 `prompts/chat_system.zh.md:1` 对模型说"档案由消息、语音和照片构成"而照片不存在**（本次已修）。

### 3. F-乙 基础设施（已就位，未启动）

- 域名 `justmissingyou.com`（用户注册）；命名隧道 `imissu-father`；CNAME `dad.justmissingyou.com`；Access 邮箱一次性 PIN + 1 个月会话，白名单记于 `people/mama_for_father/config/`（gitignore）
- **Access 全路径拦截已实测**：`/`、`/health`、`POST /tts` 均 302 跳登录页
- `~/.cloudflared/config.yml` 三路由（`tunnel ingress rule` 逐条验证）：`^/v1/chat/completions$`→:8023 / `^/(tts|health|session)$`→:8022 / 其余→:8021
- **`protocol: http2` 已钉死**：QUIC 在本机 Surfshark WireGuard 下每 ~90 s 断（`no recent network activity`）
- 用户把 cloudflared 加入 Surfshark Bypasser → 边缘落点由 `ewr`（美东）改为 `hkg`（香港）
- **腾讯电脑管家不拦 cloudflared**（与它拦 Tailscale 的 SYSTEM 服务不同）
- ⚠️ **暴露事件（09-08，已关闭）**：POC 期间 ingress 把 `/tts|/health|/session` 指向**正在运行的真实 tts_server**（当时 `--token` 空、零鉴权），窗口约 3–4 分钟。tts_server 访问日志被禁用（`:250-251`），**无法证明零访问**。纪律：Access 生效 + token 开启两件都完成前，隧道不长跑

### 4. 代码产出（全部 DeepSeek 写 + Codex 审 ACCEPT）

| 任务 | 文件 | 要点 |
|---|---|---|
| T7 | `build_chat_context.py` +141 | `--relationship` + 三占位符（`archive_builder_zh`/`relationship_block`/`taboo_block`）；顺带修好 `taboo_topics` 从未进提示词的既有缺陷 |
| T8 | `build_companion_page.py` | 六项参数化：`--context-path`/`--out-name`/`--lang`/`--tts-origin`/`--tts-token`/viewer 隔离 |
| T9 | `tts_server.py` +99 | `--tokens viewer:token`、`hmac.compare_digest`、**服务端认定 viewer**（客户端 body 里的 viewer 一律被覆盖） |
| T10b | `llm_proxy.py` **新建 366 行** | PC 持 key、爸爸端零凭据；token 鉴权 + rpm/daily 限速 + 字段白名单 + model/max_tokens 强制覆盖 + SSE 流式；日志**绝不记 messages** |
| T10c | `build_companion_page.py` | `--llm-proxy`（强制要求 `--tts-token`）；代理模式下 `settingsComplete` 短路、走代理分支发 `X-TTS-Token` 不发 Authorization、抽屉三项 `removeChild`。**HTML 一个字符没改** |
| T11 | `build_companion_page.py` + `build_chat_page.py` | 检索只取 `sender=subject` |
| T12a | `build_companion_page.py` | `--intro-card` + `--intro-builder` 大字说明卡 |

新增 `prompts/chat_system.husband.zh.md`（72 行，A 诚实标注）：三条追加铁律——8「你们两个人之间的事我一概不知道，不是想不起来是档案里没有」、9「她对儿子讲起你的那些话不主动端出来，被问不否认不添油加醋、绝不编造任何一次具体争吵」、10 禁区。

**每个改动都验证"默认参数产出与基线逐字节相同"**，儿子版 companion.html 全程零影响。

### 5. 端到端实测（09-09，真 key + 真 GPU，本地模拟 ingress）

链路：页面（零凭据）→ 代理 → DeepSeek → 分条 → TTS(wu) → 语音条 → 会话日志。
真实回复：「还能哪能，老样子呀」「今朝呒没高烧，算是太平了」「[捂脸] 侬倒记得来问一声」——上海话、三条分发、各带语音条，第三条带小埋怨（铁律 4 要的）。
会话落盘每条 `viewer=father`（服务端认定）、`page=companion_father`。测试会话已清理并重新 ingest。

### 6. 本会话血泪教训（新增工艺红线）

1. **字符串存在 ≠ 位置正确**：T8 首轮我只 grep 数 `X-TTS-Token` 出现 3 次就判通过，Codex 发现 token 分支**根本不工作**（占位符残留、`var TTS_TOKEN` 未生成、header 落在 fetch options 顶层而非 headers 内）。改用**结构级探针**（残留占位符 / 声明计数 / `headers:\s*\{[^{}]*'X-TTS-Token'[^{}]*\}` 正则 / 提取 `<script>` 跑 `node --check`）才抓到后续的 `},,` 双逗号。
2. **`py_compile` 与静态审查发现不了运行时结构错误**：`llm_proxy` 五轮里前四轮全是致命 bug，全靠**活体测试**（真起服务打请求）才暴露——`ProxyServer` 从未设置 `proxy` 属性、`self.rfile.read(MAX_BODY+1)` 在 keep-alive 下阻塞到客户端超时。
3. **★ 冒烟测试的假象**：`llm_proxy` 流式响应**既无 `Content-Length` 也无 `Connection: close`**，客户端收到 `[DONE]` 后仍在等 → curl **30072 ms**、页面永远卡"正在输入"，而代理日志写着 `status=200 dur_ms=1784`。**我之前用 `curl -N --max-time 15` 看到块与 `[DONE]` 就判"流式通过"，那其实是超时退出**。只有真的用浏览器跑一遍才暴露。Codex 两轮静态审查也没看出来。
4. **占位符相邻会被正则贪婪吞掉**：`__TTS_TOKEN_LINE____LLM_PROXY_LINE__` 中间全是 `A-Z` 与 `_`，被 `__[A-Z_]+__` 当成**一个**未知占位符原样留下 → 两个都不替换、页面 JS 语法错误。解法是让占位符不相邻（不动正则）。
5. **规格让 DeepSeek 改 HTML 结构 = 与"逐字节兼容"天然冲突**：T10c 首版因此暴涨 +458 行、出现两套重复实现。改成"纯 JS 注入、一行 HTML 不碰"后一次做对方向。
6. **Git Bash 会把 `/llm/v1/...` 转成 `C:/Program Files/Git/llm/...`**（MSYS 路径转换），测 CLI 路径参数要加 `MSYS_NO_PATHCONV=1`。
7. DeepSeek 连续三轮把 `/* ===== streamRequest（唯一改动…）===== */` 注释改短，最后由 Claude 用脚本原样恢复（已声明，仅此一行文本）。

### 7. 环境现场（09-09 会话结束时）

- **在跑**：`:8020` http.server（archive_out，儿子站）、`:8021` http.server（`people/mama_for_father/site`，爸爸站，仅 127.0.0.1）、`:8022` tts_server（**已重启并启用 `--tokens`，`token=multi(2 viewers)`**）
- **未跑**：cloudflared 隧道、`llm_proxy`（持真 key，测完即停）
- 两个页面已用各自 token 重新生成：儿子版 `--tts-token <owner>`；爸爸版 `--viewer father --context-path data_father/chat_context.json --lang wu --tts-origin same --tts-token <father> --intro-card --intro-builder 儿子 --llm-proxy /v1/chat/completions`
- `people/mama_for_father/`：`config/`（relationship.father.json / tokens.env / pending_user_approval.md）+ `site/`（companion.html、avatar.html、`data` 目录联接→archive_out/data、`data_father/chat_context.json`）
- tts_server 启动方式：`~/venvs/cosyvoice/Scripts/python.exe -X utf8 tools/tts_server.py --tokens owner:<T> ,father:<T>`（脱钩 Start-Process；**注意本机 `python` 命令缺 numpy，必须用这个 venv**）

### 下回合建议顺序（09-09 刷新，覆盖下方各旧版）

1. **T14 运维自启**（上线前最后硬门槛，用户已裁决"全做"）：三服务 + 隧道登录自启 + 自动登录 + Windows Update 活动时段 + 冷启动探活重试 + 「她今天不在」离线页。**补丁夜重启后不自启 = 爸爸打开白页**
2. **T12b 老人 UX 其余项**：抽屉锁定 / 错误文案人话化 / TTS 周期重探 / **Access session 过期时 fetch 收到 302 跳登录页而非 401 的降级**（会拿到 HTML 而不是 MP3）
3. **T12c A1 主屏图标**（apple-touch-icon + manifest）——顺带消灭一直刷的 `favicon.ico` 404
4. T13 `rhythm_dad` 按家庭群语料重算（家庭群中位 20 字 vs 私聊 15 字）
5. **archive_dist 重打包**（`chat.html` 的 T11 检索修复还没进离线档案）
6. 爸爸手机真机验收（经隧道 + Access）
7. 待用户裁决：VoiceStudio 的 P1（流式改造立项）/ P2（`/v1/audio/speech` 兼容端点）/ P3（记入 GENERALIZATION 作泛化线候选）；图片输入的 NO-GO 认可 / 时间锚用法 / **A 补档案照片层是否立项**

## ⓪¹⁰ 增补（2026-09-02→07：#22 研究 + 8B-10/8B-11 + #23，最先看这段）

1. **#22 研究收口（09-02/03）**：a `docs/research/ios-app-deployment.md`——companion 对外只依赖 LLM(BYOK) + :8022 三路由；iOS 26 主屏网页默认作为 Web App 打开，http 无 secure-context 需求 → **A1 加 apple-touch-icon 即成手机专属入口**；A2 WKWebView 壳技术可行但收益全在 desktop-companion 6.2③ 禁区；她的声音出不了 4090（端侧运行时无 CosyVoice2 SFT）；云 GPU NO-GO。**用户裁决 D1–D5：A1 接受 + 8A-2b 先行 / https 跳过 / Phase 13 有声档案立项 / A2 暂不做 / PC 常开手动拉起。** b `docs/research/build-app-productization.md`——"建档工作台"而非"产出 companion 的自动化 App"；三条硬边界（微信取 key / 4090 / 判断力工作）；§4 把关功能表是 8A-2b 超集；分期 P0–P3。**E1–E6 待用户裁决。**
2. **8B-10 微信式语音条 + ≤30 字分条（09-05→06）**：用户看 sessions 日志后两条反馈。根因 `TTS_TOTAL_MAX=240` 整段跳过语音（7/17 条 skipped_length）；另发现 `build_rhythm_block` 读的键全不在 rhythm.json（模型从未见"中位 17 字/69% 单条/70% 无句末标点"）。现状：`splitMessages`（换行→句末→子句→硬切且不拆代理对，≤30）→ 每条独立 `.bubble.subject`，三点占位串行；前 MSG_MAX_VOICE=12 条各自 `/tts`（30 s 超时盖到 body）；语音条 `.voice-bar`+`.voice-text`（抽屉开关，键 storageKey+'_ui'）；回放/停止（`stopReplay` 模块级，回合进行中不回放，被拒当前条点击=按 ▶）；`vt.waiting` 文字延时闸门；内部气泡 `noDivider`；标签/标点-only 不送 TTS；Blob 保留 60 条；sessions simulacrum 记 `tts∈{requested,partial,unavailable}`+`messages`。工艺：DeepSeek 区域规格两轮 + Claude 声明 hotfix + 三视角 workflow 审查（26 发现→10 确认修）+ Codex 三轮 ACCEPT；E2E 两套 Playwright route-mock 全绿；单测 14 例。提示词加"分条发：一行一条 ≤30 字"。
3. **8B-11 起音爆音淡入（09-07）**：模型每次开口前 ~15 ms 爆音（两语域/companion/批量签名一致）→ tts_server `soften_onsets`（5 ms 帧起音检测，30 ms 升余弦淡入，`--onset-fade-ms` 0 关）；实测起音比 2.5→0.7。DeepSeek 两轮 + Codex ACCEPT；单测 6 例。**事故**：第二轮区域锚点吞掉相邻 `strip_brackets` → 500，已恢复；教训见 findings。
4. **#23 给爸爸六段语音（09-06，已交付关闭）**：家人向首次实际使用，用户知情自决。脚本 `scratchpad/synth_for_dad.py`（按句 ≤80 字走 :8022、句间 0.3 s/段间 0.85 s 拼接、WAV+MP3+manifest sha256），两语域各 6 段，用户选 **wu**；产物 `people/mama/exports/for_dad_20260906/`（Tier-3 标识，不进 archive_dist；那批合成于 8B-11 之前）。
5. **Codex MCP**：ChatGPT 账号下必须传 `model: gpt-5.5`（5.4/5.6 被拒）；登录态失效表现为 "refresh token was revoked"，PC 上 `codex login`，远程 `codex login --device-auth`（设备码 15 分钟过期）。
6. **服务现状**：:8020 http.server（archive_out）与 :8022 tts_server（e14，soften_onsets 已生效，session 日志开）均在跑；重启机器后需手动拉起（用户 D5 裁决：PC 常开手动拉起）。
7. **实施队列（已裁决）**：8A-2b 护栏 → A1 主屏图标 → Phase 13 有声档案；8B-4 真机验收顺带覆盖 8B-10/11 的体验反馈。
8. **09-07 上午两件事**：a `docs/status-2026-09-07.md` 全景状态报告（Workflow 20 agent；40 行文档失真表待逐条修）。b **凯西相关记录全层清除**（用户裁决）：`scrub_sensitive.py apply` 174 条（170 消息 + 2 语音转写 + 2 语音清单，manifest 188 行）；两段原声 WAV 移入 `versions/pre_kaixi_scrub_20260907/`（该目录=删除前完整快照，含名字，用户决定何时删）；persona.md T34/T35 引文名字→〔前儿媳〕；sessions 09-04 日志、for_dad 导出、corr_v02_p6/p7、gate_page 涂〔已隐去〕；candidates 150→141（124/17）；全链重跑，**archive_dist 已重打包 169 文件 verify=ok，M3 欠账同时还清**。UIF 现 20739、语音 123。scrub verify residue=0。用户 09-04 的纠正"已离婚/现任兔兔"仍为 Tier-3，暂不升级。 **同日下午补**：用户复测仍"记得凯西"=浏览器启发式缓存（http.server 无 Cache-Control，旧 transcripts.json 新鲜期约 2 天）→ hotfix：companion/chat 页 7 处数据 fetch 加 `{cache: 'no-cache'}`（声明直改），页面已重建；各设备需强刷一次。
9. **Phase 15 跨会话记忆上线（09-07 夜→09-08 凌晨，用户拍板先于 8A-2b；Codex 四轮 ACCEPT）**：新开窗口后她能接上上次的话。链路＝`tools/ingest_sessions.py`（sessions/*.jsonl → `archive_out/data/sessions_<viewer>.json`，**按 viewer 分文件**，确定性+原子写+敏感省略）→ tts_server 每次写完日志**去抖 5 秒自动重算**（`--sessions-out-dir` / `--no-sessions-ingest`，`/health` 增 `sessions_ingest`、`sessions_ingest_last`）→ companion 页以 no-cache 拉自己那份，把「上次对话卡」拼进系统提示（**仅内存，不落盘**）并作为**第四检索源**（`[对话者自述 · 往次对话 Tier-2]` / `[往次数字对话 Tier-3]`，排在第一纪元之后）。抽屉新增**「本次对话不进记忆」**开关（勾选即补发 `exclude_session` 事件，整会话被排除）；另有 `people/mama/sessions/exclude.txt` 手工清单（已预填 09-07 三次凯西复测）。提示词加第 7 条铁律「往次对话纪律」（只能以「侬上趟搭我讲过」口吻引用，数字人的话永不能说成「妈妈记得」）。`build_archive` 排除 `sessions_*.json`（第二纪元不进可分发档案）。**测试首次入库** `tests/`（36 例 unittest + 1 套 E2E 15 断言，用标准库 unittest 因默认 Python 无 pytest）。构建 companion 页新增 `--viewer`（默认 owner），为 #24 爸爸场景预留。**⏳ 剩用户真机验收：PC/iPhone 各强刷一次再开新窗口，看她第一句是否提到上次日期与你说过的事。**

## ⓪⁹ 增补（2026-09-01→02：情绪层激活 + 多服务商抽屉 + 时间分隔/会话日志 + 分句语音流水线+正在输入，最先看这段）

> 本段含 10 点：1-6 情绪贴片定稿激活（09-01）；7-8 多服务商抽屉 + 真机首测/blob 守卫（09-01）；9 轴五会话日志 + 时间分隔（09-01）+ TTS 剥括号（09-02）；10 分句语音流水线 + 微信式「正在输入」（09-02）。工程工艺沉淀见 memory [[deepseek-full-file-echo]]（区域规格法）[[verify-rendered-pixels]]（DPR/route-mock）[[deepseek-pipeline-lessons]]（PS 自杀坑/TTS 重启）。

1. **用户定稿**：四情绪均取种子 5002（happy s5003 瞳孔变棕=形象漂移、sad s5003 带泪珠被排除）。原始 12 候选+manifest 已存 `people/mama/versions/emo_candidates_20260829/`。
2. **8B-3b 完成（DeepSeek 写 + Codex ACCEPT）**：新工具 **`tools/bake_face_patch.py`**（person-generic 贴片烘焙：`--base` + 单任务 `--src/--out/--region x0,y0,x1,y1:feather` 或 `--jobs jobs.json`；掩码=矩形填充→GaussianBlur(feather)→lighter 合并，**与 emo_review 预览同数学、不内缩**——注意与 Phase 1 旧脚本"内缩+blur(f/2)"不同；内建 alpha_composite 自验 ≤2）；`build_avatar_page.py` 新增 `load_emotion_assets`（persona/emotions.json 裸文件名 → 校验 → 复制 data/avatar → file 改写 `data/avatar/<name>?v=<hash>` → reconcile 白名单）。**改情绪/关键词只需改 `persona/emotions.json` 然后 `python tools/build_avatar_page.py --person mama`**，companion 页零改动。
3. **`persona/emotions.json` 契约**：`emotions` 键序 = detectEmotion 优先级（sad>stern>think>happy，小写子串首中即返）；关键词已按 Codex 误报实证收窄（无标点类/单字/泛词）；`neutral_delay_ms` 8000。默认微笑=底图本身。
4. **验证链**：贴片叠底图 vs 用户审核合成图 max_diff=0；Playwright mock 同源 SSE + UI 配置 + 真按发送 → 真实运行时 sad→happy 切换→回落，computed style/层序/尺寸全对，截图人眼确认。**新教训：Playwright 截图是 devicePixelRatio 1.5×，像素 diff 的 CSS 坐标必须乘 DPR**（第一次算成"眉眼带 0 变化"是探针错误）。
5. **环境**：机器曾重启——本会话已手动拉起 :8020（archive_out）与 :8022 TTS（e14，73s 加载）；Tailscale 进程在；:9880 GSV 未起。
6. **同会话另一裁决（2026-09-01）**：用户移除四项待办（601 敏感复核 / persona Q1-Q13 / DeepSeek key 轮换 / 拟音词释义），见第六节。
7. **companion 多服务商抽屉（同日，用户提出）**：OpenAI/Anthropic/DeepSeek/Kimi/自定义，选中即预填端点+模型（`gpt-5.6`/`claude-opus-5`/`deepseek-v4-flash`/`kimi-k3`，2026-09-01 官方文档核实；Kimi 国内 `api.moonshot.cn`，海外改 `.ai`；四家 CORS 预检实测通）。存档结构升级为 `{provider,url,model,key,profiles:{<provider>:{url,model,key}}}`，每家各自记 key；旧存档按 URL 自动归类。改预填值只改 `PROVIDERS` 常量表（build_companion_page.py）。存档字段为空一律补默认（`withDefaults`）——用户实测「切到 DeepSeek 没预填」即此根因（旧页只存了 key）。
8. **用户真机首测通过 + 一 bug 修复**：API 配置成功、文字+语音回复通；bug=她念完 TTS 后接播训练用真实语音——根因 avatar.html `ended`→`playAt(cur+1)`，修法=`blob:` 音源守卫 1 行（build_avatar_page.py，Codex ACCEPT）。**avatar.html 因此有改动，archive_dist 未重新同步**（独立档案页行为不变，可择机 `build_archive` 重打包）。
9. **轴五 sessions 日志已落地（同日，用户提出「记录双方文字+时间戳+每轮语音」）**：`tts_server.py` 新增 `POST /session`，companion 每轮把 user/simulacrum/event 记录 POST 过去，`/tts` 带 session_id/turn 时把 WAV 另存。**落盘位置 `people/mama/sessions/YYYY-MM/session_<YYYYMMDD-HHMMSS-rand>.jsonl` + `audio/session_<id>_t<turn>.wav`**（gitignore 内）。服务不在时记录进 localStorage 队列（`companion_mama_byok_sessionq`），下次 /health 通或任一条发送成功后补传。tts_server 现默认 `--person mama` 开日志（`--no-session-log` 关）；**重启 TTS 用 venv python 直启**：`C:/Users/justin/venvs/cosyvoice/Scripts/python.exe -X utf8 tools/tts_server.py`（Start-Process 脱钩 + 日志重定向；⚠️ 用 CommandLine 匹配杀进程时要限定 Name=python.exe，否则 PowerShell 会杀掉自己）。聊天栏同时上了微信式时间分隔（与上一条消息间隔 >5 分钟显示一次）。**09-02 增量：/tts 合成前 `strip_brackets` 剥掉 [表情]/（动作）**（显示保留、念白剥除；日志附 spoken_text）。
10. **分句语音流水线 + 微信式「正在输入」（09-02，用户提出「文字出现要等语音／越长越久」+「学微信正在输入」）**：companion 回复按句号/叹问/分号/换行切段（`splitSegments`，`SEG_FIRST_MAX 24`/`SEG_MAX 42`/短尾并回），首段先合成先播、后段串行边播边合成，**每段文字随该段语音开播同刻浮现**——首声从「正比全文合成」降到「首段合成」。核心状态机 `voiceTurn`；旧回合遗留的 iframe player `ended` 靠模块变量 `activePlay`（当前占用播放器的回合）归属校验，不会误推进新回合；发送后气泡先 `setTypingIndicator`（三点 CSS 动画），onDelta 不再逐 token 写 DOM。TTS 不可用或全文 >240 字 → 文字节奏兜底；停止键显示已生成文字；`cancelVoiceTurn` 文字永不丢；20s safetyTimer 防服务端挂死。**这项显著提升沉浸感 → 8A-2b 伦理护栏更应尽早补。**下一步可做 `tools/ingest_sessions.py`（GENERALIZATION：校验/去重(qid)/敏感扫描 → 第四检索源），**数字人话语永久 Tier-3**。

### 下回合建议顺序（09-07 刷新，覆盖下方各旧版）
0. **8B-10（语音条分条）与 8B-11（起音爆音淡入）已提交（09-07）**：剩用户真机体验反馈（分条节奏、30 字上限、语音条样式、开头是否还有"啵"）→ 提交。#23 给爸爸六段语音已交付关闭（`people/mama/exports/for_dad_20260906/`，注意那批是淡入修复前合成的）。**Codex MCP 注意**：ChatGPT 账号下 `mcp__codex__codex` 必须传 `model: gpt-5.5`（默认 gpt-5.4 与铁律写的 gpt-5.6 都被拒）；登录态失效表现为 "refresh token was revoked"，`codex login status` 仍显示已登录，在 PC 上 `codex login`（浏览器流）即可，远程用 `codex login --device-auth`（设备码 15 分钟过期）
0b. #22-b 裁决 E1–E6（用户"晚点再裁决"）；已裁决的 a 实施队列：8A-2b → A1 主屏图标 → Phase 13 有声档案
1. **8A-2b 伦理护栏**（companion 日常可用前必须；⚠️ sessions 日志显示已进入真机实际使用而护栏未上，分句流水线又提升了沉浸感——优先级最高）：关窗道别/空闲离场/rhythm 限速/使用统计卡。
2. **8B-4 完整真机验收**（09-01 首测已通；iPhone/Mac 经 Tailscale `http://100.116.45.2:8020/companion.html`，含情绪层）。
3. 微信三线等用户裁决方向（自用验证 / 先不做）；若自用，先建共享 `persona_core.py`（chat.html 检索/Tier 逻辑 Python 直译，所有 headless 皮肤共用）。用户可秒级自查：微信 设置>插件 有无 ClawBot 入口。
4. 择机 `python tools/build_archive.py --person mama` 重打包 archive_dist（archive_dist 缺 avatar.html 的 blob 守卫（08-27 版 vs archive_out 09-01 版，md5 实证不一致）+ data/avatar 下的情绪贴片资产）。
5. 可选：`tools/ingest_sessions.py`（sessions → 校验/去重(qid)/敏感扫描 → 第四检索源，数字人话语永久 Tier-3）；talking-head 特别版试片；chat_system 长度纪律 / 非 DeepSeek 服务商 reasoning_effort 低档（等用户表态，progress 09-02）；8A-3 的 chat.html 侧同步（占位符 deepseek-chat）。
> 旧版列表里静默消失的零散项（VoxCPM2 A/B、TG bot 通道网关、relative_to 小修、记音字还原、archive_dist 分发备份）**未经用户裁决移除，只是未排期**——需要时可重提。

## ⓪⁸ 增补（2026-08-28→29：桌面陪伴上线 + 微信接入四路径全查 + 情绪贴片首轮）

**本轮主线=任务 #18 桌面陪伴（companion）从立项到三平台上线；支线=为"接入各平台聊天"副产品把微信四条路径全部查清（#20 iLink / #21 OCR），以及 #19 蕾咪拆解。**

### A. 桌面陪伴 companion（任务 #18，Phase 8A/8B）——已有可用产物
1. **形态定案（用户裁决链）**：报告 `docs/research/desktop-companion.md` 三档裁决→用户选**上限形态"打开才在的对话窗口"**（条件 a-f 硬规格，非常驻桌宠）；架构=**iframe 组合**（companion 父页 iframe 内嵌 avatar.html face-only + 复用 chat 大脑），**avatar.html/chat.html 零改动，companion 纯新增**。
2. **8A-0 告别/降级协议**：`docs/companion-farewell-protocol.md`（条件 f 前置件，第五格留用户填一句话）。
3. **8A-2a 核心闭环**（commit caa1771）：`tools/build_companion_page.py` → `people/mama/archive_out/companion.html`（**不进 archive_dist**）。打字→三源检索→BYOK LLM 流式→:8022 合成她的声音→路由进 iframe 的 `audio#player`→脸的嘴动（RMS）。DeepSeek 写 + Codex 三轮 ACCEPT。**真浏览器实测：TTS→脸→嘴动端到端通**（speaking 态 + half 嘴型）。
4. **8B-甲 三平台兼容 + 情绪层**（commit 7602150）：①**iOS 音频解锁**（send 手势内 SILENT_WAV 静音 play/pause + 向 iframe 派发合成 click 触发 avatar 的 audioCtx.resume）②**自动播放被拒→气泡 ▶"播放她的声音"按钮兜底**（同步 throw/promise reject 双路径）③CSS：viewport-fit/100dvh/safe-area/输入框 16px 防缩放 ④**情绪层运行时**：companion 侧向 iframe 注入 `emotion-overlay` img（**显式 inline style 不挂 mouth-patch 类**，插眨眼层之下）+ `emotions.json` 数据驱动（emotion→file+keywords，**404 静默关闭**）+ 关键词检测 + 同名防呆滞刷新计时 + 回落。Playwright 桌面 + iPhone 390×844 视口全绿。
5. **8B-3 情绪贴片首轮**（commit 6465724）：ComfyUI 复用 gen_avatar_candidates.build_graph（Qwen-Image-Edit）生成 **4 情绪×3 种子=12 张**（happy 弯眼/sad 蹙眉/stern 嗔怪/think 侧看）；**首轮即温和+形象一致性全保**（归因=眉眼改动比嘴型温和 + prompt 锁死嘴/镜框/发/脸）。烘焙区域=双镜片内区(blink rects 羽化8)+眉带(370,225,820,315 羽化10)（定稿烘焙 `bake_face_patch.py` 与 emo_review 预览同数学=矩形→GaussianBlur(feather)→lighter 合并、不内缩，与 Phase 1 嘴/眨眼旧脚本"内缩+blur(f/2)"不同，见 ⓪⁹ 第 2 点）。审核页 `archive_out/emo_review.html`（12 GIF 底图↔情绪 0.8s 交替）已上 8020。**→ ✅ 2026-09-01 定稿+烘焙+激活完成，见 ⓪⁹。**
6. **DeepSeek 新工艺定式（重要）**：改现有大文件用**"全文回显+区域纪律+diff 校验"**——规格含改动区+原文件全文，产出逐块对应规格、diff 实证零漂移（对照 8A-2a 让 DeepSeek 整函数重生成→标识符全猜错的漂移事故）。
7. **访问方式**：本机/手机经 Tailscale `http://100.116.45.2:8020/companion.html`；⚠️ **iPhone 上她的声音可能被 iOS autoplay 拦→出 ▶ 按钮**（点一下即放）；桌面浏览器完整。**⏳ 8B-4 用户真机验收（iPhone/Mac 经 Tailscale）未做。** → 已过期：09-01 首测已通（API 配置+文字/语音回复），完整验收待续（⓪⁹）
8. **⏳ 未做：8A-2b 伦理护栏**（条件 a-e：关窗道别语/空闲离场/rhythm 节律限速/使用统计自见卡）——**companion v1 是纯技术闭环，护栏没上，日常常用前必须补**。

### B. 微信接入四路径——全部查清，结论：没有一条为"家人向"打开干净的门
> 副产品诉求=把"调教好的 mama"接入各平台（尤其微信）文字+语音聊天。四路径全景（详见各 docs/research）：
- **① UIA 自动化**（任务 #16，wechat-ui-automation.md 第六节）：4.1.12.26 **NO-GO 铁证**（Qt 无障碍桥被主动关，控件树恒 3 节点空壳，五重触发全败）。
- **② iLink/ClawBot 官方协议**（任务 #20，dsh-im-analysis.md）：**腾讯 2026 官方个人号 Bot 协议，第三条路，实质更新"微信封死"结论**；reply-only 天然契合"永不主动"。**但校核 refuted"官方=可给家人用"**：机主控自己 agent 设计/dsh-im 直连属未授权客户端/家人拓扑无据/腾讯可随时终止。dsh-im=连接层非大脑（接 persona 要写冒充 DeepSeek Harness 的本机 shim）、**不发原生语音条**。
- **③ 服务号/企业微信**：需企业主体；企微 aibot 对外部个人微信直接拦截=家人向 NO-GO。
- **④ OCR/RPA**（任务 #21，wechat-ocr-automation.md）：**GitHub 有零件没成品**（社媒"skill"=YoKo/pywechat 是 UIA 路线，在 4.1.12.26 死）；**★新事实：微信 PC 4.1.9+（用户 4.1.12.26 已有）支持发原生语音条（按住右Alt）**，VB-Cable 虚拟声卡+keyDown/keyUp 可发她真声语音条（**唯一 iLink 给不了的能力**，但微信 AGC/降噪可能劣化克隆音色待 A/B）。校核 refuted"OCR 唯一绕 UIA"（DB 读才是可靠读侧）。
- **共同裁决**：**自用**（绑用户自己号+仅自己模式+顺带落地轴五 sessions 采集）=低风险 GO；**家人向=默认 NO-GO**（第三方受众=griefbot 哀悼者/继承人须三方同意，沉浸/欺骗最大化）。**OCR 家人向比 iLink 更该 NO-GO**（零 bot 标识、欺骗性最强）。**⏳ 三条微信线均等用户裁决方向；未写一行接入代码。**
- **用户可自查两硬点**：①微信 设置>插件 看有无 **ClawBot** 入口（秒级，判 iLink 灰度，**不用备弃号**）②iLink/OCR 能否发原生语音条动工前活体验证。

### C. 蕾咪拆解（任务 #19，kira-remy-analysis.md）
"这种效果"=透明桌宠立绘窗 + 情绪表情立绘切换 + 打字机气泡；技术栈仅 **PyQt5 + 8 张 PNG，无 Live2D、无语音、口型仅 Open/Shut 双帧**（比我们落后两代）。**用户否全身化（维持半身框）**——蕾咪"全身动画"实为整图切换已拆穿。借形（情绪表情层→已做进 8B）不借魂（常驻/主动/游戏化/云识图全排除）。桌宠壳（方案乙 QWebEngineView/Tauri）留远期。

### D. 环境现场（08-29 会话结束时）
- **:8022 TTS 常驻**（生成情绪贴片时曾停腾显存，已恢复；exp=mama_v02f160_llm e14）；**:9880 GSV 生成时被停未恢复**（需要时手动 api_v2）；**:8020 档案站常驻**（companion.html/emo_review.html/avatar/chat 都在）；**ComfyUI 起过（生成完可停，占显存）**；Tailscale userspace 常驻 100.116.45.2。**机器重启后 8020/8022 需手动拉起；Tailscale 有登录自启任务 `TailscaleUserspace`（⓪⁹ 重启后实证进程在）。**
- 新装库：`uiautomation 2.0.29` + `comtypes 1.4.16`（#16 探针用）。dsh-im/kira-remy 克隆在 scratchpad（研究用，未入库）。
- **系统 python 无 numpy/ffmpeg**（PIL 合成改用 ImageChops；转码需 ffmpeg 在盘状态待复核）；ComfyUI 情绪生成调用器坑：poll_history 返回 (status,entry) 元组、extract_output_image 返回 (fname,subf,type) 元组。

### 下回合建议顺序（08-29 刷新，覆盖下方各旧版）
1. ~~情绪贴片收尾~~ ✅ 2026-09-01 完成（见 ⓪⁹）。
2. **8A-2b 伦理护栏**（companion 日常可用前必须）：关窗道别/空闲离场/rhythm 限速/使用统计卡。
3. **8B-4 用户真机验收**（iPhone/Mac 经 Tailscale 开 companion.html）。
4. 微信三线等用户裁决（自用验证 / 先不做）；若自用，先建共享 `persona_core.py`（chat.html 检索/Tier 逻辑 Python 直译，所有 headless 皮肤共用）。
5. 零散续：talking-head 特别版试片。
> ❌ **四项待办已移除（2026-09-01 用户裁决——此前误记 08-29，git 实证该裁决出自 09-01 会话；不再列待办、不再催办）**：601 敏感疑似复核 / persona Q1-Q13（早已收口，见 progress 08-13）/ DeepSeek API key 轮换 / 4 个拟音词释义。旧版章节再出现这四项一律视为已废止。

## ⓪⁷ 增补（2026-08-22→08-27：纸片人从"疯狂闪烁"到整脸微活全弧线，最先看这段）

1. **双帧架构判死 → 贴片主线定案（08-23 任务 #17）**：用户对双帧口型两报"疯狂闪烁"，三根因修复（看门狗/帧素材/缓存）后仍闪 → 架构性死因=两张独立 AI 整图互换必然全图抖动。渲染研究收口 `docs/research/digital-human-rendering.md`（4f4849d）：**主线=viseme 嘴部贴片+预计算时间轴**（五约束唯一全绿）；talking-head 预渲染 MP4 降为"特别版"增强+第一备选；Live2D 闭源 core 违 20 年红线不投入
2. **Phase 0 三态贴片（08-25）+ 假阳性事故与根治**：恒定底图+全尺寸 RGBA 透明嘴贴片（用户定稿 A 温和版）上线后用户报"按播放后没变化"——**真根因：`style.display=''` 被 CSS 类规则回落吃掉，贴片从未渲染过一个像素；我方此前"三态验证"采的是 inline style 遥测=假阳性**（workflow 三视角审计代码级实锤）。修复=显示分支全显式 `display='block'`+scale 改打 img（容器 transform 被 bob 动画覆盖）；**新铁律入 memory（verify-rendered-pixels）：视觉验收必须 computed style+截图 diff**。诊断 HUD 常驻（`avatar.html?debug=1`：BUILD/MODE/SRC/SPK/LV/FRM/AUD/IMG/ERR，HUD 缺席=旧缓存判据）
3. **Phase 1 收官（08-26/27，用户定稿"先按照这些定稿"）**：
   - **时间轴管线**：Rhubarb 1.14.0（`~/tools/Rhubarb-Lip-Sync-1.14.0-Windows`）`-r phonetic` 批跑 125 条上海话全过（18516 cues）→ `tools/build_visemes.py`（增量模式；坑：`--machineReadable`+stdout 拿不到 JSON 必须 `-o` 文件；hotfix=mkstemp fd 双重 close 竞态 + 失败条目退缓存）→ `archive_out/data/avatar/visemes.json`（326KB，构建时内联进页面）
   - **运行时**：build_avatar_page.py patch 模式数据驱动 N 态——mouth_patches.json v2（states/viseme_map/rms_states/blink，Python 端 fallback resolve：wide→open/round→half/pucker→round）；驱动优先级=时间轴（currentTime 查 cue）>RMS 回退（BYOK 动态 TTS 分支）>closed；眨眼调度器待机也眨；`.avatar` ambient 常驻微摆。审核链：DeepSeek×2 + Codex REJECT（增量吞失败/config 损坏回退死路→DOM 扫描恢复/空 states 建运矛盾）→ ACCEPT + 声明 hotfix×4（含 DeepSeek 丢 avatar-base img 的 BLOCKER）
   - **资产定稿**：W1=wide2_s4211（温和大张）/ R1=round_s4203（圆唇）/ 嘟唇并入圆唇 / B1=blink_s4201（眨眼=双镜片内区替换，镜框恒用底图像素）；烘焙全尺寸 RGBA（RGB 取 raw 非 comp——叠加数学要求，自验 diff=0）。工艺：嘴型 prompt 首轮必夸张需温和化迭代；round 二轮精修反而更厚（模型爱给她涂厚唇），回用首轮
   - **像素级验收**：8 秒采样六通道全动（closed/half/open/wide/round+眨眼，TL 驱动 178/178）；慢放 0.25× 抓 wide 实拍、克隆节点抓眨眼实拍（**截图验收防 rAF/调度器覆写竞态**——两次假阴性被识别绕过）
4. **微信 UI 自动化研究（任务 #16，08-22 立项完成研究）**：`docs/research/wechat-ui-automation.md`（2f37ed4）——可行但有闸门；微信 4.x Qt Quick 自绘 UI"按需暴露无障碍树"；wxauto 家族对 4.1.x 已死；**下一步=30 分钟 go/no-go 探针（uiautomation attach + inspect.exe，需用户备一次性小号）**；回退=DB 轮询读 + UIA/剪贴板发 **→ 已被 ⓪⁸ B① 覆盖：08-28 活体探针 NO-GO 铁证（4.1.12.26 控件树恒空壳），ClawBot 灰度自查亦不用备小号；本条仅历史。**
5. **环境现场（08-27 收尾时）**：api_v2 :9880 已恢复常驻（**真实路径=`~/gpt-sovits/GPT-SoVITS-v2pro-20250604/runtime/python.exe` + workdir/tts_infer_v2pro.yaml**，勿再用 `~/gpt-sovits/runtime` 旧记法）；8020 档案站常驻（archive_out）；ComfyUI 已停；archive_dist 已同步（166 文件 checks=ok）；Rhubarb 在 ~/tools。机器重启后 8020/9880 需手动拉起，Tailscale 有登录自启任务 **→ 已过期（见 ⓪⁹ 第 5 点）：9880 现未起；archive_dist 自 09-01 起落后 archive_out（avatar.html 缺 blob 守卫、data/avatar 缺情绪资产），待重打包**
6. **审核物料红线（08-25 固化）**：SendUserFile 在部分会话被禁用且曾报成功未送达——**音频/图片/GIF 审核物料一律走 8020 站点页面**（先例：mouth_preview.html / phase1_preview.html / gsv_review.html）

### 下回合建议顺序（08-27 刷新，覆盖下方各旧版）

1. **talking-head 特别版试片**（用户已知情待点头）：挑 3-5 条珍贵语音渲整脸表情 MP4（候选 InfiniteTalk 1.5 / EchoMimicV3 / FantasyTalking / Sonic / LivePortrait+JoyVASA），逐帧人工验收，合格以 `<video>` 并存入档
2. 微信 UI 自动化 go/no-go 探针（需用户备小号）或 TG bot 通道网关（messaging-channels P1）——按用户意愿
3. 零散：601 敏感疑似复核 / relative_to 小修 / 记音字还原（待用户表态）/ VoxCPM2 A/B / archive_dist 真机验收+分发备份 / DeepSeek key 轮换（用户）

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

1. **对话页新能力（全部 Codex 审 + 真浏览器 E2E）**：①file:// 直开引导（修"Failed to fetch"实报）②接口类型双模式——OpenAI 兼容（DeepSeek：`https://api.deepseek.com/chat/completions` + `deepseek-chat`；**→ companion 页 09-01 起预填 `deepseek-v4-flash`，chat.html 占位符仍旧**）/ **Claude 官方**（`https://api.anthropic.com/v1/messages` + `anthropic-dangerous-direct-browser-access` 头，CORS 直连实测通；Max 订阅≠API 额度，需 console 充值）③**用户气泡漏渲染文本 bug 修复**（自 v1 潜伏）④**微信式语音回复**——tools/tts_server.py 本地合成服务 :8022（v0.2 e14，默认沪普；`wu-sft/tts_server/start_tts.bat` 一键启动，已常驻）+ 语音条 UI（点击播放/右键长按转文字/"合成语音·非原声"标签/≤120 字/四类失败降级文字）。审核插曲：Codex 首轮 REJECT 的 BLOCKER 被六格矩阵实证不能复现（其分帧实验污染自身连接），复审撤回改 ACCEPT；真发现（分帧加固/token 选项/blob 池/touchcancel）全修
2. **远程访问已通（Tailscale 私网）**：**手机任何网络访问 `http://100.116.45.2:8020/`** = 家里档案站全部页面（含语音对话，TTS 走同主机 8022）。架构：**userspace 模式用户态 tailscaled**（腾讯电脑管家拦 SYSTEM 服务出网 WSAEACCES，服务版已停用禁用；提权用户态 + --unattended）；登录自启任务 `TailscaleUserspace`；设备 justin-pc(100.116.45.2) + iphone182(100.111.127.101)。排障链与风险详见 progress 08-17 节（管家若日后拦用户态进程需回家白名单；UDP 受限走 DERP TCP 中继）
3. TTS 服务与 LAN http.server 均非开机自启（TTS 用 start_tts.bat、档案站用 archive_out/start_server.bat 手动起；后续可仿 TailscaleUserspace 注册计划任务）**→ 现行 TTS 启动法见 ⓪⁹ 第 9 点（venv python 直启；cmd /c 包 bat 会静默失败，progress 09-01）**

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
| 语音选型（**2026-08-18 刷新**） | **现役：CosyVoice2-Wu-SFT 全量 SFT = v0.2 e14 双语域**（上海话 `<|wuyu|>` + 沪普裸文本）。十维度选型矩阵见 `docs/research/tts-frontier-2026.md`：普通话/粤语泛化=GPT-SoVITS v2Pro 主选（Phase 6 已于 08-21 收官）· VoxCPM2=唯一沪语 A/B 候选 · Qwen3-TTS=方言开源化观察对象。~~家人盲听是唯一标准~~ → 08-21 用户裁决移除家人盲听，M1 以本人盲听 v2 关口 |
| 微信导出（**已定案 2026-08-04**） | 用户微信实测 **4.1.11.24**（08-28 时已升 4.1.12.26；4.1.x 取 key 方法见 memory wechat-key-extraction）。chatlog/chatlog-new 不支持 4.1.x（出局）。**采用混合方案**：①文字+图片→ `chatlog-keeper`（MIT，已在 4.1.11 取到 key 并缓存，`wechat`+`images` 命令）；②视频→ **直接复制** `xwechat_files/<wxid>/msg/video/**/*.mp4`（4.1 视频是明文 mp4，实测 387 个）；③语音→ **自研提取器**（SILK blob 在加密消息库内，需先探测表/字段，DeepSeek 写 Codex 审，pilk/silk→wav）。详见 `docs/research/wechat-media-extraction.md`。备选交叉验证：`LifeArchiveProject/WeChatDataAnalysis`（无协议、DMCA靶心，用完即弃）。chatlog-keeper 源码在 `installers/chatlog-keeper-0.2.0/`，已建 .venv 装好依赖 |
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
     - **微博（#14，⚠️ 编号后被 08-18 GPT-SoVITS 泛化管道任务 #14 复用，引用时称"微博适配器"）**：两部分素材——①她自己微博账号的全部内容；②**用户（justin）微博下她的评论/回复**。适配器 `tools/parse_weibo.py` 输出 UIF post 记录（schema 已支持 author/comments）。前置：素材获取方式待研究（她的账号官方导出是否可行/网页存档抓取；justin 自己的微博可官方导出后筛她的评论），先由用户收集 raw → `people/mama/raw/weibo/`
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

## 六、用户待办（2026-09-02 刷新）

**当前有效（用户侧动作）**：
- 8B-4 完整真机验收：iPhone/Mac 经 Tailscale 开 `http://100.116.45.2:8020/companion.html`（含情绪层）
- 微信接入方向裁决（自用验证 / 先不做）；可秒级自查：微信 设置>插件 有无 ClawBot 入口
- talking-head 特别版是否点头（可选）
- `docs/companion-farewell-protocol.md` 第五格留你填一句话（首次自查日 2026-11-28）
- chat_system 长度纪律 / 非 DeepSeek 服务商 reasoning_effort 低档——是否要做（progress 09-02）

**已移除 / 已闭环（历史）**：

- ~~安排家人盲听~~ **已移除（2026-08-21 用户裁决）**——M1 以本人盲听 v2 关闭
- ~~说话帧确认~~ **已闭环（2026-08-23）**——用户实报口型 bug 后三根因修复（看门狗/帧素材重做/缓存穿透，见 progress 08-22/23 节）：新映射 静息=闭嘴微笑 s3002（用户选定）/ 说话=原张嘴笑定稿 **（注：此映射属双帧体系，同日 08-23 双帧架构判死；现行=Phase 1 贴片体系：底图 s3002 + 四态嘴贴片 W1/R1 + 眨眼 B1 + 情绪贴片，见 ⓪⁷/⓪⁹）**
- ~~DeepSeek API key 轮换~~ **已移除（2026-09-01 用户裁决）**
- ~~4 个拟音词释义~~ **已移除（2026-09-01 用户裁决）**
- ~~601 敏感疑似复核~~ **已移除（2026-09-01 用户裁决）**——报告文件保留在 normalized/，闸门页默认剔除逻辑不变，仅不再作为待办
- ~~persona Q1-Q13~~ **已移除（2026-09-01 用户裁决）**——实际早已全部收口（progress 08-13），此前为陈旧残留
