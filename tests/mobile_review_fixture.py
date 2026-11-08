"""纯合成评测夹具；不读取 people，不签发任何真实 Access 身份。"""
from __future__ import annotations

import argparse
import json
import math
import struct
import time
import wave
from pathlib import Path

from tools.build_mobile_review import write_json, inventory
from tools.viewpoint_manifest import digest, sha256
from tools.benchmark_voice_references import experiment_schedule,take_identity


def wav(path, index=0):
    path.parent.mkdir(parents=True,exist_ok=True)
    with wave.open(str(path),'wb') as stream:
        stream.setparams((1,2,8000,0,'NONE','not compressed'))
        stream.writeframes(b''.join(struct.pack('<h',int(3000*math.sin(2*math.pi*(220+index)*i/8000))) for i in range(24000)))


def fixture(root):
    root=Path(root).absolute()
    root.mkdir(parents=True,exist_ok=True)
    package=root/'package'
    package.mkdir()
    media,candidates,ab,source={},{},[],[]
    def audio(index):
        key=f'{index:032x}'
        path=package/'audio'/(key+'.wav')
        wav(path,index)
        media[key]=dict(file='audio/'+key+'.wav',sha256=sha256(path))
        return '/review/audio/'+key+'.wav'
    for i in range(14):
        ab.append(dict(id=f'ab{i:030x}',number=i+1,text='合成试听示例 '+str(i+1),audio_a=audio(2*i+1),audio_b=audio(2*i+2)))
    for i in range(12):
        key=f'cd{i:030x}'
        url=audio(29+i)
        c=dict(record_id='synthetic-'+str(i),audio_sha256=media[url.rsplit('/',1)[1][:-4]]['sha256'],revision=digest(['candidate',i]),person='synthetic',split='validation' if i==11 else 'train')
        candidates[key]=c
        source.append(dict(id=key,number=i+1,text='合成原声草稿 '+str(i+1),audio=url,source_label='合成来源 '+str(i+1),split=c['split'],actual_duration_ms=3000,expected_duration_ms=3000,duration_requires_confirmation=i==0))
    manifest=dict(schema_version=1,tasks=[dict(id='ab',title='声音对比',items=ab),dict(id='source',title='原声核验',items=source)],
                  media=media,candidates=candidates,study_id='synthetic-only',readonly_roots=[],source_hashes={},synthetic=True)
    manifest['package_revision']=digest(manifest)
    write_json(package/'manifest.json',manifest)
    return package


def credentials():
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    claims=dict(iss='https://synthetic.example',aud='synthetic-review',sub='synthetic-owner',iat=int(time.time()),exp=int(time.time())+3600)
    token=jwt.encode(claims,key,algorithm='RS256',headers={'kid':'synthetic-key'})
    return key,claims,token


def config(root,port=0):
    root=Path(root).absolute()
    return dict(package_dir=str(root/'package'),state_dir=str(root/'state'),host='127.0.0.1',port=port,
                public_origin='http://127.0.0.1:'+str(port),access_issuer='https://synthetic.example',access_audience='synthetic-review')


