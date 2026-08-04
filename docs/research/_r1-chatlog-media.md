# R1 · chatlog 导出微信语音/视频/媒体文件能力深挖

> **三行摘要**
> 1. **语音**：chatlog 的 HTTP API `/voice/<id>` 会把微信原始 SILK 音频**实时转码成 MP3** 后直接返回（`audio/mp3`），转码失败才回退裸 `audio/silk`——源码 `route.go::HandleVoice` + `silk/silk.go::Silk2MP3` 铁证。
> 2. **视频/图片**：`/video/<id>`、`/image/<id>` 走 **302 跳转到 `/data/<相对路径>`**，最终 `c.File()` 直接吐**磁盘上的真实文件**（视频是微信原生 `.mp4`，图片是把 `.dat` 用 `Dat2Image` 解密成 jpg/png）——是真文件，不是占位符。
> 3. **版本/坑**：原版 **sjzar/chatlog 已于 2025-10-20 被微信官方函件要求删库**（仅剩说明文件）；活跃 fork **WechatRagAgent/chatlog-new 停在 v0.0.16 / 2025-07-25**，官方只声明支持 **微信 3.x / 4.0**，**不支持 4.1.x**；4.1.10.31+ 明文 key 已移出内存，需靠 wx_key 类第三方 DLL 注入取 key（该工具本身也已被 DMCA 删库）。

**核查日期：2026-08-04**

---

## 0. 背景：仓库现状（关键前提）

- **原版 `sjzar/chatlog` 已删库**。仓库 README 现仅剩《项目移除通知》，更新日期 **2025-10-20**，原文：「我收到了来自微信官方的函件，明确项目的核心功能存在合规风险……我决定**移除本项目的全部代码与提交历史记录**。此代码仓库现在仅保留这份说明文件。」
  来源：<https://github.com/sjzar/chatlog>（README，核查 2026-08-04）
- 因此原版代码/预编译包已无法从官方仓库获取。分析只能依据**活跃 fork `WechatRagAgent/chatlog-new`**（保留了删库前的完整代码），以及 fork 前的历史 issue。
  - chatlog-new 元数据：最后 push **2025-07-25**，唯一 release **v0.0.16（2025-07-25）**，默认分支 `main`，仅 18 stars。
    来源：`gh api repos/WechatRagAgent/chatlog-new`（核查 2026-08-04）
  - chatlog-new 提交历史显示媒体能力早在 2025 年 4 月就定型：`support voice message (#31)` 2025-04-11、`support thumb url (#62)` 2025-04-19；此后无媒体相关更新。
    来源：`gh api repos/WechatRagAgent/chatlog-new/commits`（核查 2026-08-04）

> 注意：本地安装目录 `installers/chatlog-keeper-0.2.0` 是一个 **Python 封装层（chatlog-keeper）**，它调用 chatlog 的 HTTP API，本身不实现解密/转码。真正的媒体导出逻辑在 chatlog（Go）里。

---

## 1. 语音音频文件导出：真的能拿到 MP3

**结论：能，直接拿到 MP3，是「实时 SILK→MP3」转码。**

### 证据 A — HTTP 路由与语音处理（chatlog-new `internal/chatlog/http/route.go`）

```go
router.GET("/voice/*key", s.GetVoice)   // 路由

func (s *Service) GetMedia(c *gin.Context, _type string) {
    ...
    switch media.Type {
    case "voice":
        s.HandleVoice(c, media.Data)   // 语音走独立处理
        return
    default:
        c.Redirect(http.StatusFound, "/data/"+media.Path)  // 图片/视频/文件走 302
    }
}

func (s *Service) HandleVoice(c *gin.Context, data []byte) {
    out, err := silk.Silk2MP3(data)              // 实时转码
    if err != nil {
        c.Data(http.StatusOK, "audio/silk", data) // 转码失败才回退裸 SILK
        return
    }
    c.Data(http.StatusOK, "audio/mp3", out)       // 正常：返回 MP3
}
```
来源：<https://github.com/WechatRagAgent/chatlog-new/blob/main/internal/chatlog/http/route.go>（核查 2026-08-04）

