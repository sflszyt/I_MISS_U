# 交接文档（HANDOFF）

> 给下一个会话的 Claude（或未来的自己）。最后更新：2026-08-04，Phase 1 完成时。
> 读这份之前先读 `CLAUDE.md`（铁律）。研究依据在 `docs/research/`。

## 一、项目一句话

为逝去的亲人建可传承数字档案（档案优先于对话，20 年后仍能打开）。首个对象：**mama**（已离开），**上海话为主辅普通话**，素材全数码、全用户（justin）视角。

## 二、已定决策（grill 会话拍板，勿重新讨论）

| 决策 | 结论 |
|---|---|
| 多人架构 | 方案 A：单仓库多人，`people/<slug>/`，工具/prompts 通用 |
| 产品形态 | **混合 C**（构建端 Claude skill + 消费端自包含静态 HTML + 可选 BYOK 对话页）✅ 用户已确认 |
| 语音选型 | Fun-CosyVoice3 主选（含上海话）· VoxCPM2 备选 · GPT-SoVITS 普通话对照；M1 必做跨方言 A/B，**家人盲听是唯一标准**；跨方言掉音色就尊重素材语言 |
| 微信导出 | 首选 chatlog 镜像 `forkgitss/sjzar-chatlog`（语音直出 MP3）；备选 WeChatMsg_2026（补朋友圈）。**用户手动执行** |
| 数据源架构 | 源适配器 → UIF 统一中间格式（`schema/uif.schema.json`）→ 下游只消费 UIF |
| 三条自我保护约束 | 已入 CLAUDE.md 铁律（Tier 分级+人工闸门 / 保留完整性 / 沉浸度克制） |
| 硬件 | RTX 4090 24GB + i9-14900KF + 64GB RAM，全本地无约束 |

## 三、Phase 1 已交付（全部经 DeepSeek 写 + Codex 三轮审核 ACCEPT）

- `CLAUDE.md` 三大铁律 · 仓库骨架 · `.gitignore`（people/ 隔离）
- `schema/uif.schema.json` + README（4 类记录：message/post/email/media_item；信封含 viewpoint/tier/provenance）
- `docs/research/wechat-export.md` · `docs/research/form-factor.md`
- `tools/ingest_media.py`（媒体清点+EXIF+报告）· `tools/silk_decode.py`（备用）· `tools/backup_check.py`（备份审计）
- `scripts/deepseek_call.py`（流式调用器，唯一可靠通道）

## 四、下一步（按序）

1. **等用户微信导出完成**（2026-08-04 晚执行）→ 产物放 `people/mama/raw/wechat/`
2. **写 chatlog 输出解析器** `tools/parse_wechat_chatlog.py`：chatlog 的 JSON/CSV → UIF `message` 记录（DeepSeek 写、Codex 审；先看真实导出文件的结构再写 spec）
3. **M0 收尾**：跑 `ingest_media.py --person mama` 清点照片/视频；配 `people/mama/backup_targets.json`，`backup_check.py` 达到 PASS（2 份备份+1 异地）
4. **M1 语音验证**：写 `clip_picker.py`（候选片段打分+人工试听清单）→ 用户戴耳机挑 3-5 个最干净 20 秒 → 装 Fun-CosyVoice3 跑克隆 → 跨方言 A/B → 家人盲听
5. M2 起步前：把 prompts/（persona/记忆/节律模板，关系层参数化）设计出来

## 五、工程注意事项（血泪教训，别再踩）

- **DeepSeek 调用**：只用 `python scripts/deepseek_call.py <spec> <out> 32000`。非流式会被网络掐断；<32k tokens 会被推理烧光正文；生成后 strip markdown 围栏 + `py_compile`；`scripts/deepseek.ps1` 勿用于含中文的文件（PS 5.1 响应解码乱码）
- **DEEPSEEK_API_KEY** 在用户级环境变量（Bash 工具进程可能不继承，可作第 4 参数传入）。⚠️ key 曾在对话明文出现，已提醒用户轮换
- **pilk**（silk_decode 依赖）在 Python 3.13 无 wheel——不阻塞（主路径 chatlog 直出 MP3），真需要时装 VS Build Tools 或用 py3.11
- **控制台中文乱码**是 GBK 代码页显示问题，文件都是 UTF-8，勿在脚本里强改 stdout 编码（Codex 建议保持现状）
- 审核循环战绩参考：Codex 第一轮抓过 3 个 blocker（--person 路径注入写 raw/），修复模式是 slug 正则 + resolve() 锚定校验——新工具写 spec 时直接把这两条要求写进去

## 六、用户待办

- [ ] 今晚：chatlog 导出微信（先冷备份微信数据目录！版本 ≥4.0.3.36 需降级或 wx_key 取密钥，见 wechat-export.md 第五节）
- [ ] DeepSeek API key 轮换
- [ ] 准备两个备份目标（一个异地，如 NAS/网盘加密包/亲戚家硬盘）
