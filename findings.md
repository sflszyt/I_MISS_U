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

## 任务 #21 OCR 控微信 / 微信第四路径关键发现（2026-08-29，workflow 11 代理）
- **★新事实：微信 PC 4.1.9+（2026-04-22 发布，用户 4.1.12.26 已有）首次支持发原生语音条**，麦克风按钮"按住右Alt"录音、60s 上限、松手即发——**实质更新 dsh-im/messaging-channels"PC 只能把她声音当文件发"旧结论**。自动化=keyDown/keyUp('altright')+VB-Cable 虚拟声卡把 :8022 TTS 灌进微信麦克风→发出原生语音条（虚拟线顺带消噪）。唯一 iLink 给不了的能力；**风险=微信语音低码率+AGC/降噪可能劣化她克隆音色（M1 盲听关口保的东西），待活体 A/B**
- **GitHub 有零件没成品**：真 OCR 读像素只散件——swigger/wechat-ocr(964★)只是 wxocr.dll 引擎、jxyk2007(91★)PaddleOCR 导航+发文字无语音、openclaw-agent(4.1.7.33)只读未读不回、EasyOCR 玩具(26/19★)。星最多的"视觉"框架(omni-bot 542★/ChisBread/weix)**实为解密 DB 读+OCR/YOLO 只定位点击发送**——实证 #16"DB 读可靠 OCR 只配脆弱发送层"
- **你社媒看到的"skill"=UIA 路线，在你版本死**：LeoMusk/wechat-rpa-bot-skill(YoKo 83★，YoBot 开源壳+闭源 exe，4.1.7+/语音≥4.1.9)、Hello-Mr-Crab/pywechat(1874★，监听+发文字+send_audios_to_friend 发真语音条)——**都是 UIAutomation，非 OCR**；#16 已铁证 UIA 在 4.1.12.26 死（控件树空壳）；pywechat 194 open issues、4.1.x 多版报障、4.1.12.26 未证
- **收沪语语音硬缺口**：微信自带转文字只认普/英/粤不认上海话；纯 OCR 读不懂沪语来话，须绕 DB/文件取音频喂本机 SenseVoice(吴语 CER~20%)
- **校核 refuted 两强论断**：①"OCR 唯一绕开 UIA"——我们 #16 已列 DB 读为非 UIA 首选读侧，OCR 只是脆弱发送侧；②"OCR 独占家人可达格子"——iLink 扫码同样可达，被排除靠伦理非技术
- **封号**：不注入不伪协议=客户端最低档，但风险搬到服务端行为模型(高频/秒回/24h/内容重复照旧)；本项目永不主动+被动+低频几乎清空触发器；残余=新号权重(养号)+违 ToS(可弃小号合同处置)。绝不用逝者原号
- **伦理（比 iLink 更该保守）**：OCR 劫持"看着完全是真人在用"的号、**零 bot 标识、欺骗性最强**（iLink 天然 bot+扫码知情兜底）；能发冒真度最高语音条=技术加分即伦理加压。裁决=自用低风险 GO(但 TG/iLink 自用比脆 OCR 干净)/家人向默认 NO-GO 更甚。详见 docs/research/wechat-ocr-automation.md
- **四路径全景定论**：①UIA #16 死 ②iLink #20 官方但家人向 NO-GO ③服务号/企微需主体 ④OCR 本路可行但最脆+欺骗性最强——**没有一条微信路径为家人向打开干净的门**

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

