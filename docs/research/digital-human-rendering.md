# 研究：数字人实时本地渲染技术选型（digital-human-rendering）

> 2026-08-23 立项（任务 #17）。背景：纸片人双帧口型历经三根因修复（看门狗/帧素材/缓存）后用户仍报"疯狂闪烁"——**架构性死因定案：两张独立 AI 生成的整图互换，像素级全图偏移在任何节奏下都呈现为闪烁而非动嘴**。用户裁决"这个技术有问题"，立项找成熟方案。
> 方法：workflow 5 代理（4 路线并行核证 + 场景适配裁决），90 次网络检索，2026-08 现状。
> 场景五约束：①单张定稿卡通头像出发（铁律不做真人脸）②口型自然+呼吸感 ③构建端 4090 任意重 ④消费端自包含静态 HTML 活 20 年 ⑤一人业余维护、一次性成本可高持续维护须零。

> **执行状态（2026-08-27）**：✅ Phase 0 三态贴片（08-25，附加战果：display=''被类规则回落的假阳性根因，验收铁律升级为像素层，见 findings 08-25 节）；✅ Phase 1 viseme 时间轴（08-27 收官：Rhubarb 125 条 18516 cues + build_visemes.py + 四态嘴 W1/R1 + 眨眼 B1 + ambient 微摆，用户定稿）；⬜ 混合增强 talking-head 特别版待用户点头。实施细节见 task_plan Phase 7 与 progress 08-25/26/27 节。

---

## 一、裁决：路线 4「viseme 嘴部贴片 + 预计算时间轴」定为主线

**唯一五约束全绿的路线，且路线 3（runtime 地基评估）独立研究收敛到同一架构——双重验证。**

核心原理（百年动画工艺，非新发明）：
- **底图恒定为公理**：只在嘴部矩形区域贴 3-9 张嘴型差分贴片，掩码外像素逐字节等于定稿头像——整图零抖动是**工艺保证**，不是调参祈祷。Adobe Character Animator（11 viseme + 3 静默嘴型）、日式 galgame 立绘口パク（3 帧标准）、整个 PNGTuber 生态全是这套。
- **旧方案死因的行规印证**：PNGTuber 生态（veadotube mini 等）隐含前提=所有状态图必须是同一底图的图层差分，绝不用两张独立生成的整图——我们违反的正是这条行规。
- **口型时间轴构建端预计算**：Rhubarb Lip Sync（2.6k★，v1.14.0 2025-04，活跃）音频→viseme JSON 时间轴；**phonetic 模式语言无关**（识别元音不识别单词），中文已被社区实证，**是上海话唯一现成方案**。普通话 TTS 条目可选 MFA 拼音对齐（mandarin_mfa 官方模型）提精度。
- **消费端零依赖**：PNG 贴片 + JSON 时间轴 + `audio.currentTime` 查表（≈200 行可审计 JS）——不碰 WebAudio（iOS Safari 的坑架构性绕开）、零库零 license 零闭源 core。**20 年红线全场最高分。**
- **贴片生成**：盘上现成 Qwen-Image-Edit-2511（Apache-2.0，主打 character consistency）+ ComfyUI 掩码 inpaint 标准工法（ImageCompositeMasked 节点保证掩码外直接取原图）。
- **独有加分**：同一套贴片既服务 125 条预计算时间轴，又能音量级驱动未来 BYOK 对话的动态 TTS 音频——视频路线对动态音频无解。

## 二、四路线排名与关键证据

| 排名 | 路线 | 一句话裁决 |
|---|---|---|
| 1 | **viseme 嘴部贴片**（主线） | 五约束全绿；底图恒定为公理根治闪烁；消费端 PNG+JSON+原生 API |
| 2 | 零依赖 runtime 地基 | 与路线 4 同构收敛；独立价值=消费端排他结论（见下） |
| 3 | talking-head 预渲染 MP4 | 表现力天花板最高、MP4+`<video>` 20 年合规；但身份漂移/眼镜 artifact 踩在"形象稳定"红线上→降为精品条目增强 + 主线失败第一备选 |
| 4 | Live2D | 工艺最成熟但：单图→分层 PSD 缺口（外包 $450-1450+忠实还原验收风险）、Cubism Core 闭源 blob 违 20 年自救原则、rigging 投入最重→当前不投入 |

### 消费端 runtime 排他结论（路线 3）
- **纯 Canvas/CSS sprite**：仅依赖 1998-2005 世代冻结 API，20 年把握最高 ✅ 主线
- 预渲染 H.264 MP4：开放格式（专利 2027 后全清，LoC 认可 access format），兜底基准 ✅
- rive-wasm（@rive-app/canvas-single，MIT 单文件内嵌 WASM）：唯一及格的第三方 runtime，备选
- **Live2D**：Cubism Core 闭源无源码不可自救 ❌；**Spine**：license 要求集成方持有效编辑器授权 ❌；**Inochi2d web**：原型态 ❌；3D VRM 路线：与单图起点根本错位 ❌
- WebAudio 运行时音量分析=实锤雷区（iOS 17 createMediaElementSource broken、AnalyserNode 全零史——本项目已亲踩）→ 预计算时间轴架构性绕开