### 证据 B — SILK→MP3 转码实现（`pkg/util/silk/silk.go`）

```go
import (
    "github.com/sjzar/go-lame"   // LAME MP3 编码
    "github.com/sjzar/go-silk"   // SILK 解码
)
func Silk2MP3(data []byte) ([]byte, error) {
    sd := silk.SilkInit()
    pcmdata := sd.Decode(data)        // SILK → PCM
    ...
    le := lame.Init()
    mp3data := le.Encode(pcmdata)     // PCM → MP3
    return mp3data, nil
}
```
即 **go-silk 解码 SILK → PCM，go-lame 编码 PCM → MP3**，纯内存实时完成，不落中间文件。
来源：<https://github.com/WechatRagAgent/chatlog-new/blob/main/pkg/util/silk/silk.go>（核查 2026-08-04）

### 证据 C — README 明文描述

原文：「针对原始 SILK 语音做了**实时转码 MP3 处理**」；「语音内容：`GET /voice/<id>`」。
来源：<https://github.com/WechatRagAgent/chatlog-new/blob/main/README.md>（核查 2026-08-04）

**要点/坑**：
- 返回的 MP3 是流式响应体（`c.Data`），**不带 Content-Disposition 下载头**，也**没有 `?format` 让它存成 silk**——只要转码成功一律 MP3。要批量落盘需自己抓 HTTP body 存 `.mp3`。
- 转码失败会静默回退成 `audio/silk`（裸 SILK，浏览器/普通播放器放不了）。少数损坏或非标准 SILK 会踩这条路径。

---

## 2. 视频 / 图片 / 文件导出：真实 mp4，不是占位符

**结论：视频是真实 `.mp4`；图片是解密后的真实 jpg/png；文件是原始文件。全部真文件。**

### 机制（同一份 `route.go`）

- 路由：
  ```go
  router.GET("/image/*key", s.GetImage)  // → GetMedia(c,"image")
  router.GET("/video/*key", s.GetVideo)  // → GetMedia(c,"video")
  router.GET("/file/*key",  s.GetFile)   // → GetMedia(c,"file")
  router.GET("/data/*path", s.GetMediaData)
  ```
- 图片/视频/文件在 `GetMedia` 里走 `default` 分支：**302 重定向到 `/data/<media.Path>`**。
- `GetMediaData` 把 data 目录下的相对路径拼成绝对路径，然后：
  ```go
  switch {
  case ext == ".dat":
      s.HandleDatFile(c, absolutePath)   // 图片 .dat → 解密成 jpg/png/gif/bmp
  default:
      c.File(absolutePath)               // 视频.mp4 / 文件 直接原样返回磁盘文件
  }
  ```
- 图片解密：`HandleDatFile` 调 `dat2img.Dat2Image(b)`，按魔数输出 `image/jpeg|png|gif|bmp`；解密失败则 `c.File(path)` 回退原始 `.dat`。

来源：<https://github.com/WechatRagAgent/chatlog-new/blob/main/internal/chatlog/http/route.go>（`GetMedia` / `GetMediaData` / `HandleDatFile`，核查 2026-08-04）

**为什么视频是真 mp4**：微信 4.0/3.x 把视频与短视频（Sight）以**原生 `.mp4`** 存于本地 data 目录，chatlog 不做转码、直接 `c.File()` 吐原文件——所以拿到的就是可播放的真实 mp4，非占位。README 也列「视频内容：`GET /video/<id>`」「多媒体内容：`GET /data/<data dir 相对路径>`」。
来源：<https://github.com/WechatRagAgent/chatlog-new/blob/main/README.md>（核查 2026-08-04）

### 如何批量拿媒体（API 端点/参数）

1. **先查消息**：`GET /api/v1/chatlog?time=<范围>&talker=<对方>&format=json`，从每条消息里解析出媒体的 key/id（图片/视频/语音/文件在 message 结构里各有引用）。
   来源：`route.go::GetChatlog`（核查 2026-08-04）
