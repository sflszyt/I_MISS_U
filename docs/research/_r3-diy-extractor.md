# R3 — 自研微信 4.x 语音+视频提取器：技术可行性

> 摘要 1：**视频**基本已解决——聊天视频在 `FileStorage/Video` 下就是和图片一模一样的 V1/V2 `.dat`（AES-128-ECB + XOR），chatlog-keeper 现有的 `_decrypt_v1v2()` 直接复用即可，解出来就是 mp4。难度低。
> 摘要 2：**语音**主流形态是 SILK v3（`\x02#!SILK_V3` 头），PC 端多数**不加密**（存 db blob 或 `.dat` 文件），解码只需 SILK→PCM→ffmpeg。真正的空白是"blob 存哪张表/哪个字段"，需在你自己已解密的 db 上实测确认。难度中（几乎全在验证，不在密码学）。
> 摘要 3：**重大情报**：整个生态（wechat-dump-rs / sjzar-chatlog / ylytdeng）已在 2025Q4–2026Q1 被腾讯 DMCA 全部下架，源码不可读；但格式本身已充分公开，自研不依赖这些仓库。

核查日期：2026-08-04。所有来源 URL 见文末。

---

## 0. 前置：现有工具（chatlog-keeper）已具备的能力

读源码 `chatlog_keeper/wechat_image.py` 确认，它已经把**最难的那块密码学**做完了：

- `_decrypt_v1v2(data, aes_key, xor_key)`：解 V1/V2 `.dat`，layout = `[15B header][对齐后的 AES-ECB 段][raw 中段][XOR 尾段]`。
- `_V1_FIXED_AES_KEY = b"cfcd208495d565ef"`（= `md5("0")[:16]`，全网固定）。
- V2 AES key 派生 `derive_v2_key_from_uin(uin, wxid) = md5(f"{uin}{wxid}").hexdigest()[:16]`；XOR key = `uin & 0xFF`（默认 `0x88`）。
- 头识别 `_V1_SIG = 07 08 "V1" 08 07`、`_V2_SIG = 07 08 "V2" 08 07`；旧格式单字节 XOR（用 JPEG/PNG magic 反推 key）。
- 附带 `wxgf_to_jpeg()`（微信自定义 HEVC 静图 → ffmpeg 转 jpeg）。

**结论**：图片 `.dat` 通路 = 已验证并落地。视频 `.dat` 与它同构（见 §2），语音是另一条完全不同的、更简单的通路（见 §1）。源码里 "STT is deferred" 指的是语音转文字（speech-to-text），不是解密——解密语音根本不需要破 AES。

---

## 1. 微信 4.x 语音文件

### 存哪
两种形态并存，PC 4.x 以 **db blob** 为主：
- **数据库内 blob**：3.x 叫 `MediaMsg.db`，4.0 拆成分片的 `media_*.db`（如 `media_0.db`）。语音 SILK 字节直接作为 BLOB 字段存在消息/媒体表里。db 本身是 SQLCipher4 加密——但**你的 key 已在手**，解开 db 后 blob 就是明文 SILK。
- **文件形态**：安卓端历史是 `voice2/` 目录下 `.amr`/`.aud`；PC 端也可能在 `FileStorage` 落 `.aud` 文件。`.aud` = "没有头的 AMR" 或直接 SILK。

### 加密方案
**关键判断：语音 SILK 本体基本不做 AES/XOR 加密。** 唯一的加密层是外层数据库（SQLCipher4），而你已经能解 db。所以 chatlog-keeper 注释里暗示的"voicemsg XML 里的 aeskey 做 AES"——**在 PC 4.x 聊天语音这条路上大概率不成立**：那个 `<voicemsg ... aeskey=.../>` 是消息 XML 的传输层元数据，落地到本地 db/文件后并不是用它再 AES 一遍。（对照：`<enc key=.../>` 的 AES/ISAAC-64 加密只出现在**朋友圈媒体**，不是聊天语音——见 §2 的重要区分。）

> ⚠️ 待测空白：极少数版本可能对文件形态的 `.aud` 有轻加密。以你实际的 db + FileStorage 为准，先假设"不加密"，实测 hexdump 头部是否为 `02 23 21 53 49 4C 4B 5F 56 33`（`\x02#!SILK_V3`）即可证伪/证实。

### 解出来是什么格式
是 **SILK v3**。签名：首字节 `0x02`，紧跟 ASCII `#!SILK_V3`。（2015-03 之前是 AMR，PC 4.x 时代基本都是 SILK。）

