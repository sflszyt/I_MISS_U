# 方言 TTS 成熟度与上海话路线判定（2026-08-07 首轮 · 2026-08-08 补跑完成）

> workflow 深挖分两轮：08-07 首轮完成成熟度对比 + 商用云核查（其余 agent 因登录态掉线）；08-08 补跑完成音素强制 / 微调细节 / 模型全景三向 + 综合。**首轮的核心前提"吴语底座权重不公开"已被补跑推翻，本报告为修订后完整版。**

## 一句话结论（修订版）

**成熟度：普通话 ≫ 广东话 ≫ 上海话，断层很大——但上海话的唯一实证可听路线已经打通：CosyVoice2-Wu 全套权重 2026 年 2 月已在 HuggingFace 公开（Apache-2.0、免申请、自带 zero-shot 克隆接口）。** 路线 B 从"不可行"变为"立即可行"：零训练 1 天内可出她的上海话克隆样本进家人盲听；另新增全本地"TTS→VC 两段式"保底路线 D。

## 量化对比（回答"普通话/广东话是不是更成熟"）

| 语言 | 语料规模 | 零样本地道度 | 产品化 | 对本项目 |
|---|---|---|---|---|
| **普通话** | 海量 | CER **1.45%** / 音色相似度 **0.806**（CosyVoice2 官方基准）——已"解决" | 多个强模型（CosyVoice/IndexTTS…） | ✅ 克隆她的普通话，音色像+发音地道，**当天可落地** |
| **广东话** | **21,800h**（WenetSpeech-Yue，2025，粤语约吴语 2.7 倍）| MOS ~2.8–3.0，明显可用 | 第一梯队（Qwen3-TTS/Step-Audio/ElevenLabs 均一等支持）| ⚠️ **母亲不说粤语**——广东话版=陌生方言+她的音色，档案/情感意义弱 |
| **上海话/吴语** | **8,000h**（WenetSpeech-Wu，2026 初才出，此前几乎无大规模数据）| 零样本 MOS **1.80–2.22**（DiaMoE-TTS 实测，"不能听"级）；**但 CosyVoice2-Wu-SS 达 IMOS 4.0–4.37 / CER 5.42%** | 几乎无产品化，唯一系统性工作是 ASLP-lab 的 WenetSpeech-Wu 生态 | ✅（修订）通用模型零样本救不回（与本机实测一致），**但专用吴语底座已可得** |

关键佐证：CosyVoice2 官方论文承认**方言语音连打分器都识别不了、无可靠地道度指标**——方言是通用模型的公认弱项。上海话还额外有连读变调（tone sandhi）这层韵律工程障碍。

## 决定性新发现（2026-08-08 补跑，两个方向独立确认 + 综合复核）

### CosyVoice2-Wu 权重已公开

- 仓库：HuggingFace `ASLP-lab/WenetSpeech-Wu-Speech-Generation`（13.7 GB，2026-02 上传）。**必须用全名，短链 URL 会 401。**
- 许可：**Apache-2.0，无 gated 申请，`snapshot_download`/`huggingface-cli download` 直接可下**
- **5 个变体**：`CosyVoice2`（底座）、`CosyVoice2-Wu-SFT`、`CosyVoice2-Wu-CPT`、`CosyVoice2-Wu-SS`、`CosyVoice2-Wu-instruct-emotion`（`<|开心|>` 类标签）、`CosyVoice2-Wu-instruct-prosody`（`<|语速快|>` 类标签）
- **原生 zero-shot 音色克隆**：`inference_zero_shot(text, prompt_text, prompt_speech_16k)` + 文本加吴语标签 `<|wuyu|>`；Wu 权重以 `llm.pt` 替换方式载入 CosyVoice2 目录（README：SFT.pt 改名 llm.pt）
- 指标：CosyVoice2-Wu-SS 最佳——论文总体 CER 5.42% / IMOS 4.37；官方 demo 页难测试集 IMOS 4.04 / AMOS 3.88。决策取保守值 ≈4.0，仍碾压 DiaMoE-TTS 的 1.80–2.22
- **工程红线**：Wu 权重是 **CosyVoice2-0.5B** 底座的 llm.pt，**与已部署的 Fun-CosyVoice3 不通用**——zero-shot 与微调都必须在 CosyVoice2 代码栈上做（同 CosyVoice 仓库 + third_party/Matcha-TTS，py3.10，与现有环境同源）。参考音频按 16kHz 加载，**微信 SILK 窄带素材在此路线不吃亏**
- 附带风险：`ASLP-lab/WenetSpeech-Wu` **数据集**仓库音频本体未传完（只有 README）——对本项目影响小，模型权重仓库完整可用；微调混合数据可用 MagicHub 4.19h 上海话对话语料替代