### talking-head 模型格局（路线 2，备选知识）
- **老三样直接排除**：SadTalker（停更+卡通脸检测失败）、MuseTalk（需模板视频+真人特化）、AniPortrait/Hallo3（photoreal 特化）、EMO（未开源）
- **新一代卡通可用四强**：InfiniteTalk 1.5（7.7k★ Apache-2.0，官方声明泛化 stylized 域）、EchoMimicV3（蚂蚁 AAAI 2026，1.3B Apache-2.0，官方 4090D 实测）、FantasyTalking（阿里 Apache-2.0，官方声明 cartoon avatar）、Sonic（腾讯 CVPR 2025，anime demo，4090 16 倍实时，CC BY-NC）
- **形变路线**：LivePortrait（19k★，官方卡通支持，4090 实时级）+ JoyVASA（音频→运动，hubert-chinese 对中文友好）——身份零漂移但动作幅度小
- 产能核算：125 条语音（25-40 分钟）4090 一夜到一个周末批完，200-600MB sidecar
- 两大实测风险：125 条片段间身份/画风漂移（扩散系无跨片段一致性机制）；**眼镜是所有 talking-head 模型的经典 artifact 区**

## 三、落地计划（用户批准后执行）

**Phase 0 止血（约 1 天）**：
1. ComfyUI + Qwen-Image-Edit inpaint 出 3 态嘴型贴片（闭/半开/张），掩码严格限嘴部；**验收硬标准=逐字节 diff 脚本校验掩码外像素与定稿头像完全一致**（程序校验非肉眼）
2. 前端从"整图互换"改"恒定底图+嘴部贴片 Canvas 合成"，3 态按 RMS 映射（DeepSeek 写+Codex 审）→ 闪烁即刻消灭

**Phase 1 viseme 升级（2-3 晚）**：
3. Rhubarb `-r phonetic` 批跑 125 条出 JSON 时间轴（抽查 5-10 条核口型时机）
4. 贴片扩到 A-F+X 6-9 态（大张口档最易画风跳变——宁可减档合并也不要画风不一致）
5. 消费端 ≈200 行零依赖 JS：currentTime 查表 + 随机眨眼帧 + CSS transform 整体微摆（呼吸感；整图统一变换无像素错位）
6. Rhubarb 并入 build skill：新增语音=一条 CLI 追加一个 JSON，零持续维护
7. 动态 TTS 分支：BYOK 对话页用 WebAudio RMS 驱动同一套贴片（唯一用 WebAudio 的分支）

**混合增强（主线稳定后可选）**：挑 3-5 条最重要语音用 InfiniteTalk/EchoMimicV3 渲 MP4"特别版"，逐帧人工验收后以 `<video>` 并存入档（不合格直接弃）；档案默认展示层永远是贴片层。

**Kill criteria**：K1 贴片画风迭代 2-3 晚仍不一致且画师外包不可行→路线 2 四模型淘汰赛；K2 家人评"僵硬出戏"→转 MP4 主线；K3 Rhubarb 上海话时间轴错位 >30% 且音量级不可接受→转路线 2（扩散模型不依赖音素识别器）；总开关=一旦陷入持续手工维护或被迫引入在线依赖/闭源 runtime，立即停下重审。

**风险对策**：R1 贴片画风一致性（最大风险）→同 seed 批量+人工挑；不济则画师照稿画 6 张嘴部差分小图（局部差分成本远低于整图/Live2D 分层稿）。R3 情感验收→贴片与最终效果**家人过目**——"还是不是她"只有家人能判，与 M1 盲听同级闸门。

---

## Sources（节选）
- Rhubarb Lip Sync https://github.com/DanielSWolf/rhubarb-lip-sync
- ComfyUI 掩码 inpaint 工法 https://civitai.com/articles/5333/
- MFA Mandarin 模型 https://mfa-models.readthedocs.io/en/latest/dictionary/Mandarin/
- InfiniteTalk https://github.com/MeiGen-AI/InfiniteTalk · EchoMimicV3 https://github.com/antgroup/echomimic_v3 · LivePortrait https://github.com/KwaiVGI/LivePortrait · JoyVASA https://github.com/jdh-algo/JoyVASA
- Live2D license https://www.live2d.com/en/sdk/license/ · rive-wasm https://github.com/rive-app/rive-wasm
- veadotube（PNGTuber 行规佐证） https://veado.tube/docs/usage/mini/
- LoC 视频格式保存建议 https://www.loc.gov/preservation/digital/formats/fdd/fdd000579.shtml

*2026-08-23 首版。方法：workflow 4+1 代理并行核证。*
