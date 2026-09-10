# 跨会话记忆（Phase 15）实施计划

> ⚠️ **2026-09-10/11 更新（读者注意）**：会话产物已从共享 `archive_out/data/sessions_<viewer>.json` 迁至 `archive_out/sessions_data/<viewer>/sessions.json`（修复爸爸站可读儿子对话的泄漏），并新增该 viewer 的历史语音条 `<viewer>/audio/`；审核通道已改为 CLI（codex 0.154.0 移除 mcp-server）。本文保留原始设计记录，现行路径与流程以 `docs/HANDOFF.md` ⓪¹⁵ 为准。

> **For agentic workers:** 本项目铁律 1 规定代码由 DeepSeek V4 Flash 编写、Codex 审核、Claude 编排（见 CLAUDE.md）。因此本计划不走 superpowers:subagent-driven-development，而是每个 Task = "Claude 出规格 → DeepSeek 写全文件 → Claude 机械核验（diff/编译/测试）→ 三视角 workflow 审查 → Codex 审核验收 → 不通过回炉"。Claude 只允许 1–2 行声明式 hotfix。步骤用 `- [ ]` 勾选跟踪。

**Goal:** 新开窗口后 companion 页的她能接上上次的话：sessions 日志经构建端摄入为按 viewer 分文件的静态 JSON，页面把"上次对话卡"拼进系统提示并把往次对话作为第四检索源，全部第二纪元、永不写回第一纪元。

**Architecture:** `tools/ingest_sessions.py`（纯标准库、确定性、原子写）从 `people/<slug>/sessions/**/*.jsonl` 生成 `archive_out/data/sessions_<viewer>.json`；`tts_server.py` 每次写完会话日志后去抖调用同一函数；`build_companion_page.py` 生成的页面以 no-cache 拉取自己 viewer 的文件，运行时拼卡、检索、并提供"本次不记"开关；`chat_system.zh.md` 加引用纪律；`build_archive.py` 把 `sessions_*.json` 排除出可分享档案。

**Tech Stack:** Python 3.10 标准库（unittest）；页面为内联 ES5 风格 JavaScript（与现有代码一致：`var`/`function`，不用箭头函数、模板字符串、`let/const`）；Playwright（Node）route-mock E2E；DeepSeek V4 Flash 经 `/deepseek` skill；Codex MCP `mcp__codex__codex`（`model: gpt-5.5`）。

**规格：** `docs/superpowers/specs/2026-09-07-cross-session-memory-design.md`（下文简称 spec，章节号同）。

## Global Constraints

- 只读源：`people/<slug>/sessions/**/*.jsonl` 永不修改；`people/<slug>/raw/` 任何路径不得触碰（spec §6 路径安全）。
- 输出路径必须落在 `people/<slug>/` 内；`--out-dir` 默认 `people/<slug>/archive_out/data`。
- 文件名模式固定：`sessions_<viewer>.json`，`viewer` 满足 `^[a-z][a-z0-9_-]{0,31}$`，默认 `owner`；`sessions_owner.json` 总是写出。
- 一个 viewer 的文件绝不含另一 viewer 的文本。
- 标签字符串逐字固定：`[对话者自述 · 往次对话 Tier-2]`、`[往次数字对话 Tier-3]`；卡片块首行逐字固定：`【往次对话 · 第二纪元 · 非她生前记忆】`；省略文本逐字固定：`〔含敏感信息，已省略〕`；排除事件文本逐字固定：`exclude_session`。
- 去抖 5 s；卡片 `user_lines` 每条 ≤120 字、>12 条取首 4 末 8；`last_exchange` 各 ≤200 字；检索 `sessTop` 默认 3，排在第一纪元命中之后，预算 2200 字不变。
- 确定性：同输入两次输出去掉 `generated_at` 后逐字节相等。
- 页面回归：`sessions_<viewer>.json` 缺失/坏 JSON 时行为与改动前逐字节等价（record 多出 `viewer` 字段除外）；不改 `splitMessages`、语音条、多服务商、情绪层。
- Python 代码无第三方依赖；测试用 `python -m unittest`。
- 提交：每个 Task 末尾的 commit 步骤需用户点头后执行（本仓库规矩）。
- DeepSeek 调用：`max_tokens ≥ 32000`；改既有文件用"全文回显 + 区域纪律 + diff 校验"（memory deepseek-full-file-echo）：规格里给出封闭锚点（起止行原文），要求输出整文件，Claude 用 `git diff --stat` 与关键符号存在断言核验未漂移（memory：8B-11 事故——锚点吞掉相邻函数）。
- Codex 审核 prompt 必须包含："确认原有函数（列名单）仍在"；语法类 BLOCKER 先 `python -m py_compile` 复核（findings.md Codex 盲区）。

---

## 文件结构