## companion 四连教训（2026-09-01/02，8B-3b～8B-9）
- **Playwright 截图是 devicePixelRatio 像素（本机 1.5×）**：像素 diff 用 CSS 坐标裁区域会算出"目标区 0 变化"假阴性——坐标必须乘 DPR（`screenshot.width / viewport.cssWidth`）；ambient 微摆/眨眼给全脸带底噪 diff，数字之外必须再拼状态对照图人眼看。能走真实运行时就别直调函数：`page.route` mock 上游 SSE + 经 UI 真操作（情绪层 E2E 做法）
- **PowerShell 按 CommandLine 匹配杀进程会杀掉自己**：`Get-CimInstance Win32_Process | ? { $_.CommandLine -like '*tts_server.py*' }` 命中执行它的 PowerShell 本身 → 必须加 `$_.Name -eq 'python.exe'`（重启 TTS 时自杀过一次）。Git Bash curl 发中文 body 会坏编码（服务端 400 是工具问题）→ 用 Python urllib + `ensure_ascii=False`
- **DeepSeek 区域规格变体**：文件超 ~32k 输出上限（build_companion_page.py 50KB+）时不再全文回显，规格给每处「原文本锚点块 + 要求」，只让 DeepSeek 输出 `=== R1 ===`… 分段新文本，Claude 侧 splice 脚本精确替换；规格文件用 Write 落盘不用 heredoc（含单引号/中文/正则时 shell 反复炸）
- **外部注入音频与内建清单混用的归属问题**：avatar.html `ended`→`playAt(cur+1)` 无条件推进，companion 灌进 `#player` 的 TTS blob 播完即接播训练用真实语音（用户真机实报）→ `blob:` 音源守卫一行。同族：分句流水线里旧回合的 iframe `ended` 会误推进新回合（Codex BLOCKER）→ `activePlay` 模块变量做 owner 校验；手点 ▶ 重播分支也要设 owner
- **情绪关键词误报纪律**：『太好了！！！→stern』『不错→happy』实证误报 → 关键词表去标点类/单字/泛词；`emotions` 键序即优先级（sad>stern>think>happy），子串首中即返
- **两套贴片烘焙数学并存**：Phase 1 嘴/眨眼旧脚本=内缩+blur(f/2)；情绪贴片 `bake_face_patch.py`=矩形→GaussianBlur(feather)→lighter 合并、不内缩，与 emo_review 预览同数学——"所见即所得"（叠底图 vs 用户审核合成图 max_diff=0）靠的是这个一致性
- **存档字段空值必须补默认（withDefaults）**：多服务商抽屉"切到 DeepSeek 没预填"根因=旧存档只存了 key、其余字段为空串被当作已配置
- **回复变长≠深度思考**：sessions 日志实据——deepseek-v4-flash 回复 90-163 字 vs 她节律中位 17 字，页面对 deepseek 已显式 `thinking:disabled`；是模型铺陈+动作描写风格。Kimi kimi-k3 官方"始终推理"只可调低不可关；切非 DeepSeek 服务商时推理默认在跑（更慢更贵不显示）
- **分句流水线首声**：synth 时长与音频时长成正比（90 字 8.9s），整句批量合成是首声慢根因；按句切段、首段先合成先播、文字随该段语音开播同刻浮现，首声从"正比全文"降到"首段合成"。代价=沉浸感显著上升 → 8A-2b 护栏优先级上升

## 8B-10 语音条分条教训（2026-09-05）
- **"太长不出声"的根因是保护阈值本身**：`TTS_TOTAL_MAX=240` 是 8B-9 为防失控回复设的，却让 7/17 条回复整段无声。保护阈值要落在"每条消息"粒度（MSG_MAX=30 + 前 12 条出声），而不是"整段回复"粒度——粒度错了，保护就变成故障。
- **节律统计从未进过提示词**：`build_rhythm_block` 读 `avg_length/median_length/peak_hours/...`，真实 rhythm.json 是 `mean/median/p90/buckets/top_hours/distribution`——一个键都不对，输出静默退化成只剩口头禅。写"消费统计"的代码必须用真实文件跑一次断言关键行存在（本次加了 `中位 17 字` 存在性检查）。
- **多气泡后所有"每回合一个元素"的假设都要重审**：时间分隔线（addBubble 逐条触发）、▶ 兜底按钮（旧回合残留可劫持 player）、回放与回合互斥（cancel 早退时不清回放）、文字延时（不再是闸门）——三视角审查 + 对抗核证抓出 10 条，全部源自"一回合一气泡"变"一回合多气泡"的隐含假设。
- **对抗核证的价值**：26 条发现里 2 条被反驳（其中 1 条 major"白名单未加 messages"是审查用的 diff 快照落后于工作区），避免了无谓返工；未核证的 14 条人工过一遍又捞出 4 条真问题（代理对硬切、纯空白 ['']、标签行送 TTS 必 400、标点类漏 …）——核证上限 12 不是"其余不重要"。
- **Codex MCP 登录态**：`codex login status` 显示已登录 ≠ 可用（refresh token 被吊销只在调用时暴露）；远程场景用 `codex login --device-auth`（help 里没列，但错误提示会给），设备码 15 分钟过期。
- **Playwright MCP 沙箱**：无 `Buffer`/`setTimeout`（用 `page.waitForTimeout`、ASCII-safe 字节串造 WAV）；`filename` 参数只认仓库根与 `.playwright-mcp/`；中途抛错的脚本继续在同一页面上跑成僵尸——重跑前 `browser_close`。

