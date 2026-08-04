# 微信 Windows 电脑版聊天记录第三方导出方案调研报告（2026）

> 核查日期：2026-08-04　｜　场景：从**自己的** Windows 微信电脑版导出与家人的完整聊天记录，用于个人纪念档案（纯自用，援引 PIPL 第 72 条个人／家庭事务豁免）。

---

## 三行摘要

1. **两个并列首选（用户选择自测哪个先跑通）**：① **`WechatRagAgent/chatlog-new`**（chatlog 原版的活跃续版，Apache-2.0，有 Win/Mac 发布包，**语音实时 SILK→MP3**）；② **`labazhou2024/chatlog-keeper`**（MIT，2026-07 活跃，有 Windows exe，**唯一支持微信 4.1.10.31+ 新版**，JSON+HTML 双导出）。
2. 若想要「一键生成 HTML/Word 存档 + 年度报告 + 朋友圈」的图形界面，用 **`WeChatMsg_2026`（留痕 WeChatMsg 的社区续命镜像，支持微信 4.0）** 作为备选。
3. **两大拦路虎**：①腾讯 2026-01 向 GitHub 发 DMCA 下架约 4195 个仓库，原始仓库多数删库/451，必须走镜像/续版；②微信 **Windows 4.0.3.36+ 不再把密钥留在内存**、**4.1.10.31+（2026-05）更把明文 key 移出进程堆**——被动内存扫描取不到 key，需临时降级、用 `ycccccccy/wx_key` 手动取，或用能自动回退到调试器取 key 的 `chatlog-keeper`。

> ⚠️ **2026-08-04 存亡核查更正**：原报告首选的镜像 `forkgitss/sjzar-chatlog` 经 GitHub API 实测为**冷门旧快照**（2025-04、1⭐、无 Releases），已不推荐；改用下方「零、仓库存亡核查」表中标 ✅ 的活跃仓库。

---

## 零、仓库存亡核查（2026-08-04 GitHub API 实测）

> 每个仓库都用 `gh api repos/<owner>/<repo>` 实测了 `archived`/`disabled`/`pushed_at`/`stars`/Releases。下载前请再核一次（镜像随时可能被下架）。

| 仓库 | 存活 | 最近更新 | Star | 可下载包 | 微信版本 | 结论 |
|---|---|---|---|---|---|---|
| **WechatRagAgent/chatlog-new** | ✅ | 2025-07 | 18 | ✅ v0.0.16 Win/Mac | ≤4.0 | **首选①**：chatlog 活跃续版，语音实时→MP3 |
| **labazhou2024/chatlog-keeper** | ✅ | 2026-07 | 25 | ✅ v0.2.0 `chatlog-keeper.exe` | **≤4.0 + 4.1.x** | **首选②**：MIT，唯一吃新版微信；JSON+HTML；图片.dat 自动还原 |
| `ycccccccy/wx_key` | ✅ | 2026-06 | 1786 | — | 4.0+ 取密钥 | 辅助：取 key 工具，配合上面用 |
| `xlight/chatlog-session` | ✅ | 2026-07 | 122 | — | 依赖 chatlog | chatlog 的 Web 前端（挂 NAS 用），非独立导出器 |
| `sjzar/chatlog` | ⚠️ 空壳 | 2025-10 删库 | 9185 | — | ≤4.0 | 原版代码已清空，仅存说明 |
| `forkgitss/sjzar-chatlog` | ⚠️ 弃用 | 2025-04 | 1 | ❌ | — | 冷门旧快照，**原报告首选，已撤** |
| `AwAcitizen/WeChatMsg_2026` | ✅ | 2025-04 | 8 | — | 4.0 | 备选：GUI+HTML+朋友圈，三个镜像内容一致 |
| `yangbuyiya/WeChatMsg_2026` | ✅ | 2025-04 | 0 | — | 4.0 | 同上镜像拷贝 |
| `tigriszhang/WeChatMsg_2026` | ✅ | 2025-04 | 1 | — | 4.0 | 同上镜像拷贝 |
| `LC044/WeChatMsg`（原留痕） | ✅ | 2025-12 | 41k | — | ≤4.0 | 作者已声明**不再更新** |
| `xaoyaoo/PyWxDump` | ⚠️ | 2025-10 | 9k | — | 3.x–4.0 | 仓库描述已变「删库」，停更 |

