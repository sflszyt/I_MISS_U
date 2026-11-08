"""Offline prompt contracts; these do not score generated dialect or TTS quality."""
import copy
import json
from pathlib import Path
import subprocess
import unittest

from tools.build_relationship_site import rebuild_father_context


class FatherDialectPromptTests(unittest.TestCase):
    def setUp(self):
        self.template = (Path(__file__).resolve().parents[1] /
                         'prompts/chat_system.husband.scoped.zh.md').read_text(encoding='utf-8')
        self.context = dict(schema_version=2, person='synthetic', viewer='father',
                            relationship_id='synthetic_father', language='mandarin',
                            coverage_status='partial', system_prompt='old',
                            message_shards=['synthetic.json'])
        self.rhythm = dict(person='synthetic', relationship_id='synthetic_father',
                           text_stats={'mean': 3, 'median': 2},
                           punctuation_habits={'no_end_punct_ratio': 1})

    def test_rebuilt_prompt_keeps_synthetic_examples_separate_from_evidence(self):
        row = dict(person='synthetic', relationship_id='synthetic_father',
                   viewpoint='father', conversation_kind='direct',
                   participant_ids=['synthetic', 'father'], sender_person_id='synthetic',
                   sender='subject', tier=2, record_id='synthetic-1',
                   text='合成引用：术语ABC，数值12.5。\n下一句。',
                   provenance={'source_record_id': 'synthetic-1', 'source': 'synthetic'})
        examples = [dict(person='synthetic', relationship_id='synthetic_father', target=row)]
        before = copy.deepcopy((self.context, self.rhythm, examples))
        built = rebuild_father_context(self.context, self.rhythm, examples, template=self.template)
        prompt = built['system_prompt']
        synthetic, evidence = prompt.split('原话片段（Tier-2', 1)
        self.assertIn('合成措辞示例（Tier-3）', synthetic)
        self.assertIn('不可当作检索来源或默认事实', synthetic)
        self.assertNotIn('→', evidence)
        fragments = [json.loads(line) for line in evidence.splitlines() if line.startswith('{')]
        self.assertEqual(fragments, [dict(text=row['text'], record_id=row['record_id'],
                                         provenance=row['provenance'])])
        self.assertEqual((self.context, self.rhythm, examples), before)
        self.assertEqual({k: v for k, v in built.items() if k != 'system_prompt'},
                         {k: v for k, v in self.context.items() if k != 'system_prompt'})

    def test_request_carries_style_and_fact_boundaries_without_language_switch(self):
        built = rebuild_father_context(self.context, self.rhythm, [], template=self.template)
        # Exercise the actual JS request builder with only a synthetic user turn.
        result = subprocess.run(['node', '-e',
            "const fs=require('fs');const h=require('./tests/companion_voice_harness').context();"
            "const p=JSON.parse(fs.readFileSync(0,'utf8'));"
            "process.stdout.write(JSON.stringify(h.buildMessages(p,[], '', '合成问题')));"],
            input=json.dumps(built['system_prompt']), text=True, encoding='utf-8',
            capture_output=True, check=True, cwd=Path(__file__).resolve().parents[1])
        messages = json.loads(result.stdout)
        prompt = messages[0]['content']
        self.assertEqual(messages[0]['role'], 'system')
        self.assertEqual(prompt, built['system_prompt'])
        for rule in ('本轮没找到不等于整个档案没有', '不能编造具体事件、日期、人名或地点',
                     '不是她本人', '不要主动逐项念出', '不逐字替换',
                     '不在词语、专业术语内部或句末标点之前插入换行',
                     '不为沪语口吻改写医学事实', '原话引用保留原文',
                     '这里只调整措辞与句式，不添加语音控制标记'):
            with self.subTest(rule=rule):
                self.assertIn(rule, prompt)
        self.assertEqual(built['language'], 'mandarin')
        self.assertNotIn('e14', prompt)
        self.assertNotIn('mandarin', prompt)
        self.assertNotIn('<|wuyu|>', prompt)
        self.assertNotIn('消息长度：', prompt)
        self.assertEqual(messages[-1], {'role': 'user', 'content': '合成问题'})


if __name__ == '__main__':
    unittest.main()
