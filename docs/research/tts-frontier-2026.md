# 研究：前沿 TTS 模型十维度对比（tts-frontier-2026）

> 2026-08-17 立项。问题：VoxCPM2 / IndexTTS2 / GPT-SoVITS / dots.tts / Qwen3-TTS / Grok Voice 这些前沿模型，相对现役 CosyVoice2-Wu-SFT 方案如何？
> 方法：每模型一个研究代理独立检索核证（2026-08 状态，共 60+ 信息源），另加沪语生态扫描；维度 8/9（数据要求、人工干预）单独补充轮。
> **结论速览：不换现役方案。六个候选全部不支持上海话克隆——这一条就定了大局。** 唯一值得排期的行动：VoxCPM2 按 M1 标准做一轮 A/B 盲听（它预训练含"吴语"大类）；Qwen3-TTS 列为观察对象（阿里内部握有沪语数据，等开源下放）。

---

## 〇、基线：现役方案是什么

| 项 | 现役状态 |
|---|---|
| 底座 | CosyVoice2-Wu-SFT（ASLP-lab WenetSpeech-Wu，约 8000 小时吴语语料，Apache-2.0） |
| 训练 | 本人数据 **LoRA-free 全量 SFT**，160 条 / 47.2 分钟微信语音（SILK 窄带 16k），RTX 4090 24GB 本地 |
| 现役模型 | mama_v02f160_llm **epoch_14**（2026-08-16 定稿） |
| 双语域 | `<|wuyu|>` 前缀 = 上海话；裸文本 = 她的沪普（带口音普通话）——SFT 后裸文本自动携带本人口音 |
| 验证 | 试听批 14 条全绿；盲听 v1 自听 7/8；盲听 v2 物料就绪等家人 |
| 输出 | 24kHz，离线批量，:8022 本地 TTS 服务 |
| 人工干预 | ASR 初转写→逐条人工校对（首批 45 条中 18 条需修正，**错误率 40%**）→epoch 试听盲选→合成后逐条筛选 |

评判基准（CLAUDE.md 既定）：**家人盲听是唯一有效标准**；她的声音数据不出本机（云端克隆 API 一律只作风向标记录，不可采用）。

---

## 一、总评表（先看这张）

| 模型 | 上海话/吴语 | 本地微调 | 许可 | 一句话裁决 |
|---|---|---|---|---|
| **CosyVoice2-Wu-SFT（现役）** | ✅ 吴语专用底座 | ✅ 全量 SFT（已验证） | Apache-2.0 | **继续现役** |
| VoxCPM2 (2B, 2026-04) | ⚠️ 预训练列表含"吴语"大类，上海话质量零口碑 | ⚠️ LoRA 可（~20GB）；全量 SFT 需 ~40GB **超出 4090** | Apache-2.0 | **唯一值得 A/B 的候选** |
| IndexTTS2 / 2.5 (2026-01) | ❌ 无（连粤语都没有） | ❌ 官方无微调代码 | 权重自定义许可（非商用免费，衍生受限） | 情绪解耦技术风向标 |
| GPT-SoVITS v2Pro/ProPlus | ❌ 无（粤语是唯一方言） | ✅ 少样本微调（1 分钟即可用） | MIT | 维持"普通话对照组"定位 |
| dots.tts (2026-08-13 刚开源) | ❌ 无（24 语止步粤语） | ⚠️ 官方 SFT 脚本有，2B 在 24GB 上未验证 | Apache-2.0 | 普通话对照候选 + 连续自回归路线风向标 |
| Qwen3-TTS 开源线 (2026-01) | ❌ 开源无上海话（**API 线有沪语预置音色但克隆×方言不相交**） | ⚠️ /finetuning 目录有，无官方指引 | Apache-2.0 | **观察对象**：等阿里把方言下放开源 |
| Grok Voice (xAI, 云 API) | ❌ 无中文方言 | ❌ 纯云端 | 闭源 API | **制度性排除**（见 4.6） |

核心事实一句话：**2026 年 8 月，全网没有第二个可本地部署的上海话克隆底座。** WenetSpeech-Wu 生态（我们现役的根）依然是独一份——沪语生态扫描的详情见第五节。

---

## 二、十维度对比矩阵

