# 跨会话记忆（Phase 15）设计规格

> 日期：2026-09-07 · 状态：用户已批准设计（brainstorming 三问 + 整体设计通过）· 实施工艺：DeepSeek 写 / Codex 审 / Claude 编排（CLAUDE.md 铁律 1）
> 上游设计：docs/GENERALIZATION.md 轴五 5.1（两个纪元永不合流）、5.2 步骤 ②摄入 与 ④连续性检索。本规格只落这两步；步骤 ③记忆升级闸门 后置。

## 1. 背景与目标

companion 页每轮对话已落盘到 `people/<slug>/sessions/YYYY-MM/session_<id>.jsonl`（tts_server `POST /session`），但页面的对话历史只在内存里（`var history = []`，送模型时取最近 12 条），刷新或新开窗口即清空。用户 09-04 对数字人说过的纠正（"已离婚，现任叫兔兔"）09-07 新会话完全不知道。

目标：新开窗口后她能接上上次的话。连续感来自真实对话史（第二纪元），不来自人格漂移。用户原话："能记得昨天的聊天会更有沉静感"。

## 2. 用户裁决（2026-09-07）

| 问题 | 裁决 |
|---|---|
| 记什么 | 双方都记。用户的话标 `[对话者自述 · 往次对话 Tier-2]`；她的回复标 `[往次数字对话 Tier-3]`，永久 Tier-3 |
| 测试对话怎么排除 | 页面抽屉加"本次不记"开关 + `sessions/exclude.txt` 手工清单；今天三次测试会话预填 |
| 记忆文件怎么更新 | 静态 `data/sessions_<viewer>.json` + tts_server 每次写完日志后去抖自动重算；不做页面实时查服务 |
| 整体设计 | 通过（未选"卡片不含她的回复"与"卡片 30 天时效"两个变体）。spec 落盘后依 #24 研究批评改为每 viewer 一文件（隐私边界），未改任何裁决 |
| 优先级 | 用户决定先于 8A-2b 伦理护栏 |

## 3. 范围与明确不做

做：`tools/ingest_sessions.py`（新）、`tools/tts_server.py`（去抖自动刷 + 字段白名单）、`tools/build_companion_page.py`（加载/第四检索源/上次对话卡/本次不记/viewer）、`prompts/chat_system.zh.md`（一条引用纪律）、`tools/build_archive.py`（排除 sessions_*.json）、`tests/`（标准库 unittest + Playwright route-mock）。

不做：闸门升级 `sessions_memories.md`（轴五 ③）；chat.html 侧接入；数字人主动问候/推送；模型摘要（卡片全部抽取式）；跨 viewer 共享记忆；卡片时效截断；persona.md / memories.md 的任何自动改动。

## 4. 架构总览

```
sessions/YYYY-MM/*.jsonl ──► ingest_sessions.ingest(person_dir, out_dir) ──► archive_out/data/sessions_<viewer>.json
   (第二纪元源，只读)          │ 校验 / 去重 / 排除 / 敏感省略 / 抽卡            │ (静态，每个 viewer 一个文件，页面只拉自己那份，不进 dist)
                              │                                                │
   tts_server /session ───────┘ 每次 append 后去抖 5 s 调用；启动时跑一次        ▼
                                                                    companion.html 加载（no-cache）
                                                                      ├─ systemPrompt 末尾拼"上次对话卡"（仅内存）
                                                                      └─ 第四检索源（每轮 ≤3 条，排在第一纪元之后）
   companion 抽屉"本次不记" ──► 记录带 exclude:true + 事件 exclude_session ──► ingest 整会话排除
   sessions/exclude.txt（手工 session_id 清单）──────────────────────────────► ingest 整会话排除
```

第一纪元（raw / normalized / memories.md / persona.md）不被本功能读写。

## 5. 数据模型：`archive_out/data/sessions_<viewer>.json`（每个 viewer 一个文件）