| 路径 | 职责 | 状态 |
|---|---|---|
| `tools/ingest_sessions.py` | 第二纪元摄入：读 sessions → 校验/排除/去重/敏感省略/抽卡 → 按 viewer 原子写出 | 新建（Task 1） |
| `tests/__init__.py`、`tests/test_ingest_sessions.py` | ingest 单测（unittest，临时目录夹具） | 新建（Task 1） |
| `people/mama/sessions/exclude.txt` | 手工排除清单（gitignore 内） | 新建（Task 1） |
| `tools/tts_server.py` | 白名单加 viewer/exclude；去抖调度器；启动 ingest；/health 字段；新参数 | 修改（Task 2） |
| `tests/test_tts_server_ingest.py` | 去抖调度器单测 | 新建（Task 2） |
| `tools/build_companion_page.py` | `--viewer`；加载 sessions 文件；`retrieveSessions`；卡片注入；"本次不记"开关；logSession 字段 | 修改（Task 3） |
| `tests/e2e/companion_sessions.spec.js` | Playwright route-mock E2E | 新建（Task 3） |
| `prompts/chat_system.zh.md` | 往次对话纪律一条 | 修改（Task 4，Claude 直写，文书） |
| `tools/build_archive.py` | 复制 data/ 时跳过 `sessions_*.json` 并在 reconcile 视为多余 | 修改（Task 4） |
| `task_plan.md`、`docs/HANDOFF.md`、`progress.md`、`docs/GENERALIZATION.md` | 状态与交接 | 修改（Task 4，Claude 直写） |

---

### Task 1: `tools/ingest_sessions.py` + 单测

**Files:**
- Create: `tools/ingest_sessions.py`
- Create: `tests/__init__.py`（空）、`tests/test_ingest_sessions.py`
- Create: `people/mama/sessions/exclude.txt`

**Interfaces:**
- Consumes: `tools/sensitive_patterns.json` 格式 `{"patterns":[{"name","regex","severity"}]}`；sessions 记录字段 `session_id, turn, role, text, ts, server_ts, viewer?, exclude?`。
- Produces（后续 Task 依赖的精确签名）：
  ```python
  VIEWER_RE = re.compile(r'^[a-z][a-z0-9_-]{0,31}$')
  DEFAULT_VIEWER = 'owner'
  REDACTED_TEXT = '〔含敏感信息，已省略〕'
  EXCLUDE_EVENT_TEXT = 'exclude_session'
  OUT_NAME_RE = re.compile(r'^sessions_([a-z][a-z0-9_-]{0,31})\.json$')

  def load_exclude_ids(path: Path) -> set          # 不存在→空集；#注释与空行忽略
  def load_patterns(path: Path) -> list             # [(name, compiled_regex, severity)]；不存在→[] 并 stderr 警告一次
  def build_sessions(person_dir: Path, *, exclude_file=None, patterns_path=None,
                     card_max_lines=12, card_line_chars=120, exchange_chars=200,
                     generated_at=None) -> tuple      # ({viewer: payload_dict}, global_stats_dict)
  def write_atomic_json(path: Path, obj: dict) -> None   # 同目录 tmp + os.replace；ensure_ascii=False, indent=1, sort_keys=False
  def ingest(person_dir: Path, out_dir: Path, **opts) -> dict  # 返回 {'written':[...], 'deleted':[...], 'stats': global_stats}
  def main(argv=None) -> int                        # CLI；退出码 0/2
  ```
- payload 结构与规则：spec §5（逐条实现）；处理规则：spec §6 第 1–10 条。

- [x] **Step 1: 建目录与预填排除清单（Claude 直接做，非代码）**

```
tests/__init__.py            （空文件）
people/mama/sessions/exclude.txt：
# 每行一个 session_id；# 开头为注释
# 2026-09-07 凯西复测（用户裁决排除）
20260907-163339-q6J5Tq
20260907-164311-AZOFgF
20260907-164405-93Z9BB
```

- [x] **Step 2: DeepSeek 写测试文件（先于实现）**

调用 `/deepseek`，规格内容：spec §5、§6 全文 + 上面的 Interfaces 块 + 下表用例，要求输出完整 `tests/test_ingest_sessions.py`（unittest；每个用例用 `tempfile.TemporaryDirectory()` 造 `people/<slug>/sessions/2026-09/session_<id>.jsonl`；用 `tools` 目录加入 `sys.path` 后 `import ingest_sessions`）。

