# T14-4 离线降级「她今天不在」（部署与验收）

> 最后更新：2026-09-10。配套：`scripts/start_services.ps1`（T14-2）、`scripts/register_startup_task.ps1`（T14-3）、`docs/ops-autologon.md`（T14-5）。

---

## 1. 为什么要四层

爸爸打开 `https://dad.justmissingyou.com/companion.html` 时，可能撞上四种故障。**它们各自需要不同的东西来兜底，没有任何一层能覆盖全部。**

| # | 故障 | 他原本会看到 | 谁兜底 |
|---|---|---|---|
| L1 | PC 关机 / cloudflared 没跑 | Cloudflare **Error 1033** 英文技术页 | Cloudflare Worker（PC 上任何代码都够不着） |
| L2 | 隧道在但 `:8021` 静态站没起 | cloudflared **502** | Cloudflare Worker |
| L1'/L2' | 他自己完全没网 | 浏览器断网页 | **Service Worker**（请求根本出不去，Worker 也够不着） |
| L3 | 站起了但 `:8022` TTS 冷启动中（约 73 秒）或挂了 | 页面正常，但**她永久不出声** | companion 页自身 |
| L4 | `:8023` llm-proxy 挂 | 发消息报技术错误 | Worker 返回 JSON + 页面降级 |

**L3 是最可能真实发生的那条**，也是最阴险的：补丁夜重启 → 早上他打开页面 → TTS 还在加载 → 探活失败 → `ttsAvailable` 永远是 false → 她再也不说话，直到有人想起来重开页面。他不会重开，他会以为她不说话了。

---

## 2. 文件清单

| 文件 | 层 | 说明 |
|---|---|---|
| `deploy/dad-site/offline.html` | L1'/L2' | 离线页本体，完全自包含（无外部字体/图片/JS）。**版本控制里的源** |
| `deploy/dad-site/sw.js` | L1'/L2' | Service Worker：预缓存上面那页，只拦 navigate 请求。**版本控制里的源** |
| `people/mama_for_father/site/{offline.html,sw.js}` | — | 上面两个的**运行副本**（`people/` 按铁律 3 全目录 gitignore，所以源必须放在 `deploy/`） |
| `deploy/cloudflare-worker/dad-offline.js` | L1/L2 | Cloudflare Worker：源站不通时返回同样的页面 |
| `tools/build_companion_page.py` | L3/L4 | `--offline-fallback` 注册 SW；TTS 探活改为重试 |

> **改这两个文件时改 `deploy/dad-site/` 下的源，再复制到站点目录**，否则改动不进版本控制、下次重装就没了：
>
> ```powershell
> Copy-Item deploy\dad-site\offline.html people\mama_for_father\site\ -Force
> Copy-Item deploy\dad-site\sw.js        people\mama_for_father\site\ -Force
> ```
>
> 核对两边一致：
>
> ```powershell
> foreach ($f in 'offline.html','sw.js') {
>   $a = (Get-FileHash "deploy\dad-site\$f").Hash
>   $b = (Get-FileHash "people\mama_for_father\site\$f").Hash
>   "{0}: {1}" -f $f, $(if ($a -eq $b) { 'identical' } else { 'DIFFERS' })
> }
> ```
>
> 改了 `sw.js` 还要**同时把 `CACHE_NAME` 的版本号加一**（`imissu-dad-offline-v1` → `-v2`），否则浏览器会继续用旧缓存里的 `offline.html`。activate 阶段会自动清掉旧版本缓存。

### 文案（四句，两处必须逐字一致）

```
她今天不在
等电脑醒过来，她就回来了。
明天再来看看吧。
这是家里那台电脑的事，不是她走了。
```

同一份文案同时存在于 `offline.html` 和 `dad-offline.js` 的内联 HTML 里。**改一处必须改另一处**，否则哪层生效就看到哪个版本。核对：

