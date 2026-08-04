# 微信语音+视频提取专项研究（第二轮）

> 核查日期：2026-08-04　｜　触发：用户明确要求档案必须包含微信**语音和视频**，不接受纯文字。
> 方法：4 个并行研究 agent（chatlog 媒体能力 / 工具全景 / 自研可行性 / 版本与存储）+ **在用户实机上只读实测**。
> 详细子报告见同目录 `_r1`~`_r4`（如已清理，结论已并入本文）。

## 三行摘要

1. **视频：已解决，且是白捡的。** 用户微信 4.1.11.24 的聊天视频以**明文 mp4 直接存在磁盘**（`xwechat_files/<wxid>/msg/video/<年-月>/*.mp4`，实测 `ftypmp42` 真 mp4，387 个 + 缩略图），**零解密、零工具，直接按消息归属复制即可**。
2. **图片：已有解。** 加密 `.dat`（4.0.3 起 per-user AES），chatlog-keeper 的 `images` 命令已实现解密；实测 attach 目录 7.3 万文件、6.8G。
3. **语音：唯一需要动手的一环，但难度中等且路线清晰。** 语音消息不落地成文件，而是 **SILK v3 blob 存在加密的 SQLCipher 消息库里**（`db_storage/message/*.db`，11 个分片）。chatlog-keeper **已经能取到库 key、能读这些库**（它渲染出了 `[语音 Ns]`），只差"取出 blob → SILK 解码成 wav/mp3"。自己写，不依赖任何会被 DMCA 的仓库。

---

## 一、用户实机现状（2026-08-04 只读实测）

