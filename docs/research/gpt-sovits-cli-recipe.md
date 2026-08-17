# GPT-SoVITS v2Pro 整合包 CLI 化配方（盘上代码逐行核对）

> 2026-08-18 产出（Explore 代理深挖 75 次工具调用，全部结论带盘上代码行号证据，零猜测）。
> 目的：绕开 WebUI，把 v2Pro 微调全链路做成纯 CLI 管道（Phase 6 / 任务 #14 的 spec 素材）。
> 代码根 `R = C:\Users\justin\gpt-sovits\GPT-SoVITS-v2pro-20250604`，Python = `R\runtime\python.exe`（3.9.13 embeddable，torch 2.0.0+cu118，CUDA 可用）。

## 0. 先决条件（最容易翻车，必须先解决）

### 0.1 runtime python 是 embeddable 版，PYTHONPATH 被忽略

- `R\runtime\python39._pth` 存在 ⇒ 隔离模式：`PYTHONPATH`/`PYTHONHOME` 全被忽略，脚本所在目录也不进 `sys.path`（实测确认）。
- 各预处理/训练脚本依赖仓库根/GPT_SoVITS/tools 在 `sys.path`（1-get-text.py:20,22 / 3-get-semantic.py:38,41 / s2_train.py:6,27-39）。
- 唯一生效机制 = `webui.py:38-58` 启动时写 `runtime\Lib\site-packages\users.pth`（6 行）。**当前盘上 users.pth 还是打包机旧路径 `D:\BaiduNetdiskDownload\...`（site 静默丢弃）**。
- **管道硬性要求（二选一）**：
  1. 把 `users.pth` 重写为当前 R 的 6 行绝对路径：`R`、`R\GPT_SoVITS\BigVGAN`、`R\tools`、`R\tools\asr`、`R\GPT_SoVITS`、`R\tools\uvr5`；或
  2. 注入式启动：`runtime\python.exe -s -c "import sys;sys.path[:0]=[...];exec(compile(open(script,'rb').read(),name,'exec'))"`（脚本不用 `__file__`，可安全 exec）。

### 0.2 其它环境要求

| 项 | 证据 | 说明 |
|---|---|---|
| CWD 必须是 R | 2-get-hubert-wav32k.py:26-27、2-get-sv.py:23-25、sv.py:5-6、3-get-semantic.py:35-36 用 os.getcwd()；预训练模型全是相对路径 | 所有命令先 cd R |
| PATH 需含 R\runtime | go-webui.bat:4；ffmpeg/ffprobe 在 runtime 下；tools/my_utils.py:16-37 load_audio 走 ffmpeg CLI | 否则 1b/训练读音频全挂 |
| 目录预建 | webui.py:200-201、webui.py:516 | `logs\<exp>\logs_s2_v2Pro`、`SoVITS_weights_v2Pro`、`GPT_weights_v2Pro` |
| 子进程一律 `python.exe -s` | webui.py:808,898,920,992,542,636 | 照抄 |

## 1. 训练集标注 .list 格式

- **每行 4 字段 `|` 分隔，无表头，UTF-8**：`<wav名或绝对路径>|<说话人名>|<语言码>|<文本>`（1-get-text.py:129 / 2-get-hubert-wav32k.py:114 / 2-get-sv.py:104 / 3-get-semantic.py:110 各自独立 split 一致）。
- **语言码白名单**（1-get-text.py:110-126 唯一权威）：ZH/zh→zh、JP/jp/JA/ja→ja、EN/en/En→en、KO/Ko/ko→ko、yue/YUE/Yue→yue。不在表内 ⇒ warning + 跳过该行（1c 仍会算特征，最后被交集丢弃）。
- 第 2 字段 spk_name 全链路**从未被使用**，随便填。
- wav 路径：设 `inp_wav_dir` 时取 basename 拼接；`inp_wav_dir` 留空时第 1 字段须绝对路径（2-get-hubert-wav32k.py:116-122）。**basename 是全链路主键，必须全局唯一（含扩展名）**（3-get-semantic.py:111-112、1-get-text.py:89-90 无条件取 basename）。
- **采样率无硬检查**：任意 wav，ffmpeg 统一解码 32k 单声道 f32（tools/my_utils.py:24-28）。
- **静默丢弃的硬检查**：
  - 幅度 >2.2 过滤（2-get-hubert-wav32k.py:84-86）
  - s2 时长过滤 **0.6s < dur < 54s**（module/data_utils.py:88-101）
  - s1 semantic >1350 token（≈54s）丢、音素 >540 丢、语速比 phone/sec 必须在 [3,25]（AR/data/dataset.py:145-173）
  - 有效样本 <100 自动复制到 ≥100（data_utils.py:55-59、dataset.py:179-188）