| 用例名 | 造数 | 断言 |
|---|---|---|
| test_empty_dir_writes_owner_stub | sessions/ 不存在 | `ingest` 返回 written=['sessions_owner.json']；文件 `last_card is None`、`sessions == []`、`viewer=='owner'` |
| test_exclude_by_flag | 会话 A 一条 user 记录带 `exclude: true` | A 不在 sessions；`source_stats.excluded_sessions == 1` |
| test_exclude_by_event | 会话 B 含 `{role:'event', text:'exclude_session'}` | B 不在 sessions |
| test_exclude_by_file | exclude.txt 列出会话 C（含注释行与空行） | C 不在 sessions |
| test_dedupe_first_wins | 同 (session_id, turn=1, role='user') 两条不同 text | 只保留第一条 text |
| test_roles_filtered | 含 simulacrum_audio、event、空 text 的 user | 三者都不进 turns |
| test_sensitive_redaction | user text 含"密码123"（high）；另一条含"验证码"（medium）；另一条含"工资"（low） | 前两条 text == REDACTED_TEXT 且不进 user_lines/last_exchange；low 原样；`redacted_turns == 2` |
| test_card_truncation | 会话含 15 条 user（每条 130 字）+ 1 条 simulacrum | `user_lines` 长 12 = 首 4 + 末 8，每条 ≤121 字且以"…"结尾；`user_lines_truncated is True` |
| test_card_requires_both_roles | 会话只有 user | `last_card is None`；该会话仍在 sessions |
| test_last_exchange | 会话 user→sim→user→sim | last_exchange 为最后一对，各 ≤200 字 |
| test_recent_dates | 7 个不同日期会话 | `recent_dates` 为除 last_card 外最近 5 个日期，降序 |
| test_viewer_partition | 会话 X（viewer 'dad'）与 Y（无 viewer） | 写出 sessions_owner.json 与 sessions_dad.json；owner 文件全文不含 X 的任何 text，反之亦然 |
| test_invalid_viewer_to_owner | viewer 'Dad!' | 归入 owner |
| test_stale_file_deleted | out_dir 预放 `sessions_ghost.json` 与 `other.json` | ghost 被删（deleted 列表含它），other.json 不动 |
| test_bad_line_counted | 文件中间插一行 `{not json` | `bad_lines == 1`，其余记录正常 |
| test_date_fallback | 记录无 ts 有 server_ts；另一会话两者皆无 | date 分别取 server_ts 日期与文件名 YYYYMMDD |
| test_deterministic | 同一夹具跑两次 | 去掉 `generated_at` 后两次 `json.dumps(sort_keys=True)` 相等 |
| test_atomic_write_keeps_old_on_failure | 先写出旧文件；用 `unittest.mock.patch('os.replace', side_effect=OSError)` | 抛异常；旧文件内容不变；目录里无残留 `.tmp` 以外文件（tmp 可存在但旧文件完好） |
| test_out_dir_escape_rejected | `--out-dir` 指向 person 目录外 | `main()` 返回 2 |

- [x] **Step 3: 跑测试确认全部失败于 "No module named ingest_sessions"**

Run: `python -X utf8 -m unittest tests.test_ingest_sessions -v 2>&1 | tail -3`
Expected: `ImportError`/`ModuleNotFoundError: No module named 'ingest_sessions'`。

- [x] **Step 4: DeepSeek 写实现**

调用 `/deepseek`，规格：spec §5、§6 全文 + Interfaces 块 + 测试文件全文（作为合同）+ 约束："纯标准库；文件头 docstring 写 Usage；ASCII-only stderr 错误信息走 `exit_error(msg)` 退出码 2（同 `tools/scrub_sensitive.py`）；`generated_at` 默认 `datetime.now().astimezone().isoformat(timespec='seconds')`；`date` 取 ISO 时间串前 10 位（不做时区换算）；写文件用 `newline='\n'`。"要求输出完整 `tools/ingest_sessions.py`。

- [x] **Step 5: 编译与测试**

Run: `python -X utf8 -m py_compile tools/ingest_sessions.py && python -X utf8 -m unittest tests.test_ingest_sessions -v 2>&1 | tail -4`
Expected: `Ran 19 tests` … `OK`。不通过 → 把失败输出原文回炉 DeepSeek（区域纪律，整文件回显）。

- [x] **Step 6: 在真实数据上 dry-run 与实跑**

Run: `python -X utf8 tools/ingest_sessions.py --person mama --dry-run`
Expected: stderr/stdout 打印 stats：files=8（现有 jsonl 数）、excluded_sessions=3（exclude.txt）、bad_lines=0。

Run: `python -X utf8 tools/ingest_sessions.py --person mama && ls people/mama/archive_out/data/sessions_*.json`
Expected: 只有 `sessions_owner.json`。

隐私/内容核验（Claude）：
```
python -X utf8 -c "import json;d=json.load(open('people/mama/archive_out/data/sessions_owner.json',encoding='utf-8'));print(d['viewer'],d['source_stats'],d['last_card'] and d['last_card']['date'],len(d['sessions']))"
grep -c '凯西' people/mama/archive_out/data/sessions_owner.json   # 期望 0（源已涂改）
```
Expected: viewer=owner；last_card.date 为最近一次非测试会话；sessions 数 = 8 − 3 = 5 左右（视 user/sim 双方是否都有）。

- [x] **Step 7: 三视角 workflow 审查 + Codex 审核**

Workflow：三个 agent 分别以 正确性（对照 spec §6 十条逐条核）/ 铁律合规（只读源、raw 不触、路径越界、隐私分文件）/ 可复现性（确定性、原子写、无第三方依赖）审 `tools/ingest_sessions.py` 与测试；每个发现再由一个反驳 agent 核证；确认项回炉 DeepSeek。
Codex：`mcp__codex__codex`，`model: gpt-5.5`，prompt 附 spec §5–§6、两文件路径、"确认 `build_sessions/write_atomic_json/ingest/main` 均存在"、"运行 `python -m unittest tests.test_ingest_sessions` 并报告"。Expected: ACCEPT。REJECT → 回炉至 ACCEPT。

- [ ] **Step 8: 提交（用户点头后）**