```bash
grep -c "等电脑醒过来" people/mama_for_father/site/offline.html deploy/cloudflare-worker/dad-offline.js
```

> ⚠️ 这段文案是 2026-09-09 的**显式产品裁决**（温情型）。Codex 两轮独立审查都指出它有拟人化风险（暗示她「会回来」「还在某处」），与铁律 2「克制沉浸度」张力明显。用户在被明确告知该风险后选定此版本，记为对铁律 2 的显式覆盖，复核日与 #24 的三项覆盖对齐（2026-11-28）。**改文案前先回看这条。**

---

## 3. 部署步骤

### 步骤 1：重建爸爸站页面（加 `--offline-fallback`）— ✅ 已于 2026-09-10 执行

token 在 `people/mama_for_father/config/tokens.env`，格式是 `TTS_TOKENS=viewer:token[,viewer2:token2]`（**页面里存的是冒号后面那截裸 token，不含 `father:` 前缀**）。实际执行的命令：

```powershell
python tools\build_companion_page.py `
  --person mama `
  --archive-dir people\mama_for_father\site `
  --viewer father `
  --context-path data_father/chat_context.json `
  --sessions-path data_father/sessions/sessions.json `
  --lang wu `
  --tts-origin same `
  --llm-proxy /v1/chat/completions `
  --intro-card `
  --intro-builder 儿子 `
  --tts-token <tokens.env 里 father: 后面那截> `
  --offline-fallback
```

全部参数都是从重建前的 `companion.html` 反推 + 实测核对的：

- **`--sessions-path` 绝不能漏**（2026-09-10 新增）。默认值是 `data/sessions_<viewer>.json`，
  而 `data` 是指向儿子站的目录联接——会话产物已于当日迁出共享目录以修复隐私泄漏。漏传这个参数，
  页面会去读一个已经不存在的旧路径（跨会话记忆静默失效），更糟的是它标志着共享目录里又出现了
  viewer 私有数据。爸爸站取值固定为 `data_father/sessions/sessions.json`（经 `data_father/sessions`
  这条**只指向 father 子目录**的联接读取），儿子站是 `sessions_data/owner/sessions.json`。
- **`--tts-origin same` 绝不能漏**。默认值 `auto` 生成的是 `location.protocol + '//' + location.hostname + ':8022'`——经隧道就成了 `https://dad.justmissingyou.com:8022`，那个端口在 Cloudflare 上不存在，**爸爸会一点声音都没有**。`same` 生成 `location.origin`，由 cloudflared ingress 把 `^/(tts|health|session)$` 路由到 :8022。（此前本文件的命令模板漏了这一条，2026-09-10 补。）
- `--intro-builder 儿子`：**能反推**（此前本文件说"由 JS 动态生成、反推不出来"，是错的）。说明卡是构建期字符串替换，直接在 HTML 里搜 `来自X手机里的聊天记录` 即可。
- `--tts-token`：`tokens.env` 里 `father:` 后面那截。可以从旧页面 `var TTS_TOKEN = '...'` 取，与 tokens.env 的 father 条比对一致后复用，无需人工输入。

> 注意：token 会写进 HTML（页面要拿它调 TTS，设计如此），但**不要**让它进 PowerShell 历史之外的地方。这条命令本身会留在 `ConsoleHost_history.txt` 里——若在意，先 `Set-PSReadLineOption -HistorySaveStyle SaveNothing`。

构建后确认：

```powershell
Select-String -Path people\mama_for_father\site\companion.html -Pattern 'serviceWorker'
```

应出现两行注册代码。2026-09-10 实测：`ttsBase = location.origin`、`VIEWER='father'`、`LLM_PROXY='/v1/chat/completions'`、context 指向 `data_father/`、说明卡称呼 `儿子`、token = tokens.env 的 father 条，十项结构探针 ALL PASS；与重建前的 diff 只有两处（`probeTts` 改为返回 promise + `startTtsProbeLoop` 重试循环、SW 注册），儿子站 `people/mama/archive_out/companion.html` 字节未动。