> 维度编号沿用立项口径：0 语言方言 · 1 情绪 · 2 还原度 · 3 长文本 · 4 敏感字 · 5 参数调节 · 6 生成速度 · 7 本地训练硬件 · 8 训练数据质量数量 · 9 人工干预程度。
> 维度 8/9 的完整对比见第六节（补充轮专项）。

### 维度 0：语言与方言支持

| 模型 | 中文方言 | 备注 |
|---|---|---|
| 现役 Wu-SFT | 吴语 8 子方言（专用底座） | 上海话 + SFT 后沪普双语域已验证 |
| VoxCPM2 | 川/粤/**吴**/东北/豫/陕/鲁/津/闽南 | 30 语种；"吴语"是大类，上海话未单列、无第三方口碑 |
| IndexTTS2.5 | 无 | 中/英/日/西/阿五语种，普通话为主 |
| GPT-SoVITS | 仅粤语（'yue'） | 无吴语 G2P 前端，社区也无上海话方案 |
| dots.tts | 仅粤语 | 24 语种 |
| Qwen3-TTS 开源 | 预置说话人级：北京话、四川话 | API 线 Flash 有上海话**预置音色**；但声音复刻线 qwen3-tts-vc 的语言清单不含任何方言——**"克隆你的声音"与"说上海话"在阿里产品矩阵中不相交** |
| Grok Voice | 无 | 28 语种全球主流覆盖，无中文方言颗粒度 |

### 维度 1：情绪控制

| 模型 | 机制 | 口碑 |
|---|---|---|
| 现役 Wu-SFT | 底座另有 instruct-emotion/prosody 变体（未采用）；现役靠 SFT 数据自带语气 | 满足档案场景 |
| VoxCPM2 | 参考音频迁移 + 文本内嵌自然语言指令 + Voice Design | 官方自认指令控制"多次运行间不稳定" |
| **IndexTTS2.5** | **情绪-音色解耦**：情绪参考音频 / 文字描述 / 8 维情绪向量，三选一 | **开源第一梯队**；但情绪调强会侵蚀音色相似度 |
| GPT-SoVITS | 无显式机制，纯参考音频迁移 | 每种情绪需备干净参考段 |
| dots.tts | 基座隐式迁移 + 换 seed；显式控制仅在 dots.tts.edit（`<emo>` 标签） | 刚发布，口碑样本少 |
| Qwen3-TTS | instruct 自然语言指令（"用特别愤怒的语气说"） | 克隆音色与 instruct 控制能否兼得，无第三方口碑 |
| Grok Voice | speech tags（[laugh]/[sigh]/whisper 等内联标签） | 宣传强、独立验证弱 |

### 维度 2：还原度（克隆相似度）

| 模型 | 路径 | 指标/口碑 |
|---|---|---|
| 现役 Wu-SFT | 47 分钟全量 SFT | 盲听 v1 自听 7/8；家人盲听待验 |
| VoxCPM2 | zero-shot 3-10s / LoRA r=32 | **SIM 85.4% vs ElevenLabs 61.3%（第三方复测）**，头牌强项；但弱势语言"像但听不清"风险 |
| IndexTTS2.5 | 仅 zero-shot | "工业级"定位，无一手 SIM 数字；无微调提升通道 |
| GPT-SoVITS | 5s zero-shot / 1 分钟微调 | 开源中文克隆第一梯队口碑；v2Pro 加说话人向量再提升 |
| dots.tts | zero-shot（continuation 模式更好）/ base+SFT | **Seed-TTS-Eval 中文 SIM 81.0，开源 SOTA 档** |
| Qwen3-TTS | zero-shot 3s / finetuning | 自报 10 语种平均 SIM 0.789 超 MiniMax/ElevenLabs（无独立复测） |
| Grok Voice | 云端 zero-shot 60-120s | 无公开指标 |

### 维度 3：长文本

- **现役**：离线批量逐句合成 + 人工筛选，长文本无压力（管线级解决）。
- **VoxCPM2**：官方自认长输入"偶发不稳定"，CLI 带 retry 参数——**相对弱项**。
- **IndexTTS2.5**：时长控制是卖点（首个精确时长控制的 AR TTS）；专门 batch 模式改善长文，但社区实测有时更慢。
- **GPT-SoVITS**：AR 固有漂移，靠强制文本切分（按标点/50 字/4 句）解决，切分得当稳定可用。
- **dots.tts**：单次最长 ~82 秒桶；流式 + 双流交互；官方称"稳定性可被驯服"，独立实测少。
- **Qwen3-TTS**：官方有 long-zh 基准自报优于基线，缺独立验证。
- **Grok Voice**：REST 15k 字符上限，WebSocket 无上限流式，字符级时间戳。