### SILK → wav/mp3 用什么
经典两段式（全网工具都这么做）：
1. **SILK → PCM**：用 Skype SILK SDK 编译出的解码器。参考实现 `kn007/silk-v3-decoder`（C，需 gcc 编译；输入接受"wechat amr/aud、qq slk"）。Python 侧可用 `pilk`（对 SILK SDK 的 Python 绑定，pip 可装，无需自己编译 C）。
2. **PCM → wav/mp3**：`ffmpeg`（chatlog-keeper 已经在用 ffmpeg 转 wxgf，环境里已有）。
   - 注意采样率：微信 SILK 通常 24000 Hz 单声道；解码器输出裸 PCM，喂 ffmpeg 时要 `-f s16le -ar 24000 -ac 1`。

推荐组合：**pilk（SILK→pcm）+ ffmpeg（pcm→mp3/wav）**，纯 Python + 一个已装的外部二进制，最省事。备选：`kn007/silk-v3-decoder` 自带 `converter.sh` 一步到位但要编译 C。

来源：`kn007/silk-v3-decoder`、Kronopath 取证博客（确认 `\x02#!SILK_V3` 头 + SDK 解码 + ffmpeg 出 wav）、CSDN "从 MediaMSG 中提取语音消息"。

---

## 2. 微信 4.x 视频文件

### 存哪
`FileStorage/Video/<YYYY-MM>/` 下的 `.dat`（与图片 `FileStorage/Image/` 平级、同组织方式，按年-月分目录）。db 里存的是指向该文件的元数据（文件名/大小/md5），不是视频二进制。

### 怎么加密
**和图片完全同构**：聊天视频 `.dat` 用同一套 **V1/V2 头 + AES-128-ECB + XOR** 混合方案，头也是 `07 08 V1/V2 08 07`、结构 `[6B sig][4B aes_size LE][4B xor_size LE][1B pad][AES-ECB 段][raw 段][XOR 段]`。key 来源与图片一致（V1 固定 `cfcd208495d565ef`；V2 = `md5(uin+wxid)[:16]`，XOR = `uin&0xFF`）。

> 🔑 **必须区分的两条视频加密路线**（很多博客混为一谈）：
> - **聊天视频**（本任务目标）：FileStorage V1/V2 `.dat`，AES-ECB+XOR，chatlog-keeper 现成代码可解。
> - **朋友圈/视频号视频**（非本任务）：`<enc key=.../>` XML + **ISAAC-64 生成 keystream 再 XOR**，且只加密文件头部（`ftyp`/`moov` atom，因为整段加密对大文件不划算）。这条路更复杂，但你不需要它。

### 怎么还原 mp4
直接把视频 `.dat` 丢进 chatlog-keeper 的 `_decrypt_v1v2()`，输出即完整 mp4 字节（首部应见 `ftyp` atom）。基本不用额外转码。若个别文件解出来仍非标准 mp4，再用 ffmpeg remux 兜底。

来源：多个 4.0 解密工具确认 "same hybrid AES-128-ECB+XOR approach applies to video files in FileStorage/Video"；kanxue 逆向帖确认 ISAAC-64 是**朋友圈**专用。

---

## 3. 微信 4.x 图片 .dat（作对照，确认现工具方法）

chatlog-keeper 用的方法，与全网 4.0 工具一致，**已验证**：
- 旧格式：单字节 XOR，key 由文件头 vs JPEG/PNG/GIF magic 反推。
- **V1**（`07 08 V1 08 07`）：固定 AES key `cfcd208495d565ef` + XOR `0x88`。
- **V2**（`07 08 V2 08 07`，2025-08+）：AES key = `md5(f"{uin}{wxid}")[:16]`（也可从 `Weixin.exe`/`WeChatAppEx.exe` 内存扫），XOR key = `uin & 0xFF`。
- AES 段长度对齐：`aes_size + (16 - aes_size%16)`（PKCS7，块对齐时补满一整块）。
- 解出可能是 jpeg/png/gif/webp，或 `wxgf`（微信 HEVC 静图，需 ffmpeg 转 jpeg）。

结论：图片方法无需改动，视频复用它，语音走独立 SILK 通路。

---

## 4. 4.0 与 4.1.x 的媒体存储/加密差异

- **数据库分片命名**：4.0 起把单一大库拆成 `message_*.db` / `media_*.db` 等约 20+ 个分片；4.0→4.1 是渐进演化，未见"换加密算法"级别的破坏性变更报道。
- **`.dat` 加密**：V2 格式（AES-ECB+XOR）是 2025-08 前后（对应 4.0.x 后期 / 4.1 早期）引入的新格式，早期 4.0 仍可能是 legacy XOR / V1。所以自研工具**必须三种都探测**（legacy_xor / V1 / V2），chatlog-keeper 的 `_detect_encrypt_variant()` 已这么做。
- **语音**：SILK 编码跨 4.0/4.1 稳定，未见差异。
- ⚠️ 待测空白：4.1.x 是否对 V2 的 XOR key 派生或 AES key 来源有微调，需在真实 4.1 数据上比对（现有代码的 UIN 派生法应覆盖，但没有 4.1 专门验证）。

