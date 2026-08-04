# R2 · 微信 4.x 语音音频 + 视频导出工具全景（2026）

> **摘要（三行）**
> 1. 唯一被代码确认能同时把微信 **4.x**（含较新 4.x）语音落成可播放 mp3/wav/裸silk、视频落成 mp4、且今日仍在活跃维护的工具是 **`LifeArchiveProject/WeChatDataAnalysis`**（纯本地）；次选 **`ILoveBingLu/CipherTalk`（密语/Miyu）**（确认导 mp4、语音格式待自测）。另有 **`WeChatMsg_2026` fork** 源码确认能导语音 mp3+视频 mp4，但**冻结在微信 4.0.3、不含 4.1.x**。
> 2. 经典大库几乎全军覆没：`0xlane/wechat-dump-rs`、`ylytdeng/wechat-decrypt`、`TC999/WeChatMsg`、连镜像都被腾讯 DMCA（HTTP 451）下架；`PyWxDump` 作者自行删库（仅 3.x）；`sjzar/chatlog` 与 `hicccc77/WeFlow` 被"掏空"只剩 README。
> 3. 多数"活着"的工具只能导**文字/图片**或只做**语音转文字（转录）**，并不产出可播放音频；且很多依赖已被 DMCA 的上游解密器，工具链断裂——**建议立即镜像可用工具**，因为它们全在腾讯打击范围内。

**核查日期：2026-08-04。** 目标：微信 4.x Windows 桌面版（重点 4.1.10.31+），要求产出**可播放语音音频 + 可播放 mp4 视频**，而非纯文字或占位符。

---

## 对比总表（工具 × 语音 / 视频 / 版本 / 存活）

