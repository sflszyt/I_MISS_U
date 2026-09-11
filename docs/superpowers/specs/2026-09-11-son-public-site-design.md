# 儿子站公网入口（son.justmissingyou.com）设计

日期：2026-09-11 · 状态：**已上线**（2026-09-11 12:53 隧道重启生效）；待用户手机实测

## 目标
让机主（儿子）不连 Tailscale 也能在手机上用陪伴页：打开 `https://son.justmissingyou.com/companion.html`，过 Cloudflare Access，文字 + 她的声音 + 历史回放照常可用。Tailscale 上的 `:8020` 儿子站保持原样。

## 已定的决定
- **只开陪伴页**（用户选 1）：不把 `:8020`（整个 `archive_out/`，287 MB，含评审页与 `sessions_data/father`）挂上公网。
- **域名** `son.justmissingyou.com`（用户选，与 `dad.` 对称）。
- **方案 A**：独立站点目录 + 独立静态服务，边界由目录与联接决定（不是 ingress 路径正则——「按文件分≠隔离」的教训）。

## 不可让步的约束
- **Access 独立应用「son」，策略只放机主邮箱**；绝不能把 son 加进爸爸的 Access 应用（否则爸爸的邮箱能读到儿子全部私人对话）。上线前以「未登录全路径 302 到 Access」为门槛。
- **铁律 3 提示**：经 Cloudflare 隧道即页面与数据在 Cloudflare 边缘解密转发。爸爸站已如此（用户显式放行）；儿子站多了机主自己的全部私人对话。用户知情后要求执行。
- 所有登录方式须实测：One-time PIN 当日才启用（爸爸站此前只有「Cloudflare 账号登录」，见记忆 access-login-method-verification）。

## 结构
```
people/mama_for_owner/site/          (gitignore)
├── companion.html     build_companion_page 参数与 Tailscale 版相同，唯一差别 --tts-origin same
├── avatar.html        archive_out/avatar.html 的副本（重建 avatar 后需同步复制）
├── data/              联接 → people/mama/archive_out/data
└── sessions_data/
    └── owner/         联接 → people/mama/archive_out/sessions_data/owner   （只有 owner，没有 father）
```
- 静态服务：`tools/static_server.py --port 8024 --bind 127.0.0.1 --directory people\mama_for_owner\site`，纳入 `scripts/start_services.ps1`（服务名 `son-public`，先于隧道启动、晚于隧道停止）。
- 隧道 ingress（`~/.cloudflared/config.yml`）：`son.justmissingyou.com` + `^/(tts|health|session)$` → `127.0.0.1:8022`；其余 → `127.0.0.1:8024`。不需要 `/v1/chat/completions`（儿子站 BYOK，浏览器直连模型服务商）。
- viewer：页面内嵌 owner token → tts_server 认定 viewer=owner → 会话与 Tailscale 版共用同一份历史。

## 构建命令
```powershell
python tools\build_companion_page.py --person mama --archive-dir people\mama_for_owner\site `
  --viewer owner --sessions-path sessions_data/owner/sessions.json --tts-origin same `
  --tts-token <tokens.env 里 owner: 后面那截>
```
验收：与 `people/mama/archive_out/companion.html` 逐行 diff，只允许 `ttsBase` 一行不同。

## 上线顺序与验证
1. 用户建 Access 应用 son（只放本人邮箱）✅
2. `cloudflared tunnel route dns imissu-father son.justmissingyou.com` ✅；未登录 `/`、`/health`、`/tts`、会话路径全部 302 → 「Log in to son」✅
3. 建站点目录与联接 ✅；构建页面并 diff ✅（只差 ttsBase）
4. `start_services.ps1` 加 `son-public`（DeepSeek 写，Codex 审）；`-SkipTunnel` 拉起 :8024 ✅（Codex REJECT→ACCEPT：自启兜底清单补 son-public，并修掉该检查恒为 False 的旧 bug）
5. 本地负向测试：`/corr1.html`、`/sessions_data/father/sessions.json`、`/sessions_data/owner/../father/sessions.json` 必须 404；`/companion.html`、`/data/chat_context.json`、`/sessions_data/owner/sessions.json` 200 ✅（14 项）
6. ingress 加两条（先备份，`cloudflared --config … tunnel ingress validate/rule` 本地验证匹配）→ 重启隧道（爸爸站断约 5 秒）→ 再测未登录 302 ✅（12:53，4 连接）
7. 机主手机实测（新 origin 需重填 API key）：文字、语音、历史回放；核对会话落 viewer=owner ⏳

## 不做（YAGNI）
离线兜底（Worker/SW；机器关机时显示 Cloudflare 自带错误页）、部署层站点清单（Phase 21）、改动 Tailscale 儿子站。

## 已知风险
- iPhone 上「历史语音条无声」（研究中，H1/H2）同样存在于公网版。
- avatar.html 是副本：`build_avatar_page` 重建后要同步复制到本站与爸爸站。
