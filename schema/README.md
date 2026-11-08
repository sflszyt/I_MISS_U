# 统一中间格式（UIF · Unified Intermediate Format）

`uif.schema.json`（JSON Schema draft 2020-12）是**所有数据源适配器的合同**：

```
raw/（各源原始数据）→ parser（每源一个）→ UIF JSONL → 下游构建器（rhythm/persona/memory/archive）
```

下游只消费 UIF，不接触任何源特定格式。**新增数据源（笔记/WhatsApp/Facebook…）= 只写一个新 parser，下游零改动。**

## 文件约定

- 每行一条 JSON 记录（JSONL），UTF-8，`ensure_ascii=False`
- 存放位置：`people/<person>/normalized/*.jsonl`（如 `wechat_messages.jsonl`、`media_items.jsonl`）
- 记录内所有路径均为相对 `people/<person>/` 的正斜杠路径

## 四种记录类型

| record_type | 用途 | 关键字段 |
|---|---|---|
| `message` | 聊天消息（微信等） | `conversation_id` `sender` `content_type` `text` `media_ref` `duration_ms` |
| `post` | 朋友圈/微博帖子 | `author` `text` `media_refs` `location` `comments` |
| `email` | 邮件 | `from` `to` `subject_line` `body_text` `attachments` |
| `media_item` | 独立照片/视频/音频 | `media_type` `file_ref` `sha256` `exif` |

## 公共信封字段（每条记录必带 → 标 *）

| 字段 | 说明 |
|---|---|
| `record_id` * | 稳定唯一 id（建议 sha256(source + native_id)） |
| `record_type` * | 四种类型之一 |
| `person` * | 建档对象 slug（如 `mama`） |
| `viewpoint` * | **视角**：数据来自谁的账号导出（如 `owner`；`self` 保留给对象本人账号） |
| `source` * | `wechat` `wechat_moments` `weibo` `email` `photos` `videos` `notes` `whatsapp` `facebook` `other` |
| `timestamp` | ISO 8601 带时区；未知为 null |
| `timestamp_precision` | `exact` / `date` / `month` / `year` / `unknown` |
| `tier` * | **事实分级**：1=家人确认 · 2=自动抽取（parser 默认）· 3=模型生成/推断（**禁止陈述为事实**） |
| `lang` | BCP-47 提示（`zh`、`wuu`=吴语/上海话） |
| `provenance` * | 溯源：`source_file` / `parser` / `parser_version` / `extracted_at` / `native_id` |

## 校验

```bash
pip install jsonschema
python -c "import json, jsonschema; s=json.load(open('schema/uif.schema.json',encoding='utf-8')); v=jsonschema.Draft202012Validator(s); [v.validate(json.loads(l)) for l in open('people/mama/normalized/media_items.jsonl',encoding='utf-8')]"
```

## 演进规则

### 多视角导入 v1

`viewpoint` 继续表示导出账号主人；`viewer=owner` 映射 `owner/mama_owner`，
`viewer=father` 映射 `father/mama_father`。新增字段全为可选，不改变旧必填集合。
`sender_person_id` 与音频 `speaker_id` 分开；群聊无自动夫妻关系或受话人推断。
`quality`、`provenance.source_account_id/source_batch_id/source_row/source_file_sha256`
保留可用性与来源，隔离记录不输出 `text`。新数据维持 Tier-2。

新导入入口（只应对已经验收的本地包执行）：

```text
python tools/import_wechat_viewpoint.py --person mama --viewpoint father --source <accepted-dir> --legacy-uif <legacy.jsonl> --batch <new-slug> [--repo-root <root>] [--registry <private.json>]
```

`--registry` 是可选的显式私有注册表，必须与旧 UIF subject/owner 和新包
is_self/voice_requested 的交叉核对结果完全一致，不能跳过身份核对。
当前自动推导入口仅支持 mama/father；未识别发送人登记为稳定 unknown ID。
包清单为 `package-manifest.json` 数组，每项严格包含 `path/bytes/sha256`，
清单本身不列入；所有其他文件都必须列出。媒体路径相对于所在 messages.json。
导入拒绝链接、junction、路径越界、未列文件、哈希不符、同包重复原生键和既有目标。
复制后再次验包；I/O 中断可能留下不完整新批次，后续拒绝覆盖，需人工检查。

输出 `raw/wechat/father/<batch>/` 全包副本和
`normalized/wechat/father/<batch>/{messages.uif.jsonl,media_manifest.jsonl,quarantine.jsonl,canonical_events.jsonl,import_manifest.json,dataset.json}`。
注册表独占新建为 `registry.father.<batch>.json`；不覆盖全局注册表或旧 UIF。
重复导入只有输入指纹、raw 和所有已登记输出验证一致时才幂等返回。

Python API：`import_package(*, person, viewpoint, source: Path, legacy_uif: Path,
batch, repo_root: Path, registry: Path | None = None) -> Path` 返回 dataset.json。
`load_registry(path: Path) -> dict` 和 `load_dataset(path: Path) -> (dict, list[dict])`
在 `tools.viewpoint_manifest` 中；无目录扫描补全数据，错误抛 `ValueError`。

注册表字段为 `schema_version=1, person, participants, accounts, viewers, conversations`。
`participants` 为人物 ID → 对象；`accounts` 为私有账号别名 →
`{participant_id,native_id}`；`viewers` 为 viewer → `{participant_id,relationship_id}`；
`conversations` 为源会话 ID → `{kind,participant_ids}`。未知人物不等于已确认身份。

dataset v1 固定字段：`schema_version,person,viewpoint,source_batch_id,records_path,
records_sha256,media_manifest_path,media_manifest_sha256,registry_path,registry_sha256,
coverage_status,counts`。路径相对 `people/<person>/`，manifest 必须位于上述 normalized 批次目录。
`counts` 包含 `records,media,quarantined`；`coverage_status` 为 partial/complete。
`load_dataset` 核对来源文件、媒体与注册表哈希，以及人物/来源/场景归属。

媒体清单每条逻辑语音一项：`record_id,person,viewpoint,provenance,representations,
missing,speaker_id,speaker_status,transcript_status,source_kind,training_eligible`。
SILK/WAV 为同条记录的 representations；每种保存路径、哈希、字节数、格式和时长检查。
说话人默认 unknown/pending，转写 pending，training_eligible=false；消息发送者不证明说话人。

新 ID 使用账号别名、会话和 native ID；无 native ID 时用源文件哈希/source_row。
`canonical_events.jsonl` 仅记录与旧数据有一致 native ID、会话、发送者、类型、正文的强关联；
只关联可用文字，媒体事件不凭同文本猜测。旧 record_id 原样保留，不在导入时合并来源。
旧 `parse_wechat` 的配置支持 `viewpoint`（默认 owner）与 `source_account_id`；
非默认 viewpoint 或显式账号别名启用 ID 命名空间，默认配置的旧 ID 保持不变。

- 只加字段，不改语义、不删字段、不改必填集合（除非 major 版本升级并写迁移说明）
- 所有类型 `additionalProperties: true`——旧校验器容忍新字段