## 三向补跑要点

### ① 音素/注音强制发音（结论：字音补丁，非根治）

- CosyVoice3 拼音 inpainting 语法（本机 `CosyVoice/example.py:94`，官方注释就叫 "hotfix"）：`给`→`[j][ǐ]`，声母 token+带调韵母 token 稀疏替换，与 zero-shot/instruct2 均兼容（可叠加，无人验证过，半天可实测）
- **硬天花板（本机 `cosyvoice/tokenizer/tokenizer.py:288-307` 实锤）**：发音 token 库是**封闭的普通话库**。上海话的全浊声母 /b d g v z/、入声喉塞尾、/ø/、ŋ 声母、尖音、吴语调值**在表示空间里没有坐标**——标注写得再对也发不出来。CosyVoice3 论文确认拼音能力来自普通话单音字替换的辅助训练集，只见过合法普通话音节
- 其他模型同一天花板或更低：IndexTTS2 只留合法普通话拼音组合；fish-speech 中文无音素输入;GPT-SoVITS 粤语靠专门 G2P+粤语数据（吴语两者皆无）；DiaMoE-TTS 是唯一真 IPA 前端但吴语零样本 MOS 1.80-2.22。**"纯输入侧标注让普通话模型说地道方言"的成功案例：零**
- 吴语 G2P 资源齐全但无现成 pip 包：Rime 词库（NGLI/rime-wugniu_zaonhe 等）+ MCPDict 上海话逐字读音可 2-3 天搭出查表式 G2P；上海话左重式连读变调 Wiktionary Module:wuu-pron 已完整编码——但算出的吴语调值递不进普通话四声表示层
- **能到**："字音大致对的普通话腔"（像认真学过上海话的北方人）；**到不了**：音系层地道。定位：B/D 全败后的兜底，先花半天手工标 3-5 句实测（顺带测零成本变体"借音字改写"，如"做啥"→"组撒"），不预投 5-8 天完整管道

### ② 微调路线细节（结论：55 分钟可用但偏少，B1 完全可操作）

- 数据量甜点：单说话人 2-3 小时舒适区；<1 小时推荐 LoRA 防过拟合（r=32 达全量约 98% 相似度、一半显存）；**混入底座数据防灾难性遗忘**——对应"她的 55 分钟 + 公开吴语数据 1:1~1:3 混合"；SFT lr 惯例 1e-5
- 窄带增强（全本地）：首选 **AP-BWE**（arXiv 2401.06387，MIT，16k→48k 预训练权重，4090 上 292 倍实时）；链路 = SILK 解码→去噪修复→AP-BWE 超分→重采样。注意 CosyVoice2 speech tokenizer 输入本来就是 16kHz，zero-shot 场景窄带损失有限，BWE 主要提升 flow/mel 侧上限与微调目标质量
- 微调实操：官方 `examples/libritts/cosyvoice2/run.sh` 全流水线（数据准备→spk embedding→speech token→Parquet→训练→模型平均）；阿里云 PAI 教程假定每卡 24GB——**4090 单卡可跑**（0.5B llm，bf16，micro batch 1-2）；官方无 LoRA,llm 就是标准 Qwen2-0.5B 可自己挂 peft
- 公开数据集：WenetSpeech-Wu 数据本体未传完；**MagicHub ASR-CShhiDiaCSC 上海话对话 4.19h**（注册可下）可作混合数据；MagicHub 10h 录音棚上海话女声 TTS 语料是 Proprietary（要商谈，不可得）；Common Voice 无吴语、KeSpeech 是官话子方言（均不可用）
- 社区现状：**无人做过公开的沪语 CosyVoice 微调**——WenetSpeech-Wu 生态太新（2026-01 论文/02 放权重），本项目大概率是最早一批个人音色适配用户，遇坑可走 README 里的邮箱/微信群直连 ASLP-lab 团队
- 她的素材需先按语种切分，只用上海话部分做方言微调

