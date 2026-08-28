# 蕾咪（kira-remy-official）拆解研究：把纸片人做成桌宠立绘效果（任务 #19）

> 立项：2026-08-28 用户指令"立项研究这个项目，我想把数字人做成这种效果"（https://github.com/SingularDance/kira-remy-official）。
> 方法：GitHub 仓库全量克隆逐行拆解（~14k 行 Python，核心 desktop_pet.py 1809 行）+ 本地 Remy_v1.2.1 实装对照（用户 08-27 已试装并截图，见 findings"实物样本启发"条）。
> 关联：任务 #18 桌面陪伴（companion v1 已上线）、docs/research/desktop-companion.md（壳选型/伦理三档）。

---

## 〇、一句话结论

**"这种效果"= 三件事：①透明无边框桌面立绘窗（人物悬浮在桌面上）②情绪表情立绘切换 ③打字机气泡对话流。三件全部平移可行，且我们的底子在关键处反超它**——蕾咪没有语音、口型只是 Open/Shut 静态双帧（正是我们 Phase 4 判死的路线的更简版）、人格是硬编码提示词；我们有她的真声 TTS、viseme 四态口型+眨眼+微摆、persona+三源检索+Tier 纪律。**真正要补的只有两样：情绪表情资产（ComfyUI 再出 4-6 个表情，走用户定稿闸门）和桌宠壳形态（透明窗）。** 蕾咪的行为设计（托盘常驻/主动搭话/游戏化/恋人模式）与我们条件 a-f 冲突——**借形不借魂**。

---

## 一、项目档案

| 项 | 值 |
|---|---|
| 技术栈 | Python 3.10 + **PyQt5**（无 Live2D/无 Unity/无 Electron） |
| 形象 | **8 张静态 PNG 立绘**：Shut(默认闭口)/Open(开口)/Angry/Happy/Wronged(委屈)/Expect(期待)/Sleep/Dangle(拖拽) |
| 语音/口型 | **无 TTS、无音频**；"说话"= Open/Shut 双帧 + 打字机气泡 |
| 人格 | 硬编码傲娇少女 prompt + 37 字回复约束 + 恋人关系模式 + 硬编码台词库 |
| LLM | DeepSeek/通义 BYOK（config.json + UI 双通道）；识图走云端 GLM-4V |
| 许可 | 完全开源，"欢迎学习、使用、二创"（7★/5 fork/37 commits，PyInstaller 单 exe 发布） |
| 20 年红线 | 无闭源 runtime，纯 PyQt5 + PNG——**合规可借鉴** |

## 二、效果拆解（机制级，源码定位）

1. **透明桌宠窗**（desktop_pet.py:96-101）：`Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint` + `setAttribute(Qt.WA_TranslucentBackground)`——QWidget 无边框透明置顶，QLabel `setPixmap` 放立绘，PNG 的 alpha 就是人物轮廓。拖拽=mousePress/Move/Release 三件套（含跨屏 metrics 恢复）。托盘=QSystemTrayIcon（双击显隐）。
2. **情绪系统**（utils.py:388 + desktop_pet.py:467）：LLM 回复文本 → `detect_emotion` **关键词匹配**（'生气/笨蛋'→angry、'开心/喜欢'→happy、'委屈/难过'→wronged、'期待/想'→expect）→ `set_emotion_avatar` 换立绘。两个好细节：**同表情连续命中时用 Open 替代**（防呆滞）；说完 2 秒气泡淡出**回落 Shut 默认态**（finish_speaking → fade_out_bubble）。
3. **对话流**：思考气泡（thinking bubble，流式增量更新）→ 打字机逐字 `type_char`（QTimer）→ 完成后延迟淡出；输入框空时透明"不露底"。**37 字回复上限写死在 system prompt**——为气泡排版服务（与我们 TTS ≤120 字约束异曲同工）。
4. **互动层（多为我们的反模式）**：点击随机表情+硬编码台词、拖拽松手委屈表情、剪贴板监听、音乐/视频监听主动评论、小游戏、好感度式统计。

## 三、与我们现状对照

