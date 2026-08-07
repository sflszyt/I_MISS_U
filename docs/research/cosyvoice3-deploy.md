# Fun-CosyVoice3 部署与上海话克隆研究（2026-08-05）

> 4 agent 并行研究 + 逐条来源核验（verification 全 confirmed）。目标环境：Windows 11 原生 / RTX 4090 24GB / 驱动 591.86。

## 一、安装定案

| 项 | 结论 |
|---|---|
| 仓库 | `github.com/FunAudioLLM/CosyVoice`，**只有源码安装**（`git clone --recursive`）。PyPI 的 `cosyvoice` 包是第三方旧物（v0.0.8, 2024, py3.6-3.9），勿用 |
| Python | **必须 3.10**（README 钦点；requirements 钉死 torch==2.3.1/numpy==1.26.4，无 cp313 wheel）。本机已 winget 装 Python 3.10.11 user-scope。**conda 非必需**：历史上 conda 只为 pynini，现 requirements 已改纯 wheel 的 `wetext==0.0.4` |
| PyTorch | 钉死 `torch==2.3.1+cu121`（requirements 自带 extra-index-url）。4090(sm_89)+驱动 591.86 兼容 |
| 模型 | ModelScope/HF 同名 **`FunAudioLLM/Fun-CosyVoice3-0.5B-2512`**，约 9.75GB（llm.pt 2.02G / llm.rl.pt 2.02G / flow.pt 1.33G / flow onnx 1.33G / tokenizer onnx ×2 各 969M / hift 83M / campplus 28M）。国内 `modelscope.snapshot_download` |
| 加载 | `from cosyvoice.cli.cosyvoice import AutoModel; cosyvoice = AutoModel(model_dir=...)`，模型卡明确支持 **Shanghai（上海话）** 等 18+ 方言，Apache-2.0 |
| 显存/速度 | 第三方实测 FP16 约 3.2GB VRAM、RTF 0.72-0.82（无优化）；4090 无压力 |

### Windows 已知坑（全部有解）

1. `wget==3.2` 装不上（setuptools metadata 报错）→ 从 requirements 删掉该行
2. Matcha-TTS submodule 克隆失败 → Gitee 镜像 `https://gitee.com/sleepingOuku/Matcha-TTS.git` 手动克隆到 `third_party/`
3. `kaldifst` DLL load failed → 装 VC++ 2015-2022 x64 运行库
4. `ttsfrd` 只有 linux cp310 wheel → 不装，自动回退 wetext（官方明言默认行为）
5. Windows 平台标记默认装 CPU 版 onnxruntime==1.18.0 → ONNX 组件（speech_tokenizer/campplus）跑 CPU，整体可用（issue #1046 实测）；追求速度可从 onnxruntime-cuda-12 feed 手动装 GPU 版
6. sox 无 Windows 原生支持 → 跳过

## 二、克隆 API 定案（对本项目的直接结论）

- **zero-shot**：`inference_zero_shot(tts_text, prompt_text, prompt_wav)`。CosyVoice3 的 prompt_text 格式：`"You are a helpful assistant.<|endofprompt|>" + 参考音频逐字转写`。**prompt_text 必填且必须准**——转写错会破坏 LM 的文本-语音对齐（发音错、内容乱、prompt 泄漏进输出）。参考音频**硬上限 30s**（assert）、需 ≥16kHz（内部自动重采样 16k 给 tokenizer/说话人嵌入 + 24k 给 mel）。我们的 18s/24kHz 切片直接合规
- **上海话 instruct**：官方 instruct_list 含 `"请用上海话表达。"`。调用 `inference_instruct2(上海话文本, 'You are a helpful assistant. 请用上海话表达。<|endofprompt|>', prompt_wav)`。**注意 instruct2 模式下 instruct_text 顶替 prompt_text，不再给参考转写**。没有上海话语言标签（`<|yue|>` 仅粤语）
- **跨方言 A/B**：官方只有 zh↔en 跨语言数据（音色相似度 0.674/0.664 vs 同语言 ~0.77），跨语言确掉音色；沪→普通话属中文内部，预期损失更小但无官方数据——**必须自行盲听验证**（呼应 CLAUDE.md：掉音色就尊重素材语言）
- **窄带参考**：SILK 24kHz 解码音过 ≥16k 检查没问题；但 24k mel 路径会把窄带痕迹复刻进输出（音色偏闷）。可选增强：阿里官方 ClearerVoice-Studio（48k 增强+带宽扩展）做预处理后再克隆——留作 A/B 变量
- 合成文本若比 prompt 文本短，官方有效果差的运行时警告——测试句别太短

## 三、备选方案核查

- **VoxCPM2**（OpenBMB/VoxCPM，2026-04，2B，Apache-2.0）：30 语言含**吴语**（未单列上海话），双档克隆（Controllable/Ultimate），4090 RTF≈0.13；无 Windows 专项文档（pip + py3.10-3.12 + CUDA≥12）。**有意义的 fallback**
- **GPT-SoVITS**（v2Pro 当前推荐，MIT）：Windows 整合包最省事，但语言仅中/英/日/韩/粤——**无吴语前端，上海话克隆不适用**，只按原定位做普通话对照组
- 结论：Fun-CosyVoice3 仍是上海话唯一明确主选

## 四、本机部署实况（随进度更新）