### ③ 开源模型全景补漏（结论：无其他遗漏模型；两段式 TTS→VC 是活路）

- 逐一核实排除（截至 2026-08-08）：Qwen3-TTS 开源版方言只有北京/四川话（上海话音色 Jada 仅商用 API）；IndexTTS2 官方零方言宣称（网传"22 方言"是第三方营销）；fish-speech/OpenAudio、SoulX-Podcast（川豫粤）、MOSS-TTS（31 语种无吴语）、Step-Audio、GLM-4-Voice、Spark-TTS、MegaTTS3、F5-TTS、MiniCPM-o——**全部无吴语**
- **VoxCPM2**（本项目备选，2026-04，2B，48kHz）：官方 demo 页**明确含上海话口语对话样例** + 短片段克隆——沪语能力有最新实证，值得进 A/B
- 保底源：ModelScope 达摩院 `speech_sambert-hifigan_tts_xiaoda_WuuShanghai_16k`（专门上海话固定音色，可本地离线跑）
- **两段式 TTS→VC（新路线 D）**：地道沪语源（CosyVoice2-Wu / VoxCPM2 / xiaoda）→ **Seed-VC V2 timbre-only 模式**（只换音色、保留源的口音韵律，1-30 秒参考即可，GPL-3.0，输出上限 22.05kHz）或 RVC（10 分钟以上数据训专属音色，社区"TTS+RVC 换音色"配方成熟）。机制上绕开"克隆×方言"死结；失败模式（音色不像）与 B 的失败模式（发音不地道）**互补**，适合双保险。全本地

## 路线框架（修订版）

| 路线 | 内容 | 新评级 | 变化 |
|---|---|---|---|
| **A：退普通话** | GPT-SoVITS 克隆她的普通话原声 | 兜底（不变），M1 盲听对照组 | 无 |
| **B：吴语底座**（原"押注"） | **B0** = CosyVoice2-Wu zero-shot 克隆（零训练）；**B1** = B0 之上用她 55 分钟素材（AP-BWE 增强后）本地 SFT llm 模块 | **立即可行，升为主路线** | 权重公开是决定性变化 |
| **C：CosyVoice3 + 拼音/借音字补丁** | 现有 instruct2 基线之上的输入侧标注 | **降级为补丁性兜底**（仅 B/D 全败后半天实测） | 音系天花板被本机代码实锤 |
| **D：TTS→VC 两段式（新增）** | 本地沪语源 → Seed-VC timbre-only / RVC 换她音色 | **可行，与 B 并行的保底分支** | 新路线 |

**技术可行性排序（排死）**：B0 > B1 > D > C > A。B0 零训练、1 天出样本、唯一实证 MOS ≈4.0 的沪语底座、克隆接口原生、窄带不吃亏——**没有任何理由不先做 B0**。

**M1 盲听批次建议同场放入**：B0 两变体（SS/SFT）+ D 样本 + VoxCPM2 沪语克隆 + 现有 CosyVoice3 instruct2 基线 + GPT-SoVITS 普通话对照。家人盲听是唯一有效标准不变。

## 各路线下一步第一个动作