```json
{
  "schema_version": 1,
  "generated_at": "2026-09-07T17:00:00+08:00",
  "person": "mama",
  "epoch": 2,
  "viewer": "owner",
  "tier_policy": {"user": 2, "simulacrum": 3},
  "source_stats": {"files": 8, "records": 130, "bad_lines": 0, "excluded_sessions": 3, "redacted_turns": 0, "sessions_kept": 5},
  "last_card": {
        "session_id": "20260904-214553-7pZokX",
        "date": "2026-09-04",
        "started_at": "2026-09-04T21:45:59+08:00",
        "ended_at": "2026-09-04T22:06:26+08:00",
        "turns": 12,
        "user_lines": ["…", "…"],
        "user_lines_truncated": false,
        "last_exchange": {"user": "…", "simulacrum": "…"}
      },
  "recent_dates": ["2026-09-04", "2026-09-02"],
  "sessions": [
    {"session_id": "…", "date": "2026-09-02",
     "turns": [{"turn": 1, "role": "user", "text": "…", "ts": "…"},
               {"turn": 1, "role": "simulacrum", "text": "…", "ts": "…"}]}
  ]
}
```

规则：
- 文件按记录的 `viewer` 字段分桶，`sessions_<viewer>.json` 一桶一文件；缺失视为 `"owner"`（现有全部日志）。`sessions_owner.json` 即使为空也总是写出；其它 viewer 只在有记录时写出。`source_stats` 中 `files/records/bad_lines` 为全局计数，`excluded_sessions/redacted_turns/sessions_kept` 为本 viewer 计数。
- 一个 viewer 的文件里绝不含其它 viewer 的任何文本（隐私边界：设备只下载自己的文件）。
- `last_card` 取该 viewer 最近一次未排除、且同时含 ≥1 条 user 与 ≥1 条 simulacrum 的会话；没有则 `null`。
- `user_lines`：该会话全部 user 文本，每条去首尾空白、超过 120 字截断加"…"；超过 12 条时取首 4 条 + 末 8 条并置 `user_lines_truncated: true`。
- `last_exchange`：该会话最后一条 user 与其后最后一条 simulacrum 文本，各 ≤200 字。
- `recent_dates`：该 viewer 除 last_card 外最近 5 个会话的日期，降序去重。
- `sessions`：该 viewer 全部未排除会话，按 `date` 升序；`turns` 只含 role ∈ {user, simulacrum}，按 (turn, role=user 先) 排序；文本保留全文（敏感省略除外）。
- 输出确定性：同输入必得逐字节相同输出（`generated_at` 除外）。

## 6. `tools/ingest_sessions.py` 规范

person-generic，无第三方依赖，Python 3.10。

CLI：
```
python tools/ingest_sessions.py --person <slug>
    [--out-dir <dir>]         默认 people/<slug>/archive_out/data（写 sessions_<viewer>.json）
    [--exclude-file <path>]   默认 people/<slug>/sessions/exclude.txt
    [--patterns <path>]       默认 tools/sensitive_patterns.json
    [--card-max-lines 12] [--card-line-chars 120] [--exchange-chars 200]
    [--dry-run]               只打印 source_stats，不写文件
```
退出码：0 成功（含"目录不存在→写出空结构"）；2 参数/路径越界错误（同 scrub_sensitive 的 exit_error 风格）。

库接口（tts_server 调用）：
```python
def build_sessions(person_dir: Path, *, exclude_file=None, patterns_path=None,
                   card_max_lines=12, card_line_chars=120, exchange_chars=200,
                   generated_at=None) -> tuple[dict, dict]   # ({viewer: payload}, global_stats)
def write_atomic_json(path: Path, obj: dict) -> None        # tmp + os.replace
def ingest(person_dir: Path, out_dir: Path, **opts) -> dict  # 写全部 viewer 文件、删陈旧 sessions_*.json，返回 stats（含 written/deleted 列表）
```

