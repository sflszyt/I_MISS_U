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

## 来源（关键）

- https://github.com/FunAudioLLM/CosyVoice （README/requirements/issues #1046 #1078）
- https://www.modelscope.cn/models/FunAudioLLM/Fun-CosyVoice3-0.5B-2512 · 同名 HF
- https://github.com/pytorch/pytorch/blob/main/RELEASE.md （torch 2.3 ≤py3.11）
- https://github.com/OpenBMB/VoxCPM · GPT-SoVITS 社区文档
- CSDN Windows 实测教程（Matcha-TTS Gitee 镜像/wget/kaldifst 三坑）
