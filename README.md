# I_MISS_U

为关键的人建立可传承的数字档案：原声、照片、时间线、语言习惯和经过人工确认的记忆卡片。档案使用 Markdown、JSON、WAV、PNG 和自包含 HTML 等开放格式；对话只是访问档案的一种方式。

## 目录

- `schema/`：统一中间格式，包含来源、视角、事实分级和溯源信息。
- `tools/`：素材导入、档案编译、人工核验、语音处理和可选对话服务。
- `prompts/`：按关系参数化的提示模板。
- `tests/`：合成数据单元测试和浏览器测试。
- `deploy/`：通用静态页面及 Worker 源码；实际部署配置仅保留本地。

`people/` 存放个人档案，整个目录不进入 Git。原始素材 `people/*/raw/` 只读；处理结果必须写到新目录。个人运维记录、代理配置、安装器、日志和密钥文件同样只保留本地。

## 事实分级

1. Tier-1：经过人工确认的记忆。
2. Tier-2：自动抽取的信息，必须可溯源。
3. Tier-3：模型生成或推断，不得陈述为事实，升级必须经过人工确认。

保留人物完整性，不能系统性删除负面特质。档案完整性优先于对话沉浸感。

## 本地验证与提交检查

```powershell
python -X utf8 -m unittest discover -s tests -t .
node --check tests/e2e/companion_sessions.spec.js
python -X utf8 tools/audit_git_privacy.py
python -X utf8 tools/audit_git_privacy.py --staged
```

TTS 测试需要已安装音频依赖的 Python 环境。浏览器测试支持通过 `PLAYWRIGHT_CORE` 指定本地 Playwright 模块。语法检查不等于浏览器实测。

TTS 路径通过命令行参数指定；本机可使用已忽略的 `tools/tts_local_defaults.json` 保存 `MODELS_DIR_DEFAULT`、`EXP_DIR_DEFAULT`、`REF_DEFAULT`、`PROMPT_TEXT_DEFAULT` 四个非空路径字符串。不在该文件保存凭据。

旧档案的账号标识可在已忽略的 `tools/identity.local.json` 中设置 `owner_participant`；未配置时为中性的 `owner`。显式参数优先于 `IMISSU_OWNER_ID` 环境变量，再优先于本机文件。身份配置只改变读取与新构建所用的标识，不迁移已有数据。测试使用合成身份，不加载真实个人身份。

冻结语音对照实验需要本机 `tools/reference_bindings.local.json`（或 `IMISSU_REFERENCE_BINDINGS` 指定的文件）提供三项参考素材 SHA-256 绑定；未配置时拒绝运行。个人扫描词可放在已忽略的 `.privacy-policy.json` 中，以正则表达式字符串数组表示；扫描报告不会输出匹配内容。

`scripts/start_services.ps1` 与 `scripts/register_startup_task.ps1` 是本机专用运维脚本，保留在本地，不随源码分发；新检出需要自行配置服务启动方式。

隐私扫描只输出路径、行号和类别；默认检查整个候选树，`--staged` 检查整个 Git 索引。忽略规则不会移除已跟踪文件，也不会清除旧提交中的内容。扫描用于发现常见密钥和个人标识，不能替代人工审核，尤其不能自动判断自由文本中的私人记忆。