### 步骤 2：确认三个文件都在站点根

```powershell
Get-ChildItem people\mama_for_father\site\ | Select-Object Name, Length
```

必须有 `companion.html`、`offline.html`、`sw.js`。`sw.js` 必须在**根目录**——它的作用域取决于自身路径，放子目录会导致拦不到 `/companion.html`。

### 步骤 3：部署 Cloudflare Worker — ✅ 已于 2026-09-10 部署

**实际走的是 wrangler，不是面板复制粘贴**（配置已入版本库 `deploy/cloudflare-worker/wrangler.toml`）：

```powershell
npx --yes wrangler@latest login                                            # 一次性，浏览器点 Allow
npx --yes wrangler@latest deploy --config deploy\cloudflare-worker\wrangler.toml
```

部署结果：`dad-offline`，Version ID `693b90d6-ff26-43f4-8528-d5953ec13c79`，100% 流量，触发器 `dad.justmissingyou.com/*`（zone `justmissingyou.com`），上传 4.10 KiB / gzip 1.81 KiB，Worker 启动 7 ms。

> **坑：`compatibility_date` 不能填未来日期**（API 报 `code: 10021`）。Cloudflare 按 **UTC** 判定，本机 UTC+8 已经是 09-10 时那边还是 09-09。填 UTC 当天或更早。
>
> **坑：`wrangler login` 的 OAuth scope 远不止 Workers**——一并要走 `ssl_certs:write`、`connectivity:admin`、`email_routing:write`、`email_sending:write`、`d1:write`、`pages:write`、`containers:write` 等一长串，无法在该流程里裁剪。用完建议 `npx wrangler logout`；日常运维更适合建一个只含 `Workers Scripts:Edit` + `Workers Routes:Edit` + `Zone:Read` 的最小权限 API token 走 `CLOUDFLARE_API_TOKEN`。

**顺序说明（2026-09-10 实测确认，此前只是推断）**：Cloudflare Access 运行在 Worker **之前**。未登录 `curl https://dad.justmissingyou.com/companion.html` 返回 **302** 跳 `small-rice-b952.cloudflareaccess.com` 的登录页，请求根本到不了 Worker——这是对的，离线页不该对公众可见。

> **由此产生的验收前提**：要验 L1 必须先过 Access。`relationship.father.json` 的 `access.allowed_emails` 当时**只有爸爸一个邮箱**，机主自己也打不开这个站。验收前需在 Zero Trust → Access → Applications → `dad.justmissingyou.com` → Policies 里把机主邮箱也加进去（顺带以后才能帮爸爸排查问题）。

**额度**：Worker 免费版 100,000 请求/天。爸爸一个人用，量级完全不成问题。

**回滚**：`npx wrangler delete --config deploy\cloudflare-worker\wrangler.toml`（连路由一起删）。Worker 是整条链路的必经之地，万一它出问题，爸爸的站会整个不可用而不只是兜底失效——所以出任何异常先删它再排查。

---

## 4. 验收（三层要分别验，本地能验前两层）

