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
| `viewpoint` * | **视角**：数据来自谁的账号导出（如 `justin`；`self` 保留给对象本人账号） |
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

- 只加字段，不改语义、不删字段、不改必填集合（除非 major 版本升级并写迁移说明）
- 所有类型 `additionalProperties: true`——旧校验器容忍新字段
