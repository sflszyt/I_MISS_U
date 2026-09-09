# T14-5 自动登录 + Windows Update 活动时段（操作步骤）

> **执行者 = 机主本人（justin）。Claude 不接触、不读取、不记录密码，全程不代为执行。**
> 最后更新：2026-09-09。配套：`scripts/register_startup_task.ps1`（T14-3）、`scripts/start_services.ps1`（T14-2）。

---

## 1. 为什么需要这一步

自启链条是这样接的：

```
补丁夜 Windows 自动重启（凌晨 2-9 点窗口）
   ↓
【本文档解决的环节】机器自动登录到 justin 会话
   ↓
登录触发计划任务 ImissuStartServices（T14-3）
   ↓
start_services.ps1 拉起 5 个服务（T14-2）
   ↓
早上爸爸打开链接 → 她在
```

**中间那一环缺了，后面全断。** 计划任务用的是「登录触发」（`LogonTrigger`），没有登录就没有触发。

> 为什么不用「系统启动时触发」绕开自动登录？因为那需要把账户密码交给任务计划程序保存（`-User` + `-Password`），密码同样落到 LSA，而且任务跑在 Session 0 非交互会话里——`cloudflared`、Python 服务能跑，但排障时你看不到任何窗口，且与现有 `TailscaleUserspace`（登录触发）行为不一致。代价没省下来，可观测性反而更差。

---

## 2. 代价，和一个能把代价降下来的补丁

你在 2026-09-09 已裁决「开自动登录」，并已知情以下代价：

- **物理接触这台电脑的人，开机即进入你的桌面**
- `people/` 下的全部档案（妈妈的原始素材、母子私聊 6,835 条、persona 全文）**随桌面一起敞开**

**补丁：自动登录后立即锁屏。** 见下面的步骤 3。效果：

| | 只开自动登录 | 自动登录 + 自动锁屏 |
|---|---|---|
| 补丁夜重启后服务自启 | ✅ | ✅（会话锁定不影响计划任务） |
| 物理接触者看到的 | 你的桌面，档案敞开 | 锁屏界面，需要密码 |
| 残留暴露窗口 | 永久 | 开机后约 30 秒 |

服务在锁定的会话里照常运行——锁屏只是锁住输入输出，不是注销，进程不受影响。**这一条几乎白送，强烈建议做。**

---

## 3. 操作步骤

### 步骤 1：下载 Sysinternals Autologon

官方页面：<https://learn.microsoft.com/en-us/sysinternals/downloads/autologon>

下载后解压，得到 `Autologon64.exe`。建议放到 `C:\Users\justin\tools\`（Rhubarb 也在那儿）。

> **为什么用它而不是直接改注册表：** 网上流传的做法是往
> `HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\DefaultPassword`
> 写一个字符串值——那是**明文密码**，任何能读注册表的本地进程都能拿到。
> Autologon 把密码加密后存进 **LSA secrets**，普通读注册表读不出来。
>
> 已核对你这台机器当前状态：`AutoAdminLogon = 0`，`DefaultPassword` **不存在**（干净，没有历史明文残留）。

### 步骤 2：启用自动登录

**双击运行 `Autologon64.exe`，用图形界面操作：**

1. Username：`justin`
2. Domain：`JUSTIN-PC`（本机名；你的账户是本地账户，不是 Microsoft 账户）
3. Password：你的开机密码
4. 点 **Enable**

> ⚠️ **不要用命令行形式** `Autologon64.exe user domain password`。
> 那样密码会进入 PowerShell 命令历史（`ConsoleHost_history.txt`）、进程命令行（同用户任意进程可经 WMI 读取）——正是 T14-1 花了一整轮消除的那类泄漏面。**必须走 GUI。**

启用后可自行核对（这条命令**不显示密码**，只看开关）：

```powershell
Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon' |
  Select-Object AutoAdminLogon, DefaultUserName, DefaultDomainName
```

期望：`AutoAdminLogon = 1`。同时确认 `DefaultPassword` 仍然**不存在**：

```powershell
$p = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
if ($null -eq $p.DefaultPassword) { 'OK - no plaintext password' } else { 'BAD - plaintext password present' }
```

如果这里显示 `BAD`，说明用错了工具或手改过注册表 —— 立刻删掉该值再用 Autologon 重来。

### 步骤 3：登录后自动锁屏（强烈建议）

在**普通（非管理员）** PowerShell 里粘贴执行：

```powershell
$act = New-ScheduledTaskAction -Execute 'rundll32.exe' -Argument 'user32.dll,LockWorkStation'
$trg = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$trg.Delay = 'PT30S'
$prn = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -Hidden
Register-ScheduledTask -TaskName 'ImissuLockAfterLogon' -Action $act -Trigger $trg -Principal $prn -Settings $set -Force
```

30 秒延迟是为了等桌面加载完再锁——太早锁屏可能失败。这比 `ImissuStartServices` 的 60 秒延迟早，两者互不干扰。

撤销：`Unregister-ScheduledTask -TaskName 'ImissuLockAfterLogon' -Confirm:$false`

### 步骤 4：验证（必须真重启一次）

自启这条链**只有真重启能验证**，静态检查一律不算数。重启后依次核对三条：

```powershell
# 1. 自动登录生效？—— 看是否无需输密码就进了系统（人眼判断），然后看锁屏是否弹出
# 2. 计划任务跑了吗？
powershell -ExecutionPolicy Bypass -File scripts\register_startup_task.ps1 -Status