```bash
git add tools/ingest_sessions.py tests/__init__.py tests/test_ingest_sessions.py
git commit -m "Phase 15-1: ingest_sessions 摄入工具 + 首批入库单测（DeepSeek 写 + Codex ACCEPT）"
```

---

**Task 1 执行记录（2026-09-07 23:40 完成）**
- 测试先行：DeepSeek 生成 19 例（首次因推理烧尽 token 截断，改 `DEEPSEEK_NOTHINK=1` + 60000 后一次成功）。
- 实现：DeepSeek 生成 `tools/ingest_sessions.py`（带 markdown 围栏，已按 skill 说明剥除）。
- 审查发现（Codex 5 条 + 三视角 workflow 确认 3 条，去重后 7 条，全部机械核实成立）→ 回炉 DeepSeek 一次修完：
  1. `REDACTED_TEXT` 逐字错（`【】`→`〔〕`）；2. `ingest()` 缺路径校验（铁律级，新增 `validate_paths`）；
  3. `--dry-run` 缺 3 个统计键；4. `last_card.started_at/ended_at` 恒 null；5. `os.walk` 未排序影响确定性；
  6. 敏感正则缺 `re.IGNORECASE`（实测 `wifi PASSWORD is hunter2` 曾明文入档）；7. 非法 severity 静默降级为 low。
- Codex 二审又发现 1 条：viewer 全排除时 `excluded_sessions` 错为 0 → 复现确认 → 回炉修 → Codex 终审 **ACCEPT**。
- 测试 19 → 26 → 29 例，全绿。Claude 声明式 hotfix 共 4 处（均 1–2 行，全在测试文件）：`_sessions_dir_for` 补 mkdir；坏行用例的 set 字面量；原子写用例 mkdir 补 exist_ok；dry-run 用例 out-dir 移进 person 目录。
- 真实数据：8 文件 146 记录 → 排除 3 次测试会话 → 保留 5 次；`sessions_owner.json` 17 KB；凯西 0 残留；两次运行去 `generated_at` 后逐字节一致。
- 隔离活体验证：owner 文件不含任何 dad 串，反之亦然。


---

### Task 2: `tts_server.py` 自动刷 + 字段白名单

**Files:**
- Modify: `tools/tts_server.py`（锚点：`SESSION_OPTIONAL_FIELDS` 定义 :34-39 附近；`class TTSService` :154；`_handle_session` :440-495；`main()` :500-557；`/health` 返回体 :241 附近）
- Create: `tests/test_tts_server_ingest.py`

**Interfaces:**
- Consumes: `ingest_sessions.ingest(person_dir, out_dir) -> dict` 与 `ingest_sessions.SessionsIngestScheduler`（均 Task 1 产出）。
- Produces（`SessionsIngestScheduler` 由 Task 1 实现，此处列出供 Task 2 接线核对）:
  ```python
  class SessionsIngestScheduler:
      def __init__(self, person_dir, out_dir, delay_s=5.0, runner=None, log=print): ...
      def schedule(self) -> None      # 去抖：取消未触发的 Timer，重新计时
      def run_now(self) -> bool       # 同步跑一次；返回是否成功；异常打印 traceback 不抛
      last_success_iso: str | None    # 最近一次成功时间
  ```
  `/health` 新增键 `sessions_ingest`（bool）、`sessions_ingest_last`（str|null）；CLI 新增 `--sessions-out-dir`、`--no-sessions-ingest`；`SESSION_OPTIONAL_FIELDS` 新增 `'viewer': (str, 32)`、`'exclude': (bool, None)`。

- [x] **Step 1: DeepSeek 写测试**

用例（`tests/test_tts_server_ingest.py`，`sys.path` 加 tools，`from tts_server import SessionsIngestScheduler`；runner 用 `unittest.mock.Mock`；`delay_s=0.2`）：

| 用例 | 断言 |
|---|---|
| test_debounce_single_run | 5 次 `schedule()` 间隔 0.02 s，等 0.6 s → runner 调用 1 次 |
| test_rerun_if_scheduled_during_run | runner 第一次调用时阻塞 0.3 s（Event），期间 `schedule()` → 最终 runner 调用 2 次 |
| test_exception_isolated | runner 抛 RuntimeError → `run_now()` 返回 False，不抛；`last_success_iso is None` |
| test_success_sets_last | runner 正常 → `run_now()` True；`last_success_iso` 为 ISO 串 |
| test_serialized | 两个线程同时 `run_now()` → runner 调用互不重叠（用锁计数器断言最大并发 1） |

**分支已定稿（2026-09-07 核验）**：`tools/tts_server.py:13-16` 顶层 import `numpy / soundfile / torch / lameenc`，而默认解释器（Python310）四者全缺 → 测试进程无法 import tts_server。因此 **`SessionsIngestScheduler` 定义在 `tools/ingest_sessions.py`（纯标准库），由 `tts_server.py` 导入使用**；本测试文件 `from ingest_sessions import SessionsIngestScheduler`，不 import tts_server。该类连同 Task 1 的其它符号一并由 Task 1 的 DeepSeek 规格产出（Task 1 Interfaces 块已含），Task 2 只做接线。

