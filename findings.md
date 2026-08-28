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
- MP3 编码路线：soundfile + lameenc（64kbps mono），勿找 ffmpeg。**库在 cosyvoice venv**（C:\Users\justin\venvs\cosyvoice\Scripts\python.exe）；chatlog-keeper venv 与 asr venv 均没有（2026-08-10 实测）

## Codex 审核可靠性（2026-08-12 第二次实证）
- **Codex 读含 CJK 的文件会产生"语法错误/字符串未闭合"类误报**（scrub_sensitive.py 的 ⏎ 字符与 sensitive_patterns.json 的中文 regex 被判"unterminated string"，py_compile+json.load 双双实证不成立；08-12 上午 make_contact_sheet 已发生过一次）。对策已固化：①凡 Codex 报语法类 BLOCKER，先本机 py_compile/json.load 实证再回炉；②给 DeepSeek 的源码尽量用 \uXXXX 转义替代裸特殊字符；③给 Codex 的复审 prompt 明确要求"跑命令验证，勿目测"（实测有效：复审时 Codex 自跑命令撤回了两条误报）
- Codex read-only sandbox 下 `python -m py_compile` 会因写 __pycache__ 报 Permission denied——它改用了无写盘 parse 验证，说明复审 prompt 给验证方式留余地是对的

## 敏感扫描存量（2026-08-12，删除 14 条后）
- 全量 scan：21249 条记录命中 601 疑似（high 273/medium 50/low 278），报告 people/mama/normalized/sensitive_scan_report.{jsonl,md}
- high 里大头是 password/account 关键词与 16-19 位连续数字（含大量误报如淘宝单号），须人工复核，3d 闸门页对命中候选默认剔除

## 音频产物验收盲区（2026-08-12 用户实锤）
- **make_blind_page v1 把 float32 采样字节直喂 lameenc（要 int16 PCM）→ 全部音频变强噪音+低沉"男声"，连真实录音都坏**——node --check/泄漏检查/体积检查全过，唯独没人"听"。用户预演一耳朵抓出
- 对策已固化进工具与流程：①MP3 编码一律复用 build_avatar_page.encode_mp3 的 int16 成熟模式；②凡产音频的工具内置**解码回读自检**（sf.read(BytesIO(mp3))，时长 ±10% + RMS ≥¼ 源）；③交付前跑独立 roundtrip 脚本（scratchpad/roundtrip_check.py 模板：时长零漂移=无音调偏移的判据）；④诊断口诀：连"未经处理的真实素材"都坏 → 缺陷在打包/编码层而非生成层
- 法证佐证（Codex）：坏 MP3 体积恰为正常 2 倍（float32 被当 int16 读，采样数×2）——体积比对可作快速嗅探

## Phase R 移动 review 体验（2026-08-10）
- DeepSeek 三引号拼接陷阱：让它在 Python '''模板''' 里注入占位符时，容易写出 `''' + '"' + '''` 这类产出非法 JS 的拼接——生成后必须实跑并 grep 关键 JS 行验证
- avatar_preview.html：3 条内嵌语音仅 0.10MB（24kbps mono），1MB 预算内可放 5-10 条

## GPT-SoVITS zh G2P 对沪语本字的破坏面（2026-08-18，160 条全量探测实锤）
- **崩条字：「覅」（fiao）**——g2p 拼音 fiao 不在普通话音节表，AssertionError 崩整条被 1a 的 try/except 静默吞掉：160 条丢 13 条（8%），且全是含覅的高频口语句。1a 丢条只在对账时可见（2-name2text.txt 行数 < list 行数），**预处理对账是管道必备步骤**
- **静默删字：「㑚」×23、「嗯」×4**——TextNormalizer 直接删除，norm_text 与音频错位（音频有音节、文本无对应），比崩条更隐蔽
- **对策（voice_profile.g2p_char_map 参数，mama 首例）**：覅→表（biǎo，韵母 iao 全同、唇音近，社区沪语拟音惯用）、㑚→拿（ná 声韵全同）、嗯→恩（ēn）。替换只发生在喂 G2P 的 .list 生成层，**校对转写原文不动**（Tier-2 溯源保持）
- 通过验证的沪语本字（147 条成功佐证）：侬/伊/搿/辣/汏/囡/侪/伐/廿/唻/咾/覅以外的常用本字均可过 G2P（按普通话字音，臂 C 口音映射机制的一部分）
- **1a 的 bert 特征按文件名缓存跳过（1-get-text.py:94），文本变更后缓存不失效**——同 exp 改转写重跑 1a 会留下旧文本的 bert，s1 训练在 dataset.py:234 崩 assert（bert 长度 ≠ 新 phones 数）；s2 不用 bert 不受影响。实锤过程：char_map 改 .list 后重跑 1a，147 条旧 bert 被跳过 → s1 启动即死。**对策（进 gsv 工具 spec）：凡 .list 文本有任何变更，先清 3-bert/ 再跑 1a；跑 s1 前全量对账 bert.shape[-1]==len(phones)（probe_verify_bert.py 模板）**。4-cnhubert/5-wav32k/7-sv/6-semantic 按音频算与文本无关，可安全复用

