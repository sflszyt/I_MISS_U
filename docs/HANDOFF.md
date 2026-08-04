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
| 微信导出（**已定案 2026-08-04**） | 用户微信实测 **4.1.11.24**。chatlog/chatlog-new 不支持 4.1.x（出局）。**采用混合方案**：①文字+图片→ `chatlog-keeper`（MIT，已在 4.1.11 取到 key 并缓存，`wechat`+`images` 命令）；②视频→ **直接复制** `xwechat_files/<wxid>/msg/video/**/*.mp4`（4.1 视频是明文 mp4，实测 387 个）；③语音→ **自研提取器**（SILK blob 在加密消息库内，需先探测表/字段，DeepSeek 写 Codex 审，pilk/silk→wav）。详见 `docs/research/wechat-media-extraction.md`。备选交叉验证：`LifeArchiveProject/WeChatDataAnalysis`（无协议、DMCA靶心，用完即弃）。chatlog-keeper 源码在 `installers/chatlog-keeper-0.2.0/`，已建 .venv 装好依赖 |
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

**微信导出与媒体提取的 RE 已全部跑通验证**（2026-08-05），完整配方见 `docs/research/wechat-media-extraction.md` 第三点五节。关键状态：
- 全量文字已导出 → `people/mama/raw/wechat/export_full/wechat_messages.json`（75万条；妈妈 laurawang001 6968 条）
- 语音 84/85、视频 13/25 已验证可提取（真实 60s 语音样本已解码到 `~/ck-decrypted/sample_mama_voice.wav`）
- 解密环境：key 在 `~/ck-data/secrets/`，db 镜像(已删shm)在 `~/ck-mirror`，明文库在 `~/ck-decrypted`，pysilk-mod 已装进 venv

**待建（DeepSeek 写 + Codex 审）**：
1. `tools/extract_wechat_voice.py`（#11）：VoiceInfo.voice_data → pysilk.decode(blob,24000) → wav；按 svr_id 关联妈妈会话；输出 processed/wechat_voice/ + UIF media_ref
2. `tools/collect_wechat_video.py`（#12）：packed_info md5 → 复制 msg/video mp4 → raw/wechat/video/ + UIF media_ref
3. `tools/parse_wechat.py`（#13）：wechat_messages.json 筛 laurawang001 → UIF message JSONL（含 viewpoint=justin/tier=2/provenance），合并语音视频 ref
4. **M0 收尾**：ingest_media 清点照片/视频；配 backup_targets.json 达 PASS
5. **M1 语音验证**：clip_picker → 挑 20s → Fun-CosyVoice3 克隆 → 家人盲听。注意：微信语音是最差声源(SILK窄带)，克隆主素材应来自家庭录像；但妈妈 84 条微信语音本身是珍贵档案

**注意 pysilk.decode 要传完整含 0x02 头的 blob（剥离会报 Not a valid silk_data）。**

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