- **微信版本**：`Weixin.exe` **4.1.11.24**（4.1.x 新版，明文 key 已离开内存的一档）。最新版为 4.1.12.26（2026-07-22）。
- **数据目录**：新版 `C:\Users\justin\xwechat_files\justzheng525_6e59\`（旧 `WeChat Files` 也在，但主数据在 xwechat_files）。
- **chatlog-keeper 状态**：`probe` 已通过——**key 已缓存、消息库可解密**。即它的主动取 key 在 4.1.11.24 上work（这是全场最关键的资产：一把已经到手、适配你确切版本的钥匙）。

| 数据 | 存储实况 | 提取难度 |
|---|---|---|
| **视频** | `msg/video/<年-月>/*.mp4` **明文** + `*_thumb.jpg`；387 个真 mp4，5.0G | **极低**：直接复制 |
| **图片** | `msg/attach/**/*.dat` per-user AES 加密；7.3 万文件，6.8G | **低**：chatlog-keeper `images` 已实现 |
| **文字** | SQLCipher 消息库（11 分片，802M） | **已解决**：chatlog-keeper `wechat` 导出 |
| **语音** | **无独立文件**——SILK blob 在加密消息库内 | **中**：需自研 blob 提取 + SILK 解码 |
| **文件** | `msg/file/<年-月>/*` 明文（含对方发的文档/音乐） | 极低：复制 |

---

## 二、四个角度的研究结论

### R1 · chatlog（sjzar/chatlog，fork chatlog-new）能否出语音/视频？
- **能**：`/voice/<id>` 把 SILK **实时转 MP3**（`silk.go::Silk2MP3`）；`/video`、`/image` 走 302→`c.File()` 吐**真实 mp4** 和解密 jpg/png。代码级铁证。
- **但对我们没用**：官方只支持微信 **3.x / 4.0**，**不支持 4.1.x**（DB schema 变了，光有 key 也解析不了 4.1 库）。原版 2025-10 删库，fork 停在 2025-07。**用户是 4.1.11.24 → chatlog 直接出局。**

### R2 · 全景：还有哪些工具能同时出语音+视频？
- `LifeArchiveProject/WeChatDataAnalysis`：代码确认语音 SILK→mp3（pilk）+ 视频→mp4，微信 4.x、纯本地、仍活跃、有安装包。**硬伤：无开源协议、DMCA 靶心、未在 4.1.11 明确验证。**
- `CipherTalk/密语(Miyu)`：视频→mp4 确认，语音格式未确认；CC BY-NC-SA、活跃。
- `WeChatMsg_2026`：语音 mp3+视频 mp4，但**冻结在 4.0.3、不含 4.1.x**。
- 经典大库（wechat-dump-rs、wechat-decrypt、PyWxDump、WeFlow）**几乎全被 DMCA 下架**（451/删库）。
- **结论**：没有任何工具"明确宣称"支持 4.1.11.24；现成工具都在 DMCA 靶心，且要么版本不够、要么协议/来源存疑。作为**一次性交叉验证**可用 WeChatDataAnalysis，但不宜作为 20 年档案的长期依赖。

### R3 · 自研提取器可行性（在 chatlog-keeper 已解密数据之上补语音+视频）
- **视频：低。** 实测更简单——4.1.11 聊天视频根本是明文 mp4，连 R3 说的 `.dat` 解密都省了，直接复制。
- **语音：中。** SILK 本体基本不加密（`\x02#!SILK_V3` magic），外层只有已能解的 SQLCipher。**唯一卡点：在解密后的 `message_*.db` 里定位含 SILK blob 的表名/字段名**——方法明确（扫 BLOB 找 magic），需在实库上探测一次。解码链 pilk / kn007-silk-v3-decoder → ffmpeg（24kHz mono）成熟。
- **纠偏**：源码注释猜测的"voicemsg aeskey 二次 AES"在 PC 端聊天语音上大概率不成立（那个 aeskey 是传输层元数据）；不必实现朋友圈/视频号那套 `<enc key>`+ISAAC-64。

### R4 · 版本与存储
- 最新 4.1.12.26（2026-07-22）；用户 4.1.11.24 属同一 4.1 主线。
- 4.x 用 WCDB（SQLCipher4）；4.0.3 起图片改 per-user AES；4.1.x 中后段 raw key 离开内存、改 PBKDF2-HMAC-SHA512 大迭代派生。
- **2026-07 腾讯又一波大规模 DMCA**，主流 Windows 解密工具链大面积失效——这坐实了"不依赖外部仓库、自研并本地留档"的必要性。

---

## 三、推荐方案：混合——现成工具拿易得项，自研补语音

**核心判断**：钥匙已经在手（chatlog-keeper 在 4.1.11.24 上取到并缓存了库 key），三类数据里两类已白给，只有语音需要写代码。为一个要活 20 年的档案，把这段代码**握在自己手里、直接产出 UIF 格式**，远胜于赌某个 DMCA 靶心工具。

| 数据 | 方案 | 执行者 |
|---|---|---|
| 文字 | chatlog-keeper `wechat --days 36500` | 现成，用户跑 |
| 图片 | chatlog-keeper `images` | 现成，用户跑 |
| 视频 | 直接复制 `msg/video/**/*.mp4`（按消息 md5 归属到人） | 自写小工具（简单） |
| **语音** | **自研提取器**：读 chatlog-keeper 已解密的 message db → 定位 SILK blob → pilk/silk→wav→（可选 mp3）| DeepSeek 写 + Codex 审 |

**待落地的一次性探测**（写提取器前必须做）：在你已解密的 `message_*.db` 上，找出存 SILK blob 的表和字段。做法：用 chatlog-keeper 的库 key 打开一个 db 分片，扫描各表的 BLOB 字段找 `\x02#!SILK_V3` / `#!SILK_V3` magic，定位后即可批量导。

**备选/交叉验证**：若自研语音在 blob 定位上受阻，用 `WeChatDataAnalysis` 跑一次语音导出作对照（先做安全审计、用完即弃、本地留档安装包）。

---

## 四、下一步

1. 用户跑 chatlog-keeper 文字 + 图片导出 → `people/mama/raw/wechat/`
2. Claude 写"视频复制 + 按消息归属"小工具（DeepSeek+Codex）
3. Claude 在解密 db 上做 SILK blob 定位探测 → 据此写语音提取器（DeepSeek+Codex）
4. 全部产出统一成 UIF `message` 记录（媒体 ref 指向导出的 mp4/wav）

## 来源

见子报告 `_r1-chatlog-media.md`、`_r2-tools-landscape.md`、`_r3-diy-extractor.md`、`_r4-wechat-versions.md`（各含完整 URL 与核查日期 2026-08-04）。关键实测数据来自用户本机 `xwechat_files` 目录只读排查。