> ✅ **2026-09-10 已修复：三层缓存治理上线，不必再强刷。** 历史上 :8020/:8021 是 Python `http.server`，不发 `Cache-Control`，浏览器按"距 Last-Modified 的 10%"做启发式缓存，重建后仍跑旧页面（下方保留原始踩坑记录备查）。
>
> 现在三层各司其职：
> 1. **源站** `tools/static_server.py` 取代 `python -m http.server`，对 HTML / `sw.js` / `data/*.json` 发 `Cache-Control: no-cache, must-revalidate`（媒体不发，保持原样）。
> 2. **边缘** `deploy/cloudflare-worker/dad-offline.js` 出口对同样三类路径改写该头；`cf: {cacheTtl: 0}` 只给 `/sw.js` 且仅限非导航请求（对导航请求重构造 Request 会把 mode 从 `navigate` 降级成 `same-origin`，破坏 Access 的 302 透传，**这条错了爸爸会登不进站**）。3xx（304 除外）/401/403 一律原样透传。
> 3. **Service Worker** `deploy/dad-site/sw.js` 在每次 navigate 时用 `event.waitUntil()` 后台 `fetch(url, {cache:'no-cache'})` 预热 `companion.html` 与 `avatar.html`，冲掉设备上此前存下的旧缓存。这是普通 fetch，**不是**重构造的导航请求，理由同上。
>
> **历史踩坑记录（2026-09-10 修复前）**：页面重建完毕、`curl` 拿到的 md5 与磁盘一致，但浏览器里 SW 死活不注册——栈回溯显示它跑的是**重建前**的行号（`init` 在 1809 行调 `probeTts`，而新文件里是 1843）。加 `?cb=<时间戳>` 后一次就通过。**行号即版本指纹。**
>
> 修复后实测（09-10）：`companion.html` / `avatar.html` / `sw.js` / `data/*.json` 均返回 `no-cache, must-revalidate`，媒体 PNG 不带该头；`If-Modified-Since` 正确回 304——`avatar.html` 由 387125 字节降为 0 字节，省的是爸爸的移动流量。真浏览器验证 SW 预热确实发出条件请求（访问日志中 `companion.html`/`avatar.html` 各 3 次全 304：1 次真实加载 + 2 次预热，iframe 导航也会触发一轮）。

### L3 页面内降级（不需要隧道，现在就能验）

```powershell
# 1. 停掉 TTS，模拟冷启动窗口
powershell -ExecutionPolicy Bypass -File scripts\start_services.ps1 -Stop
powershell -ExecutionPolicy Bypass -File scripts\start_services.ps1 -SkipTunnel
# 立刻（TTS 就绪前）打开 http://127.0.0.1:8021/companion.html
```

判据：
- 页面能正常打开、能打字
- 约 30 秒后（第二次探活失败）出现气泡：**她的声音还在准备，稍等一会儿。现在也可以先打字跟她说。**
- TTS 就绪后出现：**她的声音准备好了。**，此后语音正常

反向判据（同样重要）：**TTS 一开始就是好的时候，不应该出现任何提示**。正常情况不打扰他。

### L1'/L2' Service Worker（本地可验）

```powershell
# 1. 用 https 或 localhost 打开页面一次，让 SW 注册
#    http://127.0.0.1:8021/companion.html  （127.0.0.1 属安全上下文，SW 可注册）
# 2. 浏览器 DevTools → Application → Service Workers，确认已 activated
# 3. 停掉静态站
powershell -ExecutionPolicy Bypass -File scripts\start_services.ps1 -Stop
# 4. 刷新页面
```

判据：看到「她今天不在」，而不是浏览器的断网错误页。

再启动服务后，离线页应在 **60 秒内自动跳回** `companion.html`（页面里有静默探针，每 60 秒 HEAD 一次 `/companion.html`）。

**2026-09-10 用重建后的真实页面实测通过（整条 L1'/L2' + L3 链）**：

| 判据 | 实测 |
|---|---|
| 页面自身注册 SW（非手动） | `register('/sw.js')` 被调用并 resolved，scope `http://127.0.0.1:8021/`，state `activated` |
| 预缓存内容 | cache `imissu-dad-offline-v1`，内含 `/offline.html` |
| 停 :8021 后导航 | 标题变 `她今天不在`，`navigator.serviceWorker.controller` 非空 |
| 文案 | 四句逐字正确（截图人眼核对，非仅 DOM 断言） |
| 走的是缓存页而非内联兜底 | 出现「再试一次」按钮——`inlineFallback()` 里没有这个按钮，说明命中的是 `cache.match('/offline.html')` |
| 恢复服务后 | 自动跳回 `/companion.html`（标题「陪伴」） |
| 页面 JS 错误 | 0 条 `pageerror` |