### 维度 4：敏感字（内容审查）

**六个候选里所有可本地部署的模型（VoxCPM2 / IndexTTS2 / GPT-SoVITS / dots.tts / Qwen3-TTS 开源线）本地推理均无内容审查、无敏感词过滤、无水印机制**——与现役方案一致，档案场景不受限。仅有的审查在云端：阿里百炼 API 线受平台合规约束（复刻音频需上传并留存）；Grok Voice 的克隆闸门见 4.6。此维度不构成任何候选间的区分度，**本地开源权重路线天然免疫此问题**。

### 维度 5：参数调节对质量的影响

| 模型 | 可调面 | 调参难度 |
|---|---|---|
| 现役 Wu-SFT | CosyVoice 系成熟社区经验 | 已沉淀（工艺红线文档在案） |
| VoxCPM2 | cfg_value/timesteps/temperature/seed | 文档无推荐区间，靠试；**文档成熟度低于 CosyVoice 系** |
| IndexTTS2.5 | 情绪源三选一 + emo_alpha + 时长/语速 + 逐字纠音 | 中等；情绪权重与相似度拉扯 |
| GPT-SoVITS | top_k/top_p/temperature + 切分策略 + **参考音频选择（事实上最重要的参数）** | 中等；默认值即可用 |
| dots.tts | num-steps/guidance-scale/seed；**无 temperature/top-p**（连续隐空间无 token 采样器） | 低；靠 seed 抽卡 |
| Qwen3-TTS | HF generate 通用参数 + instruct | 旋钮少、文档薄、社区经验空白 |
| Grok Voice | speech tags + 语速/发音替换 | 门槛低、可控深度浅 |

### 维度 6：生成速度（RTX 4090 口径）

| 模型 | RTF | 备注 |
|---|---|---|
| **GPT-SoVITS v2ProPlus** | **≈0.014**（1400 字 4 分钟音频推理 3.36 秒） | 六者最快，另有 C++/TensorRT 生产化线 |
| dots.tts | 0.21（H800）；4090 无官方数据，6GB 卡可用 | MeanFlow 蒸馏版 RTF 0.13-0.16 |
| VoxCPM2 | ~0.30，Nano-vLLM 加速 ~0.13 | 支持流式 |
| IndexTTS2.5 | 较 2.0 提速 2.28×，4090 接近实时 | 推理 ~6GB |
| Qwen3-TTS | 无 RTF 数据；首包宣称 97ms | 1.7B 推理 6-8GB |
| Grok Voice | 云端，首音频 ~285ms（第三方实测） | 不适用本地口径 |

现役离线批量场景下，速度维度对所有候选都不构成瓶颈——**此维度无淘汰权**。

### 维度 7：本地训练硬件要求

| 模型 | 推理 | 微调（4090 24GB 可行性） |
|---|---|---|
| 现役 Wu-SFT (0.5B) | 轻松 | ✅ 全量 SFT 已验证（160 条 47 分钟数小时级） |
| VoxCPM2 (2B) | ~8GB | ⚠️ LoRA ~20GB 可跑（余量紧）；**全量 SFT ~40GB 不可行** |
| IndexTTS2.5 | ~6GB | ❌ 无官方微调代码，无从谈起 |
| GPT-SoVITS | 轻松 | ✅ 6-8GB 消费卡即可微调，4090 毫无压力 |
| dots.tts (2B) | 5.3-10.5GB | ⚠️ 官方脚本有，但 2B 全量 SFT 在 24GB 上大概率需梯度检查点/8-bit 优化器，未经官方确认 |
| Qwen3-TTS (0.6B/1.7B) | 4-8GB | ⚠️ 0.6B 从容、1.7B 大概率可行（未核实）；**但底座无吴语先验，从 47 分钟数据硬教方言起点太差** |
| Grok Voice | — | ❌ 不适用 |

