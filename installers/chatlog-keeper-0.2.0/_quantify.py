import sqlite3, hashlib, re, glob
from pathlib import Path
dec=Path(r"C:/Users/justin/ck-decrypted")
rep=open(r"C:/Users/justin/AppData/Local/Temp/claude/C--Users-justin-Documents-I-MISS-U/a94cbf27-efc4-4b96-a136-f8228ebe7b93/scratchpad/quantify.txt","w",encoding="utf-8")
def wr(s=''): rep.write(str(s)+"\n")
tab="Msg_"+hashlib.md5(b"laurawang001").hexdigest()

# 1) 妈妈语音的 server_id 集合(across shards)
mama_voice_svrids=set(); mama_video_md5=[]
try: import zstandard as zstd; dctx=zstd.ZstdDecompressor()
except: dctx=None
def unz(b):
    try: return dctx.decompress(b)
    except:
        try: return dctx.decompress(b,max_output_size=1<<22)
        except: return b
for db in dec.glob("message_*_plain.db"):
    con=sqlite3.connect(db)
    if not con.execute("SELECT name FROM sqlite_master WHERE name=?",(tab,)).fetchone(): con.close(); continue
    for sid, in con.execute(f"SELECT server_id FROM '{tab}' WHERE local_type=34"):
        mama_voice_svrids.add(sid)
    for pid, in con.execute(f"SELECT packed_info_data FROM '{tab}' WHERE local_type=43"):
        if pid:
            m=re.search(rb'([0-9a-f]{32})', unz(pid) if isinstance(pid,bytes) else b'')
            if m: mama_video_md5.append(m.group(1).decode())
    con.close()
wr(f"妈妈语音消息数(Msg表 type=34): {len(mama_voice_svrids)}")
wr(f"妈妈视频消息数(Msg表 type=43): {len(mama_video_md5)}, md5样本={mama_video_md5[:3]}")

# 2) VoiceInfo 里能匹配上多少(按 svr_id)
matched=0; sample=None
for mdb in dec.glob("media_*_plain.db"):
    con=sqlite3.connect(mdb)
    if not con.execute("SELECT name FROM sqlite_master WHERE name='VoiceInfo'").fetchone(): con.close(); continue
    for sid,vd in con.execute("SELECT svr_id, voice_data FROM VoiceInfo"):
        if sid in mama_voice_svrids:
            matched+=1
            if sample is None and vd: sample=(sid,vd)
    con.close()
wr(f"VoiceInfo 中匹配妈妈的语音: {matched}")

# 3) 抽一个 silk 样本存盘
if sample:
    sid,vd=sample
    p=Path(r"C:/Users/justin/ck-decrypted/sample_mama_voice.silk")
    p.write_bytes(vd)
    wr(f"样本已存: {p} ({len(vd)}字节) 首字节={vd[:12].hex()}")

# 4) 视频 md5 能否在磁盘找到 mp4
vroot=Path(r"C:/Users/justin/xwechat_files/justzheng525_6e59/msg/video")
found=0
for md5 in mama_video_md5:
    if list(vroot.glob(f"*/{md5}.mp4")): found+=1
wr(f"妈妈视频 md5 在磁盘找到 mp4: {found}/{len(mama_video_md5)}")
rep.close(); print("done")