处理规则（按序）：
1. 输入 `people/<slug>/sessions/**/*.jsonl`（递归，排除 `audio/`）。只读，永不修改源文件。
2. 逐行解析 JSON；坏行跳过并计入 `bad_lines`（stderr 打印文件与行号）。
3. 记录归属会话：`session_id` 字段缺失时从文件名 `session_<id>.jsonl` 取。
4. 排除会话，满足任一：(a) 任一记录 `exclude === true`；(b) 任一记录 `role == 'event'` 且 `text == 'exclude_session'`；(c) `session_id` 在 exclude.txt（每行一个 id，`#` 开头为注释，空行忽略；文件不存在视为空）。
5. 保留 role ∈ {user, simulacrum} 且 `text` 为非空字符串的记录。`simulacrum_audio`、`event` 不进输出。
6. 去重键 `(session_id, turn, role)`，按文件内先后先到先得（离线队列补传可能重发）。
7. 敏感省略：用 `tools/sensitive_patterns.json`（与 scrub_sensitive 同格式）扫描每条 `text`；命中 severity ∈ {high, medium} 的，`text` 替换为 `〔含敏感信息，已省略〕`，计入 `redacted_turns`，且该条不参与 `user_lines` / `last_exchange`；low 不处理。模式文件缺失 → 不扫描并 stderr 警告一次。
8. `viewer` 缺失或非字符串 → `"owner"`；只允许 `^[a-z][a-z0-9_-]{0,31}$`，不合法的按 `"owner"` 处理并计入警告。
9. 会话 `date` = 该会话第一条保留记录 `ts` 的本地日期（`ts` 缺失用 `server_ts`，再缺用文件名里的 `YYYYMMDD`）。
10. 按 viewer 分桶后各自组卡、组 `recent_dates`、组 `sessions`，写 `source_stats`，逐文件原子写出；out-dir 内已存在但本次未重生成的 `sessions_*.json`（仅匹配该文件名模式）删除。目录不存在或无文件 → 只写出空的 `sessions_owner.json`（`last_card: null, sessions: []`），退出 0。

路径安全：`--out-dir` 必须落在 `people/<slug>/` 内；沿用 scrub_sensitive 的 raw 目录保护思路，任何路径不得指向 `people/<slug>/raw/`。

## 7. `tools/tts_server.py` 改动

1. `SESSION_OPTIONAL_FIELDS` 白名单新增：`viewer: (str, 32)`、`exclude: (bool, None)`。不加则 `/session` 静默丢弃这两个字段（现有实现是白名单过滤）。
2. `TTSService` 新增 `sessions_ingest`：`schedule()` 去抖 5 s（`threading.Timer`，新调用取消旧计时器）；到点在后台线程调用 `ingest_sessions.ingest(person_dir, out_dir)`；异常 `traceback` 打到 stdout，绝不影响 HTTP 响应；同一时刻只允许一个 ingest 在跑（锁），跑完若期间又有调度则再跑一次。
3. `_handle_session` 在 `session_log.append` 成功后调用 `service.sessions_ingest.schedule()`。
4. 启动时（模型加载后、serve 前）同步跑一次 ingest，失败只警告。
5. 新参数：`--sessions-out-dir`（默认 `people/<person>/archive_out/data`，须落在 person 目录内）、`--no-sessions-ingest`（关闭 2–4）。
6. `/health` 增加 `sessions_ingest: true|false` 与 `sessions_ingest_last`（最近一次成功 ingest 的 ISO 时间或 null）。

## 8. `tools/build_companion_page.py` 改动

构建参数：`--viewer`（默认 `owner`，正则同第 6 节第 8 条），烘进页面常量 `VIEWER`。