> 本地验 L3 时会看到 `/health` 404——这是**对的**：`--tts-origin same` 让页面打 `location.origin/health`，本地直连 :8021 静态站没有这个路由，真实部署由 cloudflared ingress 转给 :8022。同理 `logSession` 打的 `/session` 本地也 404，**所以本地验收不会往 `people/mama/sessions/` 写任何测试记录**（09-10 已核实档案零污染）。

### L1/L2 Cloudflare Worker（需要隧道已启，且 Worker 已部署）

```
1. 确认外网能正常打开 https://dad.justmissingyou.com/companion.html
2. powershell -File scripts\start_services.ps1 -Stop     # 关掉隧道和站点
3. 从手机（非本机网络）打开同一链接
```

判据：看到中文「她今天不在」，**不是** Cloudflare 的英文 Error 1033 页。

> ✅ **2026-09-10 已真跑通。** 当时隧道从未启动过，源站是真实不可达状态——正是 L1 的故障态，不需要人为制造。机主把自己邮箱加进 Access 策略后打开 `https://dad.justmissingyou.com/companion.html`，**看到的是中文「她今天不在」**。
>
> `wrangler tail` 同步捕获到 Worker 确实被执行（这是"页面对了"之外的独立证据）：
>
> ```
> GET  https://dad.justmissingyou.com/companion.html - Ok @ 2026/9/10 02:14:25
> HEAD https://dad.justmissingyou.com/companion.html - Ok @ 2026/9/10 02:14:25
> GET  https://dad.justmissingyou.com/companion.html - Ok @ 2026/9/10 02:15:50
> HEAD https://dad.justmissingyou.com/companion.html - Ok @ 2026/9/10 02:15:51
> ```
>
> 顺带验证了一个容易做错的细节：紧跟 GET 的那条 HEAD 是**离线页自己的探针**。它拿到的是 Worker 返回的 **503**（`buildOfflineResponse` 对非 API 路径返 503），所以 `response.ok` 为假、页面正确地**留在原地不跳转**。若当初把兜底页写成 200，探针会立刻误判"恢复了"并把爸爸弹回一个打不开的页面。第二组 GET/HEAD 是约 85 秒后的下一轮探针（或点了「再试一次」），行为一致。
>
> **仍未验的是"隧道起来之后"的一面**：Worker 现在是全部流量的必经之地，正常态下它必须把 `/tts`（音频）与 `/v1/chat/completions`（SSE 流式）透明穿透。代码是 `return await fetch(request)` 直接回传，Workers 不缓冲 body，理论上没问题，但**没有实测过**。隧道首次启动后要专门确认爸爸的语音和流式回复都正常。

---

## 5. 已知限制

1. **Service Worker 需要他先成功打开过一次页面**。第一次拿到链接时 PC 必须是开着的——实际上成立（你会当面或在 PC 开着时把链接给他）。这一层覆盖不了「首访即断网」，那种情况由 Cloudflare Worker 兜。
2. **Worker 兜不住他自己断网**，SW 兜不住首访前没缓存。两层互补，都要有。
3. **`-Status` 里的 tunnel 只是进程存在检查**，不证明连上了 Cloudflare。真判据只有从外网打开链接。
4. **离线页的自动跳回依赖 `/companion.html` 的 HEAD 请求**。若 Access 会话过期，HEAD 会跟随 302 拿到 200 登录页，从而误判为「恢复了」并跳转——他会看到登录页。可接受（他重新登录即可），但知道这回事。
5. **TTS 重探上限 6 分钟**（24 次 × 15 秒）。冷启动实测约 73 秒，余量充足；但若 GPU 被别的任务占满导致 TTS 起不来，6 分钟后他会看到「今天听不到她的声音，但还可以打字跟她说话」，此后不再重试，需重开页面。