**关键格局**：2026 年开源 TTS 普遍从 0.5B 涨到 2B，**"消费级单卡全量 SFT"正在从可行滑向不可行**（VoxCPM2 需 40GB、dots.tts 未验证）。现役 0.5B 底座全量 SFT 是这个窗口期的产物——这套已验证工艺本身就是资产。

---

## 三、逐模型裁决

### 3.1 VoxCPM2 —— 唯一值得排期 A/B 的候选

- **为什么值得**：预训练官方列表含吴语（六候选唯一）；tokenizer-free 连续表征的克隆相似度是开源第一梯队（SIM 85.4% 第三方复测）；48kHz 输出对窄带素材可能有听感增益；Apache-2.0 全链路开源含微调管线。
- **为什么不够**："吴语"≠上海话，质量零口碑；全量 SFT 超出 4090（只能 LoRA，与现役工艺不对等）；长文本自认偶发不稳；2026-04 才发布，踩坑积累浅。
- **行动**：按 M1 标准 A/B——zero-shot（3-10s 参考）与 LoRA r=32（47 分钟数据）各出一版样本，与 v0.2 e14 同题同文本进盲听页。**盲听赢了才有下一步，输了归档。**

### 3.2 IndexTTS2 / 2.5 —— 情绪技术风向标，不进管线

无吴语、无粤语、无官方微调路径，直接出局于主语域。情绪-音色解耦（情绪参考音频/文字/8 维向量三通道）是当前开源最强，记录为未来"情绪化档案朗读"场景的技术储备。许可为自定义 INDEX MODEL LICENSE（非商用免费，微调/量化产物均算受限衍生物）——个人纪念用途无碍，但比 Apache-2.0 多一层 20 年不确定性。

### 3.3 GPT-SoVITS v2Pro —— 维持"普通话对照组"既定定位

本次核证确认：无吴语 G2P 前端、社区亦无上海话方案，CLAUDE.md 的既定定位无需修改。它的少样本微调口碑（1 分钟可用、47 分钟充裕）、RTF 0.014、MIT 许可、6-8GB 即可训练，都使它成为**泛化轴 3（其他方言/口音用户）的重要底座候选**——普通话/粤语对象的建档可能直接用它。产品化时的选型矩阵应记入。

### 3.4 dots.tts —— 新路线风向标，暂不引入

2026-08-13 刚开源（发布仅数天），SIM 81 开源 SOTA、48kHz、Apache-2.0、官方 SFT 脚本齐全——纸面规格漂亮，但无吴语、第三方实测几乎为零、2B 全量 SFT 在 24GB 上未验证。连续自回归（无离散 codec token）是 2026 开源 TTS 的新路线，值得半年后回看其社区口碑与是否加方言。

### 3.5 Qwen3-TTS —— 最重要的观察对象

开源线无上海话，但**阿里产品矩阵暴露了它握有沪语数据**：API 线 Flash 有上海话预置音色、闭源 Qwen-Audio-3.0-TTS 宣称 20 方言。当前的制度性断裂在于：声音复刻线（qwen3-tts-vc）不支持方言——"克隆"与"上海话"不相交，且复刻需上传音频到阿里云（红线禁用）。**若未来方言能力下放到开源 Base 权重，它将成为 CosyVoice2-Wu 的第一替代候选**——同为阿里系，且参数量更大。建议每季度看一眼 QwenLM/Qwen3-TTS 的 README。

### 3.6 Grok Voice —— 制度性排除，且反向印证了我们的路线

本次研究最有意思的发现：xAI Custom Voices 的克隆闸门是**两段式活体同意验证**——说话人必须实时朗读指定校验短语（STT 比对），再与参考录音做声纹嵌入比对。**逝者的既有录音在产品设计上就无法通过**，这不是技术绕不绕的问题，是场景被明确禁止。加上纯云 API（音频必须上传 xAI）、无中文方言、仅限美国，四重排除。

它的价值是佐证：大厂云 API 的克隆合规趋势（活体同意）正在把"逝者语音档案"这个场景**制度性地锁死在本地开源权重路线上**——我们 2026-02 定下的隐私红线，如今是唯一可行路径。

---

## 四、维度 8/9 专项：训练数据要求与人工干预程度

> 补充轮 5 代理（Grok Voice 免研究：云端 zero-shot 60-120 秒参考、零训练、已制度性排除）。官方口径 / 社区实测 / 架构推断在各代理产出中分别标注。

### 维度 8：训练数据的质量与数量要求