- **实操区间：每段 1-10s（硬边界 0.6-54s，官方切分口径 ≥4s），总数 ≥100 免复制**。（mama 160 条 4.7-27.9s 全部合法 ✓）

## 2. 预处理三步（1a / 1b(+sv) / 1c）——全部环境变量传参，无 CLI 参数

webui 的做法：`os.environ.update(config)` + `Popen(cmd, shell=True)`（webui.py:807-810 等）；`webui.py:4` 全局 `os.environ["version"]="v2Pro"`。

### 环境变量总表（v2Pro 取值）

| 变量 | 1a | 1b | 1b-sv | 1c | 取值 |
|---|:-:|:-:|:-:|:-:|---|
| inp_text | ✔ | ✔ | ✔ | ✔ | .list 绝对路径 |
| inp_wav_dir | ✔ | ✔ | ✔ | — | 切片 wav 目录；留空则 list 用全路径（1c 不读） |
| exp_name | ✔ | ✔ | ✔ | ✔ | 实验名 |
| opt_dir | ✔ | ✔ | ✔ | ✔ | `logs/<exp_name>` |
| bert_pretrained_dir | ✔ | — | — | — | GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large |
| cnhubert_base_dir | — | ✔ | — | — | GPT_SoVITS/pretrained_models/chinese-hubert-base |
| sv_path | — | — | ✔ | — | GPT_SoVITS/pretrained_models/sv/pretrained_eres2netv2w24s4ep4.ckpt |
| pretrained_s2G | — | — | — | ✔ | GPT_SoVITS/pretrained_models/v2Pro/s2Gv2Pro.pth |
| s2config_path | — | — | — | ✔ | **GPT_SoVITS/configs/s2v2Pro.json** |
| is_half | ✔ | ✔ | ✔ | ✔ | `"True"`（脚本 eval()，须 Python 字面量） |
| i_part / all_parts | ✔ | ✔ | ✔ | ✔ | 单卡 `"0"` / `"1"` |
| _CUDA_VISIBLE_DEVICES | ✔ | ✔ | ✔ | ✔ | `"0"` |
| version | (✔) | — | — | — | `"v2Pro"`（1a 传给 clean_text） |

### 产出物与合并（⚠️ 合并逻辑在 webui 层，CLI 必须自己做）

| 步骤 | 脚本 | 产出 |
|---|---|---|
| 1a | 1-get-text.py | `2-name2text-<i>.txt`（tab 4 列）+ `3-bert/<name>.pt`（仅 zh）→ **自行合并为 2-name2text.txt（无表头）**（webui.py:819-827） |
| 1b | 2-get-hubert-wav32k.py | `4-cnhubert/<name>.pt` + `5-wav32k/<name>`（32k int16） |
| 1b-sv | 2-get-sv.py | `7-sv_cn/<name>.pt`（[1,20480]）——**v2Pro 必跑，漏跑 s2 启动即崩**（data_utils.py:35 assert） |
| 1c | 3-get-semantic.py | `6-name2semantic-<i>.tsv` → **自行合并 + 加表头行 `item_name\tsemantic_audio`**（webui.py:1003-1011；缺表头会吃掉首条样本 AR/data/dataset.py:57-61） |

- 1c 的 version 按 s2G 文件大小猜（3-get-semantic.py:18-28），s2Gv2Pro.pth 落 v2 分支 + strict=False——**正常行为不要修**。

