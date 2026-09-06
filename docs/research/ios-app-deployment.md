# iOS 部署与专属 App 可行性研究（任务 #22-a，2026-09-02）

> 用户原话："电脑端做完的 companion，如何在手机端（iOS）可以部署？做一个专属 APP 可行不？这样就不用硬部署微信了。"
> 定位：消费端**第三形态**（现有=Tailscale 开 :8020 网页；微信四路径 UIA 死 / iLink 家人向 NO-GO / 服务号需主体 / OCR 最脆）。
> 方法：内部盘点（companion 运行时依赖 / 伦理约束，workflow 内部三路完成；外部扫描因账号限额失败后由主模型逐条补查）+ 本机实测。研究文档由 Claude 直写（docs/research 属主模型职责）。

---

## 0. 一句话结论

**可以，而且几乎不用写代码：iOS 26 起"添加到主屏幕"的网页默认以 Web App 形态打开，现有 companion 页加一个图标即可变成手机上的专属 App（方案 A1）。真正的"专属 App"（WKWebView 壳）技术上同样可行，但它带来的全部收益——图标、无地址栏、少一次点击——恰好全部落在本项目自己划定的禁区"每缩短一步启动路径都是净沉浸增量"里，且不解决任何 A1 解决不了的问题，不推荐。无论哪种形态，她的声音都出不了 4090：手机端只能远程调 PC，或改走"预渲染语音库"的有声档案路线（A3′）。前提条件不变：8A-2b 伦理护栏先上。**

---

## 1. 现状盘点（事实，取自代码与本机）

companion 页对外只有两条依赖：

| 依赖 | 事实 | 出处 |
|---|---|---|
| LLM | BYOK，裸 fetch 任意 OpenAI 兼容端点（OpenAI/Anthropic/DeepSeek/Kimi/自定义），https 跨域，与部署位置无关 | `tools/build_companion_page.py` PROVIDERS |
| TTS | `ttsBase = location.protocol + '//' + location.hostname + ':8022'`，**写死同主机同协议**；三路由 `/health` `/tts` `/session`；`:8022` 不通则文字降级（仅初始化时探测一次） | build_companion_page.py:211、:779、:1157、:328 |

其它与手机部署相关的运行时事实：

- **同源硬要求**：companion 通过 `frame.contentWindow.document` 直接操作 avatar.html（player、click 合成事件、贴片状态），iframe 必须与父页严格同源（:873–:1240 多处）。
- **`file://` 守卫**：`location.protocol === 'file:'` 直接拦截提示（:1249）——本地双击打开不可用，任何壳都必须给页面一个 http(s) 或自定义 scheme 的"源"。
- **iOS 处置已齐**（8B-8/9，09-01 首测已通）：SILENT_WAV 静音解锁、合成 click 打进 iframe、▶ 兜底按钮、`100dvh` + safe-area + `viewport-fit=cover` + 16px 输入防缩放、blob: `ended` 守卫、无需 playsinline。
- **口型在本地算**：avatar.html 用 WebAudio RMS 驱动嘴型，服务端只返 MP3 + `X-Duration-Seconds`，没有 viseme 时间轴——即任何能播 MP3 的 WebView 都能带口型。
- **状态全在 localStorage**：API key / 服务商 / sessions 离线队列（:302、:435、:509）。主屏 Web App 与 Safari 标签**不共享存储**，第一次要重输一次 key。
- **最小可移植静态集**：23 文件 / 22.8 MB（messages 分片 19.9 MB；不带分片 ≈ 2.9 MB）。companion 刻意不进 archive_dist。
- **TTS 服务端**：`tools/tts_server.py`，CosyVoice2-Wu 全量 SFT v0.2 e14（LLM 权重 2.02 GB，exp 目录 31 GB），fp16 关，加载 73 s，≈6 s/句，`max_chars` 120，绑 0.0.0.0、无 token；GPU 常驻 5.8/24.5 GB。**重启后 :8020/:8022 需手动拉起**（HANDOFF ⓪⁸ D），Tailscale 有登录自启任务 `TailscaleUserspace`（userspace 网络模式）。
- **护栏**：8A-2b 条件 a–e 仍是 TODO（build_companion_page.py:834；task_plan Phase 8A）。

## 2. 硬约束（由三条铁律直接推出，不随方案变）

### 2.1 她的声音出不了 4090