| 工具 | 语音音频导出 | 视频导出 | 微信版本 | 存活状态（2026-08-04） | Star | 协议 | 纯本地 |
|---|---|---|---|---|---|---|---|
| **WeChatDataAnalysis**（LifeArchiveProject）| ✅ **mp3**（首选）+ wav + **裸 .silk 回退**（`pilk` 代码确认）| ✅ **mp4**（ffmpeg + WxAM/wxgf DLL 解码，代码确认）| **微信 4.x**（v4 密钥派生；未标 4.1.10 字样）| 活跃，**今日推送 2026-08-04**，v1.18.5 有 Windows 安装包 | ~1977 | ❌ 无协议（保留所有权利）| ✅ localhost |
| **CipherTalk / 密语 Miyu**（ILoveBingLu）| ⚠️ 很可能（代码含 silk/ffmpeg），**导出格式未文档确认** | ✅ **mp4**（hardlink.db 4.x 视频索引，changelog 确认）| **微信 4.x** | 活跃，推送 2026-08-03 | ~1673 | CC BY-NC-SA 4.0 | ✅ Electron 本地 |
| **lyrcsjy/wechat-decrypt** | ✅ **mp3**（`voice_to_mp3.py` SILK_V3→mp3）+ **wav**（`decode_voice`）| ❌（仅图片 .dat）| **微信 4.0**（SQLCipher4）；未标 4.1.10 | 活跃，推送 2026-07-24 | ~5 | ❌ 无协议 | ✅（本地转录；OpenAI 转录才上传）|
| **gitpyc/WxDencryptedDatabaseReader** | ✅ **mp3**（内置 silk-v3-decoder + ffmpeg）| ✅ **mp4**（弹窗播放器）| 微信 PC，**3.x / 早期 4.x**；需 pywxdump 先解密；未验证 4.1.10 | 活跃未归档，代码最后推送 **2024-10-31**（旧）| ~9 | GPL-3.0 | ✅ |
| **milkgod722/wechat-voice-exporter** | ✅ 裸 **SILK** + **wav**（24kHz/单声道；`silk-python`）| ❌（仅语音）| **微信 4.x**（`message_*.db`/`media_*.db`）| 活跃，推送 2026-07-24 | ~0 | MIT | ✅（音频/库/密钥不上传）|
| **328336690/wechat-decrypt** | ❌ | ❌（仅图片 .dat V2 AES）| **微信 4.0** | 活跃，推送 2026-06-05 | ~11 | MIT | ✅ |
| **H3CoF6/wechat-decrypt-rs** | ❌ | ❌（仅图片 .dat）| 微信 4.x（密钥+图片）| 活跃，推送 2026-04-15 | ~17 | MIT | ✅ |
| **EchoTrace**（ycccccccy/echotrace）| ⚠️ 仅**界面展示/播放**语音，无导出证据 | ❌ | 未明确标 4.1.x | **已停止维护**（推送 2026-03-20，README 自述停维护）| ~3732 | MIT | ✅ |
| **WeFlow**（hicccc77/WeFlow）| ❌（已掏空）| ❌（已掏空）| — | **活着但只剩壳**：代码+Release 全删，README 变段子 | ~13497 | 无 | —（无意义）|
| **PyWxDump**（xaoyaoo）| 仅 3.x 可 mp3/wav；**4.x 完全不支持** | 仅 3.x | **仅 3.x**（≤3.9.12），4.x 打不开 | **作者自行删库** 2025-10-20，仅剩 README | ~9684 | MIT（PyPI 包仍在）| ✅ |
| **WeChatMsg_2026 forks**（LC044 系源码快照）| ✅ **mp3**（`pysilk-mod`→PCM + 内置 ffmpeg，代码确认；3.x+4.0.x）| ✅ **mp4**（4.x 视频为明文，按硬链接库 `shutil.copy` 拷出，代码确认）| **3.x + 4.0.x（≤4.0.3）**；**不含 4.1.x** | 源码冻结于 2025-04（WeChat 4.0.3 期），三个 _2026 fork 字节相同、真源码非占位 | 各 0-8 | MIT | ✅ |
| **WeChatMsg 原库 / MemoTrace 桌面**（LC044）| 见上（同代码）；桌面 2.x 4.x 媒体常受阻 | 见上 | 原库已删源、无 Release | 原库 **未归档但已退役删码**（仅剩 doc+README，转向 TrailSnap）；4.x 版 **TC999/WeChatMsg 已被 DMCA(451)** | ~41929 | MIT | ✅ |
| **0xlane/wechat-dump-rs** | ❌（仅解密数据库，不碰媒体）| ❌ | 3.x + 4.0.x（≤4.0.3）| **DMCA 下架 HTTP 451**（2026-01-29；含镜像）| — | — | ✅ |
| **ylytdeng/wechat-decrypt** | —（不可访问）| — | 4.0 | **DMCA 下架 HTTP 451**（2026-07-15）| — | — | — |
| **sjzar/chatlog** | —（已掏空）| — | — | 在线但 README 变"停止维护/删码"公告 | ~9185 | — | ✅ |

图例：✅=确认可导可播放　⚠️=可能/未确认　❌=不能/不适用

---

## 背景：腾讯的两波 DMCA（这是整份报告的大前提）
- **2026-01-08 腾讯 DMCA**（`github/dmca/2026/01/2026-01-08-tencent.md`）：一次性扫掉 **~4,195 个**微信导出/解密仓库（含大量 fork/镜像），点名 `ppwwyyxx/wechat-dump`、`0xlane/wechat-dump-rs`、`AdminTest0/SharpWxDump`、`git-jiadong/wechatDataBackup`、**`TC999/WeChatMsg`** 等约 27 个主库。
- **2026-07-13 第二波**（`2026/07/2026-07-13-wechat-3.md`）：击杀 `ylytdeng/wechat-decrypt`（2026-07-15 生效）——它是很多语音工具的上游解密器，导致下游工具链断裂。
- 后果：**死库/掏空/改名/镜像**混杂。判断某工具是否可用，必须逐个核实 `pushed_at`、是否 451、是否只剩 README。
- 来源：<https://github.com/github/dmca/blob/master/2026/01/2026-01-08-tencent.md>、<https://github.com/github/dmca/blob/master/2026/07/2026-07-13-wechat-3.md>（核查 2026-08-04）

---

## 逐工具调查

