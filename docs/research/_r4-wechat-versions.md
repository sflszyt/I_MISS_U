# R4 · 电脑版微信（Windows）版本现状与本地数据/媒体存储格式

> **摘要（三行）**
> 1. 2026-08 电脑版微信最新版为 **4.1.12（4.1.12.26，2026-07-22 发布）**；4.x 全线用 WCDB（SQLCipher 4）加密消息库，数据目录已从 `WeChat Files` 换成 `Documents\xwechat_files\<wxid>\`（db_storage 存库、msg/attach 存媒体）。
> 2. 关键转折：**4.0.3 起图片 .dat 从"单字节异或"改成 per-user AES 加密**；**4.1.x（约 4.1.8/4.1.10）后进程内存不再缓存 raw key**，只留 passphrase 需按每库 salt 做 PBKDF2-HMAC-SHA512 256000 次派生，旧的"内存扫 x'...'特征"工具批量失效。
> 3. **2026-07-13 腾讯发起大规模 DMCA**，GitHub 上主流解密项目（chatlog、wechat-decrypt 系列等）被下架/清空——这是当前对我们最大的现实约束。

**核查日期：2026-08-04**（"今天"=2026-08-03/04；下称"核查日"）
**方法：** WebSearch / WebFetch + `gh api`（GitHub 仓库与 DMCA 记录）。

---

## 1. 版本号与 4.0 / 4.1 时间线

**2026-08 最新版：微信 4.1.12 for Windows，详细版本号 4.1.12.26，发布于 2026-07-22。**（腾讯软件中心页显示更新时间 2026-07-28。）

时间线（Windows 平台，官方 updates 日志 + 腾讯软件中心）：

| 版本 | 发布时间 | 关键点 |
|---|---|---|
| 4.0.0（测试版） | 2024-10 官网上架 | 4.0 首个公开构建；架构大改（见下） |
| 4.0.3 | 2025-03-31 | 去掉"测试版"字样，4.0 正式化。**图片 .dat 改为 per-user AES 加密**（此前为单字节异或） |
| 4.0.5 / 4.0.6 | 4.0.6 = 2025-07-01 | 4.0 收尾版本 |
| 4.1.0 | 2025-08-14 | 4.1 系列起点 |
| 4.1.6 | 2025-12-17 | — |
| 4.1.7 | 2026-01-28 | — |
| 4.1.9 | 2026-04-21 | — |
| 4.1.10 | 2026-05-27 | 内存布局进一步变化，memory-scan 取 key 工具（如 wx-cli）报 0 候选 key（Windows 4.1.10.27 实测） |
| 4.1.11 | 2026-06-24 | — |
| **4.1.12** | **2026-07-22** | **当前最新（4.1.12.26）** |

### 关于两个"节点"版本号的核查

用户点名的两个精确版本号 **需要打折扣看待**：

- **"4.0.3.36 密钥离开内存"** — 未在权威来源中逐字命中"4.0.3.36"这个四段号。能确认的是：**4.0.3 是图片加密从异或升级到 AES 的分水岭**（chatlog 文档口径：4.0.3 起图片采用 AES、每个用户有独立图片 AES key）。而"数据库 key 离开内存/格式变化"更准确的说法属于 **4.1 系列**（见下条），不是 4.0.3。所以"4.0.3.36 密钥离开内存"这一表述**大概率把"图片改 AES"和"库 key 离开内存"两件事混在了一起**，建议在我们文档里拆开写。
- **"4.1.10.31 明文 key 移出堆"** — 方向正确、精确小版本号未逐字确认。可确认：**4.1.x（约 4.1.8 起、到 4.1.10.x 更彻底）微信不再在进程内存缓存 raw enc_key**（旧格式 `x'<64hex_enc><32hex_salt>'`），改为只保留 passphrase、按每库 salt 现场 PBKDF2 派生；4.1.8 还伴随 fts5 索引消失，4.1.10.27（Windows）实测 memory-scan 找不到 key。"4.1.10.31"这个具体四段号我核查日未直接命中，但"4.1.10 附近 raw key 移出内存导致旧工具失效"这个事实成立。

> 结论：两个节点的**技术方向都对**，但**精确四段版本号未被独立来源逐字证实**，且 4.0.3 那条更像是"图片 AES 化"而非"库 key 离开内存"。在下游文档里应按"事实"而非"精确版本号"引用。

---

## 2. Windows 上的数据目录结构（4.x）

**默认根路径（4.0 已改）：**
`C:\Users\<用户>\Documents\xwechat_files\<wxid_xxx 或 wxid+后缀>\`

- 3.x 及更早：`Documents\WeChat Files\`（旧结构，FileStorage 直挂其下）。
- 4.0 升级时：客户端启动自动检测旧路径并迁移；**新根目录名为 `xwechat_files`**。注意存在命名混淆——部分社区帖把迁移前后写反，实测 4.0/4.1 用的是 `xwechat_files`。**4.0 之后基本无法在设置里自由改这个存储路径**（社区大量投诉换盘符/改路径导致记录丢失）。
- 主程序也换了：`Wechat.exe` → **`Weixin.exe`**，核心逻辑集中进 **`Weixin.dll`**（单个大 DLL）。

**子目录（每个 wxid 账号目录下）：**

- `db_storage\` — **加密的 WCDB/SQLCipher 数据库**所在。消息库为分片形式（`message\msg_0.db`、`msg_1.db` … 按会话哈希分片；另有联系人、会话、媒体索引等库）。
- `msg\attach\<会话标识>\...` — 媒体与文件附件（4.0 结构）。
- `msg\file\` — 接收/发送的普通文件。
- 图片历史上位于 `FileStorage\MsgAttach\<聊天对象标识>\Image\<年月>\`（如 `2022-08`），**按年-月分目录**；4.0 迁移后并入 `xwechat_files\...\msg\attach` 体系，但"按年月分目录"的组织习惯延续。
- `Backup\<微信号>\` — 官方"备份与恢复"生成的加密备份文件（见 §5）。

**媒体文件格式：** 图片/缩略图以 **`.dat`（无标准扩展名的加密块）** 存放，不是直接的 jpg/png。视频/语音/文件各有目录。语音早期为 SILK/amr 编码，视频为 mp4；新版部分图片走 **`wxgf`** 私有封装（需转码/重打包为可浏览格式）。

---

## 3. 消息数据库加密（SQLCipher / WCDB）

**是 SQLCipher 4（经 WCDB 封装）。** 逆向确认 `cipher_compatibility = 4`。

**4.0 参数（SQLCipher4 标准档）：**
- 加密：**AES-256-CBC**；完整性：**HMAC-SHA512**（每页带 HMAC）。
- KDF：**PBKDF2-HMAC-SHA512**；页大小 4096（SQLCipher4 默认）；每个 .db 有**独立 salt 与独立 key**（数据库文件头前 16 字节即 salt）。
- WCDB 会把**派生后的 raw key 缓存在进程内存**，格式 `x'<64hex enc_key><32hex salt>'`——4.0 时代解密工具就是内存里扫这个特征串、再用 page-1 HMAC 校验命中正确 key。

**4.1.10.31+（准确说是 4.1.x 中后段）的派生变化：**
- **不再缓存 raw enc_key**。内存里只剩 passphrase；要得到实际 enc_key，必须对每个库**用该库自己的 salt 跑 PBKDF2-HMAC-SHA512、256000 次迭代**现场派生。
- 用户点名的 **"PBKDF2-HMAC-SHA512 256000 次"核实为真**——这正是 SQLCipher4 的默认迭代数，也是 4.1 新工具改走 passphrase→PBKDF2 路线后必须复算的参数。
- 附带影响：4.1.8 起 fts5 全文索引消失、内存布局变动，**纯内存特征扫描的旧工具（wx-cli 等）在 4.1.10 实测取不到 key**。

**图片 .dat 加密（与库 key 分开）：**
- 3.9.x 及更早：**单字节 XOR**（拿文件头两字节与已知图片魔数 FFD8/8950/4749 异或反推 key，全文件同一字节异或）。
- **4.0.3 起改为 AES**，且**每个用户一个独立图片 AES key**——所以 4.0.3+ 想还原图片，除了库 key，还得单独拿到"图片密钥"。

---

## 4. "降级取 key 再升级"是否可行？风险？

**思路：** 装一个旧版（4.0.x）微信，用内存里还缓存 raw key 的旧特征扫出 key，再升回新版。

**评估：可行性有限、风险高，不建议作为主路径。**

- **能不能降级：** 微信官方不提供旧版下载，且新版常带强制升级/协议校验；即便装到旧客户端，登录时可能被服务端要求升级才能收发消息。仅"离线读本地库"场景下旧客户端或许能起，但……
- **库格式风险（关键）：** 一旦被**新版升级过的数据库，其文件结构/schema/加密参数已按新版写回**，旧版工具与旧客户端**未必能再正确打开**（社区已有 4.0 升级后旧工具读不了、甚至聊天文件"丢失"的大量反馈）。降级后再升级属于反复横跳，**极易触发迁移/损坏**。
- **key 本身是否复用：** enc_key 由用户/设备派生、随库 salt 绑定；"旧版取到的 key"用于"新版升级后的库"能否直接解，取决于新版是否换了 passphrase 语义——4.1 改派生逻辑后**不保证旧 key 直接可用**。
- **务实建议：** 若确要取 key，**在目标数据的当前版本上、离线副本上操作**，先整目录冷备份（copy 一份 `xwechat_files`，只读操作），再针对该版本找对应方法；不要在真身目录上跨版本升降级。

---

## 5. 官方"聊天记录迁移/备份"能导出什么？能否当合法媒体旁路？

**功能：** 4.0"备份与恢复"被重写，需配合新版手机微信；PC 备份文件落在
`C:\Users\<用户>\Documents\xwechat_files\Backup\<微信号>\`。

**格式：加密、私有、非通用可读。**
- 备份采用 **RMFH 加密头**格式，约 9 个关键文件带 128 字节头/尾标记；聊天内容在加密的 **ChatPackage** 文件里。
- 手机侧 `libaff_biz.so` 用 OpenSSL，推测走 **AES-GCM**。
- **没有官方"导出为可读格式"的功能**——迁移/备份只为"在微信之间恢复"，不是导出。导出成 txt/html/json 之类可读物**官方不提供**。

**能否作为合法媒体获取旁路？**
- **迁移到另一台电脑/手机再提取**：技术上把数据搬过去了，但落地后仍是**同样的加密 WCDB + 加密媒体**，并没有绕开加密——你在新设备上面对的是一样的解密难题，不是"免解密拿明文"。
- **备份文件本身**：RMFH/ChatPackage/AES-GCM 是私有加密，社区有初步逆向但无成熟稳定还原链；把它当旁路**性价比低于直接在当前版本上取 key 解 db_storage**。
- **结论：** 官方迁移/备份**不能**当作"合法免解密的媒体导出旁路"；它只是把加密数据换个地方，仍需破解同一套加密。

---

## 6. 对"提取媒体"最要紧的现实约束（核查日新情况）

- **2026-07-13 腾讯/微信发起大规模 DMCA**（GitHub DMCA 记录 `github/dmca` 2026/07/2026-07-13-wechat.md）。核查日实测：`jackwener/wx-cli`、`L1en2407/wechat-decrypt`、`ylytdeng/wechat-decrypt` 等仓库**被 GitHub 以 DMCA 封锁**（`gh api` 返回 `block.reason=dmca`）；**`sjzar/chatlog` README 已被清空、代码/历史删除**，仅留"应微信官方要求下架"声明。
- 仍存活的多为 **macOS 分支**（如 `Thearas/wechat-db-decrypt-macos`，629★，核查日仍更新，仅测到 4.1.2.241，不支持 4.0 以下）——**Windows 侧公开工具在这波下架后明显收缩**。
- 影响：对我们（Windows 4.1.x 媒体提取）而言，**现成开源工具链在 2026-07 后大面积失效/下架**，需要么用下架前的存档版本、么自己按"passphrase→PBKDF2-HMAC-SHA512×256000 派生 + 图片 per-user AES key"这套逻辑复现。

---

## 来源（URL + 核查日 2026-08-04）

- 官方版本/时间线：
  - https://weixin.qq.com/updates?platform=windows&version=4.1.12
  - https://weixin.qq.com/updates?platform=windows&version=4.1.10
  - https://weixin.qq.com/updates?platform=windows&version=4.1.0
  - https://weixin.qq.com/updates/windows/403
  - https://weixin.qq.com/updates?platform=windows&version=4.0.6
  - 腾讯软件中心：https://pc.qq.com/detail/8/detail_11488.html
- 数据库/加密逆向：
  - 看雪 微信4.0数据库解密分析：https://bbs.kanxue.com/thread-284417.htm
  - 看雪 wx新版本(after4.0)数据库key逆向：https://bbs.kanxue.com/thread-287761.htm
  - 看雪 PC微信4.1消息监听逆向定位：https://bbs.kanxue.com/thread-290348.htm
  - wx-cli Issue #89（4.1.10.27 取 key 0 候选）：https://github.com/jackwener/wx-cli/issues/89
  - chatlog Issue #264（4.1.0.34 密钥无法获取）：https://github.com/sjzar/chatlog/issues/264
  - 加金博客 4.1.8 macOS 密钥提取：https://igaojin.me/2026/04/18/
- 目录/媒体格式：
  - 微信升级后 WeChat Files→xwechat_files：https://developers.weixin.qq.com/community/develop/article/doc/00000a13b50300fe9e935365b6ec13
  - DAT 加密/解密原理：https://blog.csdn.net/NDASH/article/details/135815620
  - DAT 转图（4.1+/3.9.x 支持）：https://blog.csdn.net/hill8/article/details/149286381
- 备份/迁移：
  - 4.0 迁移备份教程：https://blog.csdn.net/Ruheng_He/article/details/157965552
  - 解开 Windows 微信4.0 手机备份文件（RMFH/ChatPackage/AES-GCM）：https://blog.csdn.net/dujianhuaw/article/details/154291795 · https://www.ctfiot.com/275982.html
- DMCA / 工具现状：
  - GitHub DMCA 记录：https://github.com/github/dmca/blob/master/2026/07/2026-07-13-wechat.md
  - macOS 仍存活分支：https://github.com/Thearas/wechat-db-decrypt-macos