## 8B-11 起音爆音教训（2026-09-07）
- **模型每次开口有固有爆音**：CosyVoice2-Wu SFT e14 每句起音前 ~15 ms 高能量瞬态（RMS 2–3×、峰值 2×、重心 800 Hz），两语域、companion 片段、批量成品签名完全一致；推断源于训练片段自动切段的硬起音。出口 DSP（起音检测 + 30 ms 升余弦淡入）比改模型便宜得多，且 companion/批量统一受益。判断"是不是模型问题"的方法：同一签名跨文本/跨语域/跨调用路径都出现。
- **区域锚点别用"到下一个 class"这种开放边界**：第二轮把 `def soften_onsets(` … `
class ` 当锚点，吞掉了 DeepSeek 第一轮放在它后面的 `strip_brackets`，服务重启后 /tts 直接 NameError 500。规则：锚点末端用紧邻的确定文本；每轮拼接后必须跑 hunk 落区校验（本轮漏跑），再 py_compile 之外做一次"关键符号存在"断言（`grep -c '^def strip_brackets'`）。
- **Codex 只读审核也有盲区**：它在 git/py 都不可用的环境下 ACCEPT 了缺 strip_brackets 的文件（它只看新增函数）。审核 prompt 里要明说"顺带确认文件里原有的 X/Y 函数仍在"。

## T14 运维自启教训（2026-09-09，start_services.ps1 十轮）