**下载地址**：
- https://github.com/WechatRagAgent/chatlog-new/releases （首选①）
- https://github.com/labazhou2024/chatlog-keeper/releases （首选②）
- https://github.com/ycccccccy/wx_key （取 key 辅助）
- https://github.com/AwAcitizen/WeChatMsg_2026 （备选 GUI）

**⚠️ 待你今晚实测确认的一点**：`chatlog-keeper` 的 README 明确了它导出 JSON+HTML、能还原图片，但**未说明语音消息导出后是 MP3 还是裸 silk**。若它吐裸 silk，就用本项目的 `tools/silk_decode.py` 兜底解码；`chatlog-new` 则确认是实时 MP3。哪个先跑通看哪个的语音格式，据此决定后续解析器怎么写。

---

## 一、背景：2026-01 腾讯 DMCA 下架事件

2026 年 1 月，腾讯以 DMCA（含《DMCA》第 1201 条规避技术保护措施、违反微信服务条款的逆向工程、威胁用户隐私、侵犯知识产权四项理由）向 GitHub 集中发函，**下架约 4195 个**与微信聊天记录导出/清理相关的开源仓库，其中包括 star 数上万的成熟项目 WeChatMsg（留痕）与 PyWxDump。腾讯官方回应称这些项目「通过逆向破解本地数据库密钥、绕过加密措施」。

对本次调研的直接影响：

- **大量原始仓库现在返回 404 或 HTTP 451（Unavailable For Legal Reasons）**。本次核查中，`0xlane/wechat-dump-rs` 的 `README` 即返回 451；`xaoyaoo/PyWxDump` 原仓库已「删库」；`sjzar/chatlog` 原仓库更早（2025-10-20）就因收到微信合规函件自行清空代码与提交历史。
- **能用的多是社区镜像/fork**（`*_2026`、`forkgitss/*`、`fork-PyWxDump` 等）。这些镜像随时可能再被下架，**下载后请立即本地留档**，不要依赖长期在线。
- 合规提示：本报告面向「导出自己账号、纯个人纪念」用途。工具本身能力中立，请勿用于导出他人数据或商业监控。

来源：知乎《腾讯向 GitHub 发函要求下架微信聊天记录导出项目》、安全内参 secrss.com/articles/87234、博客园 longware（核查日期 2026-08-04）。

---

## 二、各方案逐一评估

### 1. chatlog（sjzar，及活跃镜像 forkgitss/sjzar-chatlog）★ 推荐

- **微信版本**：官方说明支持 Windows/macOS 的**微信 3.x 与 4.0**。取密钥原理是读取微信进程内存；**微信 Windows ≥ 4.0.3.36（macOS ≥ 4.0.3.80）后密钥不再驻留内存**，自带取密钥会失败（见其 FAQ #197、Issue #236/#264/#317）。4.1.x 需配合第三方取密钥工具手动填入。
- **数据类型**：文字、图片、语音、视频、文件全覆盖；图片支持 AES 解密与 WXGF 格式解析（建议装 FFmpeg 做图片/视频转码）。
- **语音**：✅ **HTTP 取语音时实时把原始 SILK 转成 MP3**——这是它相对其他工具的最大优势，**无需自己再解码**。
- **导出格式**：通过本地 HTTP API / MCP 提供 **JSON / CSV / 纯文本**；配合 MCP 可直接喂给本地 AI 分析。注意：它本质是「本地数据服务 + API」，不是一键生成精美 HTTP 存档的 GUI；要成册的 HTML/Word 需自行处理或搭配他工具。
- **开源/免费**：✅ Apache-2.0，免费。
- **安全性**：✅ 明确「所有数据处理均在用户本地设备进行」，无数据上传。作者在 FAQ 中反而提醒不要把记录传给云端 AI。
- **Windows 11**：✅ 兼容（显示乱码建议用 Windows Terminal）。
- **维护状态**：原仓库 2025-10 删库；社区镜像 `forkgitss/sjzar-chatlog`、`WechatRagAgent/chatlog-new` 仍在更新（镜像仍保留 Releases 与 Issues 引用）。
- **朋友圈**：主打聊天记录，朋友圈非其重点。