2. **再逐个取媒体**：
   - 语音：`GET /voice/<id>` → 直接得 MP3 body。
   - 图片：`GET /image/<id>` → 302 → `/data/...` → 解密后的 jpg/png。
   - 视频：`GET /video/<id>` → 302 → `/data/...` → 真实 mp4。
   - 文件：`GET /file/<id>` → 302 → 原始文件。
   - 附带 `?info=` 参数（任意非空）可让 `/image|/video|/voice|/file` 返回该媒体的 JSON 元数据而非文件体（`if c.Query("info") != "" { c.JSON(...media) }`）——便于先探测路径/类型。
   来源：`route.go::GetMedia`（核查 2026-08-04）
3. **key 长度约定**：`GetMedia` 里 `if len(k) != 32` 的 k 被当作 **data 目录相对路径**直接 302 到 `/data/`；长度 32 的 k 才去 DB 查媒体记录。批量脚本可两种都喂。

> 没有单一「一键导出全部媒体」端点；批量导出=遍历消息 JSON 抽 id → 循环 GET 各媒体端点 → 保存 body。chatlog-keeper（本地 0.2.0 封装）正是干这个的上层。

---

## 3. 支持的微信版本：3.x / 4.0 能用，4.1.x 官方不支持

| 微信版本 | chatlog 官方支持 | 取 key 情况 |
|---|---|---|
| 3.x（Win/mac） | ✅ 明确支持 | 内存扫描直接取 key |
| 4.0.x（Win 4.0.3.36 / mac 4.0.3 以下） | ✅ 明确支持 | 内存扫描可取 |
| 4.0.3.36+ / 4.1.x | ❌ **官方未支持** | key 不再长期驻留内存，内存扫描失败 |

- chatlog-new README 原文仅：「**支持微信 3.x / 4.0 版本**」，**全文无 4.1**。
  来源：<https://github.com/WechatRagAgent/chatlog-new/blob/main/README.md>（核查 2026-08-04）
- **4.0.3.36 & macOS 4.0.3 以上**起，微信不再长期在内存保留派生后的加密 key；**4.1+ 只存派生前 passphrase**，传统内存扫描拿到的值无法直接喂给 SQLCipher。
  来源：`sjzar/chatlog` issue #197（FAQ）、社区总结，<https://github.com/sjzar/chatlog/issues/197>（核查 2026-08-04）
- **4.1.0.34 取 key 直接失败**：用户用 chatlog v0.0.29 报「获取密钥失败:no valid key found」，issue 内无官方解法。
  来源：<https://github.com/sjzar/chatlog/issues/264>（核查 2026-08-04）
  （旁证：#264 里出现的 **v0.0.29** 说明删库前 sjzar 原版版本号已远超 fork 的 v0.0.16——fork 落后。）

### 4.1.x（含 2026 最新 4.1.10.31+）怎么取 key —— 只能靠外部工具

- **可行路线**：用第三方工具（**wx_key**，DLL 注入而非内存扫描）从 4.1 进程取 data key，再在 **chatlog UI 手动输入 key** 解密。
  - 4.1.2.17 实证：「使用大佬开发的工具手动获取秘钥，手动输入到 chatlog 解密即可」。
    来源：<https://github.com/sjzar/chatlog/issues/317>（核查 2026-08-04）
  - 有 fork（`teest114514/chatlog_alpha`）直接「通过 dll 调用方式」集成 wx_key 的 dll 取 data key、并修复 dat 解密。
    来源：<https://github.com/sjzar/chatlog/issues/321>（核查 2026-08-04）
- **坑**：`ycccccccy/wx_key` 本身**已被 DMCA 删库**，仓库现仅剩「已升级为 100% 绝对安全版本」的讽刺 README，原代码/发行版需从存档或镜像获取。其宣称「支持微信 4.0 版本以上」的 data key + 图片 key。
  来源：<https://github.com/ycccccccy/wx_key>（核查 2026-08-04）
- **4.1.10 现状**：macOS 4.1.10 上多个解密项目报「内存扫描 0 个候选密钥 / find_all_keys 扫描 0」，即最新 4.1.10.x 明文 key 移出内存后，纯内存扫描路线基本失效，DLL 注入类工具成为唯一实用手段（且随微信小版本更新易失配）。
  来源（旁证）：wechat-decrypt / wx-cli issues（4.1.10 扫描 0），见搜索结果聚合，核查 2026-08-04。