- 现役 e14 是 **CosyVoice2-0.5B 的全量 SFT `.pt`**（Wu 双语域）。2026 年的端侧 TTS 运行时只跑**官方检查点**：mlx-audio 的模型表里没有任何 CosyVoice / GPT-SoVITS（只有 Qwen3-TTS、Kokoro、OmniVoice 等）；speech-swift 只支持 Fun-CosyVoice3-0.5B 官方版（4-bit 1.2 GB ～ bf16 2.1 GB，9 语种，无方言，"works exclusively with official checkpoints"）。**没有现成运行时能加载我们的 SFT 权重。**
- 端侧零样本克隆（CosyVoice3 / Qwen3-TTS 用她的参考片段）能得到"像她的音色"，但**上海话发音会回到 M1 之前的状态**——SFT 的全部理由就是零样本读不准沪语。
- 自己把 CosyVoice2 移植到 MLX/CoreML 并转换 SFT 权重：工程量与 M1 同量级，且违背"不需要实时、离线批量"的选型前提。**不建议。**
- 结论：手机拿到她的声音只有三条路——**远程调 PC（A1/A2）、预渲染语音库（A3′）、不用声音（文字降级）**。

### 2.2 云 GPU = NO-GO

SFT 权重是她声音的派生物，与 `people/` 派生层同性质；铁律 3.2"永不上传到任何外部服务"直接适用。租云 GPU 跑 tts_server 不在选项里，不需要再研究。

### 2.3 伦理上限：App 的"默认能力"整体落在禁区

- desktop-companion.md 6.2 ①：always-on、开机自启、系统通知、"她在等你"式空闲暗示——**任何护栏救不回"永远在场"这个属性本身**。iOS App 的原生能力集（推送、角标、后台刷新、Siri 快捷指令、小组件、锁屏实况）**恰好就是这一整组**。
- 6.2 ③："现状的那一点启动摩擦，是目前唯一无法用设计替代的保护机制——**每缩短一步启动路径都是一次净沉浸增量**，没有反向补偿手段。"主屏图标缩一步，壳 App 再缩一步，两者都是这条的直接对象。
- form-factor.md：App 形态 2.5/5，20 年寿命归零。**App 只能是"壳/窗口"，永远不是档案载体**——档案仍是 archive_dist 静态 HTML。
- 09-02 起分句语音流水线显著提升沉浸感，CLAUDE.md 已记"8A-2b 护栏未上不宜日常常用"。**任何进一步缩短路径的形态，都以护栏先上为前提。**

## 3. 方案矩阵

| 方案 | 形态 | 代码改动 | 她的声音 | PC 依赖 | 伦理位置 | 结论 |
|---|---|---|---|---|---|---|
| **A0 现状** | Safari 开 `http://100.116.45.2:8020/companion.html`（Tailscale） | 0 | ✅ 远程 :8022 | PC 常开 + 两服务手动拉起 | 6.2 ② 上限内 | 已有 |
| **A1 主屏 Web App** | 添加到主屏幕 → iOS 26 默认以 Web App 打开（无地址栏、独立存储） | `build_companion_page.py` 加 `apple-touch-icon`（`<title>陪伴</title>`、`viewport-fit=cover` 已有）；可选 `tailscale serve` 给 https | ✅ 同 A0 | 同 A0（应做开机自启） | 缩一步；仍是"打开才在" | **推荐**（护栏先上） |
| **A2 WKWebView 壳 App** | Swift/Capacitor 打包 23 文件；`WKURLSchemeHandler` 自定义 scheme 保同源；`mediaTypesRequiringUserActionForPlayback=[]` 免解锁；ttsBase 改可配置；key 进 Keychain | 中：ttsBase 参数化 + 壳工程 + 签名分发 | ✅ 仍是远程 :8022 | **一个不少** | 再缩一步；原生能力全在禁区，需自我克制不用 | **不推荐**：收益全是沉浸增量，未解决 A1 解决不了的任何问题 |
| **A3 全端侧 App** | LLM + TTS 都在手机 | 大 | ❌（§2.1） | 无 | — | 不成立 |
| **A3′ 有声档案** | 预渲染语音库（Tier-1 记忆卡、常用句、问候、告别用 e14 离线批量合成 WAV）+ 检索式对话只播预渲染句 | 中（构建端批处理 + archive_dist 一页） | ✅ 但**只有预录句** | 无 | **与"档案优先"同向**：语音库本身是档案资产 | 值得另立项（不是 companion） |
| **A4 家用服务器** | PC 常开 / Wake-on-LAN；Mac mini MPS 未验证 | 小（计划任务自启） | ✅ | 就是它 | — | 不是 iOS 方案，是 A1 的前提 |
| **A5 云 GPU** | — | — | — | — | 铁律 3.2 | **NO-GO** |

### 3.1 A1 细节

