# 本地照片→卡通头像 技术方案调研（2026-08-11）

> 背景：4e 形象升级——用户反馈现有 SVG 形象"太卡通"，要求根据妈妈照片生成保留特征的风格化卡通头像。硬约束：**全程本地运行（铁律 3，照片不出本机）**、非写实真人脸、许可证允许个人使用。调研由后台 research agent 完成（WebSearch/WebFetch 核实）。

## 候选核实结果

| 方案 | 现状 | 许可 | 评价 |
|---|---|---|---|
| **photo2cartoon** (minivision-ai) | 仓库在、权重（2020 年 Google Drive）仍可下 | 代码 MIT | 技术栈太老（Python 3.6 / TF1.14 / PyTorch1.4 / dlib），Win11+Py3.10 装起来冲突大；单一固定风格，无法迭代。**不推荐** |
| **AnimeGANv3 portrait** | 活跃（2025 仍有更新），配套 `AnimeGANv3_Portrait_Inference` 仓库 + Windows exe | 非商用免费（个人使用 OK），部分风格（Ghibli/油画）Patreon 付费 | ONNX 推理，onnxruntime 即跑，几乎零依赖冲突；Disney/USA/Kpop 等风格；缺点：确定性输出、不可控、不可挑选。**适合快速出基线** |
| **SDXL + InstantID / IP-Adapter FaceID + 卡通 LoRA** | ComfyUI 节点均在维护 | InsightFace 预训练模型**仅限非商用**（个人 OK） | likeness 好、风格靠 LoRA 可换，可无限抽卡；安装中等复杂（insightface 在 Windows 需预编译 wheel） |
| **PuLID-FLUX** | 在维护，代码 Apache | 依赖 FLUX.1-dev 权重（非商用许可，个人 OK） | 身份保持最强，但会"抗拒"极端卡通化，风格化可控性反而弱 |
| **FLUX.1 Kontext dev**（2025-06，12B 编辑模型） | ComfyUI/diffusers 官方支持，4090 实测可跑 | 非商用许可（个人 OK） | 自然语言指令编辑，"变成卡通"一句话，身份保持好 |
| **Qwen-Image-Edit-2509**（2025-09，20B） | HuggingFace 官方权重 + ComfyUI 官方模板 | **Apache 2.0**（最干净） | 官方文档明确擅长"照片→迪士尼式卡通头像"，人脸一致性是其主打改进；fp8 量化适配 24GB，GGUF 更省；换 seed/换 prompt 无限迭代挑选 |

## 推荐排序

1. **首选：Qwen-Image-Edit-2509（ComfyUI）**——许可最干净、likeness 与卡通化可控性兼得、自然语言调风格、可批量抽卡
2. **备选：FLUX.1 Kontext dev**——同样一句话编辑，12B 更轻，风格略不同可对照
3. **快速基线：AnimeGANv3 portrait ONNX**——半小时内出图，用来和扩散方案盲比
4. InstantID/PuLID 仅在需要特定卡通 LoRA 画风锁定时再上

## 首选落地步骤

1. **不动现有 venv**（torch 2.3.1 太老）。装 ComfyUI Windows Portable（自带独立 Python + 新 torch），解压即用
2. 权重（已核实确切路径，Comfy-Org 整理版）：
   - `Comfy-Org/Qwen-Image-Edit_ComfyUI` → `split_files/diffusion_models/qwen_image_edit_2509_fp8_e4m3fn.safetensors` → `models/diffusion_models/`（约 20GB）
   - `Comfy-Org/Qwen-Image_ComfyUI` → `split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors` → `models/text_encoders/`
   - `Comfy-Org/Qwen-Image_ComfyUI` → `split_files/vae/qwen_image_vae.safetensors` → `models/vae/`
3. ComfyUI → Templates → Qwen Image Edit 2509 官方工作流，载入照片
4. Prompt 方向："温暖手绘卡通头像，保留脸型/发型/神态特征，非写实插画风格"；批量换 seed 生成 10-20 张供用户挑选
5. 24GB 吃紧时换 City96 GGUF Q5/Q4 量化版

Sources: photo2cartoon (github.com/minivision-ai/photo2cartoon) · AnimeGANv3 (github.com/TachibanaYoshino/AnimeGANv3) · AnimeGANv3_Portrait_Inference · IP-Adapter-FaceID/InstantID 许可讨论（HF discussions）· FLUX.1-Kontext-dev (HF) · Qwen-Image-Edit-2509 (HF) · stablediffusiontutorials.com Qwen 量化/VRAM 指南