### 2. WeChatMsg / 留痕（原 LC044/WeChatMsg，续命镜像 *_2026）★ 备选（要 GUI/成册存档）

- **微信版本**：镜像 `WeChatMsg_2026` 声明**完整支持微信 4.0**，也兼容 3.x。
- **数据类型**：文字、图片、视频、语音、表情、文件、系统消息全覆盖；可还原聊天界面。
- **语音**：支持语音消息导出（HTML 存档内含可播放语音）；底层为 SILK，导出时做转码。
- **导出格式**：**HTML / Word / CSV / TXT / SQLite 数据库**，并生成年度聊天报告、可导出联系人。
- **开源/免费**：Python + PyQt，免费开源；原版被 DMCA 下架，现存于多个 `*_2026` 镜像（AwAcitizen、yangbuyiya、tigriszhang 等）。
- **安全性**：纯本地读取 Windows 微信数据库，「我的数据我做主」；因是社区 fork，**建议校验来源、优先看 star/commit 较健康的镜像**。
- **Windows 11**：✅。
- **维护状态**：原仓库已删；镜像 2026 年仍活跃，但可信度参差。
- **朋友圈**：✅ 可导出朋友圈为 HTML/PDF（加分项达成）。

### 3. MemoTrace（memotrace.cn，留痕的桌面 App 品牌）

- **微信版本**：公开可下载的稳定版长期停在 **v2.0.6（2025）**，社区大量在求「支持微信 4.0 的版本」（52pojie 等帖），**对 4.0 的开箱支持滞后**，3.0.1 等新版流通不畅。
- **数据类型**：文字/图片/视频/语音/表情/链接全覆盖。
- **语音**：支持语音导出。
- **导出格式**：HTML / Word / Excel / CSV / TXT / **PDF**，可导出朋友圈为 HTML/PDF。
- **开源/免费**：有免费版；与 WeChatMsg 同源，桌面化程度高、上手友好。
- **安全性**：本地处理。
- **Windows 11**：✅。
- **维护状态**：官网/下载站仍在，但**版本更新明显落后于微信 4.x 节奏**，是主要短板。
- **朋友圈**：✅。

### 4. EchoTrace（ycccccccy/echotrace）

- **微信版本**：支持微信 4.x 数据解密（Flutter 构建）。
- **数据类型**：文字、语音、图片、表情；生成词云、图表、双人年度报告。
- **导出格式**：HTML 及其他可分享格式。
- **开源/免费**：✅ MIT，免费（3.7k star）。
- **安全性**：✅「完全本地」。
- **Windows 11**：✅。
- **维护状态**：⚠️ **已停止维护**，作者建议转向 **WeFlow（实时）** 或 **密语/Miyu（备份）**。
- **朋友圈**：以聊天分析/年度报告为主。

### 5. wechat-dump-rs（0xlane）

- **微信版本**：v4 分支专门分析微信 4.0（含 4.0.0.26 表结构文档），导出运行中微信进程的 key 并自动解密全部数据库，也支持离线解密。
- **语音/媒体**：偏底层「解密数据库 + 导出 key」，**不直接给成品语音/HTML**，需自己接后续处理。
- **开源/免费**：Rust，开源。
- **安全性**：纯本地。
- **维护状态/可得性**：⚠️ **原仓库已被 DMCA，`README` 返回 HTTP 451**，仅适合能找到镜像且愿意折腾底层的技术用户。
- 结论：作为「密钥/数据库解密引擎」有价值，但不是终端用户的导出方案。

### 6. PyWxDump 及其后继（xaoyaoo，镜像 wo1261931780/fork-PyWxDump、gitee 镜像）