1. **零 https 也能用**：companion 只用 fetch / WebAudio / localStorage，不用 Service Worker、麦克风、推送，**没有任何 secure-context 需求**；http 站点同样可以"添加到主屏幕"。页面 http → ttsBase 自动是 http，无混合内容问题。
2. **如需 https**（只有两种理由：Service Worker 缓存 2.9 MB 壳做离线打开；将来想用麦克风）：`tailscale serve --bg --https=443 http://127.0.0.1:8020` 与 `tailscale serve --bg --https=8022 http://127.0.0.1:8022`。因为 ttsBase 取 `location.protocol`，页面变 https 后自动请求 `https://<机器>.<tailnet>.ts.net:8022`，**零改动**。前置：管理台开 MagicDNS + HTTPS 证书；serve 只代理 `http://127.0.0.1`；**userspace 模式 + 多 https 端口须实测**（未验证项）。
3. **独立存储**：Web App 容器与 Safari 不共享 localStorage → 第一次重输 API key、重选服务商；sessions 离线队列也是独立的（`:8022` 通了即 flush，行为不变）。
4. **音频解锁规则同 Safari**：SILENT_WAV / 合成 click / ▶ 兜底全部沿用；09-01 首测已通过的路径不变。
5. **Tailscale iOS**：VPN On Demand 可设"Wi-Fi/蜂窝 Always"，图标点开即通，不必先开 Tailscale App。这是网络层常连，不是"她"常在——不触 6.2 ①。
6. **PC 侧要补的**：tts_server 与静态站的开机自启（Windows 计划任务，与 `TailscaleUserspace` 同法）。注意这与 6.2 ①"开机自启"不是一回事——自启的是服务器，不是对话窗；窗口仍要人打开。

### 3.2 A2 为什么不做（技术上全通，判断上不通）

- 技术闭环存在：自定义 scheme 解决 `file://` 守卫与 iframe 同源（Capacitor 即 `capacitor://localhost`）；`mediaTypesRequiringUserActionForPlayback = []` 让整套 iOS 解锁流程消失（iOS 26 新 SwiftUI `WebView` 尚无此项，需继续用 `WKWebView`）；ttsBase 改为设置项。
- 分发：免费 Apple ID 签名 7 天过期、每设备 3 个 app；$99/年 账号 1 年签名；TestFlight 90 天且需 App Store Connect 走审。**单用户自用不需要 App Store**，但每年至少重签一次。
- 它能给的：图标（A1 已有）、去地址栏（A1 已有）、免解锁（A1 已有兜底）、Keychain（对单用户无实际收益）。**再往上只剩推送/角标/后台/Siri——全部在 6.2 ① 名单里。**
- 唯一合理的 A2 时机：b（产品化）需要给**陌生用户**分发时。那是 b 的议题，不是 a 的。

### 3.3 A3′ 为什么值得单独立项

- 它是目前**唯一"PC 关机也有她的声音"的路**，且完全不依赖模型、订阅、显卡——正是 CLAUDE.md 第一段对档案的定义。
- 产物是 WAV + JSON 清单，直接进 archive_dist；20 年后能放。
- 代价是"她只会说预录的话"——这**恰好是把 Tier-3 关在门外的形态**（模型生成的新句子没有声音，天然可辨），比实时合成更安全。
- 与 companion 的关系：不是替代，是档案侧的补齐；companion 仍是"PC 在时的实时窗"。

## 4. "不用硬部署微信了"——对照

| 微信路径的问题 | A1 下 |
|---|---|
| 4.1.x UIA 死 / iLink 家人向 NO-GO / OCR 最脆 | 全部不存在，不碰微信 |
| 第三方受众（家人）伦理、欺骗性 | 受众只有用户本人，Tailscale 私网 |
| 需要 24h 挂号 / 小号 / 模拟输入 | 不需要；仍是"打开才在" |
| 微信语音条 = 她的声音进入别人手机 | 不发生 |

结论：a 的答案同时关闭了"为了手机而上微信"的动机；微信方向剩余的价值只在"家人也要用"——那已被 08-29 研究裁为默认 NO-GO。

## 5. 与铁律 2 的逐项对照

| | A0/A1 | A2 | A3′ |
|---|---|---|---|
| Tier 标签 / 非本人 banner / 合成声明 | 沿用 companion 现有 | 同（壳内是同一页） | 只播 Tier-1/2 来源句，天然合规 |
| 8A-2b 关窗道别 / 空闲离场 / 节律限速 / 使用统计自见卡 | **未上，须先补** | 同 | 部分不适用（无实时生成） |
| "永远在场"风险 | 无（图标≠在场） | 原生能力全在禁区，靠自律 | 无 |
| 档案优先 | 中性 | 反向（壳是死物） | 正向 |
| sessions 日志（Tier-3 永久） | 沿用 | 沿用 | 无新话语 |