- Python 3.10.11（winget user-scope）✅ 2026-08-05
- 仓库克隆 → `C:\Users\justin\CosyVoice`
- 模型下载 → `C:\Users\justin\CosyVoice-models\Fun-CosyVoice3-0.5B`（modelscope，借 ASR venv）
- venv → `C:\Users\justin\venvs\cosyvoice`（py3.10）
- 参考音频：`people/mama/voice/reference/ref03_clip18_*.wav`（主参考，18s/24kHz，用户选定）；prompt_text 待用户校对 ASR 草稿
- ASR 草稿环境：`C:\Users\justin\venvs\asr`（funasr 1.4.1 + SenseVoiceSmall，CPU）

## 五、上海话地道度调优指南（2026-08-05 二次研究 + 首轮 A/B 实测结论）

**首轮实测**：instruct2 音色"非常像"但发音不地道（用户判定）；zero-shot（未校对 ASR 草稿 + 病中参考）"发音怪、内容漂"，明显更差。

**根因判定：发音不地道主要是工程问题（输入质量），非模型天花板。** 依据：
- CosyVoice3 论文（arXiv 2505.17589 Fig 3b）确认上海话在预训练数据里真实存在（非仅 instruct 标签），但属长尾低资源方言，无单独地道度指标
- CSDN 对 CosyVoice2 方言实测：上海话"声韵母基本对，但普通话腔重/像播音腔，缺连读变调与慢节奏"——机制性普遍现象
- instruct2 的方言标签是弱引擎（风格微调），不是可靠方言引擎；zero-shot 才是正路，但地道度高度依赖 ①参考音是否纯上海话 ②转写是否用吴语本字

**最高杠杆改善清单（按性价比，先修输入再 A/B）**：
1. **校对 ASR 转写**（最高杠杆）：18s 草稿逐字改对 → 消掉 zero-shot"内容漂"。纯人工 10 分钟
2. **转写改吴语本字**：侬/伐/勿/辰光/晓得/物事/搿 等本字替换普通话近似字，prompt_text 与目标文本都用 → 触发正确读音、减普通话腔
3. **换掉病中参考**：从健康期素材挑纯上海话/干净/5-8s 完整句/语速自然的参考，宁短要纯（也符合档案伦理：不把病态固化为她的声音）
4. **A/B/C 盲听矩阵**（修好输入后才做）：A=上海话参考 zero-shot+吴语本字文本；B=同 A 但文本用普通话近似字；C=instruct2+参考音。家人盲听定位决定因素
5. **Pronunciation Inpainting**（CosyVoice3 新增，拼音/音素级）：逐字纠被读成普通话音的关键字（入声、连读变调点）
6. **instruct2 叠加**：指令 + 纯上海话参考 + 吴语本字文本三杠杆合并，可能拿"音色最像 + 发音更地道"的合并解

**不要在脏输入上跑 A/B**（会得误导性结论）。执行序：1+2+3 修输入 → 4 定位 → 5+6 精修。

**VoxCPM2 备选决策**：现在不切。触发条件=清单 1-6 全做完 + 盲听仍判普通话腔 + Inpainting 救不动。VoxCPM2 方言靠"文本+控制指令"驱动（非音色驱动），恰适配"参考音不理想"处境，届时值得并列 A/B；落地用第三方 Windows 便携版 `timoncool/VoxCPM2_portable` 规避 flash-attn 编译坑。预警：粤语 WER 38.58%，吴语稳定性存疑，长句需短分段多采样。

**跨方言（普通话）支线**：技术上最容易（普通话是模型强项），但**对本档案要克制**——铁律"她说什么话就让她说什么话"。仅当原素材本身是她说普通话时才合成普通话，不把上海话记忆"翻译"成普通话让她说。挑参考时"是不是上海话"优先级 > "是不是最干净"。

## 六、当前上海话基线配置（2026-08-07 暂存，instruct2）

用户 2026-08-07 决定：上海话发音 CosyVoice3 达不到地道（instruct2/zero-shot 都试过），**暂时保留 instruct2 版作为可用基线**，等方言深度研究（workflow）出结论再定是否替换/转向。可复现配置：

- 模型 `Fun-CosyVoice3-0.5B`，venv `C:\Users\justin\venvs\cosyvoice`（py3.10）
- 参考 `people/mama/voice/reference/ref01_clip18_20220731_...wav`（健康期日常，用户盲选，音色"非常像"）
- 调用 `inference_instruct2(tts_text, 'You are a helpful assistant. 请用上海话表达。<|endofprompt|>', ref01_wav)`
- **tts_text 必须连贯长句、无极短分句**（用逗号连、每段≥8字、结尾不留 3-4 字短句）——否则 zero-shot 会因 split 出 3 帧特征在 f0_predictor `kernel 4 > input 3` 崩溃；instruct2 更耐受但同样建议
- 产物存档 `people/mama/voice/baseline_instruct2_20260807/`（3 条样本 + README）
- 状态：**音色达标，发音不够地道**（普通话腔/缺连读变调），待替换

**已证伪的路线**：zero-shot（ref01 健康参考 + 用户校对转写，格式与长度坑都填平后）发音仍不地道——说明不是输入质量问题，是 CosyVoice3 对上海话的模型能力上限。下一步靠 `shanghainese-tts-deep-dive` workflow 找 CosyVoice3 之外的路线。

## 来源（关键）

- https://github.com/FunAudioLLM/CosyVoice （README/requirements/issues #1046 #1078）
- https://www.modelscope.cn/models/FunAudioLLM/Fun-CosyVoice3-0.5B-2512 · 同名 HF
- https://github.com/pytorch/pytorch/blob/main/RELEASE.md （torch 2.3 ≤py3.11）
- https://github.com/OpenBMB/VoxCPM · GPT-SoVITS 社区文档
- CSDN Windows 实测教程（Matcha-TTS Gitee 镜像/wget/kaldifst 三坑）