**8a. 对微信 SILK 窄带 16k 素材的适配度**（本项目最关心的一列）：

| 模型 | 窄带素材适配 | 关键事实 |
|---|---|---|
| **VoxCPM2** | ✅ **六者最佳** | 编码器原生 16kHz 输入、48kHz 输出——窄带输入是其**设计工况**，无采样率失配惩罚。但对背景噪声敏感，且有硬性清洗规则：**句尾静音必须裁到 <0.5 秒**（官方 FAQ：长尾静音是微调后 runaway generation 的头号原因） |
| GPT-SoVITS v2Pro | ✅ 官方明示宽容 | 版本特性 wiki：训练集音质一般时 v1/v2/v2Pro 能出好结果、**v3/v4 不能**——v2Pro 就是官方推荐的"平庸音质"版本；内置 UVR5→切分→降噪→ASR 脏数据处理链 |
| Qwen3-TTS | ⚠️ 中性 | 官方零规格；社区口径参考音频 ≥24kHz 为佳、5-15 秒最佳（**>15 秒会导致生成挂起**）；1.7B 对噪声鲁棒但频带缺失补不回来 |
| IndexTTS2.5 | ⚠️ 会"复印"信道 | zero-shot 架构把参考片段的窄带/闷罐感直接复刻进输出；建议先做带宽扩展增强（如 resemble-enhance）再喂参考 |
| **dots.tts** | ❌ **六者最差** | AudioVAE 固定 48kHz 全带宽；预训练清洗管线含**有效带宽估计过滤**——窄带素材大概率被系统性剔出训练分布，16k 素材与其架构正面冲突 |

**8b. 数据量要求**：

| 模型 | zero-shot 参考 | 微调最低/推荐 | 收益递减 | 47 分钟/160 条的定位 |
|---|---|---|---|---|
| VoxCPM2 | 5-30 秒 | 5-50 条即够单说话人克隆；**1-3 epoch 即收敛，练多反而差** | 极早（~50 条后） | 富余；但上海话是分布外语言，多出的数据用得上 |
| GPT-SoVITS | 5 秒 | 官方"1 分钟可用"（营销下限）；社区最佳区间 30 分钟-1 小时 | >1 小时 | **恰在最佳区间** |
| dots.tts | ~10 秒（更长无益） | **官方零指引**（smoke config 示例是 24 小时 LJSpeech）；无 LoRA 选项 | 未知 | 对 2B 全量 SFT 属极小数据，过拟合自担 |
| Qwen3-TTS | 3 秒（5-15 秒最佳） | 官方零指引；社区 10-100 条 / 10-30 分钟 | ~30 分钟 | 超社区推荐上限，数量无压力；1.7B 训练社区口径 batch 8 需 ~30GB，4090 需 batch 1-2+梯度累积 |
| IndexTTS2.5 | 1 条（2-10 秒） | 无微调路径 | — | 严重过剩：只消耗最好的 10 秒 |

**8c. 转写文本要求**（直接决定人工校对闸门去留）：

- **VoxCPM2**：微调须逐条转写且官方措辞严格（"exactly match"，失配是 loss 不收敛常见元凶）；但 **zero-shot Controllable 模式完全免转写**，Hi-Fi 模式只需转 1 条参考。
- **GPT-SoVITS**：逐条转写硬需求，但官方口径"有错是劣化项而非致命项，不追求完美可跳过校对"——容错度是微调系里最高的；内置 SubFix 式校对 WebUI（与我们自建的校对页同构）。
- **dots.tts**：逐条转写必填，且 **zero-shot 参考也要求逐字准确转写**；上海话对其 BPE 文本层（无音素层）是双重分布外。
- **Qwen3-TTS**：JSONL 三字段逐条转写必填；社区实测"准确转写把 SIM 从 0.75 拉到 0.89"（单一来源）；x_vector_only_mode 可免转写但官方明说质量下降。
- **IndexTTS2.5**：**完全不需要转写**——推理 API 根本不接受参考文本参数。整个"ASR 初转写+逐条校对"环节被结构性消除，是所有候选中对现役基线最大的单项人工节省。

**跨模型共同结论**：上海话 ASR 错误率高（我们实测 40% 修正率）是**素材语言的属性，不是模型的属性**——凡走微调路径，换任何模型都省不掉人工校对；上海话"该写成什么字"的正字法问题更是所有候选都没有答案（现役 Wu 底座至少有 WenetSpeech-Wu 的转写规范可循）。