## 3. SoVITS 训练（s2）

- **v2Pro 走 `GPT_SoVITS/s2_train.py` 全参微调（非 LoRA）**（webui.py:541-544）；lora_rank/grad_ckpt 字段写进 config 但 s2_train 不读。
- config：模板 `GPT_SoVITS/configs/s2v2Pro.json`（对 s2.json 差异仅 p_dropout 0.1→0.0、gin_channels 512→1024；ProPlus 再改 upsample 两项），覆写字段落 `TEMP/tmp_s2.json` 后 `--config` 传入。
- 覆写字段（webui.py:512-540）：train.fp16_run=true / batch_size=12 / epochs=8 / text_low_lr_rate=0.4 / pretrained_s2G+s2D（v2Pro 对）/ if_save_latest=true / **if_save_every_weights=true（否则不产可推理权重）** / save_every_epoch=4 / gpu_numbers="0" / **model.version="v2Pro"（决定 sv 分支）** / data.exp_dir=s2_ckpt_dir=logs/<exp> / save_weight_dir=SoVITS_weights_v2Pro / name=<exp>。
- **GPU 由 config 的 train.gpu_numbers 决定**（s2_train.py:9），非外部环境变量；Windows DDP 强制 gloo（s2_train.py:81）。
- 产物：训练态断点 `logs/<exp>/logs_s2_v2Pro/G|D_*.pth`（if_save_latest=1 固定名 233333333333 覆盖）；**可推理小权重 `SoVITS_weights_v2Pro/<name>_e<E>_s<S>.pth`**（半精度、剔 enc_q、内嵌 config；**首 2 字节魔数 b"05"**=版本标识，process_ckpt.py:30-38）。
- 自动 resume：logs_s2_v2Pro 里有 D_*/G_* 就续训（s2_train.py:206-221）——**换 exp 名或清目录 = 从底模重开**。

## 4. GPT 训练（s1）

- 脚本 `GPT_SoVITS/s1_train.py --config_file TEMP/tmp_s1.yaml`；模板 **`GPT_SoVITS/configs/s1longer-v2.yaml`**（v2/v2Pro/v3/v4 共用，webui.py:604-608）。
- 覆写字段（webui.py:613-627）：train.precision=16-mixed / batch_size=12 / epochs=15 / **pretrained_s1=GPT_SoVITS/pretrained_models/s1v3.ckpt（顶层）** / save_every_n_epoch=5 / if_save_every_weights=true / if_save_latest=true / if_dpo=false（开了 batch 折半）/ half_weights_save_dir=GPT_weights_v2Pro / exp_name / train_semantic_path=logs/<exp>/6-name2semantic.tsv / train_phoneme_path=logs/<exp>/2-name2text.txt / output_dir=logs/<exp>/logs_s1_v2Pro（均顶层）。
- 环境变量唯二：`_CUDA_VISIBLE_DEVICES="0"`（必须，Trainer devices=-1 吃全部可见卡）+ `hz="25hz"`。
- 模板不动的关键项：seed 1234、lr 0.01/warmup 2000、**data.max_sec 54**（同时是 s1 过滤阈值，会内嵌进 ckpt 推理时读出）。
- 产物：**`GPT_weights_v2Pro/<exp>-e<E>.ckpt`**（半精度 + 内嵌 yaml config，无魔数头）；Lightning 断点在 logs_s1_v2Pro/ckpt 自动 resume。

## 5. 微调后推理（api_v2 热切换）