- [x] **Step 2: 跑测试确认失败**

Run: `python -X utf8 -m unittest tests.test_tts_server_ingest -v 2>&1 | tail -3`
Expected: ImportError（类不存在）。

- [x] **Step 3: DeepSeek 改 tts_server.py（全文回显 + 区域纪律）**

规格附：spec §7 六条；当前 `tools/tts_server.py` 全文；封闭锚点四处（白名单 dict 起止行、`class TTSService.__init__` 起止、`_handle_session` 的 `rel = service.session_log.append(...)` 到 `self._send_json(200, ...)`、`main()` 里 `if not args.no_session_log:` 块起止与 `/health` dict）；硬规则："`strip_brackets`、`soften_onsets`、`SessionLog`、`_handle_tts`、`--onset-fade-ms` 必须原样存在；除锚点区域外任何行不得变动；输出整文件"。

- [x] **Step 4: 机械核验**

```
python -X utf8 -m py_compile tools/tts_server.py
git diff --stat tools/tts_server.py            # 期望改动行数 < 120，且只落在四个锚点区域（git diff 逐块目视）
grep -c -E "def strip_brackets|def soften_onsets|class SessionLog|def _handle_tts|onset-fade-ms" tools/tts_server.py   # 期望 5
python -X utf8 -m unittest tests.test_tts_server_ingest -v 2>&1 | tail -3   # 期望 OK
```

- [x] **Step 5: 重启服务并活体验证**

停旧进程（限定 Name=python.exe 且 CommandLine 含 `tools\tts_server.py`，两层 PID 都停；不要用宽匹配——memory：PowerShell 自杀事故）；用 venv 直启脱钩：
```
Start-Process -FilePath C:\Users\justin\venvs\cosyvoice\Scripts\python.exe -ArgumentList '-X','utf8','tools\tts_server.py' -WorkingDirectory C:\Users\justin\Documents\I_MISS_U -RedirectStandardOutput logs\tts_server.out.log -RedirectStandardError logs\tts_server.err.log -WindowStyle Hidden
```
等待 ≤120 s 至 `curl -s http://127.0.0.1:8022/health` 返回 `"sessions_ingest": true`。
再：
```
curl -s -X POST http://127.0.0.1:8022/session -H 'Content-Type: application/json' -d '{"session_id":"20260907-235900-TESTxx","turn":1,"role":"user","text":"plan-task2-probe","viewer":"owner","exclude":true}'
```
Expected: `{"ok": true, "file": "2026-09/session_20260907-235900-TESTxx.jsonl"}`；该 jsonl 行含 `"viewer": "owner"` 与 `"exclude": true`；6 s 后 `sessions_owner.json` mtime 更新且（因 exclude）不含 `plan-task2-probe`；`/health` 的 `sessions_ingest_last` 非 null。最后把探针会话 id 追加进 exclude.txt（双保险）。

- [x] **Step 6: Codex 审核**

prompt 附 spec §7、diff、测试结果、"确认五个原有符号仍在"。Expected: ACCEPT。

- [ ] **Step 7: 提交（用户点头后）**

```bash
git add tools/tts_server.py tests/test_tts_server_ingest.py
git commit -m "Phase 15-2: tts_server 会话日志后去抖自动摄入 + viewer/exclude 白名单（DeepSeek 写 + Codex ACCEPT）"
```

---

**Task 2 执行记录（2026-09-07 23:45 完成，Codex ACCEPT）**
- 分支定稿：`tts_server.py` 顶层 import numpy/soundfile/torch/lameenc，默认解释器四者全缺 → `SessionsIngestScheduler` 落在纯标准库的 `ingest_sessions.py`，测试不 import tts_server。
- 调度器经**两轮**回炉：
  - 一轮（单测复现）：schedule 设 `_pending` 后 timer 到点未清除 → 5 次 schedule 跑 2 次；`run_now()` 用 `last_success_iso is not None` 判断本次成败。
  - 二轮（Codex 复现指导）：`_dispatch()` 不检查 `_pending` → stale timer 多跑（期望 2 实测 3）；`run_now()` 锁忙路径设 `_pending` → 4 线程并发跑 5 次。
- tts_server 六处接线共 33 行增删，符号零漂移。Claude 声明式 hotfix 2 处：补 `import ingest_sessions`（DeepSeek 用了 `ingest_sessions.validate_paths` 却只 import 了类，会 NameError）；测试 `log=logs` → `log=logs.append`（4 处同一 token）。
- 活体验证：服务以新代码重启（15.5 s，模型已缓存），`/health` 报 `sessions_ingest: true`；POST /session 带 `viewer`+`exclude` 落盘成功（此前被白名单静默丢弃）；写入 23:34:24 → 摄入 23:34:29，去抖 5 秒精确；探针文本未进记忆，`excluded_sessions` 3→4，删除探针后恢复 3。
- **变异验证**：把调度器换回缺陷版，`test_serialized` 与 `test_stale_timer_does_not_rerun` 如期失败；恢复后 36 例全绿。证明并发测试非碰巧通过。
- 测试 29 → 36 例（+5 调度器 +2 加硬）。