def sources(root):
    """构造原工具的文件合同，以覆盖真实 build 验证路径。"""
    root=Path(root)
    ab,prep,training,experiment=[root/name for name in ('ab','prep','training','experiment')]
    for p in (ab,prep,training,experiment):
        p.mkdir(parents=True)
    plan=dict(targets=[dict(id='target-'+str(i),text='合成测试 '+str(i)) for i in range(7)],seeds=[1,2],
              references=[dict(id=name,audio_sha256=digest(['audio',name]),transcript_sha256=digest(['text',name])) for name in ('reference-1','reference-2','candidate','reference-4','current-long-reference')])
    rows=[]
    for i,(target,seed,reference) in enumerate(experiment_schedule(plan,False)):
        row=take_identity(i,target,seed,reference,'synthetic')
        row.update(status='ok',wav=row['id']+'.wav')
        wav(experiment/row['wav'],i)
        row['sha256']=sha256(experiment/row['wav'])
        rows.append(row)
    write_json(experiment/'plan.json',plan)
    write_json(experiment/'asr-jobs.json',{})
    (experiment/'results.jsonl').write_text('\n'.join(json.dumps(r) for r in rows),encoding='utf-8')
    write_json(experiment/'summary.json',dict(total=70,smoke=False,run_id='synthetic',plan_sha256=sha256(experiment/'plan.json'),results_sha256=sha256(experiment/'results.jsonl'),asr_jobs_sha256=sha256(experiment/'asr-jobs.json')))
    analysis=root/'analysis.json'
    write_json(analysis,dict(total=70,run_id='synthetic'))
    groups=[]
    for i,(target,seed) in enumerate((t,s) for t in plan['targets'] for s in plan['seeds']):
        takes={}
        for j,label in enumerate(('A','B')):
            row=next(r for r in rows if r['target_id']==target['id'] and r['seed']==seed and r['condition']==('current-long-reference' if j==0 else 'candidate'))
            rel=f'audio/group-{i+1}-{label}.wav'
            (ab/rel).parent.mkdir(exist_ok=True)
            (ab/rel).write_bytes((experiment/row['wav']).read_bytes())
            takes[label]=dict(source_take=row['id'],condition=row['condition'],source_wav=row['wav'],source_sha256=row['sha256'],output_wav=rel,output_sha256=row['sha256'])
        groups.append(dict(group=i+1,target_id=target['id'],seed=seed,target_text=target['text'],takes=takes))
    write_json(ab/'paired-manifest.json',dict(experiment_path=str(experiment.resolve()),analysis_path=str(analysis.resolve()),analysis_sha256=sha256(analysis),experiment_run_id='synthetic',baseline_condition='current-long-reference',candidate_condition='candidate',study_id='synthetic',groups=groups))
    write_json(ab/'answer-key.json',{'answers':'synthetic-only'})
    write_json(ab/'build-evidence.json',dict(groups=14,copied_wavs=28,source_hashes=inventory(experiment),source_files_unchanged=len(inventory(experiment)),analysis_sha256=sha256(analysis),outputs=inventory(ab)))
    candidates=[]
    index=0
    for i in range(12):
        while True:
            path=training/'audio'/f'{i}.wav'
            wav(path,index)
            index+=1
            h=sha256(path)
            split='validation' if int(h[:8],16)%10==0 else 'train'
            if split==('validation' if i==11 else 'train'):
                break
        c=dict(record_id='synthetic-'+str(i),person='synthetic',speaker_status='pending',transcript_status='draft',
               audio_file=f'audio/{i}.wav',audio_sha256=h,dedup_group=h,split=split,draft_text='合成测试',
               actual_duration_ms=3000,expected_duration_ms=3000,duration_check='within_tolerance',provenance={'synthetic':True})
        c['revision']=digest(c)
        c['exclusion_reasons']=['no_review']
        candidates.append(c)
        (prep/'audio').mkdir(exist_ok=True)
        (prep/c['audio_file']).write_bytes(path.read_bytes())
    for directory in (prep,training):
        (directory/'candidates.jsonl').write_text('\n'.join(json.dumps(c) for c in candidates),encoding='utf-8')
    write_json(training/'summary.json',dict(inputs=[],training_started=False,candidates=12,eligible=0,verified_transcripts=0))
    write_json(prep/'technical-report.json',dict(source=str((training/'candidates.jsonl').resolve()),source_sha256=sha256(training/'candidates.jsonl'),candidates=12,selected=12,training_started=False,
               records=[dict({k:c[k] for k in ('record_id','audio_sha256','revision','split','provenance')},recommended_for_review=True) for c in candidates]))
    # 使用实际导入/训练候选/技术筛选工具生成完整纯合成来源链。
    from tests.test_import_wechat_viewpoint import ImportViewpointTests
    from tools.build_training_manifest import build as training_build
    from tools.prepare_voice_upgrade import prepare
    fx=ImportViewpointTests()
    fx.root=root/'dataset-chain'
    fx.source=fx.root/'accepted'
    fx.source.mkdir(parents=True)
    fx.legacy=fx.root/'legacy.jsonl'
    fx.legacy.write_text('\n'.join(json.dumps(r) for r in [
        dict(record_id='legacy01',person='mama',viewpoint='owner',sender='subject',sender_wxid='wx_m'),
        dict(record_id='legacy02',person='mama',viewpoint='owner',sender='viewpoint_owner',sender_wxid='wx_j')]),encoding='utf-8')
    fx.rows=[fx.row(1,'wx_f',True)]
    drafts,mapping=[],[]
    for i in range(12):
        row=fx.row(i+2,'wx_m',voice=True)
        row['media']=[dict(kind='voice',path=f'{i}.wav',format='WAV',duration_check='within_tolerance')]
        fx.rows.append(row)
        target=fx.source/'records/conversation-1'/f'{i}.wav'
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes((training/'audio'/f'{i}.wav').read_bytes())
        drafts.append(dict(id=str(i),asr_text='Synthetic source draft '+str(i)))
        mapping.append(dict(id=str(i),source_file='records/conversation-1/messages.json',source_row_number=i+2,native_id=str(i+2),wav_sha256=sha256(target)))
    write_json(fx.source/'acceptance-summary.json',dict(coverage_status='partial'))
    fx.refresh()
    dataset=fx.run_import()
    draft_path, mapping_path=fx.root/'drafts.json',fx.root/'mapping.json'
    write_json(draft_path,drafts);write_json(mapping_path,mapping)
    actual_training,actual_prep=root/'training-authoritative',root/'prep-authoritative'
    training_build(person='mama',datasets=[dataset],out=actual_training,asr_drafts=draft_path,asr_mapping=mapping_path)
    prepare(actual_training,actual_prep)
    return ab,actual_prep


def main():
    from tools.mobile_review_server import create_server
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--port',type=int,default=18025)
    args=p.parse_args()
    fixture(args.root)
    key,claims,token=credentials()
    settings=config(args.root,args.port)
    server=create_server(settings,test_keys={'synthetic-key':key.public_key()})
    write_json(args.root/'launch-info.json',dict(origin=settings['public_origin'],token=token,package_revision=server.store.package.revision))
    print('Synthetic signed fixture ready',flush=True)
    with server:
        server.serve_forever()


if __name__=='__main__':
    main()
