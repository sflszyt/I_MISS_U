# MVP 生产 · 发现记录

## DeepSeek API（2026-08-09 探针实测）
- /models 只有 deepseek-v4-flash 与 deepseek-v4-pro；`deepseek-chat` 作为别名可用（走非推理路径）
- **`thinking: {"type":"disabled"}` 有效**：reasoning_content 消失，正文直出（这是修复关键）
- `reasoning_effort`（minimal/low）被接受但**不生效**，照样推理
- 病根实测：复杂 spec 下 60k max_tokens 中 59.1k 被推理吃掉，正文仅 3014 字符
- 修复：deepseek_call.py 支持 `DEEPSEEK_NOTHINK=1`（关推理）与 `DEEPSEEK_MODEL`（换模型）环境变量；Claude 直写补丁（调用器自举，已声明）

## B1 训练环境（重启恢复实测）
- 三坑：①backward OOM=残留显存，重启即愈；②GBK ds_stub 廃稿经 PYTHONPATH 遮蔽 venv 正版 → SyntaxError；③cv 的 @torch.inference_mode() 与 Windows gloo DDP _sync_buffers 冲突 → 改 @torch.no_grad()（executor.py:146）
- 45 条 8.2 分钟 15 epoch 全量 SFT 约 14 分钟（4090，梯度检查点开）
- 训练工作区已固化 ~/wu-sft/v0/（数据+脚本+checkpoint epoch_0..14+试听存档 listen_archive/）

## 训练数据质量（Codex 补审 + 复核）
- 18/45 条转写需校对：14 条含 U+FFFD（行 4,6,12,13,14,15,16,21,23,29,31,37,42,43）+ 4 条拉丁噪声（行 17,18,24,39：CATCE/XRI/BRO 等）
- 干净 27 条 + 拉丁 4 条存疑 → 31 条先行重训方案中"干净"实为 27 条纯净 + 需复核 4 条（1b 执行时按 27 条保守口径）
- MP3 编码路线：soundfile + lameenc（64kbps mono），勿找 ffmpeg。**库在 cosyvoice venv**（C:\Users\justin\venvs\cosyvoice\Scripts\python.exe）；chatlog-keeper venv 与 asr venv 均没有（2026-08-10 实测）

## Codex 审核可靠性（2026-08-12 第二次实证）
- **Codex 读含 CJK 的文件会产生"语法错误/字符串未闭合"类误报**（scrub_sensitive.py 的 ⏎ 字符与 sensitive_patterns.json 的中文 regex 被判"unterminated string"，py_compile+json.load 双双实证不成立；08-12 上午 make_contact_sheet 已发生过一次）。对策已固化：①凡 Codex 报语法类 BLOCKER，先本机 py_compile/json.load 实证再回炉；②给 DeepSeek 的源码尽量用 \uXXXX 转义替代裸特殊字符；③给 Codex 的复审 prompt 明确要求"跑命令验证，勿目测"（实测有效：复审时 Codex 自跑命令撤回了两条误报）
- Codex read-only sandbox 下 `python -m py_compile` 会因写 __pycache__ 报 Permission denied——它改用了无写盘 parse 验证，说明复审 prompt 给验证方式留余地是对的

## 敏感扫描存量（2026-08-12，删除 14 条后）
- 全量 scan：21249 条记录命中 601 疑似（high 273/medium 50/low 278），报告 people/mama/normalized/sensitive_scan_report.{jsonl,md}
- high 里大头是 password/account 关键词与 16-19 位连续数字（含大量误报如淘宝单号），须人工复核，3d 闸门页对命中候选默认剔除

## 音频产物验收盲区（2026-08-12 用户实锤）
- **make_blind_page v1 把 float32 采样字节直喂 lameenc（要 int16 PCM）→ 全部音频变强噪音+低沉"男声"，连真实录音都坏**——node --check/泄漏检查/体积检查全过，唯独没人"听"。用户预演一耳朵抓出
- 对策已固化进工具与流程：①MP3 编码一律复用 build_avatar_page.encode_mp3 的 int16 成熟模式；②凡产音频的工具内置**解码回读自检**（sf.read(BytesIO(mp3))，时长 ±10% + RMS ≥¼ 源）；③交付前跑独立 roundtrip 脚本（scratchpad/roundtrip_check.py 模板：时长零漂移=无音调偏移的判据）；④诊断口诀：连"未经处理的真实素材"都坏 → 缺陷在打包/编码层而非生成层
- 法证佐证（Codex）：坏 MP3 体积恰为正常 2 倍（float32 被当 int16 读，采样数×2）——体积比对可作快速嗅探

## Phase R 移动 review 体验（2026-08-10）
- DeepSeek 三引号拼接陷阱：让它在 Python '''模板''' 里注入占位符时，容易写出 `''' + '"' + '''` 这类产出非法 JS 的拼接——生成后必须实跑并 grep 关键 JS 行验证
- avatar_preview.html：3 条内嵌语音仅 0.10MB（24kbps mono），1MB 预算内可放 5-10 条