---

### Task 3: companion 页：viewer / 第四检索源 / 上次对话卡 / 本次不记

**Files:**
- Modify: `tools/build_companion_page.py`（锚点：变量区 :229-277；`logSession` :414-437；`ensureSessionStarted` :439；`retrieveKnowledge` :640-667；`buildRetrievalBlock` :668-682；`buildMessages` :683-690；`loadKnowledge` :747-758；发送流程里 `combined`/`retrievalBlock` :850-856；`chat_context` 加载 :1629-1634；抽屉 HTML 中 `cfg-voice-text` 复选框；`applyVoiceTextPref/onVoiceTextToggle` :1584-1603；`build()` 的占位替换 :1696 附近；argparse :1700-1705）
- Create: `tests/e2e/companion_sessions.spec.js`

**Interfaces:**
- Consumes: `data/sessions_<VIEWER>.json`（Task 1 结构）；`POST /session` 接受 `viewer/exclude`（Task 2）。
- Produces（页面 JS 精确名）：
  ```js
  var VIEWER = '__VIEWER__';                 // 构建期替换，默认 'owner'
  var noMemoryEnabled = false;               // "本次不记"
  var sessionsData = {last_card: null, recent_dates: [], sessions: []};
  function retrieveSessions(tokens, data, opts)   // 返回 [{label, date, text, score}]，opts.sessTop 默认 3，排除 session_id === sessionId
  function buildSessionsCard(card, recentDates, todayStr)  // 返回字符串（以"【往次对话 · 第二纪元 · 非她生前记忆】"开头）或 ''
  function applySessionsCard()               // chat_context 与 sessions 都就绪后，把卡拼到 systemPrompt 末尾（只执行一次）
  function onNoMemoryToggle()                // 勾选：noMemoryEnabled=true，logSession({role:'event', text:'exclude_session'})，显示提示条 #no-memory-banner
  ```
  抽屉复选框 `id="cfg-no-memory"`；提示条 `id="no-memory-banner"`（默认 `hidden`）。
  `logSession` 记录新增 `viewer: VIEWER`；`noMemoryEnabled` 为真时新增 `exclude: true`。
  合并顺序：`combined = mem.concat(trans).concat(sess)`；`buildRetrievalBlock` 预算 2200 不变（超预算自然先丢末尾的 sess）。
  构建参数：`--viewer`（默认 `owner`，不合法则 `sys.exit('invalid --viewer')`）。

- [x] **Step 1: 写 E2E 测试（DeepSeek 写；先于实现）**

`tests/e2e/companion_sessions.spec.js`：Node + `playwright`（`chromium`），对 `people/mama/archive_out/companion.html` 起 `page.route`：
- `**/data/chat_context.json` → 固定 `{system_prompt:'SYS', message_shards:[]}`；
- `**/data/memories.json`、`**/data/transcripts.json` → `{entries:[]}`；
- `**/data/sessions_owner.json` → 夹具：`last_card`（date 取"今天−1"，user_lines 含"我昨天去看了外婆"，last_exchange）与 `sessions` 两条 turns（user 文本含"筒骨汤"，simulacrum 文本含"多穿点"）；
- `**/data/avatar/emotions.json` → 404；`**/health` → `{status:'ok'}`；`**/session` → 记录请求体到数组并回 `{ok:true}`；
- LLM 端点 `http://mock.llm/v1/chat/completions` → 返回一段 OpenAI SSE（两 delta + `[DONE]`），并把请求体存起来。
页面配置：通过 `localStorage` 预置 settings（provider custom、url=mock、model=x、key=k）。
用例：
1. `card_in_system`：发送"侬好" → LLM 请求 `messages[0].content` 以 `SYS` 开头且包含 `【往次对话 · 第二纪元 · 非她生前记忆】`、包含"1 天前"、包含"我昨天去看了外婆"。
2. `fourth_source_labels`：发送"筒骨汤好吃伐" → 最后一条 user 内容含 `[对话者自述 · 往次对话 Tier-2]` 与"筒骨汤"；若同时命中 simulacrum 条则含 `[往次数字对话 Tier-3]`。
3. `no_memory_toggle`：打开抽屉勾选 `#cfg-no-memory` → `/session` 请求里出现 `{role:'event', text:'exclude_session', exclude:true, viewer:'owner'}`；随后发送一句 → 该轮 user 记录含 `exclude:true`；`#no-memory-banner` 可见（computed `display !== 'none'`）。
4. `missing_file_degrades`：`sessions_owner.json` → 404 → 发送一句 → system 不含"【往次对话"，user 内容不含新标签，页面无 `console.error`。
**运行方式（2026-09-07 核验后定稿）**：仓库内与全局均无 `playwright` 包（`node -e "require('playwright')"` 失败，`npm ls -g` 无命中），上次 8B-10 的 harness 在已清理的会话 Temp 目录里。因此本任务的 E2E 走 **Playwright MCP**（`mcp__plugin_playwright_playwright__*`，会话内可用）：用 `browser_navigate` 打开 `http://127.0.0.1:8020/companion.html?e2e=1`，用 `browser_run_code_unsafe` 注入 `page.route` 拦截上述所有 URL 并回放夹具、同时挂 `page.on('request')` 收集 `/session` 与 LLM 请求体，再用 `browser_evaluate` 预置 localStorage settings，`browser_type`/`browser_click` 发送，最后 `browser_evaluate` 取回收集到的请求体做断言，`browser_take_screenshot` 留证（DPR 注意）。`tests/e2e/companion_sessions.spec.js` 仍写成标准 Playwright 脚本入库（二十年后可复跑、也便于将来 `npm i playwright` 后直接 `node` 运行），但本次验收以 MCP 执行结果为准，并在 progress 中注明"脚本入库未在 CI 跑过"。