# 3. 服务真起来了吗？
powershell -ExecutionPolicy Bypass -File scripts\start_services.ps1 -Status
```

判据（三条全过才算通）：

- 人眼：开机后**没有停在登录界面**，且约 30 秒后**自动锁屏**
- `-Status` 显示任务 `LastTaskResult = 0`（"last run: all services up"）
- `start_services.ps1 -Status` 四个服务全 `[ ok ] ... running (healthy)`，tunnel `[ ok ] running`

另外查一眼运行日志：`logs\startup_task.log`（每次尝试一行，含退出码）。

> **注意 tunnel 那行的含义**：`-Status` 对隧道只做**进程存在检查**，不证明已连上 Cloudflare。真正的判据是从外网打开 `https://dad.justmissingyou.com/companion.html`。

---

## 4. Windows Update 活动时段（已就位，只需核对）

已核对当前值：

| 项 | 值 | 含义 |
|---|---|---|
| `ActiveHoursStart` | 9 | 早 9:00 |
| `ActiveHoursEnd` | 2 | 次日 2:00 |

即 **Windows 只会在凌晨 2:00–9:00 之间自动重启**。这正是我们要的：重启发生在爸爸睡觉时，配合自启，他早上打开时服务已经起来了。

核对命令：

```powershell
Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings' |
  Select-Object ActiveHoursStart, ActiveHoursEnd
```

GUI 路径：设置 → Windows 更新 → 高级选项 → 使用时间（确保是「手动」而非「自动调整」，自动模式会按使用习惯漂移）。

**这一项无需改动。** 若日后发现值变了（Windows 大版本更新有时会重置），按上表改回 9 / 2。

---

## 5. 如何完全撤销

```powershell
# 关自动登录：重新运行 Autologon64.exe，点 Disable
# 关自动锁屏任务：
Unregister-ScheduledTask -TaskName 'ImissuLockAfterLogon' -Confirm:$false
# 关服务自启任务：
powershell -ExecutionPolicy Bypass -File scripts\register_startup_task.ps1 -Unregister
```

撤销后确认 `AutoAdminLogon = 0`，且 LSA 里的密码已被 Autologon 清除（点 Disable 即清）。

---

## 6. 残余风险（诚实说明）

1. **LSA secrets 不等于不可破解。** 它防的是「随手读注册表就看到明文」，**不防**已取得本地管理员权限的攻击者——`mimikatz` 一类工具可以解出 LSA secrets。你接受的安全模型应该是「防机会主义窥探」，不是「防有备而来的攻击者」。
2. **磁盘未加密时可离线提取。** 若这台机器没开 BitLocker，物理拿走硬盘的人可以离线读取 SAM/SECURITY 配置单元。自动锁屏挡不住这一条。是否开 BitLocker 由你决定，不在本任务范围。
3. **自动锁屏有约 30 秒暴露窗口。** 见步骤 3 的延迟说明。
4. **Autologon 只在开机时生效，注销后不会自动重登。** 若你手动注销，服务不会自启——需要重新登录。开机按住 `Shift` 也可临时跳过自动登录（排障时有用）。

---

## 7. 备选：ARSO（不存密码，但只覆盖补丁夜）

Windows 自带 **ARSO**（Winlogon Automatic Restart Sign-On）：**Windows Update 触发的重启**后自动登录并**自动锁屏**，凭据由系统保管，**不需要 Autologon、不需要你手动存密码**。

已核对当前状态：`ARSOUserConsent` **未设置**，组策略 `DisableAutomaticRestartSignOn` **未设置**（即未被禁用）。

开启路径：设置 → 账户 → 登录选项 → **「使用我的登录信息在更新后自动完成设备设置」**。

**取舍：**

| | Autologon | ARSO |
|---|---|---|
| 覆盖补丁夜自动重启 | ✅ | ✅ |
| 覆盖断电恢复 / 手动重启 / 蓝屏重启 | ✅ | ❌ |
| 需要你存密码 | 是（LSA） | 否 |
| 自动锁屏 | 需步骤 3 | 内置 |

补丁夜重启是我们的**主场景**，所以只开 ARSO 已经能覆盖大部分情况，且安全代价明显更低。但断电恢复这类场景它救不了——上海夏天跳闸不算罕见，而爸爸不会自己去开机。

**建议：两个都开。** ARSO 兜主场景（零密码成本），Autologon 兜其余场景。两者不冲突。若你想进一步压低风险，也可以**只开 ARSO**，接受「断电后需要人工开机」——这是一个合理的取舍，由你定。