运行时（页面 JS）：
1. `logSession` 的 record 增加 `viewer: VIEWER`；若"本次不记"开着，增加 `exclude: true`。
2. 抽屉新增复选框 `#cfg-no-memory`（文案"本次对话不进记忆"），默认关，不持久化。勾上时：(a) 立即补发一条 `{role:'event', text:'exclude_session'}`（走 `logSession`，会带 exclude:true）；(b) 聊天区顶部显示细条提示"本次对话不进记忆"；取消勾选只撤提示，已发的事件不撤（整会话仍排除，符合"测试会话"语义）。
3. `loadKnowledge` 增加 `one('sessions_' + VIEWER + '.json', 'sessions')`（`{cache:'no-cache'}`，与本日 hotfix 一致）；文件缺失或 `viewer` 字段不等于 `VIEWER` 则按 `{last_card:null, recent_dates:[], sessions:[]}` 处理。
4. 第四检索源：新函数 `retrieveSessions(tokens, viewerData, opts)`，把 `sessions[].turns[]` 展平为条目，复用 `scoreText`；user 条标签 `[对话者自述 · 往次对话 Tier-2]`，simulacrum 条标签 `[往次数字对话 Tier-3]`；文本 ≤200 字；排除 `session_id === sessionId`（本次会话不检索自己）；`opts.sessTop` 默认 3。合并顺序：memories → transcripts → sessions（第一纪元优先，`buildRetrievalBlock` 的 2200 字预算不变，超预算先丢 sessions 条）。
5. 上次对话卡：`chat_context.json` 与 `sessions_<viewer>.json` 都加载完成后，若 `last_card` 存在且 `last_card.session_id !== sessionId`，把下面的块拼到 `systemPrompt` 末尾（只在内存，不写任何存储）：
   ```
   【往次对话 · 第二纪元 · 非她生前记忆】
   上次对话：YYYY-MM-DD（N 天前）。更早还有：YYYY-MM-DD、…
   对话者当时说过（Tier-2，可当真，引用时说"侬上趟搭我讲过"）：
   - …
   最后一来一回：对话者「…」／你「…」（你上次的话只用于前后一致，不是事实来源）
   ```
   `N 天前` 由页面按本地日期计算；当天为"今天早些时候"。
6. `retrieval_used` 日志沿用现有机制，自然带上新标签。

回归约束：不改 `splitMessages`、语音条、多服务商、情绪层任何行为；`sessions_<viewer>.json` 缺失/坏 JSON 时页面行为与改动前逐字节等价（除 record 多出 `viewer` 字段）。

## 9. `prompts/chat_system.zh.md` 改动

在铁律列表末尾追加一条（编号顺延）：

> **往次对话纪律。** 提示词末尾或检索片段里带 `[对话者自述 · 往次对话 Tier-2]` 的内容，是对话者本人在之前的对话里告诉你的事，可以当真，但只能以「侬上趟搭我讲过」「上回侬提到」的口吻引用，不能说成她生前经历过或记得的事。带 `[往次数字对话 Tier-3]` 的是这个模拟上次说过的话，只用于保持前后一致，不是事实来源，绝不能说成「妈妈记得」。

改后重跑 `build_chat_context.py --person mama --memories-mode index`。

## 10. `tools/build_archive.py` 改动

`copy_tree_whitelist` 复制 `data/` 子树时跳过所有匹配 `data/sessions_*.json` 的文件，并在 reconcile 阶段视其为不应存在的文件。理由：companion 不在 dist；第二纪元数据是对话者私有记录，不随可分享档案外发。

## 11. 预填与一次性动作

- 创建 `people/mama/sessions/exclude.txt`，预填三次测试会话：`20260907-163339-q6J5Tq`、`20260907-164311-AZOFgF`、`20260907-164405-93Z9BB`，每行带注释"09-07 凯西复测"。
- 首次运行 `ingest_sessions.py --person mama` 生成 sessions_owner.json；重建 companion.html（`--viewer owner`）；重启 tts_server（venv python 直启，处理两层 PID）；`build_archive` 一次以应用第 10 节的排除。

## 12. 测试

仓库内建 `tests/`（本项目首次入库测试；用标准库 `unittest`，`python -m unittest discover -s tests`）：

