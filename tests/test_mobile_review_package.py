import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.mobile_review_fixture import sources,fixture
from tools.build_mobile_review import build,Package,separate,checked_path,training_anchors
from tools import viewpoint_manifest as vm


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def test_build_projection_and_frozen_sources(self):
        ab,prep=sources(self.root)
        package=Package(build(ab,prep,self.root/'output'))
        self.assertEqual(len(package.manifest['media']),40)
        view=json.dumps(package.tasks)
        for secret in ('condition','record_id','source_take','seed','experiment_path'):
            self.assertNotIn(secret,view)
        self.assertTrue((package.path/'frozen'/'training-summary.json').exists())
        (ab/'answer-key.json').write_text('{}')
        with self.assertRaises(ValueError):package.verify()

    def test_raw_overlap_and_link(self):
        for path in (self.root/'RAW'/'out',self.root/'raw'/'..'/'out'):
            with self.assertRaises(ValueError):checked_path(path,True)
        for path in (self.root,self.root/'input'/'out'):
            with self.assertRaises(ValueError):separate(path,[self.root/'input'])
        target=self.root/'target';target.mkdir()
        link=self.root/'link'
        try:link.symlink_to(target,target_is_directory=True)
        except OSError:self.skipTest('symlink privilege unavailable; junction covered by no_links implementation')
        with self.assertRaises(ValueError):checked_path(link/'out',True)

    def test_audio_and_manifest_mutation(self):
        package=Package(fixture(self.root))
        key=next(iter(package.manifest['media']))
        (package.path/package.manifest['media'][key]['file']).write_bytes(b'changed')
        with self.assertRaises(ValueError):package.audio(key)

    def test_ab_evidence_tamper(self):
        ab,prep=sources(self.root)
        (ab/'paired-manifest.json').write_text('{}')
        with self.assertRaises((ValueError,KeyError)):build(ab,prep,self.root/'output')

    def test_candidate_revision_tamper(self):
        ab,prep=sources(self.root)
        path=prep/'candidates.jsonl'
        rows=[json.loads(line) for line in path.read_text().splitlines()]
        rows[0]['revision']='bad'
        path.write_text('\n'.join(json.dumps(r) for r in rows))
        with self.assertRaises(ValueError):build(ab,prep,self.root/'output')

    def test_raw_and_all_representations_are_frozen_without_mutating_raw(self):
        ab,prep=sources(self.root)
        package=Package(build(ab,prep,self.root/'output'))
        dataset=next(Path(p) for p in package.manifest['source_hashes'] if Path(p).name=='dataset.json')
        manifest,records=vm.load_dataset(dataset)
        raw=vm.safe_path(dataset.parents[4],records[0]['provenance']['source_file'])
        self.assertIn(str(raw),package.manifest['source_hashes'])
        for media in vm.read_jsonl(vm.safe_path(dataset.parents[4],manifest['media_manifest_path'])):
            for rep in media['representations']:
                self.assertIn(str(vm.safe_path(dataset.parents[4],rep['path'])),package.manifest['source_hashes'])
        original=vm.sha256
        def changed(path):
            return '0'*64 if Path(path).resolve()==raw.resolve() else original(path)
        with patch('tools.viewpoint_manifest.sha256',side_effect=changed),patch('tools.build_mobile_review.sha256',side_effect=changed):
            with self.assertRaises(ValueError):vm.load_dataset(dataset)
            with self.assertRaises(ValueError):build(ab,prep,self.root/'bad-output')
            with self.assertRaises(ValueError):package.verify()
        self.assertEqual(original(raw),package.manifest['source_hashes'][str(raw)])

    def test_missing_dataset_and_self_consistent_candidate_forgery_rejected(self):
        _,prep=sources(self.root)
        technical=vm.read_json(prep/'technical-report.json')
        source=Path(technical['source'])
        summary=vm.read_json(source.parent/'summary.json')
        candidates=vm.read_jsonl(source)
        self.assertTrue(training_anchors(summary,candidates))
        with self.assertRaises(ValueError):training_anchors(dict(summary,inputs=[]),candidates)
        candidates[0]['draft_text']='Self-consistent but not the original ASR draft'
        candidates[0]['revision']=vm.digest({k:v for k,v in candidates[0].items() if k not in ('revision','exclusion_reasons')})
        with self.assertRaises(ValueError):training_anchors(summary,candidates)


if __name__=='__main__':unittest.main()
