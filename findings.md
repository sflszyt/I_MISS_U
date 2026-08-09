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
- MP3 编码路线：soundfile + lameenc（64kbps mono），venv 已装，勿找 ffmpeg