- **B0（立即）**：`huggingface-cli download ASLP-lab/WenetSpeech-Wu-Speech-Generation --local-dir <路径>`（用全名）；CosyVoice2 代码栈（现有 CosyVoice 仓库同源）；`CosyVoice2-Wu-SS/SFT.pt` 改名 `llm.pt` 放入 CosyVoice2 目录；用 `people/mama/voice/reference/` 现有参考跑 `inference_zero_shot`，文本前缀 `<|wuyu|>`，与 CosyVoice3 基线同文本 A/B
- **B1（B0 音色不够时）**：clone `yxlu-0102/AP-BWE` 取 16k→48k 权重跑带宽扩展；素材按语种切分留上海话；微调走官方 `examples/libritts/cosyvoice2/run.sh`；混合数据注册 MagicHub 下 ASR-CShhiDiaCSC；遇坑联系 ASLP-lab
- **D（与 B0 并行）**：clone `Plachtaa/seed-vc` 用 V2 timbre-only；源=B0 生成的地道沪语，目标=她的参考片段；同批出 VoxCPM2 沪语克隆样本
- **C（仅 B/D 全败）**：MCPDict 查字音手标 3-5 句（拼音 token + 借音字两变体），instruct2 ± 标注 A/B，半天出结论
- **A（对照组）**：GPT-SoVITS 普通话克隆按原 M1 计划，无新动作

**数据铁律核查**：全部路线均为"下载模型到本地"方向，她的素材零外流；唯一涉外选项（Qwen3-TTS API 沪语音色作 D 的源）仅上传待念文本、非必需，默认不采用。

## 商用云现状（合规上走不通，仅作天花板参照）

- 唯一宣称支持上海话的 **Qwen3-TTS**：只能用**内置音色、不支持克隆**；宣称支持克隆的开源版又不列上海话——"克隆音色 × 上海话"这一格无任何一家给出可信证据。
- 火山/豆包、Azure、讯飞、ElevenLabs：上海话都只在**识别(STT)**侧，无 TTS 音色，更无跨方言克隆。
- **合规硬门槛**：中国云声音复刻要求"本人声纹核验+实名授权"，明文禁止克隆第三方/他人声音，素材须上传服务器——**已故母亲无法本人授权 + 与"people/ 永不上传外部服务"铁律直接冲突**。商用云克隆不可用。

## 来源

**首轮（08-07）**：WenetSpeech-Wu arXiv 2601.11027 · WenetSpeech-Yue arXiv 2509.03959 · DiaMoE-TTS arXiv 2509.22727 · CosyVoice2 arXiv 2412.10117 · 上海话连读变调 arXiv 2307.16199 · 阿里云/火山/Azure/讯飞/ElevenLabs 官方文档

**补跑（08-08）**：
- 权重/数据：huggingface.co/ASLP-lab/WenetSpeech-Wu-Speech-Generation · huggingface.co/datasets/ASLP-lab/WenetSpeech-Wu · github.com/ASLP-lab/WenetSpeech-Wu-Repo · demo 页 hujingbin1.github.io/WenetSpeechWu-Demo-Page-Public
- 音素路线：本机 CosyVoice tokenizer.py L288-307 / example.py L94 / common.py L41 · CosyVoice3 论文 arXiv 2505.17589 · UtterTune arXiv 2508.09767 · Wiktionary Module:wuu-pron · NGLI/rime-wugniu_zaonhe · edward-martyr/rime-yahwe_zaonhe · MaigoAkisame/MCPDict · GitYCC/g2pW
- 微调路线：AP-BWE arXiv 2401.06387 / github.com/yxlu-0102/AP-BWE · 低资源 PEFT arXiv 2603.10904 + Interspeech 2025 (kwon25) · 阿里云 PAI CosyVoice2 微调教程 · MagicHub 上海话语料页 · edward-martyr/shanghainese-tts · Vocos-BWE arXiv 2603.07285
- 全景/VC：Qwen3-TTS（qwen.ai blog + HF CustomVoice）· index-tts · fishaudio/fish-speech · Soul-AILab/SoulX-Podcast · OpenMOSS/MOSS-TTS · stepfun-ai/Step-Audio · VoxCPM2 arXiv 2606.06928 + openbmb demo 页 · Plachtaa/seed-vc · ModelScope xiaoda_WuuShanghai_16k · 知乎 RVC+MOSS-TTS 两段式实践（核查日 2026-08-08）
