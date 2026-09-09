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

### 步骤 1：重建爸爸站页面（加 `--offline-fallback`）

**这一步需要 TTS token，请你自己执行——我不接触凭据。**

token 在 `people/mama_for_father/config/tokens.env`。命令模板：

```powershell
python tools\build_companion_page.py `
  --person mama `
  --archive-dir people\mama_for_father\site `
  --viewer father `
  --context-path data_father/chat_context.json `
  --lang wu `
  --llm-proxy /v1/chat/completions `
  --intro-card `
  --intro-builder <上次用的称呼> `
  --tts-token <tokens.env 里爸爸那条> `
  --offline-fallback
```

前六个参数是从现有 `companion.html` 反推出来的（`viewer=father`、`lang=wu`、`LLM_PROXY=/v1/chat/completions`、context 在 `data_father/`、说明卡开启），**已核对**。两个待你确认：

- `--intro-builder`：说明卡里对建档者的称呼。默认 `家人`，若 #24 当时用的是 `儿子` 请填 `儿子`。反推不出来（说明卡由 JS 动态生成）。
- `--tts-token`：tokens.env 里给爸爸的那条。

> 注意：token 会写进 HTML（页面要拿它调 TTS，设计如此），但**不要**让它进 PowerShell 历史之外的地方。这条命令本身会留在 `ConsoleHost_history.txt` 里——若在意，先 `Set-PSReadLineOption -HistorySaveStyle SaveNothing`。

构建后确认：

```powershell
Select-String -Path people\mama_for_father\site\companion.html -Pattern 'serviceWorker'
```

应出现两行注册代码。

### 步骤 2：确认三个文件都在站点根

```powershell
Get-ChildItem people\mama_for_father\site\ | Select-Object Name, Length
```

必须有 `companion.html`、`offline.html`、`sw.js`。`sw.js` 必须在**根目录**——它的作用域取决于自身路径，放子目录会导致拦不到 `/companion.html`。

### 步骤 3：部署 Cloudflare Worker（你的账号，需你操作）

1. Cloudflare Dashboard → **Workers & Pages** → **Create** → **Create Worker**
2. 命名（如 `dad-offline`），创建后点 **Edit code**
3. 把 `deploy/cloudflare-worker/dad-offline.js` 全文粘贴进去，**Deploy**
4. 回到 Worker → **Settings** → **Domains & Routes** → **Add route**
   - Route：`dad.justmissingyou.com/*`
   - Zone：`justmissingyou.com`

**顺序说明**：Cloudflare Access 运行在 Worker **之前**，所以未登录的人先看到 Access 登录页，根本到不了这个 Worker——这是对的，离线页不该对公众可见。

**额度**：Worker 免费版 100,000 请求/天。爸爸一个人用，量级完全不成问题。

---

## 4. 验收（三层要分别验，本地能验前两层）

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

### L1/L2 Cloudflare Worker（需要隧道已启，且 Worker 已部署）

```
1. 确认外网能正常打开 https://dad.justmissingyou.com/companion.html
2. powershell -File scripts\start_services.ps1 -Stop     # 关掉隧道和站点
3. 从手机（非本机网络）打开同一链接
```

判据：看到中文「她今天不在」，**不是** Cloudflare 的英文 Error 1033 页。

> **这一层至今没有真跑过。** 隧道从未启动（启 cloudflared = 开公网入口，属外部可见动作，未经你授权不做），Worker 也还没部署。上线前必须补这一条。

---

## 5. 已知限制

1. **Service Worker 需要他先成功打开过一次页面**。第一次拿到链接时 PC 必须是开着的——实际上成立（你会当面或在 PC 开着时把链接给他）。这一层覆盖不了「首访即断网」，那种情况由 Cloudflare Worker 兜。
2. **Worker 兜不住他自己断网**，SW 兜不住首访前没缓存。两层互补，都要有。
3. **`-Status` 里的 tunnel 只是进程存在检查**，不证明连上了 Cloudflare。真判据只有从外网打开链接。
4. **离线页的自动跳回依赖 `/companion.html` 的 HEAD 请求**。若 Access 会话过期，HEAD 会跟随 302 拿到 200 登录页，从而误判为「恢复了」并跳转——他会看到登录页。可接受（他重新登录即可），但知道这回事。
5. **TTS 重探上限 6 分钟**（24 次 × 15 秒）。冷启动实测约 73 秒，余量充足；但若 GPU 被别的任务占满导致 TTS 起不来，6 分钟后他会看到「今天听不到她的声音，但还可以打字跟她说话」，此后不再重试，需重开页面。