- **微信版本**：宣称「支持所有微信版本」的账号信息获取 + 数据库密钥/解密 + 聊天记录查看 + 导出 HTML（含语音图片）。
- **语音**：导出 HTML 含语音。
- **开源/免费**：Python，开源免费。
- **可得性**：⚠️ **原仓库已删库**，靠 `fork-PyWxDump`、Gitee 镜像存活；它更多是「底层库/取密钥来源」，很多上层工具（含 chatlog 的取密钥思路）与之同源。
- **维护状态**：原作者停更，镜像零散。

### 7. 其他/新出现

- **WeChatDataAnalysis（LifeArchiveProject）**：微信 4.x 数据解密 + 高仿微信界面、实时更新、导出聊天记录/朋友圈/收藏，功能全，值得关注（较新）。
- **WeFlow（hicccc77）**：EchoTrace 作者推荐的实时向后继，仍在迭代（Issue 活跃到 4.1.7.57）。
- **密语 / Miyu**：EchoTrace 推荐的备份向后继。
- **取密钥辅助**：`ycccccccy/wx_key`——在微信新版内存不留 key 时，用第三方方式取 key 再手动填入 chatlog。
- **SILK 解码器（用于任何只给出裸 silk/amr 的方案）**：`kn007/silk-v3-decoder`、`user1121114685/silk-v3-decoder`、`lich0821/SilkMp3Converter`、`alexyangfox/wechat_silk`（拖入 amr 输出 wav）。

---

## 三、对比表

| 方案 | 微信版本支持 | 数据类型覆盖 | 语音→可用音频 | 导出格式 | 开源/免费 | 纯本地/上传风险 | Win11 | 维护状态 | 朋友圈 |
|---|---|---|---|---|---|---|---|---|---|
| **chatlog** (镜像) | 3.x + 4.0（4.0.3.36+ 需另取key） | 文字/图/视频/语音/文件 | ✅ **实时 SILK→MP3** | JSON/CSV/TXT + HTTP/MCP | ✅ Apache-2.0 | ✅ 纯本地 | ✅ | 原库删/镜像活跃 | 弱 |
| **WeChatMsg_2026** (镜像) | 3.x + **4.0** | 文字/图/视频/语音/表情/文件 | ✅（HTML内可播，转码） | HTML/Word/CSV/TXT/SQLite | ✅ 免费 | ✅ 本地(留意fork来源) | ✅ | 原库删/镜像活跃 | ✅ HTML/PDF |
| MemoTrace | 稳定版滞后于4.0 | 全 | ✅ | HTML/Word/Excel/PDF/TXT | ✅ 有免费版 | ✅ 本地 | ✅ | 版本更新慢 | ✅ |
| EchoTrace | 4.x | 文字/语音/图/表情 | ✅ | HTML 等 | ✅ MIT | ✅ 完全本地 | ✅ | ⚠️ **停更** | 分析向 |
| wechat-dump-rs | 4.0（底层） | 数据库/key | ⚠️ 需自行处理 | DB + key | ✅ Rust | ✅ 本地 | ✅ | ⚠️ 原库451 | ✗ |
| PyWxDump(后继) | 「全版本」 | 全（HTML含语音图） | ✅（HTML） | HTML/DB | ✅ 免费 | ✅ 本地 | ✅ | ⚠️ 原库删/镜像零散 | 部分 |
| WeChatDataAnalysis | 4.x | 聊天/朋友圈/收藏 | 待验证 | 高仿界面/导出 | ✅ | ✅ 本地 | ✅ | 较新 | ✅ |

---

## 四、推荐方案

### 首选：chatlog（活跃镜像 `forkgitss/sjzar-chatlog`）

理由：唯一把**语音自动实时转 MP3**、图片/视频自动解密做得最干净的方案；纯本地、Apache-2.0、同时吃 3.x/4.0；数据以 JSON/API 出来，最适合做「纪念档案」的结构化长期保存与二次加工。

### 备选：WeChatMsg_2026（要图形界面 + 成册 HTML/Word + 朋友圈）

如果你更想要「点几下就生成还原聊天界面的 HTML/Word 存档、外加年度报告和朋友圈导出」，用它；代价是需要甄别 fork 来源、并接受它是社区续命镜像。