| 能力 | 蕾咪 | 我们（companion v1） | 判定 |
|---|---|---|---|
| 形象呈现 | **透明桌宠立绘悬浮桌面** | 浏览器页内头像框 | **要补（形态）** |
| 表情 | **6 情绪立绘** | 仅四态嘴+眨眼（单一表情） | **要补（资产）** |
| 口型 | Open/Shut 静态双帧 | viseme 时间轴+RMS 四态 | 我们领先两代 |
| 语音 | 无 | 她的真声 TTS 双语域 | 我们独有 |
| 人格 | 硬编码 prompt | persona+rhythm+三源检索+Tier | 我们领先 |
| 记忆 | chat_log 明文+用户档案 | 档案+轴五 sessions（人工闸门） | 我们领先且合规 |
| 对话呈现 | 打字机气泡+思考泡 | 聊天列表流式 | 可借鉴（体验细节） |

## 四、采纳 / 排除清单

**借（形）**：
1. **透明立绘窗形态**——人物悬浮桌面无边框。实现路径三选（见第五节）。
2. **情绪表情层**——在 mouth_patches 体系上加 emotion 维度；驱动先用蕾咪同款关键词检测（零成本、无 LLM 协议改动），后续可升级"LLM 输出情绪标签"协议（先例研究已核证该模式：SillyTavern classify/z-waif）。
3. **体验细节四件**：同表情防呆滞、说完回落默认态、思考气泡、打字机节奏（配合她的 rhythm.json 更有味道）。
4. 工程细节（已入 findings）：config 文件+UI 双通道、备用 key 降级链。

**不借（魂，条件 a-f 与红线排除）**：托盘常驻/开机自启/显隐驻留、主动搭话（剪贴板/音乐监听）、游戏化/好感度/恋人模式、云端识图（照片出机违铁律 3）、硬编码台词库（她只说档案里有的话——台词库=编造）。

## 五、落地路径（Phase 8B 候选，供裁决）

**方案甲：companion 页内先补"情绪表情层"（最小改动，纯资产+运行时小改）**
- ComfyUI 复用 Phase 0/1 管线出情绪贴片（眉眼+嘴组合或整脸变体）；候选情绪集（对齐她的真实性格，不套蕾咪的傲娇）：默认微笑 / 开心 / 心疼-难过 / 嗔怪（她真实的"凶"，铁律 2 保留完整性）/ 思考。**每个表情用户定稿闸门**；工艺预警：Phase 1 实证首轮必夸张，需温和化迭代。
- 运行时：mouth_patches.json v3 加 emotion 层；关键词检测驱动 + 说完回落默认；与 viseme 口型正交叠加（表情=眉眼层，口型=嘴层——贴片架构天然支持）。
- 收益：iframe 形态与未来桌宠壳**通用**，资产一次生产两处复用。

**方案乙：桌宠壳（达成"悬浮立绘"视觉）**
- 三条实现路径：①**PyQt5 + QWebEngineView 透明窗**——蕾咪同款壳但装我们的 HTML 运行时（口型/表情/TTS 全保留），Python 栈与项目一致；②Tauri v2 透明窗（壳研究首选，Rust 工具链代价）；③保持 Edge --app 矩形窗（零代码，无悬浮感）。
- **伦理边界不变**：桌宠壳 = "打开才在的立绘窗"——快捷方式点开才出现、无托盘、无自启、关窗道别、空闲离场。蕾咪的"常驻感"恰是我们明确不做的部分。
- 待验证点：QWebEngineView 透明窗承载我们页面的可行性（WA_TranslucentBackground + 页面 body transparent + WebAudio 正常）需一个小探针。

**推荐顺序：甲 → 乙**。甲不动形态先把"活起来"的表情做出来（同时把 8A-2b 伦理护栏做完）；乙在甲的资产上加壳。

## 六、伦理对齐声明

蕾咪是给虚构角色做的通用陪伴产品，常驻+主动+游戏化是它的合理产品逻辑；我们的对象是真实的妈妈，档案优先于对话、沉浸度是唯一要克制的指标（desktop-companion.md 三档判定已定）。本研究采纳其**视觉与工程形**，排除其**行为魂**；a-f 条件（只应答/打开才在/Tier 标签/真实节律/统计自见/告别协议）在任何形态升级中不得减配。

## 附：源码溯源

克隆快照存 scratchpad/remy-src（研究用，不入库）；关键定位：desktop_pet.py:96-101（透明窗）/467-491（表情切换+防呆滞）/805（回落）；utils.py:388-407（关键词情绪检测）；config.py:54-61（人格 prompt+37 字约束）。本地实装对照：C:\Users\justin\Desktop\Remy（v1.2.1，config.json 双通道实证）。