### 1. WeChatMsg / 留痕 / MemoTrace（LC044，及 *_2026 镜像）
**关键更正：`WeChatMsg_2026` fork 里保存着真源码，代码确认能导语音 mp3 + 视频 mp4，但止步 4.0.3、不含 4.1。**
- **原库 `LC044/WeChatMsg`**：**未归档、非 DMCA**（41,929 star，未在腾讯名单里），但**作者主动退役并删光源码**——master 现只剩 `doc/`+`readme.md`（自述"此项目很久没有也不会更新了"，转向 TrailSnap），**无 Release/tag**。协议 MIT。
- **`*_2026` fork（AwAcitizen / yangbuyiya / tigriszhang）= 真源码快照，非死占位**：三者 HEAD 完全相同（`14b466dc`，2025-04-10），含完整 `wxManager`/`exporter`/`ffmpeg.exe`/protobuf。**"2026" 只是改名重挂，2026 年并未新增功能**，代码冻结于微信 **4.0.3** 期。协议 MIT。（`OverTM/LC044.WeChatMsg` 为 2024-11 更旧的 3.x 期快照，GPL-3.0；codeberg kangroo 停在 2023-12，仅 3.x。）
- **语音音频=✅ mp3（代码确认）**：4.x 下语音是 `media.db` 的 `VoiceInfo` 表里的 SILK blob（非松散 .dat）；`decode_audio_to_mp3` 用 `pysilk-mod==1.6.4` 解 SILK v3→PCM，再用**仓库自带 `exporter/ffmpeg.exe`** 封成 **`.mp3`**，写入 `./voice/YYYY-MM/*.mp3`。3.x 时代的 silk→mp3 能力**确实被移植到了 4.0 引擎**。
- **视频=✅ mp4（代码确认，靠拷贝而非解密）**：微信 4.x 视频在 `FileStorage` 里是**明文 `.mp4`**（经硬链接库定位），`VideoExporter` 用 `hard_link_db.get_video()` 解析真实路径后 `shutil.copy()` 到 `./video/YYYY-MM/*.mp4`——无需解密即得可播放 mp4。AES/`.dat` 解密只用于**图片**。
- **版本=3.x + 4.0.x（≤4.0.3）**：双引擎 `db_v3`/`db_v4`；v4 用 PBKDF2+HMAC-SHA512+AES（SQLCipher4）。最后实质提交（2025-04）注明"适配微信 4.0.3 正式版"。**不含 4.1.x**——4.1 改了文件存储路径与 DB 细节，图片 .dat 解密/密钥提取/路径解析很可能需要重新打补丁；语音/视频逻辑虽合理但**未经 4.1 验证**。
- **桌面版 MemoTrace 2.x**（社区流传 2.0.x）：52pojie 论坛（2025-10~2026）大量用户求"支持 4.0+"，实测 4.x 下"**图片没钥匙一直没获取**"、媒体导出受阻，社区把"4.x 媒体+密钥"指向 **EchoTrace+wx_key** 等外部工具。
- **4.x 分支 `TC999/WeChatMsg`**：**已 DMCA，HTTP 451（2026-01-12）**；fork `wo1261931780/fork-WeChatMsg` 尚存。
- 结论：**3.x + 4.0.x：语音✅mp3、视频✅mp4（真能用，用 _2026 fork 源码）；4.1.10.31：代码不覆盖，需自行改 4.1 schema。** 纯本地、MIT。
- 关键源码文件（任一 _2026 fork）：`wxManager/db_v4/media.py`、`exporter/exporter.py`（`decode_audio_to_mp3`/`VideoExporter`）、`wxManager/decrypt/decrypt_v4.py`、`decrypt_dat.py`、`requirements.txt`（`pysilk-mod==1.6.4`）。
- 来源：`gh api repos/LC044/WeChatMsg`（未归档/删码/无 Release）、`repos/AwAcitizen/WeChatMsg_2026`、`repos/TC999/WeChatMsg`→451、<https://www.52pojie.cn/thread-2067637-1-1.html>、<https://www.appinn.com/wechatmsg/>