> 两者可以**组合使用**：chatlog 负责稳妥拿到解密数据与 MP3 语音，WeChatMsg_2026 负责生成好看的 HTML 纪念册。

---

## 五、推荐方案操作步骤草稿（用户手动执行）

> ⚠️ 全程离线本地进行。开始前**先给微信数据目录整目录做一次冷备份**（复制一份到移动硬盘），任何解密都在副本上操作，避免动到原始数据。

> 通用前置：先看微信版本（设置→关于）。**≤4.0.3.35（含 3.x）**取 key 最省事；**4.0.3.36+** 密钥不驻留内存、**4.1.10.31+（2026-05）**明文 key 移出堆——被动扫描取不到，需 chatlog-keeper 的调试器兜底、临时降级、或用 `wx_key` 手动取。全程保持微信**登录运行**（取 key 要读进程内存）。

### 路线 A①：chatlog-new（首选，语音实时 MP3 + 结构化 JSON）

1. 确认微信版本；≥4.0.3.36 按上面的通用前置准备好取 key 方式。
2. 从 `github.com/WechatRagAgent/chatlog-new/releases` 下载 `chatlog-new_*_windows_amd64.zip`，解压，**管理员身份**运行 `chatlog.exe`。
3. 执行「获取密钥 / Get Key」→「解密数据库 / Decrypt」（或手动粘贴 `wx_key` 取得的 key）。
4. 启动内置 **HTTP 服务**（默认 `http://127.0.0.1:5030`，以实际为准）。
5. （建议）装 **FFmpeg** 加入 PATH，保证图片 WXGF/视频转码。
6. 导出：文字→调 HTTP API 按联系人+时间段取 **JSON/CSV/TXT**；语音→请求语音资源时**实时转 MP3 返回**，直接存即可播放，无需解码；图片/视频→API 302 跳到已解密媒体地址逐一保存。
7. 归档：JSON + media 文件夹（mp3/图片/视频）打包，放进 `people/mama/raw/wechat/`。

### 路线 A②：chatlog-keeper（首选备用，唯一吃微信 4.1.x 新版）

1. 从 `github.com/labazhou2024/chatlog-keeper/releases` 下载 `chatlog-keeper.exe`（或 `pip install .` 源码装，需 Python 3.9+）。
2. 探测：`chatlog-keeper probe`（看能导出什么、key 取到没）。
3. 取 key（多数自动）：`chatlog-keeper extract-key --source wechat`——默认先被动扫描，取不到自动转调试器（新版微信需要）。也可 `set-key --key <64位hex>` 手动填。
4. 导出微信：`chatlog-keeper wechat --days <天数或不限> --out ./out` → 得 `wechat_messages.json` + 怀旧 HTML。
5. 还原图片：`chatlog-keeper images --src "<微信图片.dat目录>" --out ./out/images`。
6. **⚠️ 检查语音格式**：看 `out/` 里语音是 `.mp3` 还是 `.silk/.aud`。若是裸 silk，用本项目 `tools/silk_decode.py` 批量解码。
7. 归档整个 `out/` 到 `people/mama/raw/wechat/`。

> 封号风险（chatlog-keeper README 明确）：导出本地自己的数据风险≈0；风险只来自取 key 方式——优先被动扫描，取到就缓存复用，**绝不**用它做任何服务器侧自动化。腾讯的处置是下架**仓库**（DMCA），不是封**用户账号**。

### 路线 B：WeChatMsg_2026（要 GUI + HTML 纪念册 + 朋友圈）

> 三个镜像 `AwAcitizen` / `yangbuyiya` / `tigriszhang` 内容一致（同一快照拷贝，2025-04）；只支持微信 ≤4.0，新版不适用。地址：https://github.com/AwAcitizen/WeChatMsg_2026

1. 同样先确认微信版本、做好数据备份、保持微信登录。
2. 从可信 `*_2026` 镜像（如 `AwAcitizen/WeChatMsg_2026`）获取程序，管理员运行。
3. 让它自动获取密钥、解析数据库（4.0 需程序声明支持的对应版本；遇取 key 失败同路线 A 处理版本问题）。
4. 选中与家人的会话 → 选择导出类型（文字/图片/视频/语音/表情全勾）→ 导出为 **HTML**（最能还原聊天界面）或 Word/CSV。
5. （加分）在朋友圈模块导出朋友圈为 **HTML/PDF**。
6. 归档整个导出目录。

