import copy
import json
import unittest
from pathlib import Path
from tools import build_chat_context as chat, build_relationship_site as site


class FatherStyleTests(unittest.TestCase):
    def setUp(self):
        self.template = Path('prompts/chat_system.husband.scoped.zh.md').read_text(encoding='utf-8')
        self.context = dict(schema_version=2, person='mama', viewer='father',
            relationship_id='mama_father', language='mandarin', coverage_status='partial',
            system_prompt='old', message_shards=['messages-0000.json'],
            memory_release={'revision': 'synthetic-binding', 'nested': [1, 2]})
        self.rhythm = dict(person='mama', relationship_id='mama_father',
            text_stats=dict(mean=3, median=2, p90=8, sample_count=10, buckets={'1-5': 8},
                            avg_length=3, median_length=2),
            burst=dict(distribution={'1': 9, '2': 1}, longest_burst=2),
            catchphrases=[{'phrase': '合成口头禅', 'count': 2}], punctuation_habits={'no_end_punct_ratio': .8})
        self.examples = []
        for i in range(25):
            row = dict(person='mama', relationship_id='mama_father', viewpoint='father',
                conversation_kind='direct', participant_ids=['mama', 'father'],
                sender_person_id='mama', sender='subject', tier=2, record_id=str(i),
                text=('合成争吵原句' if i % 2 == 0 else '合成平常原句') + ('甲' * 130),
                provenance={'source_record_id': str(i), 'source': 'synthetic'})
            self.examples.append(dict(person='mama', relationship_id='mama_father', target=row))

    def test_actual_builder_uses_father_prompt(self):
        from tests.test_relationship_site import RelationshipSiteTests
        fixture = RelationshipSiteTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.build()
        context = json.loads((fixture.out / 'data/chat_context.json').read_text(encoding='utf-8'))
        self.assertNotIn('消息长度：', context['system_prompt'])
        self.assertNotIn('连发习惯：', context['system_prompt'])
        self.assertIn('不是回复长度', context['system_prompt'])
        self.assertIn('最后一句', context['system_prompt'])
        self.assertIn('历史标点统计只描述原始消息', context['system_prompt'])
        self.assertIn('问句用问号', context['system_prompt'])
        # Verify the real request builder carries the built synthetic prompt.
        import subprocess
        request = subprocess.run(['node', '-e',
            "const fs=require('fs');const h=require('./tests/companion_voice_harness').context();"
            "const p=JSON.parse(fs.readFileSync(0,'utf8'));"
            "process.stdout.write(JSON.stringify(h.buildMessages(p,[], '', '合成问题')));"],
            input=json.dumps(context['system_prompt']), text=True, encoding='utf-8', capture_output=True, check=True)
        messages = json.loads(request.stdout)
        self.assertEqual(messages[0], {'role': 'system', 'content': context['system_prompt']})
        self.assertEqual(messages[-1], {'role': 'user', 'content': '合成问题'})

    def test_father_runtime_omits_length_and_burst_but_keeps_style(self):
        self.assertTrue(hasattr(site, 'rebuild_father_context'), 'missing father-only pure rebuild route')
        result = site.rebuild_father_context(self.context, self.rhythm, self.examples, template=self.template)
        prompt = result['system_prompt']
        for forbidden in ('消息长度：', '长度分布：', '平均长度约', '中位长度约', '连发习惯：'):
            self.assertNotIn(forbidden, prompt)
        for expected in ('合成口头禅', '句末标点', '不是回复长度', '不是当下事实', 'Tier-3', 'partial'):
            self.assertIn(expected, prompt)

    def test_original_fragments_provenance_and_nonprompt_context_identical(self):
        self.assertTrue(hasattr(site, 'rebuild_father_context'))
        before = copy.deepcopy((self.context, self.rhythm, self.examples))
        result = site.rebuild_father_context(self.context, self.rhythm, self.examples, template=self.template)
        fragments = [json.loads(line) for line in result['system_prompt'].splitlines() if line.startswith('{')]
        expected = [dict(text=self.examples[i * 25 // 12]['target']['text'][:120],
                         record_id=str(i * 25 // 12), provenance=self.examples[i * 25 // 12]['target']['provenance'])
                    for i in range(12)]
        self.assertEqual(fragments, expected)
        self.assertEqual({k:v for k,v in result.items() if k != 'system_prompt'},
                         {k:v for k,v in self.context.items() if k != 'system_prompt'})
        self.assertEqual((self.context, self.rhythm, self.examples), before)
        self.assertEqual(result, site.rebuild_father_context(self.context, self.rhythm, self.examples, template=self.template))

    def test_invalid_scope_rejected(self):
        self.assertTrue(hasattr(site, 'rebuild_father_context'))
        for key, value in [('viewer', 'owner'), ('relationship_id', 'mama_owner'), ('language', 'wu'), ('coverage_status', 'full')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                site.rebuild_father_context(dict(self.context, **{key: value}), self.rhythm, self.examples, template=self.template)
        with self.assertRaises(ValueError):
            site.rebuild_father_context(self.context, dict(self.rhythm, relationship_id='mama_owner'), self.examples, template=self.template)
        bad = copy.deepcopy(self.examples)
        bad[0]['target']['provenance']['source_record_id'] = 'wrong'
        with self.assertRaises(ValueError):
            site.rebuild_father_context(self.context, self.rhythm, bad, template=self.template)

    def test_default_and_legacy_rhythm_unchanged_and_empty_supported(self):
        self.assertTrue(hasattr(site, 'rebuild_father_context'))
        full = chat.build_rhythm_block(self.rhythm)
        for text in ('消息长度：', '长度分布：', '平均长度约', '中位长度约', '连发习惯：', '合成口头禅'):
            self.assertIn(text, full)
        for stats in (None, {}, {'text_stats': {'avg_length': 2}, 'burst': '只发一条'}):
            rhythm = dict(stats or {}, person='mama', relationship_id='mama_father')
            prompt = site.rebuild_father_context(self.context, rhythm, [], template=self.template)['system_prompt']
            self.assertNotIn('平均长度约', prompt)
            self.assertNotIn('只发一条', prompt)


if __name__ == '__main__':
    unittest.main()