### 2. PyWxDump（xaoyaoo）及后继/镜像
- **仅支持微信 3.x**（约 3.2.1.154 ~ 3.9.12.x）。微信 4.0 改了进程名/DLL/数据目录/SQLCipher4 加密，PyWxDump **完全打不开 4.x 库**，因此**根本触及不到 4.0+ 的 AES 加密 .dat 语音/视频**。
- 3.x 下：依赖 `silk-python`+`pyaudio`+ffmpeg，**能把语音 SILK→mp3/wav**（真音频，非纯文字），也能处理 3.x 视频。
- **原库状态：作者自行删库跑路**（commit "删库跑路~"，2025-10-20），仅剩 README+img，**非 DMCA**（未被点名）。PyPI 包 `pywxdump 3.1.46`（MIT）仍可装。活跃镜像 `wo1261931780/fork-PyWxDump`（推 2026-03-29）、`alanhzw/PyWxDump` 等**均仍是 3.x**，无一新增 4.x。未见 "PyWxDumpModified"。
- 结论：**对 4.1.10.31 目标完全无效。** 纯本地、MIT。
- 来源：`gh api repos/xaoyaoo/PyWxDump`（desc="删库"）、<https://pypi.org/project/pywxdump/>、DMCA 通知（PyWxDump 未点名，WeChatMsg 点名）

### 3. wechat-dump-rs（0xlane，及镜像）
- **DMCA 下架，HTTP 451**（2026-01-29 生效，Tencent 2026-01-08 通知）。镜像 `forkgitss/...`、`laris/...` **同样 451**。
- 能力（据存档文档/DeepWiki）：**只导出并解密 SQLCipher 数据库**，**不处理任何媒体**——语音/视频/图片 .dat 原样保留、不解密、不落 mp3/mp4。支持 3.x 与 4.0.x（≤4.0.3.22），**未确认 4.1.x**。
- 结论：**语音❌ 视频❌**（本就非媒体工具），且已死。
- 来源：`gh api repos/0xlane/wechat-dump-rs`→451、<https://deepwiki.com/0xlane/wechat-dump-rs>

### 4. ylytdeng/wechat-decrypt
- **DMCA 下架，HTTP 451**（2026-07-15 生效，通知 `2026-07-13-wechat-3.md`）。内容不可访问。
- 它是微信 4.0 SQLCipher4 内存取密钥 + 图片 .dat 解密的上游库，**被多个语音工具当依赖动态 clone**（如 milkgod722），下架后这些工具的"解密数据库"步骤会失败，需换用其他取密钥器。
- 尚存的相关活库：**`lyrcsjy/wechat-decrypt`**（见下，独立、能力更强）；`328336690/wechat-decrypt`、`H3CoF6/wechat-decrypt-rs`（图片密钥）。
- 结论：本体不可用；能力靠其活着的同名替代品继承。
- 来源：`gh api repos/ylytdeng/wechat-decrypt`→451

### 5. EchoTrace / WeFlow / 密语 Miyu
- **EchoTrace（`ycccccccy/echotrace`）**：MIT、3732 star、**未归档但已停止维护**（推送 2026-03-20，README 自述停维护并改推荐 WeFlow/密语）。README 里"解析并展示语音、图片"是**界面播放/展示**意图，**无导出 mp3/wav/裸 silk 的证据**；视频只在（未勾选的）统计雷达图里出现，**无 mp4 导出**。图片解密参考 `recarto404/WxDatDecrypt`（仅图片→jpeg，微信 4）。纯本地。→ **语音⚠️展示不导出、视频❌。**
- **WeFlow（`hicccc77/WeFlow`）**：13,497 star、未归档，**但仓库已被掏空**——源码与全部 Release 删除，只剩 README（自嘲"意念导出"）。多个第三方备份镜像（`Nixer-2301/WeFlowBackup` 等）。→ **实际已死，语音❌视频❌**（无可用代码）。
- **密语 Miyu → 现名 `ILoveBingLu/CipherTalk`**：CC BY-NC-SA 4.0、1673 star、**未归档、非常活跃（推送 2026-08-03）**，Electron 桌面。**视频✅**：changelog（2026.803.0）确认适配微信 4.x `hardlink.db` 视频索引、MD5 缺失时按文件大小匹配、修复 ffmpeg EPIPE 与明文 dat 误异或、视频气泡播放按钮 → **导出可播放 mp4**。**语音⚠️**：代码含 silk/voice/ffmpeg 引用，**但公开文档未确认导出的音频文件格式**（mp3？wav？裸 silk？）。纯本地。其 README 主旨恰是"亲人离世后把微信记录整理为家人的数字资产（那句'儿子/闺女，爸/妈想你了'的语音）"——与本项目高度契合。→ **强次选。**