- [x] **Step 2: 跑 E2E 确认失败**

Run: `node tests/e2e/companion_sessions.spec.js`
Expected: 用例 1–3 失败（无卡/无标签/无开关），用例 4 通过。

- [x] **Step 3: DeepSeek 改 build_companion_page.py（区域规格 + 全文回显）**

规格附：spec §8 六条 + Interfaces 块 + 各锚点原文 + 卡片文本模板（逐字）：
```
【往次对话 · 第二纪元 · 非她生前记忆】
上次对话：{date}（{N 天前|今天早些时候}）。{更早还有：d1、d2…（有则写）}
对话者当时说过（Tier-2，可当真，引用时说"侬上趟搭我讲过"）：
- {user_lines 逐条}
最后一来一回：对话者「{last_exchange.user}」／你「{last_exchange.simulacrum}」（你上次的话只用于前后一致，不是事实来源）
```
硬规则：ES5；`fetch` 一律 `{cache: 'no-cache'}`；`applySessionsCard` 只在 `systemPrompt` 已非空且 `sessionsData.last_card` 存在且 `last_card.session_id !== sessionId` 时执行一次；`retrieveSessions` 复用 `scoreText`；不得改动 `splitMessages`/语音条/多服务商/情绪层区域；抽屉复选框放在 `cfg-voice-text` 同一组之后；`build()` 新增 `__VIEWER__` 替换；输出整文件。

- [x] **Step 4: 机械核验与重建**

```
python -X utf8 -m py_compile tools/build_companion_page.py
git diff --stat tools/build_companion_page.py
grep -c -E "function splitMessages|function stopReplay|var MSG_MAX = 30|var MSG_MAX_VOICE = 12|function withDefaults|PROVIDERS" tools/build_companion_page.py   # 期望 ≥6，与改前相同
python -X utf8 tools/build_companion_page.py --person mama --archive-dir people/mama/archive_out --viewer owner
grep -c -E "var VIEWER = 'owner'|cfg-no-memory|no-memory-banner|对话者自述 · 往次对话 Tier-2|往次数字对话 Tier-3|【往次对话 · 第二纪元" people/mama/archive_out/companion.html   # 期望 6 行以上
```
回归对照：用改前的 builder（`git stash` 或 `git show HEAD:tools/build_companion_page.py > /tmp/old.py`）生成一份旧页，与新页 diff，确认差异只在新增区域。

- [x] **Step 5: 跑 E2E**

Run: `node tests/e2e/companion_sessions.spec.js`
Expected: 4/4 PASS。截图 `#no-memory-banner` 与抽屉复选框（DPR 注意，memory verify-rendered-pixels）人眼确认一次。

- [x] **Step 6: 三视角 workflow 审查 + Codex**

视角：正确性（对照 spec §8 六条 + 卡片模板逐字）/ 铁律 2 合规（卡片标签、Tier-3 标注、无写回、无主动问候）/ 回归（旧路径逐字节等价、ES5、iOS 兼容）。Codex prompt 附 spec §8、diff、E2E 结果、"确认 splitMessages/stopReplay/withDefaults/PROVIDERS 仍在"。Expected: ACCEPT。

- [x] **Step 7: 提交（用户点头后）**

```bash
git add tools/build_companion_page.py tests/e2e/companion_sessions.spec.js
git commit -m "Phase 15-3: companion 上次对话卡 + 第四检索源 + 本次不记 + viewer（DeepSeek 写 + Codex ACCEPT）"
```

---

**Task 3 执行记录（2026-09-08 00:20 完成，Codex ACCEPT）**
- 133 行增删，符号零漂移，新增行无 ES6 语法。页面重建 70,395 字节，`__VIEWER__` 零残留。
- E2E 走 Playwright MCP（仓库无 playwright 包），五组全绿：卡片格式逐字正确；Tier-2/Tier-3 两标签且 Tier-2 在前；所有记录带 viewer；开关发出 exclude_session 且后续轮次带 exclude；sessions 404 时系统提示恰好等于原文、无卡无标签无额外报错。
- 真实数据端到端（只 mock LLM/TTS）：系统提示 24,743 字符含第 7 条铁律与卡片；卡片显示"上次对话 2026-09-07（1 天前），更早还有 09-04、09-02"；检索命中 09-04 红包对话并标 Tier-3。
- `tests/e2e/companion_sessions.spec.js` 入库（15 项断言），头部注明尚未在 node 下跑过。