- `TTS_Config` 只读 yaml 的 **custom 段**（TTS.py:318）。⚠️ **每次装载权重会把状态回写 yaml custom 段（TTS.py:377-385,590,597）——配置文件是有状态的**，管道要意识到（我们的 workdir/tts_infer_v2pro.yaml 已被回写过一次=实证）。
- 热切换**零特殊处理**：`GET /set_sovits_weights?weights_path=SoVITS_weights_v2Pro/<name>_e8_s1234.pth` + `GET /set_gpt_weights?weights_path=GPT_weights_v2Pro/<exp>-e15.ckpt`。
- 版本自动识别链：前 8192 字节 md5 匹配底模表 → 不中则读首 2 字节 b"05" ⇒ ["v2","v2Pro",False]（process_ckpt.py:100-126）→ `"Pro" in version` ⇒ 自动加载 sv 模型（TTS.py:495-497）——**sv 路径硬编码相对路径（sv.py:6），api 进程 CWD 必须是仓库根**。
- 推理期 sv：参考音频重采 16k → sv_emb → SynthesizerTrn.decode(sv_emb=...)（TTS.py:801-804,1259-1264）；切版本后缓存自修复（TTS.py:1134）。
- v2Pro 不涉及 vocoder/超分（v3/v4 专属）。`inference_cli.py` 是老接口中文字面量参数，**不用**。

## 6. 默认值 / 显存（4090 24GB 实测 mem_gb=24.39）

| 项 | 值 |
|---|---|
| s2 batch 默认 / 上限 | **12** / 36（webui.py:119,136） |
| s2 epoch 默认 / 上限 | **8** / 25（代码注释：v2 类"训太多=作死"） |
| s2 text_low_lr_rate | 0.4（范围 0.2-0.6） |
| s1 batch 默认 / 上限 | **12** / 40 |
| s1 epoch 默认 / 范围 | **15** / 2-50 |
| s1 save_every | 5 |
| is_half | True（sm 8.9） |
| 小数据集自动缩 batch | batch=max(min(batch, len//4),1)（data_module.py:50） |

## 7. 内置工具（格式对齐点，我们已有切段+校对转写，基本不用）

- slice：`tools/slice_audio.py` 位置参数 11 个（inp, opt_root, -34, 4000, 300, 10, 500, 0.9, 0.25, i, n）；输出 32k int16 单声道，官方口径每段 ≥4s。
- denoise：`tools/cmd-denoise.py -i -o -p`（-p 未接入）；modelscope frcrn 16k。
- ASR：`tools/asr/funasr_asr.py -i <dir> -o <dir> -s large -l zh|yue -p float32`——**输出即 .list**（`完整路径|文件夹名|大写语言码|text`）。注意 funasr 也支持 **yue**（粤语 QC 候选）。
- 校对 GUI：tools/subfix_webui.py --load_list（我们有自建校对页，不用）。

## 8. 全链路最小 CLI 清单（spec 摘要）

```
前置：cwd=R；PATH 前置 R\runtime；重写 users.pth（6 行绝对路径）；预建 logs\<exp> 等目录
1a  env{version,inp_text,inp_wav_dir,exp_name,opt_dir,bert_pretrained_dir,is_half,i_part,all_parts,_CUDA_VISIBLE_DEVICES}
    → python -s GPT_SoVITS/prepare_datasets/1-get-text.py → 合并 2-name2text.txt（无表头）
1b  env{...,cnhubert_base_dir} → 2-get-hubert-wav32k.py
1b' env{...,sv_path} → 2-get-sv.py（v2Pro 必跑）
1c  env{...,pretrained_s2G,s2config_path} → 3-get-semantic.py → 合并 6-name2semantic.tsv（加表头）
2   s2v2Pro.json → tmp_s2.json → python -s GPT_SoVITS/s2_train.py --config
    → SoVITS_weights_v2Pro/<name>_e<E>_s<S>.pth
3   s1longer-v2.yaml → tmp_s1.yaml；env{_CUDA_VISIBLE_DEVICES,hz} → python -s GPT_SoVITS/s1_train.py --config_file
    → GPT_weights_v2Pro/<exp>-e<E>.ckpt
4   api_v2.py 起服 → /set_sovits_weights + /set_gpt_weights 热切换 → /tts 合成
```

**三大坑（均有代码依据非猜测）**：①users.pth 陈旧 + _pth 隔离 ⇒ 全链 ImportError；②分片合并+tsv 表头在 webui 层，脚本不做；③v2Pro 漏跑 2-get-sv.py ⇒ s2 启动即崩。