---

## 六、语音文件格式说明（重点）

- 微信语音原始格式是 **SILK（Skype SILK v3，本地常见扩展名 `.silk` / `.amr` / `.aud`）**，**不能直接双击播放**。
- **用 chatlog：无需额外解码**——它在返回语音时已**实时转码为 MP3**，保存下来即可播放。
- **用 WeChatMsg_2026：** 导出的 HTML 存档内语音一般已做转码、可在页面内播放；若某方案只吐出裸 `.silk/.amr`，则需**额外解码步骤**，用：
  - `kn007/silk-v3-decoder` 或 `user1121114685/silk-v3-decoder`（批量 SILK→MP3，需配合 FFmpeg）；
  - `lich0821/SilkMp3Converter`（微信语音 ↔ MP3 双向）；
  - `alexyangfox/wechat_silk`（把 amr 拖到 exe 输出 wav，最省事）。
- 结论：**选 chatlog 可以完全跳过手动 SILK 解码**；这是把它列为首选的关键原因之一。

---

## 七、信息来源（均于 2026-08-04 核查）

- chatlog 原仓库（现为删库说明）: https://github.com/sjzar/chatlog
- chatlog FAQ（取密钥/内存/降级/FFmpeg）: https://github.com/sjzar/chatlog/issues/197
- chatlog 4.1.x 取密钥失败与第三方方案: https://github.com/sjzar/chatlog/issues/236 、 /issues/264 、 /issues/317
- chatlog 活跃镜像: https://github.com/forkgitss/sjzar-chatlog 、 https://github.com/WechatRagAgent/chatlog-new
- 取密钥辅助工具 wx_key: https://github.com/ycccccccy/wx_key
- WeChatMsg 续命镜像: https://github.com/AwAcitizen/WeChatMsg_2026 、 https://github.com/yangbuyiya/WeChatMsg_2026 、 https://github.com/tigriszhang/WeChatMsg_2026
- MemoTrace 官网: https://www.memotrace.cn/ ；社区求 4.0 版: https://www.52pojie.cn/thread-2067637-1-1.html
- EchoTrace（含停更/后继说明）: https://github.com/ycccccccy/echotrace 、 https://github.com/ycccccccy/echotrace/blob/main/docs/beginner_guide.md
- WeFlow（EchoTrace 后继·实时）: https://github.com/hicccc77/WeFlow
- wechat-dump-rs v4（原 README 返回 HTTP 451）: https://github.com/0xlane/wechat-dump-rs 、 v4/docs/wechat_4_0_analysis.md
- PyWxDump 原库(删库) 与镜像: https://github.com/xaoyaoo/PyWxDump 、 https://github.com/wo1261931780/fork-PyWxDump 、 https://gitee.com/starplatinum111/PyWxDump
- WeChatDataAnalysis（微信4.x·含朋友圈/收藏）: https://github.com/LifeArchiveProject/WeChatDataAnalysis
- 腾讯 DMCA 下架事件报道: https://zhuanlan.zhihu.com/p/1996354534008702115 、 https://www.secrss.com/articles/87234 、 https://www.cnblogs.com/longware/p/19479076
- SILK 解码器: https://github.com/kn007/silk-v3-decoder 、 https://github.com/user1121114685/silk-v3-decoder 、 https://github.com/lich0821/SilkMp3Converter 、 https://github.com/alexyangfox/wechat_silk

---

## 八、风险与注意事项

1. **镜像随时可能再被下架**：确定要用的工具，下载后立刻本地留存安装包与源码。
2. **微信新版本取密钥变难**：4.0.3.36+ 内存不留 key 是当前最大操作障碍；优先考虑「临时降级取 key 再升级」的稳妥路径。
3. **务必在数据副本上操作**，先冷备份整份微信数据目录。
4. **合规边界**：仅用于导出自己账号、个人/家庭纪念用途；不外传、不用于他人监控。