---

## 5. 自研提取器技术路线草图

**输入**：已解密的 4.x 数据库（`message_*.db` / `media_*.db`）+ 微信 `FileStorage` 目录 + 已知 `(key, uin, wxid)`。
**输出**：语音 `.wav/.mp3`、视频 `.mp4`、图片 `.jpg`。

```
                         ┌─ 图片 → FileStorage/Image/**/*.dat
   遍历已解密 db 的消息表 ┼─ 视频 → FileStorage/Video/**/*.dat
   (拿到每条媒体消息的     └─ 语音 → media_*.db 里的 SILK blob（或 .aud 文件）
    类型 + 文件相对路径/blob)
```

| 步骤 | 算法 / 库 | 状态 |
|---|---|---|
| A. 解 db、读消息表、判定媒体类型 | SQLCipher4（key 已在手）；解析消息 XML 取文件名/md5/时长 | ✅ 已验证（chatlog-keeper 现有能力） |
| B. 图片 .dat → jpg | `_detect_variant` → `_derive_v1_key`(XOR) / `_decrypt_v1v2`(AES-ECB+XOR)；wxgf 再 ffmpeg | ✅ 已验证（现成） |
| C. **视频 .dat → mp4** | **复用 B 的 `_decrypt_v1v2()`**，输出即 mp4；异常再 ffmpeg remux | 🟡 高置信度，未在真实视频上跑通——**待测**（预计几乎零改动） |
| D1. **定位语音 blob** | 在解密后的 `media_*.db` 里找含 `\x02#!SILK_V3` 的 BLOB 字段/表 | 🔴 空白：具体表名/字段名需**实测**（用 `sqlite3` 扫 blob 头即可定位） |
| D2. SILK → PCM | `pilk`（Python 绑定）或 `kn007/silk-v3-decoder`（编译 C） | 🟡 库成熟，微信参数（24kHz/mono）待实测确认 |
| D3. PCM → wav/mp3 | `ffmpeg -f s16le -ar 24000 -ac 1 -i - out.mp3` | ✅ ffmpeg 已在环境中 |
| E. 元数据回填 | 用 db 里的时间戳/发送人给输出文件命名归档 | ✅ 直接 |

**空白待测清单（按优先级）**：
1. D1：语音 SILK blob 在 4.x db 的确切位置（这是最大的未知，但方法明确——扫 blob 找 SILK magic）。
2. C：真实视频 `.dat` 是否 `_decrypt_v1v2` 一把出完整 mp4（预计是）。
3. D2：微信 SILK 的实际采样率/是否有 20ms 帧特殊处理。
4. 4.1.x 上 V2 key 派生是否需微调（§4）。

---

## 来源（均核查于 2026-08-04）

- chatlog-keeper 源码（本地）：`chatlog_keeper/wechat_image.py`（V1/V2 .dat 方案、key 派生、wxgf）
- SILK 解码：https://github.com/kn007/silk-v3-decoder （SILK SDK，输入 wechat amr/aud，ffmpeg 出 mp3）
- 语音格式/取证：https://www.kronopath.com/blog/extracting-audio-messages-from-wechat/ （`\x02#!SILK_V3` 头、SDK 解码 + ffmpeg 出 wav）
- 语音存 MediaMsg/media db：CSDN《微信PC端数据库文件解密：从MediaMSG中提取语音消息》 https://blog.csdn.net/sugar/article/details/153715904 （WebFetch 被 521 拦，仅据搜索摘要）
- 4.0 图片/视频 .dat 同构 AES-ECB+XOR：328336690/wechat-decrypt `decode_image.py`（可读源码，确认 V1/V2 结构）https://github.com/328336690/wechat-decrypt ；及多来源搜索摘要 "same approach applies to video files in FileStorage/Video"
- 朋友圈视频 ISAAC-64（区分用，非目标）：看雪 https://bbs.kanxue.com/thread-290047.htm （ISAAC-64 keystream + XOR，仅加密 ftyp/moov 头，key 取自 `<enc key=.../>`）
- **生态 DMCA 下架情报**（均核查于 2026-08-04，返回 HTTP 451）：
  - `0xlane/wechat-dump-rs` → DMCA 2026-01（tencent）
  - `ylytdeng/wechat-decrypt` → DMCA 2026-07
  - `sjzar/chatlog` → 仓库仅剩《项目移除通知》(2025-10-20，收到微信官方函件后删除全部代码与历史)
  - 仍可读的镜像/衍生：`328336690/wechat-decrypt`（仅图片+db，无语音/视频）