---

## 4. chatlog-new 相比原版的媒体增强

- chatlog-new 是原版删库前的 fork，**媒体能力与原版同源**（语音 SILK→MP3、视频/图片 302→/data、dat 解密），**未见针对媒体导出的独立增强**——README 未列出与 sjzar 原版的差异，提交历史里媒体相关提交（voice #31、thumb #62）都是 2025 年 4 月上游同款功能。
- chatlog-new 后期新增的是**非媒体**功能：`getChatlogCount` API（`GET /api/v1/chatlog/count`，2025-07-25）、message search（#60）等。
  来源：`gh api repos/WechatRagAgent/chatlog-new/commits`、README（核查 2026-08-04）
- **最新 release：v0.0.16，日期 2025-07-25**（唯一 release）。此后仓库无新代码提交（2026-08-01 的 updated 时间仅为元数据更新，非 push）。
  来源：`gh api repos/WechatRagAgent/chatlog-new/releases`（核查 2026-08-04）

> 结论：想要「媒体导出更强」的增强，chatlog-new 并没有提供；它相对原版的价值主要是**在原版删库后仍保留可用代码**。真正解决 4.1 取 key 的增强在别的 fork（如 `teest114514/chatlog_alpha` 集成 wx_key dll）。

---

## 5. 已知媒体导出限制 / 坑（issue 实证）

1. **图片解密后只出 db 文件夹 / 图片 key 问题**：#269「已获得图片 asekey，但解密后只输出了 db 相关的文件夹」；#228「http 无法显示图片」；#255「微信 V4 下，在 ScanAndSetXorKey 完成前请求图片，图片会有问题」。→ **图片 key（XOR/aes key）与数据 key 是两套**，V4 下图片解密依赖额外的 image key 扫描完成，时序早了会拿到坏图。
   来源：<https://github.com/sjzar/chatlog/issues/269>、<https://github.com/sjzar/chatlog/issues/228>、<https://github.com/sjzar/chatlog/issues/255>（核查 2026-08-04）
2. **图片 key 需手动设置的补丁**：#238「feat(setting): add image key manual setting」、#302「fix(dat2img): fix retrieving image key」——说明 dat 图片解密在 V4 上不稳定，需手动补 image key。
   来源：<https://github.com/sjzar/chatlog/issues/238>、<https://github.com/sjzar/chatlog/issues/302>（核查 2026-08-04）
3. **语音只能转文字诉求**：#297「语音消息要怎么获取，我想把语音消息通过 ai 转成文字」——语音本身能导出 MP3，但 chatlog 不含 ASR，转文字要自己接。
   来源：<https://github.com/sjzar/chatlog/issues/297>（核查 2026-08-04）
4. **语音静默回退裸 SILK**：`HandleVoice` 转码失败返回 `audio/silk` 且 HTTP 200，不报错——批量脚本若只认 200 会把播不了的 silk 当成功。（代码级坑，见 §1 证据 A）
5. **视频/媒体依赖本地 data 目录文件仍在**：`/video` 走 `c.File()` 读磁盘，**若微信已清理/未下载原视频文件，则 302 后 404**（`GetMediaData` 找不到文件返回 `File not found`）。历史消息里「未下载」的视频拿不到。
   来源：`route.go::GetMediaData`（核查 2026-08-04）
6. **4.1.x 整体门槛**：取不到 key → 一切媒体导出免谈（见 §3）。这是 2025 下半年起最大的实际阻塞。

---

## 一句话结论

**能拿到语音 MP3 和视频 MP4**——chatlog（含活跃 fork chatlog-new）的 `/voice` 端点实时把 SILK 转成真 MP3、`/video` 直接吐微信原生真 MP4（图片则解密成 jpg/png），全是真实文件而非占位符；**唯一前提是先能解密数据库**，而这在**微信 3.x/4.0 上开箱可用、在 4.1.x（尤其 2026 的 4.1.10.31+ 明文 key 移出内存后）必须借 wx_key 类第三方 DLL 注入工具手动取 key 再喂给 chatlog**。

*(全部结论核查日期：2026-08-04)*