### 维度 9：人工干预程度

现役基线的三大人工闸门 vs 各候选（✂=可省，⚠=减负但保留，✋=省不掉）：

| 模型 × 路径 | ① 转写校对 | ② checkpoint 挑选 | ③ 产出逐条筛选 |
|---|---|---|---|
| **现役 Wu-SFT 全量微调（基线）** | ✋ 逐条校对 | ✋ 多 epoch 盲选 | ✋ 逐条人耳 |
| VoxCPM2 zero-shot | ✂ 免转写 | ✂ 无训练 | ✋ 且**音色本身逐次抽卡**（官方明示 1-3 次重试预期） |
| VoxCPM2 LoRA 微调 | ✋ 同基线 | ⚠ 1-3 epoch，候选大减 | ✋（retry_badcase 只兜长度类坏例） |
| GPT-SoVITS 微调 | ⚠ 普通话可降为抽检；上海话同基线 | ⚠ 默认轮数可用，复读/吞字时回退试听 | ✋ **"抽卡"是其社区黑话，筛选负担可能比基线更重** |
| dots.tts 微调 | ✋ 同基线且更敏感 | ✋ 官方零 eval 指引，还要自己蹚超参 | ✋ |
| Qwen3-TTS 微调 | ✋ 同基线 | ✋ 官方无验证指标 | ✋ 无内建 QC |
| IndexTTS2.5 zero-shot | ✂ **定义性消除** | ✂ **定义性消除** | ✋ 分段韵律不连续+多音字需拼音提示 |
| Grok Voice（云） | ✂（60-120s 参考） | ✂ | 云端黑盒（但已制度性排除） |

三行结论：

1. **闸门 ③（产出人耳筛选）没有任何模型能消除**——包括云端方案。可半自动化压缩（ASR 回读比对 CER 自动淘汰 + 说话人相似度打分初筛），但韵律怪异、音色漂移是机器查不出的，家人盲听终审更是铁律层面的要求。
2. **闸门 ①② 只有 zero-shot 路径能消除**，而 zero-shot 的代价恰恰是还原度上限（单条参考 vs 47 分钟全量 SFT）和方言能力（全部候选的 zero-shot 都不认识上海话）。**"省人工"与"最像她"目前是直接对立的**。
3. VoxCPM2 的"1-3 epoch 即收敛"与 GPT-SoVITS 的"默认轮数可用"说明闸门 ② 有真实的压缩空间——反观现役方案的 15 epoch 盲选流程，可借鉴收紧（如只出 e2/e8/e14 三候选）。

---

## 五、沪语/吴语生态 2026-08 扫描

1. **SS 变体仍未放出**：直查 HF 文件树，ASLP-lab/WenetSpeech-Wu-Speech-Generation 仍只有 5 个 checkpoint（基座/CPT/SFT/instruct-emotion/instruct-prosody），全部 2026-01 后零更新。GitHub 榜单列了 SS SFT 成绩（Easy CER 5.42% / SIM 0.727）但无权重下载——与我们 2026-02 结论一致，**只有榜单数字，没有可用权重**。
2. **现役底座无升级目标**：Wu 系全线自 2026-01 起冻结；数据集与 Bench 正常在线。ASLP-lab 组织本身活跃，2026-08 新入库 **CN-MultiDialect-ASR（2B 多方言 ASR）**——不是 TTS，但可作为我们合成结果的自动 CER 质检工具候选（值得单独评估，可能替代部分人工筛选）。
3. **Fun-CosyVoice3-0.5B-2512**（2025-12，Apache-2.0）：**目前唯一官方宣称含上海话的通用开源克隆模型**（18+ 方言/口音，instruct 路线"用上海话说"）。CLAUDE.md 旧备注"主选"指的就是它。注意"克隆音色 × 方言指令"能否同时成立官方未保证——若 VoxCPM2 A/B 排期，它应作为第三组一起测（成本增量小，同一盲听页）。
4. **DiaMoE-TTS**（清华+巨人网络，F5-TTS 系 + IPA 前端 + 方言 MoE）：新闻稿称上海话在计划中，实际 checkpoint 无上海话，且 2025-10 后零更新——不可用。
5. **带口音普通话**（泛化轴 3 相关）：2026 年仍以论文为主。最相关是 **Joycent**（arXiv 2606.16417，扩散式 accent TTS，参考音频携带口音），思路与我们"她说什么话就让她说什么话"同向，权重开源未核证。产品侧最接近的现成能力是 Fun-CosyVoice3 的 instruct 口音路线。**我们自己的发现（SFT 后裸文本=本人口音的双语域现象）在公开研究里尚无对应物**，这是可分享的一手经验。