`tests/test_ingest_sessions.py`（临时目录造 jsonl）：
- 排除三路径各一例：exclude:true 记录；exclude_session 事件；exclude.txt 命中。
- 去重：同 (session_id, turn, role) 两次，保留首条。
- 敏感省略：high/medium 命中文本被替换且不进卡；low 保留。
- 卡片：user_lines 截断到 120 字、>12 条取首 4 末 8 且标记；last_exchange 正确；无 simulacrum 的会话不成卡。
- viewer 分区：两个 viewer 写成两个文件，任一文件不含另一 viewer 的文本；非法 viewer 归 owner；out-dir 里陈旧的 `sessions_ghost.json` 被删除，其它文件不动。
- 空目录 → 合法空结构，退出 0；坏行计数不中断。
- 原子写：目标已存在旧文件，构造异常路径（如模拟写盘失败）时旧文件不变。
- 确定性：同输入两次输出去掉 generated_at 后逐字节相等。

`tests/test_tts_server_ingest.py`：去抖器在 5 s 内多次 schedule 只跑一次；跑中再 schedule 会补跑一次；ingest 抛异常不影响返回。

`tests/e2e/companion_sessions.spec.js`（Playwright，route-mock 真实运行时，按 [[verify-rendered-pixels]] 纪律）：
- mock `data/sessions_owner.json`（含 last_card 与两条 turns）+ mock LLM 端点 → 发一句 → 断言送出的 `system` 含"【往次对话"块与日期；断言 user 消息前的检索块含两种新标签且第一纪元条目在前。
- 勾"本次不记" → 断言随后 POST /session 的 body 含 `exclude:true` 且出现一条 `exclude_session` 事件。
- `sessions_owner.json` 返回 404 → 页面无卡、无新标签、无报错。

验收标准：unittest 全绿；E2E 三例全绿；Codex 审 ACCEPT；`build_companion_page` 产物 grep 到 `VIEWER`、`cfg-no-memory`、两种标签；真机：新开窗口第一句她能提到上次日期与你说过的一件事。

## 13. 工艺与分工

- DeepSeek 写全部代码：`ingest_sessions.py` 整文件新建；`tts_server.py` / `build_companion_page.py` / `build_archive.py` 走区域规格 + 全文回显 + diff 校验（[[deepseek-full-file-echo]]），锚点用封闭边界。
- 三视角 workflow 审查（正确性 / 铁律 2 合规 / 回归）→ Codex（`model: gpt-5.5`）审核验收 → 不通过回炉。
- Claude 只做 1–2 行声明式 hotfix；提示词与文档由 Claude 直接写。

## 14. 风险与伦理说明

- 沉浸度上升是本功能的目的也是铁律 2 唯一要克制的指标。缓冲：卡片块自带"第二纪元 · 非她生前记忆"标签；引用纪律写进提示词；不做主动问候；用户裁决把 8A-2b 护栏排在本功能之后，护栏仍是下一项。
- 数字人的话永久 Tier-3：sessions_*.json 不进 dist、不进 memories.md、不进 persona.md；页面只在内存拼接卡片。
- 隐私：sessions 里会有比微信记录更私密的内容，因此摄入时跑敏感省略，且按 viewer 分文件（一个 viewer 的设备永远不会下载到另一个 viewer 的对话文本；为任务 #24 爸爸场景预留）。
- 删除传播：源 jsonl 就地编辑（如 09-07 凯西涂改）下次 ingest 自然生效；整会话用 exclude.txt；不需要 manifest。

## 15. 与其他任务的接口

- 任务 #24（爸爸以丈夫角色对话）：若成立，其页面以 `--viewer dad`（或裁决的 id）构建，sessions 自动分区；关系层提示词属 #24 范围，不在本规格内。
- 8A-2b：条件 d "使用统计自见卡" 可直接读 `sessions_<viewer>.json` 的 `source_stats` 与 `recent_dates`，本规格不实现。