### 6. WeChatDataAnalysis（LifeArchiveProject）——★ 唯一双确认
- `LifeArchiveProject/WeChatDataAnalysis`，Python，**未归档、极活跃（今日 2026-08-04 10:32 推送、当天多次提交）**，1977 star，Windows 安装包 v1.18.5（2026-07-22）+ macOS(Apple Silicon)。明确"**微信 4.x 数据解密**"。**无开源协议**（LICENSE 缺失=默认保留所有权利）。
- **语音音频=✅（代码确认）**：`src/wechat_decrypt_tool/media_helpers.py` 的 `_convert_silk_to_wav()` 用 **`pilk`** 做 **SILK→WAV**（`rate=24000`）；`routers/chat_media.py` 用 `_convert_silk_to_browser_audio(preferred_format="mp3")` 产出/导出 **`voice_{id}.mp3`**，转码失败时**回退裸 `.silk`**（`audio/silk`），数据取自 `VoiceInfo` 表。→ **mp3（首选）+ wav + 裸 silk 三保险。**
- **视频=✅（代码确认）**：解密加密 .dat，用 **ffmpeg**（`_find_ffmpeg_executable`）+ **WxAM/wxgf DLL 解码器**处理微信私有容器，产出/服务 **`.mp4`**（含 `.m4v/.mov`），`ftyp`/`wxgf` 魔数识别。
- **版本**：v4 密钥派生（`key_v4.py`）、微信 **4.x**；README 未出现精确 "4.1.10.31"，但这是当前在维护、紧跟 4.x 的工具（并致谢 echotrace/WeFlow/H3CoF6）。
- **纯本地=✅**：前端 `localhost:3000` + API `localhost:10392`，免责声明强调本地库/密钥、不上传。Windows 需授管理员/大图 Hook 取密钥；Mac 需手填 64 位密钥。
- 结论：**唯一被代码层证实"加密语音 .dat→可播放 mp3/wav/裸 silk"且"加密视频 .dat→mp4"、微信 4.x、纯本地、在活跃维护**的工具。**唯一硬伤：无开源协议 + 处腾讯 DMCA 靶心，随时可能消失，务必尽快镜像。**
- 关键证据文件：`src/wechat_decrypt_tool/media_helpers.py`（`_convert_silk_to_wav`/pilk、WxAM/wxgf、mp4）、`src/wechat_decrypt_tool/routers/chat_media.py`（`_convert_silk_to_browser_audio(preferred_format="mp3")`、`.silk` 回退、`VoiceInfo`）、`key_v4.py`

