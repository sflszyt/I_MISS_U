# 儿子站公网入口 运维说明（son.justmissingyou.com）

> 2026-09-11 上线。设计与决定见 `docs/superpowers/specs/2026-09-11-son-public-site-design.md`。
> 本站是**机主本人**用的公网入口；Tailscale 上的 `http://100.116.45.2:8020/companion.html` 照旧可用、互不影响。

## 链路

```
手机浏览器 → son.justmissingyou.com
  → Cloudflare Access（独立应用「son」，策略只放机主邮箱；登录方式：Cloudflare 账号 或 邮箱一次性 PIN）
  → 命名隧道 imissu-father（~/.cloudflared/config.yml，protocol http2）
      ├─ ^/(tts|health|session)$ → 127.0.0.1:8022  tts_server（页面内嵌 owner token → viewer=owner）
      └─ 其余                      → 127.0.0.1:8024  static_server（只绑 127.0.0.1）
```

- 不需要 `/v1/chat/completions`：儿子站是 BYOK，浏览器直连模型服务商。公网地址是新 origin，**手机上要重新填一次 API key**。
- 会话与 Tailscale 版共用同一份历史（同为 viewer=owner）。
- **铁律 3 提示**：经隧道即页面与数据在 Cloudflare 边缘解密转发；用户知情后要求执行（爸爸站同理）。

## 站点目录（`people/`，gitignore）

```
people/mama_for_owner/site/
├── companion.html     构建产物（见下）
├── avatar.html        people/mama/archive_out/avatar.html 的副本
├── data/              目录联接 → people/mama/archive_out/data
└── sessions_data/
    └── owner/         目录联接 → people/mama/archive_out/sessions_data/owner   （只有 owner，没有 father）
```

从零重建目录（PowerShell）：

```powershell
$root = 'C:\Users\justin\Documents\I_MISS_U'; $site = "$root\people\mama_for_owner\site"
New-Item -ItemType Directory "$site\sessions_data" -Force | Out-Null
New-Item -ItemType Junction -Path "$site\data" -Target "$root\people\mama\archive_out\data"
New-Item -ItemType Junction -Path "$site\sessions_data\owner" -Target "$root\people\mama\archive_out\sessions_data\owner"
Copy-Item "$root\people\mama\archive_out\avatar.html" "$site\avatar.html"
```

**边界靠目录，不靠路由正则**：看不到的东西根本不在这个目录里（评审页、`sessions_data/father`、`data_father` 都不在）。

## 重建页面

```powershell
python tools\build_companion_page.py --person mama --archive-dir people\mama_for_owner\site `
  --viewer owner --sessions-path sessions_data/owner/sessions.json --tts-origin same `
  --tts-token <tokens.env 里 owner: 后面那截> `
  --default-key-env DEEPSEEK_API_KEY --default-provider deepseek
```

Tailscale 版（`:8020`）同一套参数，只把 `--archive-dir` 换成 `people\mama\archive_out`、`--tts-origin` 换成 `auto`。**改了 `tools/build_companion_page.py` 两个都要重建。**

- **`--tts-origin same` 绝不能漏**（默认 `auto` 会生成 `…:8022`，经隧道无此端口 → 没声音）。
- **内置 API Key（2026-09-12 起）**：`--default-key-env DEEPSEEK_API_KEY` 把 key 烤进页面，手机上不用再填、iOS 清掉 localStorage 也不会丢。规则：只填 `--default-provider` 那一个档位（绝不写进别的服务商，否则会把 key 发到别家端点）；抽屉里存过的 key 永远优先；页面不会把内置 key 写回 localStorage。key 会明文出现在 HTML 里——`people/` 是 gitignore，公网站在 Access 后面，Tailscale 站在 tailnet 内。**构建器会拒绝 `--out-name chat.html/avatar.html/index.html` 配内置 key**（那些文件名会被 `build_archive` 分发出去）。
- **历史不再依赖 API key（2026-09-12）**：没配接口时也照常显示往次对话，配置提示追加在历史下方。
- 验收：与 `people/mama/archive_out/companion.html`（Tailscale 版）逐行 diff，**只允许 `ttsBase` 一行不同**。
- 改了 `tools/build_companion_page.py` 时，Tailscale 版、本站、爸爸站三个页面都要重建。
- 重建 avatar（`build_avatar_page`）后，把 `archive_out/avatar.html` 复制到本站与爸爸站。

## 服务

`scripts/start_services.ps1` 的第 6 个服务 `son-public`（:8024，`--bind 127.0.0.1`），先于隧道启动、晚于隧道停止；`-Status` 可见。登录自启任务 `ImissuStartServices` 自动覆盖；`register_startup_task.ps1` 的兜底健康检查（启动脚本 exit 3 时）清单已含 `son-public`（2026-09-11，同时修掉了该检查因 `ExitCode` 读成 `$null` 而恒为 False 的旧 bug，见 `findings.md`）。

## 验证清单

1. 未登录：`curl -s -o /dev/null -w "%{http_code}" https://son.justmissingyou.com/<任意路径>` 必须 **302** 到 `…cloudflareaccess.com/…/login/son.justmissingyou.com`；登录页应同时有「Cloudflare」按钮与「Email → Send login code」。
2. 本地正向（200）：`/companion.html` `/avatar.html` `/data/chat_context.json` `/sessions_data/owner/sessions.json` 及其 `audio/*.wav`。
3. 本地反向（404）：`/corr1.html` `/sessions_data/father/sessions.json` `/sessions_data/owner/../father/sessions.json`（`curl --path-as-is`）、`..%2f`、`%2e%2e` 变体、`/data_father/chat_context.json`。
4. 路由：`cloudflared --config C:\Users\justin\.cloudflared\config.yml tunnel ingress rule https://son.justmissingyou.com/tts`（→8022）与 `/companion.html`（→8024）；dad 三条路由不变。
5. 改 Access（应用、策略、登录方式）后重跑第 1 条，并用**非账号成员**邮箱实走一次 PIN（见记忆「Access 登录方式要实测」：爸爸站曾只有 Cloudflare 账号登录，机主是成员所以一直没发现）。

## 不做
离线兜底（机器关机时显示 Cloudflare 自带错误页）；部署层站点清单化。