---

## 六、App 化视角：一键管道的可行边界

> 呼应产品化设想（Windows App 内自动化整套 pipeline）。本节回答：语音层的哪些环节能全自动、哪些必须留人工闸门。

### 6.1 产品应做成两档，而不是一档

维度 9 的数据揭示了一个清晰的产品结构——**"省人工"与"最像"是一条光谱的两端**，应做成用户可选的两档：

| | ⚡ 快速档（zero-shot） | 💎 精修档（微调） |
|---|---|---|
| 底座候选 | IndexTTS2.5（免转写）/ VoxCPM2 Controllable | 现役 Wu-SFT 工艺 / GPT-SoVITS（普通话）/ VoxCPM2 LoRA |
| 用户等待 | **分钟级**：上传素材→自动选段→出声 | 小时级：校对→训练→试听→筛选 |
| 人工参与 | 仅两处：确认参考片段 + 听成品 | 全套三闸门 |
| 还原度上限 | 单条参考片段决定，窄带素材下折扣明显 | 全量数据吃进去，现役已验证的高上限 |
| 方言 | ❌ 全部候选 zero-shot 均不识上海话 | ✅ 唯一路径（需吴语底座） |
| 适用 | 试用期/普通话对象/让用户先"听到可能性" | 正式建档 |

快速档的产品意义不是质量，是**转化**：让用户十分钟内听到亲人声音的雏形，再决定是否投入精修档的校对劳动。这是纯商业逻辑之外的伦理优势——用户在投入大量情感劳动前先验货。

### 6.2 全自动化清单（工程视角）

**可全自动**（所有底座通用）：格式转换/重采样、VAD 切分、SNR/DNSMOS 打分选参考段、静音裁剪（VoxCPM2 的 <0.5s 尾静音规则可脚本化）、音量归一化、ASR 初转写、训练启动与监控（现役 Start-Process 脱钩+Monitor 工艺直接复用）、批量合成、**长度类坏例自动重试**（VoxCPM2 retry_badcase 已内建；其他底座可自建 ASR 回读 CER + 说话人相似度双指标过滤——ASLP-lab 新出的 CN-MultiDialect-ASR 是方言场景的质检器候选）。

**必须留人工闸门**（模型选型改变不了）：

1. **方言转写校对页**——ASR 对上海话 40% 错误率是素材属性；自动管道在方言素材上会**静默产出劣质模型**，校对页是防线不是负担。普通话素材可降级为抽检模式（GPT-SoVITS 官方口径背书）。
2. **checkpoint 试听页**——所有开源微调线都无官方验证指标（"loss 与感知质量不总相关"是 VoxCPM2 官方原话）。可自动生成各 epoch 固定测试句样本降低成本，人耳终审保留。
3. **成品盲听页**——铁律层面的要求，且是 Tier 纪律在语音层的体现。
4. **同意闸门**（泛化轴 1）——活人对象需本人同意；Grok Voice 的活体验证设计说明行业合规正走向强制化，我们提前内建是合规资产。

**结论：我们现有的校对页、试听页、盲听页不是管道还没自动化的临时脚手架，而正是产品的核心组件**——大厂一键克隆（Grok 2 分钟出声）恰恰因为砍掉这些闸门而做不了方言、做不了逝者、做不了"确认这真的像她"。三个 HTML 闸门页 + 中间全自动的管道，就是这个产品在 skill/App 形态下的正确形状。

### 6.3 对泛化轴 3（语音泛化）的选型矩阵更新

维度 8/9 数据补全后，voice_profile 参数化选型可以落成：