### 7. 2026 年其它 / 组合方案
- **lyrcsjy/wechat-decrypt**（活，2026-07-24，无协议）：微信 4.0 SQLCipher4 解密 + 图片 .dat（V1/V2/wxgf）+ **语音 `voice_to_mp3.py`（SILK_V3→mp3，需 ffmpeg）与 `decode_voice`→WAV** + Whisper 转录。**语音音频✅mp3/wav**；**视频未提及=❌**。默认本地（仅选 OpenAI 转录才上传）。
- **milkgod722/wechat-voice-exporter**（活，2026-07-24，MIT）：微信 4.x 入站单聊语音→**裸 SILK + 24kHz WAV** + `manifest.json`（SHA-256）；**纯本地不上传**。**视频❌**。硬伤：其 setup 动态 clone 已 DMCA 的 `ylytdeng/wechat-decrypt` 做数据库解密——该步会失败，需替换取密钥器（如 lyrcsjy）；但语音导出逻辑本身独立，可作用于任意已解密的 4.x 库。
- **gitpyc/WxDencryptedDatabaseReader**（活未归档，GPL-3.0，代码最后 2024-10-31）：Windows WinForms GUI，**语音→mp3**（内置 `silk-v3-decoder`+ffmpeg）、**视频→mp4 弹窗播放**、图片 .dat 转换——**同时具备语音+视频**，但需 **pywxdump 先解出 `de_*.db`** 且拷入 `Video/`、`MsgAttach/` 目录；面向 **3.x/早期 4.x**，**未验证 4.1.10**。
- **328336690/wechat-decrypt**（活，MIT）：微信 4.0 图片 .dat（XOR/V1/**V2 AES-128-ECB+XOR**，密钥从 Weixin.exe 内存取 16 字节 ASCII）——**仅图片**，语音❌视频❌，但**是 4.0 V2 .dat 方案最清晰的文档**。
- **H3CoF6/wechat-decrypt-rs**（活，MIT，Rust）：快速图片 .dat 批量解密——仅图片。
- **SILK v3 解码器（把裸 silk 转 mp3/wav 的"下半段"，均活）**：`kn007/silk-v3-decoder`（3.2k star，MIT，经典、Windows 可跑）、`ljh-sh/silk`（单二进制→wav，mp3 规划中）、`hiwanz/homebrew-silk2mp3`（→mp3/wav 批量）、`geniusnut/silk2wav`。
- **视频→mp4 是全场最薄弱环节**：`gh search` 中**没有任何 2026 年专门做 4.x 视频→mp4** 的独立库；`WxDatDecrypt`(recarto404)/`328336690`/`H3CoF6` 都只做图片。微信 4.0 视频 .dat 与图片同用 V2 AES 方案，理论上可扩展，但除 WeChatDataAnalysis / CipherTalk 外，几乎无人成品化视频导出。
- 技术要点（V2 .dat）：魔数 `07 08 V2 08 07`，结构 `[6B签名][4B aes_size][4B xor_size][1B pad][AES-ECB段][明文段][XOR段]`，AES 密钥=进程内存 16B ASCII，XOR 单字节。

---

## 结论与建议（针对 微信 4.1.10.31+、Windows、要可播放语音音频+mp4 视频）
1. **首选：`LifeArchiveProject/WeChatDataAnalysis`** — 唯一代码确认"语音→mp3/wav/裸silk"且"视频→mp4"、微信 4.x、纯本地、今日仍在更新。硬伤：无协议、DMCA 靶心 → **立刻下载 v1.18.5 安装包并镜像源码。**
2. **次选：`ILoveBingLu/CipherTalk`（密语/Miyu）** — 确认 mp4 视频导出 + 4.x + 活跃，主旨与本项目"思念逝者"高度契合；语音导出格式待自测确认（代码有 silk/ffmpeg）。
2b. **若你的微信恰是 4.0.x（≤4.0.3）**：`WeChatMsg_2026` fork 源码可直接一站式导语音 mp3 + 视频 mp4（pysilk-mod+内置 ffmpeg + 明文 mp4 拷贝）；但 4.1.10.31 不覆盖，需自改 4.1 schema。
3. **仅要语音音频**：`lyrcsjy/wechat-decrypt`（4.0，mp3+wav）或 `milkgod722/wechat-voice-exporter`（4.x，silk+wav；需替换已死的解密依赖）。
4. **组合退路（4.x 全媒体）**：任一存活的 4.x 内存取密钥器（`lyrcsjy` / `H3CoF6/wechat-decrypt-rs` / `328336690`）解出数据库 + 图片/视频 .dat → 语音用 `kn007/silk-v3-decoder` 转 mp3；若能供 `de_*.db` 则 `gitpyc/WxDencryptedDatabaseReader` 一站式看语音 mp3+视频 mp4（限 3.x/早 4.x）。
5. **明确避开**：`ylytdeng/wechat-decrypt`（DMCA 死）、`0xlane/wechat-dump-rs`（DMCA 死且不碰媒体）、`WeFlow`（掏空空壳）、`PyWxDump`（仅 3.x/已删库）、`EchoTrace`（停维护/仅展示不导出）、`sjzar/chatlog`（停维护/删码）。
6. **诚实缺口**：**没有任何工具明确宣称"4.1.10.31"专门支持**；WeChatDataAnalysis/CipherTalk 面向的是 4.1.10.31 所属的**微信 4.x 主线**，实测需自行在该精确版本上验证。**所有可用工具都是腾讯 DMCA 目标，用前先镜像。**

---

*核查方式：WebSearch + WebFetch + `gh api`/`gh search`（GitHub REST），核查日期 2026-08-04。凡标"代码确认"者均已读取对应源码文件核对。*