## 视觉/动画验收盲区（2026-08-25，纸片人贴片假阳性事故）
- **`style.display = ''` 不等于"显示"**：清空 inline 声明后计算样式回落 CSS 类规则——`.mouth-patch{display:none}` 把贴片吃掉，**贴片自上线起从未渲染过一个像素**，而 inline style 采样"验证"全绿（假阳性）。对策已固化（memory: verify-rendered-pixels）：①显示元素一律显式 `display='block'`；②断言用 `getComputedStyle()`；③终验做状态间**截图像素 diff**；④CSS animation 作用元素上的 inline transform 会被 animation 覆盖——transform 打到无 animation 的子元素
- **截图验收的运行时竞态**（08-27 两次假阴性）：rAF 循环每帧重写贴片 display、眨眼调度器定时翻转——evaluate 强制显示后截图会被覆写。绕法：慢放 `playbackRate=0.25` 拉长 cue 窗口抓实拍；或 cloneNode 复制一个不受运行时管的验证节点

## 任务 #20 dsh-im / 微信 iLink 关键发现（2026-08-29，workflow 11 代理）
- **微信 iLink/ClawBot = 腾讯 2026 官方个人号 Bot 协议**（GitHub Tencent verified + npm @tencent-weixin 签名 + 官方 ToS 深圳南山；端点 ilinkai.weixin.qq.com/协议 2.4.6/扫码 get_bot_qrcode/35s 长轮询/context_token≈24h）——**第三条微信路径，实质更新 messaging-channels.md + wechat-ui-automation.md 的"微信封死"结论**。绕开 UIA(#16 死于客户端无障碍关闭)与 hook 灰产(伪造注入)两死因；reply-only 硬性契合"永不主动"
- **但"官方≠可给家人用"（校核 refuted 强论断）**：iLink 是"机主控自己 agent"设计、须用户先发触发；dsh-im 脱离官方 OpenClaw 直连=未授权客户端；家人入站与 bot 聊天拓扑无据；腾讯保留随时终止+裁定"可连哪些第三方 AI"（把 iLink 指向本地 persona 是否允许存疑）
- **查你号在不在 iLink 灰度=秒级 in-app**：微信 设置>插件>ClawBot 看有无入口，**不用备弃号**（校核 refuted 了"须弃号探针"）
- **dsh-im 是连接层非大脑**：DeepSeek Harness(dsh) 的 Cordis 插件，无 LLM 推理；接 persona=写冒充 Harness Host 的本机 HTTP+WS shim（仿真 host.describe/workspace/session/带 seq 事件日志+WS mux，非"一个 /reply"那么轻）或摘 MIT 的 weixin-api.mjs 进自有网关；禁 agentPreset 塞 persona（大脑变云 LLM roleplay 违 Tier+数据出机）；禁 dsh AI Office 云中继
- **不发原生语音条（confirmed 逐文件）**：TG/WA 出站无 audio 方法、wecom 只收语音；她真声只能当文件发；发语音条=逐平台自建转码（TG/WA=opus、微信/QQ=SILK 有 pilk、企微=AMR）；ffmpeg 在盘状态待复核
- **裁决**：自用(绑自己号)=低风险 GO+顺带轴五 sessions；家人向=默认 NO-GO(第三方受众+沉浸最大化，先例=团队拒绝把逝母微信做数字分身)。企微 aibot 对家人个人微信 NO-GO。详见 docs/research/dsh-im-analysis.md

## 任务 #16 微信 UI 自动化活体探针：NO-GO 铁证（2026-08-28）
- **微信 4.1.12.26 UIAutomation 路线彻底关闭**（Claude 直写 8 个只读探针，声明在案；小号 PID 15396）。控件树恒为 3 节点空壳（1 Window+2 空 Pane，深度 1）
- 五重触发全败：①uiautomation attach 遍历 ②ElementFromPoint 坐标级命中**穿不透窗口内部**（只返回顶层 WindowControl）③SPI_SETSCREENREADER=TRUE ④**真实 Narrator 讲述人运行期间** ⑤comtypes 独立 RawViewWalker——排除全部假阴性（库封装/view 过滤/客户端不够强/窗口未激活）
- **killer_risk 命中**（研究报告预言应验）：腾讯在 4.1.9→4.1.12 间收紧"按需暴露"，即使检测到最强无障碍客户端也不暴露 Qt 控件树。社区库最高只实测到 4.1.8.29/4.1.9.35
- 连带：UIA 死 = 读（控件文本）+ 发（定位输入框）同时归零。读退路=解密 DB 轮询（4.1.11 跑通过，4.1.12 未复验）；发退路只剩坐标/OCR 最脆层
- 环境全清理：探针只读未发消息未采集正文；Narrator 关闭+SPI 复位+窗口未留置顶。三选项交用户裁决（A 放弃微信实时线[推荐]/B 降级混合方案/C TG bot）→ 见 docs/research/wechat-ui-automation.md 第六节

## 任务 #18 桌面陪伴研究关键发现（2026-08-27，workflow 14 代理 + 本机探针）
- **上海话本地 ASR 存在（原判"不存在"被校核翻案）**：DataoceanAI+清华 **Dolphin**（2025-03 开源，pip install dataoceanai-dolphin，权重 HF/ModelScope）语言表含 zh-WU/zh-SHANGHAI，厂方论文 0.4B 上海话 CER 7.81%（SenseVoice-S 吴语 20.43%）；另有含流式的 Dolphin-CN-Dialect。**未在她/用户口音上实测**——也可能是转写校对减负工具
- **CosyVoice2 流式本机实测**：现役 SFT e14 fp32 无优化，`stream=True` 首包 2.18-4.44s（方差大）；本机 cosyvoice.py:91 原生支持，tts_server.py:70 写死 stream=False，改流式=改参数+HTTP chunked。GSV api_v2 streaming_mode 首包实测 ~1.07s。Rhubarb 5.8s 音频仅 1.09s（准实时"合成完先跑再播"可行）
- **DeepSeek 思考模式陷阱**：裸 `deepseek-v4-flash` 默认开思考（首 content 实测 4.69s），须请求体加 `thinking:{"type":"disabled"}`（后 1.68s）；chat.html payload 硬编码无此项且占位符仍是已退役的 deepseek-chat（该别名实测仍通 1.69s）——两处一行级待修
- **"本地 LLM 只能 8-14B 且小模型必违 Tier"推理链被校核否决**：CosyVoice2 量化后占用可压很低、27B/30B-A3B Q4 可能挤入 24GB；Vectara HHEM 榜实证体量不决定检索忠实度（Phi-4 14B 3.7% 优于 Llama-3.3-70B 4.1%）
- **avatar/chat 两页"各持一半"实锤（代码级）**：avatar.html RMS 分支就是为动态 TTS 预留（无时间轴音频自动落入），chat.html TTS 语音条却用独立 Audio 不驱动嘴——把 :8022 MP3 blob 喂给挂 analyser 的 audio 即通，拼装级
- **伦理证据链**（详见 docs/research/desktop-companion.md 第六节）：transitory use 是 deadbot 文献唯一接近共识的安全定位；MIT×OpenAI 2025 实证日时长与孤独/依赖正相关；Replika/Soulmate 证明"知情"不是护栏——**常驻形态被判①档不应做，上限=打开才在的对话窗**
- **实物样本启发（08-27 用户提供某桌宠 app'蕾咪'截图）**：①思考模式开关被做成 UI 配置项（印证 v4-flash 默认思考坑普遍）——我方应硬编码永远关；②备用 API Key 自动切换值得抄，且我方可加独有末档：主/备端点全挂→降级纯检索回放原声+记忆（档案即降级层）；③config.json+UI 双通道配置优于纯 localStorage（清缓存丢配置）；④"如何获取 Key"引导=泛化产品 onboarding 范式；⑤**红线：其"拖图给她识图"走云端 GLM-4V——照片出机违铁律 3 绝不照搬**，合规替代=本地 VLM 或"拖图只做本地 EXIF/timeline 检索锚定、她用 Tier-1/2 真实内容回应"；⑥其常驻+输入框永在形态=我方①档"不应做"的活对照

## Rhubarb / 贴片管线坑（2026-08-26/27，Phase 1）
- **rhubarb CLI**：`--machineReadable` 与 stdout 组合拿不到 JSON（125 条全空）——必须 `-o <文件>` 输出再读文件
- **mkstemp fd 双重 close 竞态**（Windows+线程池实锤）：close 过的 fd 号被并行线程的 subprocess 管道复用，二次 close 关掉别人管道 → 全场 "Bad file descriptor"。mkstemp 后立即 close 一次，finally 只 unlink
- **RGBA 叠层烘焙数学**：RGB 必须取 raw 变体（非 comp 合成图）——叠加公式 base×(1-α)+RGB×α，若 RGB 用 comp 会二次混合出鬼影；烘焙后 alpha_composite 抽验中心像素 diff≤2
- **嘴型生成 prompt 规律**（三轮实证）：首轮必夸张（大张=喊叫、圆唇=香肠嘴）；"温和克制/嘴唇厚度颜色保持原样/不露舌头"类约束词有效；但 round 精修一轮反而更厚——模型对该画风有"厚唇先验"，两轮不收敛就回用首轮最佳而不是继续抽
- **眨眼贴片架构**：只替换双镜片内区（两矩形羽化 8），镜框 100% 底图像素——从架构上杜绝镜框漂移 artifact，三种子全部一次可用