| 对象语言 | 快速档 | 精修档 | 校对负担 |
|---|---|---|---|
| 上海话/吴语 | ❌ 无可用 zero-shot | CosyVoice2-Wu-SFT（唯一） | 高（逐条） |
| 普通话（含口音） | IndexTTS2.5 / VoxCPM2 | GPT-SoVITS v2Pro（1 分钟起训，6-8GB 卡即可——**大幅降低用户硬件门槛**）或现役工艺 | 低（抽检） |
| 粤语 | VoxCPM2 / dots.tts zero-shot | GPT-SoVITS（官方 'yue' 支持） | 中 |
| 英文等外语 | 全部候选可用 | GPT-SoVITS / VoxCPM2 LoRA | 低 |
| 其他方言 | 视 VoxCPM2 方言大类覆盖 | Fun-CosyVoice3 instruct 路线试探 | 高 |

注意 GPT-SoVITS 6-8GB 即可微调这一点对产品化意义重大：**精修档不必绑定 4090 级硬件**，普通话用户在主流游戏本上就能跑通全管道。

---

## Sources

主轮 60+ 信息源分散在各模型小节的研究代理产出中，关键一手来源：

- [OpenBMB/VoxCPM](https://github.com/OpenBMB/VoxCPM) · [VoxCPM2 微调文档](https://voxcpm.readthedocs.io/en/latest/finetuning/finetune.html) · [第三方 vs ElevenLabs 评测](https://medium.com/@tentenco/voxcpm2-the-open-source-voice-model-that-beats-elevenlabs-on-similarity-but-the-full-benchmark-ffe408b50b87)
- [index-tts/index-tts](https://github.com/index-tts/index-tts) · [IndexTTS-2.5 技术报告](https://arxiv.org/pdf/2601.03888) · [INDEX MODEL LICENSE](https://github.com/index-tts/index-tts/blob/main/LICENSE)
- [RVC-Boss/GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS) · [4090 RTF 基准 issue #2579](https://github.com/RVC-Boss/GPT-SoVITS/issues/2579)
- [rednote-hilab/dots.tts](https://github.com/rednote-hilab/dots.tts) · [dots.tts-soar](https://huggingface.co/rednote-hilab/dots.tts-soar)
- [QwenLM/Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) · [阿里云声音复刻文档（vc 线语言清单）](https://help.aliyun.com/zh/model-studio/qwen-tts-voice-cloning)
- [xAI Custom Voices（活体同意验证）](https://x.ai/news/grok-custom-voices) · [xAI TTS/STT API](https://x.ai/news/grok-stt-and-tts-apis)
- [WenetSpeech-Wu HF 文件树（SS 未放出的直接证据）](https://huggingface.co/ASLP-lab/WenetSpeech-Wu-Speech-Generation/tree/main) · [Fun-CosyVoice3-0.5B-2512](https://huggingface.co/FunAudioLLM/Fun-CosyVoice3-0.5B-2512) · [Joycent](https://arxiv.org/abs/2606.16417)

维度 8/9 补充轮关键来源：

- [VoxCPM 微调 FAQ（尾静音/exact-match 转写/1-3 epoch）](https://voxcpm.readthedocs.io/en/latest/finetuning/faq.html) · [usage guide（5-30s 参考区间）](https://voxcpm.readthedocs.io/en/latest/usage_guide.html) · [retry_badcase 实测 issue #209](https://github.com/OpenBMB/VoxCPM/issues/209)
- [GPT-SoVITS 版本特性 wiki（v2Pro 对音质宽容的官方口径）](https://github.com/RVC-Boss/GPT-SoVITS/wiki/GPT%E2%80%90SoVITS%E2%80%90features-(%E5%90%84%E7%89%88%E6%9C%AC%E7%89%B9%E6%80%A7)) · [官方语雀教程](https://www.yuque.com/baicaigongchang1145haoyuangong/ib3g1e)
- [dots.tts 技术报告（有效带宽估计过滤）](https://arxiv.org/html/2606.07080)
- [Qwen3-TTS /finetuning 目录](https://github.com/QwenLM/Qwen3-TTS/tree/main/finetuning) · [sruckh 社区一键微调管道](https://github.com/sruckh/Qwen3-TTS-finetune)
- [IndexTTS2 论文（情绪参考可来自他人声音）](https://arxiv.org/pdf/2506.21619)

*2026-08-17 首版，十维度完整（主轮 6 模型代理 + 沪语生态扫描 + 维度 8/9 补充轮 5 代理，共 12 个研究代理、100+ 信息源）。*