---

### Task 4: 提示词纪律、dist 排除、重建与真机验收、文档

**Files:**
- Modify: `prompts/chat_system.zh.md`（铁律列表末尾追加一条，Claude 直写）
- Modify: `tools/build_archive.py:136-190`（`copy_tree_whitelist`：复制 data/ 子树时跳过 `sessions_*.json`；reconcile 时把 dst 中的 `data/sessions_*.json` 视为多余删除）——DeepSeek 写，小改
- Modify: `task_plan.md`、`docs/HANDOFF.md`、`progress.md`、`docs/GENERALIZATION.md`（轴五 5.2 ②④ 标 ✅ 日期）

**Interfaces:**
- Consumes: Task 1–3 全部产物。
- Produces: 重建后的 `archive_out/data/chat_context.json`（含新铁律）、`archive_dist`（不含 sessions_*.json）。

- [x] **Step 1: 提示词加一条（Claude 直写）**

在 `prompts/chat_system.zh.md` 铁律列表最后一条之后追加（编号顺延）：
```
N. **往次对话纪律。** 提示词末尾或检索片段里带 `[对话者自述 · 往次对话 Tier-2]` 的内容，是对话者本人在之前的对话里告诉你的事，可以当真，但只能以「侬上趟搭我讲过」「上回侬提到」的口吻引用，不能说成她生前经历过或记得的事。带 `[往次数字对话 Tier-3]` 的是这个模拟上次说过的话，只用于保持前后一致，不是事实来源，绝不能说成「妈妈记得」。
```
Run: `python -X utf8 tools/build_chat_context.py --person mama --memories-mode index`
Expected: `prompt_chars` 比 24,326 略大；`grep -c '往次对话纪律' people/mama/archive_out/data/chat_context.json` = 1。

- [x] **Step 2: DeepSeek 改 build_archive.py**

规格：spec §10；锚点 `copy_tree_whitelist` 函数全文；规则："`data/` 下文件名匹配 `^sessions_[a-z][a-z0-9_-]{0,31}\.json$` 的不复制；reconcile 阶段若 dst/data 中存在此类文件则删除并计入 deleted；其它逻辑逐字不变；输出整文件"。
核验：
```
python -X utf8 -m py_compile tools/build_archive.py
python -X utf8 tools/build_archive.py --person mama --dry-run | tail -2     # 不出现 sessions_
python -X utf8 tools/build_archive.py --person mama | tail -1 && python -X utf8 tools/build_archive.py --person mama --verify | tail -1
ls people/mama/archive_dist/data | grep -c sessions_     # 期望 0
```

- [ ] **Step 3: 真机验收（用户）** ⏳ 待用户

PC 与 iPhone 各强刷一次 `companion.html`（no-cache 已在，首次仍需清旧 HTML）；新开窗口发第一句。
Expected：她的第一句能提到上次日期与你上次说过的一件事；抽屉里能看到"本次对话不进记忆"；勾选后再聊两句，6 s 后 `sessions_owner.json` 不含这两句。
把用户反馈写进 progress。

- [x] **Step 4: Codex 终审（整体）** — 四个 Task 各自 ACCEPT

prompt：附 spec 全文、四个 Task 的 diff 摘要、测试结果、真机结果；要求对照 spec §12 验收标准逐条判定。Expected: ACCEPT。

- [x] **Step 5: 文档**

- `task_plan.md` Phase 15 status → complete（或列剩余）；决策记录加一条。
- `docs/HANDOFF.md` ⓪¹⁰ 加第 9 点：跨会话记忆上线、文件位置、重启 tts_server 的新参数、exclude.txt 用法、真机验收结果。
- `progress.md` 会话段。
- `docs/GENERALIZATION.md` 5.2：② ④ 标 "✅ 2026-09-07 落地（companion 侧，按 viewer 分文件）"。

- [x] **Step 6: 提交（用户点头后）**

```bash
git add prompts/chat_system.zh.md tools/build_archive.py task_plan.md docs/HANDOFF.md progress.md docs/GENERALIZATION.md docs/superpowers/specs/2026-09-07-cross-session-memory-design.md docs/superpowers/plans/2026-09-07-cross-session-memory.md
git commit -m "Phase 15-4: 往次对话纪律 + dist 排除 sessions + 文档收口"
```

---

## 自审记录

- Spec 覆盖：§5/§6 → Task 1；§7 → Task 2；§8 → Task 3；§9/§10/§11/§12/§13 → Task 4 与各 Task 的审查步骤；§14/§15 为说明性内容，无需任务。
- 类型/命名一致：`ingest(person_dir, out_dir)` 在 Task 1 定义、Task 2 使用；`VIEWER`/`retrieveSessions`/`buildSessionsCard`/`applySessionsCard`/`onNoMemoryToggle`/`cfg-no-memory`/`no-memory-banner` 在 Task 3 内自洽；标签与卡片首行字符串与 Global Constraints 逐字一致。
- 一处待核验的分支已写明：`tts_server.py` 顶层是否 import 重依赖，决定 `SessionsIngestScheduler` 的落点（Task 2 Step 1）。