- **"脚本谎报成功"是无人值守脚本的头号故障模式**：Codex 三次 REJECT 共 8 条阻断，其中 4 条都属这一类——端口被占就当服务正常（坏进程占着 8022 也报 ok）／已有隧道只看进程存在（cloudflared 卡住未退出就报 ok）／mutex 拿不到就退化无锁继续／健康检查通过但端口其实被外来服务占着。判据要三条件齐备：**端口监听 + 健康检查过 + 存在命令行匹配本服务的进程**，缺一不可 skip。爸爸打不开页面不会打电话，只会以为她不在了。
- **PowerShell 单元素数组展开（栽了两次）**：`return $matched` 在集合只有一个元素时被展开成标量 `CimInstance`，而它**没有 `.Count` 属性** → 所有 `$x -and $x.Count -gt 0` 判断恒假。实际故障：脚本把自己刚启动的 son-site/dad-site/llm-proxy 判成"外来进程占端口"并 FAIL，而 tts 因有父子两进程返回真数组而幸免。修法 `return ,$matched`（逗号一元操作符）。同族陷阱：`Sort-Object -Unique` 结果单元素时同样展开（`Stop-MatchingProcessTree` 的 `$matching.Count` 第二次栽），一律写 `@(...).Count`。
- **判重写错方向 = 死循环**：`$candidate.ProcessId -notin $descendants` 拿整数比对象数组，恒为真 → 同一进程无限重复入列，`do-while` 永不退出，`-Stop` 卡死 90 秒以上持续烧 CPU。**`[PSParser]::Tokenize()` 静态语法检查放行了它**——和 py_compile 一样只看语法不看语义。所有 do-while 递归都要加迭代上限兜底。
- **修 bug 引入的静默失效比原 bug 更隐蔽**：把判重改成 `$toCheck.ProcessId` 却没同步改初始化（仍是整数数组）→ `.ProcessId` 求值 `$null` → 条件恒假 → 递归一个子进程都找不到。从"死循环卡住"变成"秒回报成功但子进程还持着端口"。**修完必须在真实进程树上跑一遍对照**（错写法找到 0 个 / 正确写法找到 2 个），不能只看代码。
- **`param()` 必须是第一条可执行语句**：DeepSeek 把它放在文件第 490 行的 "Main" 段落，PowerShell 直接报 `param : The term 'param' is not recognized`。同样地 `[PSParser]::Tokenize()` **放行**了这个错误，只有真正执行才暴露。
- **区域规格 vs 全文回显的分界线**：脚本涨到 943 行后全文回显开始不稳（一次 `finish=length` 推理烧光、一次 `finish=None` 流式中断截断到 570 行）。改用**函数级区域规格**——按大括号配平提取整个函数、让 DeepSeek 只输出改动的那几个函数、Claude 侧按函数边界 splice 替换——8 秒出结果且从此零截断。比 8B-11 的"行级锚点"更安全：函数边界是确定的，不会吞掉相邻定义。
- **`$matches` 是 PowerShell 自动变量**：被 `-match` 操作符填充。当普通变量用时当前不出事（函数内用的是 `.Contains()`），但调用链里一旦出现正则就被悄悄覆盖。已改名 `$matched`。
- **token 落到命令行 = 落到两处可读位置**：进程命令行（同用户任意进程可经 WMI 读）与计划任务 XML（`C:\Windows\System32\Tasks\` 普通用户可读）。加 `--tokens-file` 后实测生产进程命令行零 token。配套三条：文件来源的解析错误**不得回显原值**（`parse_viewer_tokens`/`parse_tokens` 都会原样打印非法输入，命令行来源无所谓、文件来源必须捕获 stderr 换成统一文案）；`utf-8-sig` 读（Windows BOM 已坑过一次）；**空值必须 fail-closed**（`TTS_TOKENS=` 空串会让鉴权静默关闭）。
- **测试夹具用假数据会掩盖泄漏路径**：我用 `BADFORMAT_NO_COLON` 做非法值测试，看到 `Invalid --tokens entry: "BADFORMAT_NO_COLON"` 却没意识到那个位置在真实场景打印的**就是 token 本身**。Codex 一眼看出。夹具要用"长得像真凭据"的串（`SUPERSECRETTOKENVALUE123456`）才能让泄漏显形。
- **客户端工具怪癖会把成功伪装成失败**：PowerShell 5.1 `Invoke-WebRequest` 处理二进制音频响应时抛异常，我据此报"correct token -> HTTP ERR"，而服务端日志明写 `status=200`。与 memory 里"curl --max-time 把永不结束伪装成成功"是镜像关系。**两侧证据对不上时，先怀疑测试客户端。**

## T14-3/T14-4 自启任务与离线降级教训（2026-09-09→10，DeepSeek 6 轮 + Codex 3 轮 REJECT→ACCEPT）

### 无人值守脚本

- **`Start-Process -Wait` 等的是进程树，不是那个进程**。`-Run` 调 `start_services.ps1` 用了 `-Wait`，挂死 494 秒——因为 start_services 拉起的四个**常驻服务**是它的子进程，永不退出。而 start_services 自己早在 3 秒后就正常退出并写好了 `Summary: 4 ok`。判据：日志时间戳显示子脚本已完成，父脚本却还在等 → 一定是等错了对象。修法 `-PassThru`（不带 `-Wait`）+ `WaitForExit($ms)`，后者只等该进程本身。
- **把「启动成功吗」和「返回了什么」两阶段检查合并 = 每次成功都判成失败**。写成 `$proc=$null; $code=$null; try{$proc=Start-Process...}catch{$code=1}; if($null -eq $proc -or $null -eq $code){当作启动失败}`。成功路径上 `$code` 本来就还是 `$null`（要等 `WaitForExit` 后才赋值），于是**每次健康启动都被记成 `exit=launch-failed`**，重试 3 次烧掉 240 秒，最后报 exit 1——而服务全都好好跑着。两个阶段必须分开判：启动只看 `$proc`，退出码等 `WaitForExit` 之后再看。
- **「另一个实例持锁」不等于「服务在跑」**。Codex 两轮死咬这条：`start_services.ps1` 的 exit 3 既表示别人在干活，**也表示 mutex 获取本身抛了异常**；更要命的是上一次运行留下的、杀不掉的僵尸会**跨调用**持锁，进程内的 `$hadTimeout` 标志根本看不见它。最终修法是不再信退出码——收到 3 就去跑 `-Status` 实测四个服务，全 `[ ok ]` 才报成功。这是 T14-2「判据要三条件齐备」的延续：**凡是"我推测它没问题"，都要换成"我去看了它有没有问题"**。
- **超时后 `Kill()` 必须验尸**。`try{$proc.Kill()}catch{}` 吞掉失败又不确认，僵尸就会带着锁活下去，把下一次的 exit 3 洗成成功。要 `WaitForExit(10000)` + `Refresh()`/`HasExited` 双重确认，确认不了就立即 exit 1 且**不再重试**（重试只会一直撞到那把锁）。

### PowerShell / Windows 特有

- **`Write-Host "{0} {1}" -f $a,$b` 缺括号 → `-f` 被当成 `-ForegroundColor` 缩写**，报 `Cannot convert ... to ConsoleColor`。格式化表达式必须整个套括号：`Write-Host ("..." -f $a,$b)`。
- **任务计划用 `1999-11-30` 表示「从未运行」**，不是 `DateTime::MinValue`，naive 的 MinValue 判断会放它过去，运维看到 1999 年一脸问号。用 `Year -ge 2000` 兜。
- **`Get-ScheduledTaskInfo` 的 `LastTaskResult` 是 UInt32**，所以 `-is [int]` **恒假**，人话翻译被静默跳过，只剩裸的 `267011`。别做类型测试，直接 `[int64]` 防御性转换。配套陷阱：转换时不能拿"信息不可用"的哨兵字符串 `'-'` 去转（会落进 catch 被写成 `-1`），要用独立变量，`$null` 时不碰原值。
- **PS 5.1 的 `Get-Content`/`Set-Content` 往返会毁掉 UTF-8 无 BOM 文件里的中文**：读时按系统 ANSI(GBK) 解码，再以 utf8 写回 = 双重编码损坏。我用它 strip markdown 围栏，把 Worker 里的四句中文全毁了（grep 归零才发现）。**碰非 ASCII 文件一律用 Python 读写**，且 `Set-Content -Encoding utf8` 在 5.1 还会写 BOM。
- **Git Bash 会把 `/v1/chat/completions` 这种参数转成 Windows 路径**（MSYS 路径转换，变成 `C:/Program Files/Git/v1/...`）。传以 `/` 开头的非路径参数时走 PowerShell。

### 与模型协作的工艺

- **全文重生成会丢掉上一轮的修复**。6 轮里丢过 2 次（`[int64]` 修复被冲掉、Status 段被整段换掉），还出过一次截断（409 行的半成品，语法直接坏）。**修复轮次一多就必须换区域规格**：按大括号配平提取目标块 → 只让模型重写这一块 → 自己 splice → 跑「关键符号仍在」断言。本轮 splice 后固定检查 `hadTimeout/killConfirmed/-Force/四个模式` 是否都还在，抓住过一次相邻代码被吞。
- **计划任务指向的是磁盘上那个文件**。生成出语法坏的版本时，任务已经注册并指着它——那一刻若重启，服务起不来。**发现坏版本要立刻回滚**，别等修好再说。所以每轮生成前先 `Copy-Item` 备份，失败即还原。
- **测试前提错了会把正确行为误判成 bug**。我等了两轮 45 秒没见到 TTS 降级提示，以为循环没跑；实际是探活打到了 `:8022`（测试页没传 `--tts-origin`，默认 auto）并返回 200，**首探成功本就该静默**。是 network 记录（而不是 console）指出请求真正去了哪。**判断"功能没生效"之前，先确认请求实际发到了哪、回了什么。**
- **route-mock 比停服务更适合验降级**：`page.route('**/health', r => r.abort())` 直接造出冷启动，实测 16 秒出提示、`unroute` 后 12 秒出恢复提示，全程没碰真实服务。比停 TTS 再等 73 秒冷启动便宜得多。

### 三层离线降级的设计

- **没有任何一层能覆盖全部故障**：PC 关机要 Cloudflare Worker（PC 上的代码够不着）；用户自己断网要 Service Worker（请求根本出不去，Worker 也够不着）；TTS 冷启动要页面自身。三层缺一，就有一类故障让爸爸看见白页或英文报错。
- **Worker 自造的响应必须带 `Cache-Control: no-store`**。否则 Cloudflare 边缘会把离线页缓存住，PC 回来了还继续发"她今天不在"——这是这套东西最坏的可能故障，比不做还糟。
- **两层的兜底页必须行为等价**。Codex 抓到 Worker 版缺了「再试一次」按钮和恢复探针：哪层生效对读者不可见，若 Worker 版没探针，PC 恢复后他会一直盯着"她今天不在"。同一份文案存在两处，改一处必须改另一处（`grep -c` 核对已写进部署文档）。
- **Service Worker 只能拦 navigate**。`/tts` 与 `/v1/chat/completions` 一旦被缓存重放，就等于让她说出当时根本没被问到的话——这是伦理红线，不是性能选项。离线页每 60 秒的 `HEAD` 探针同理必须放行，否则会从缓存拿到"通了"而跳回一个死站。