## 6. 推荐路线

0. **前提**：8A-2b a–e 落地（所有形态共享；当前最高优先，与 HANDOFF 下回合顺序一致）。
1. **A1**（≤ 半天）：`build_companion_page.py` 加 `apple-touch-icon`（用 avatar 静帧）→ DeepSeek 写、Codex 审；PC 侧 tts_server + 静态站计划任务自启；真机：添加到主屏幕 → 首次重输 key → 8B-4 验收顺带覆盖。
2. **可选**：`tailscale serve` https（仅当要离线壳/麦克风时；先实测 userspace 模式）。
3. **建议另立项 A3′ 有声档案**：预渲染语音库进 archive_dist——无论 iOS 与否都是档案净增量。
4. **A2 不做**，留待 b 的分发需求再议。
5. **A5 不做**，已由铁律裁定。

## 7. 待用户裁决

- **D1** 接受 A1 为 iOS 正式形态？同意"8A-2b 先行"作为前提？
- **D2** 要不要 https（tailscale serve）——现无必要，只为将来离线壳/麦克风。
- **D3** 是否立项 A3′ 有声档案（预渲染语音库）。
- **D4** 确认 A2 壳 App 在 a 范围内不做。
- **D5** 用户侧：PC 常开 + 两服务自启（或接受每次手动拉起）。

## 8. 未验证项（写明，不当事实）

- `tailscale serve` 在 Windows **userspace-networking** 模式下的行为；同时开 443 与 8022 两个 https 监听。
- iOS 26 对 **http** 站点"作为 Web App 打开"的实际行为（iOS 26 前 http 站点可加主屏为既有事实；26 的默认切换是否区分协议未见文档）。
- Apple Foundation Models（端侧 ~3B，4096 token/会话，iOS 26.1 起支持简中）装不下 persona + 124 条记忆，仅记录不作候选；llama.cpp 手机端跑 4–7B 的沪语人格质量未测。
- Mac mini / MPS 跑 CosyVoice2 SFT 推理未测（A4 变体）。

## 9. 来源

**内部**：`tools/build_companion_page.py`（:211 ttsBase、:244 SILENT_WAV、:302/:435/:509 localStorage、:779 probeTts、:834 8A-2b TODO、:873–:1240 iframe 同源操作、:1249 file:// 守卫）；`tools/tts_server.py`；`docs/research/desktop-companion.md` §6.2 ①②③、§7；`docs/research/form-factor.md`（A 0.5 / B 2.5 / C 5）；`docs/HANDOFF.md` ⓪⁸ D、⓪⁹；`task_plan.md` Phase 8A/8B/10/11；本机实测（archive_out 270 MB、e14 LLM 权重 2.02 GB、GPU 5.8/24.5 GB、:8020/:8022 在线、任务 `TailscaleUserspace`）。

**外部**：
- iOS 26 主屏网页默认作为 Web App 打开：https://mjtsai.com/blog/2025/10/03/web-apps-in-ios-26/ ；WebKit Safari 26 特性：https://webkit.org/blog/17333/webkit-features-in-safari-26-0/ ；iOS PWA 限制综述：https://www.magicbell.com/blog/pwa-ios-limitations-safari-support-complete-guide
- Tailscale serve（`--https=<port> http://127.0.0.1:<port>`，仅代理 127.0.0.1，TLS 由 tailscaled 终止）：https://tailscale.com/docs/reference/tailscale-cli/serve ；https://tailscale.com/docs/features/tailscale-serve ；iOS VPN On Demand：https://tailscale.com/docs/features/client/ios-vpn-on-demand
- WKWebView / Capacitor 自定义 scheme 同源：https://github.com/ionic-team/capacitor/issues/788 ；`mediaTypesRequiringUserActionForPlayback` 与 iOS 26 SwiftUI WebView 缺项：https://developer.apple.com/forums/thread/803344
- Apple 免费签名 7 天、TestFlight 需分发证书：https://learn.microsoft.com/th-th/previous-versions/xamarin/ios/get-started/installation/device-provisioning/free-provisioning ；https://developer.apple.com/testflight/
- 端侧 TTS 运行时模型表（无 CosyVoice2/GPT-SoVITS）：https://github.com/Blaizzy/mlx-audio ；speech-swift 仅官方 CosyVoice3-0.5B：https://soniqo.audio/guides/cosyvoice
- Apple Foundation Models 端侧 4096 token：https://developer.apple.com/documentation/technotes/tn3193-managing-the-on-device-foundation-model-s-context-window ；语言支持：https://rudrank.com/exploring-foundation-models-supported-languages-internationalization
