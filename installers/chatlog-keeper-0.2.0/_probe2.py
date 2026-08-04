import sqlite3, hashlib, json
from pathlib import Path
outdir = Path(r"C:/Users/justin/ck-decrypted")
rep = open(r"C:/Users/justin/AppData/Local/Temp/claude/C--Users-justin-Documents-I-MISS-U/a94cbf27-efc4-4b96-a136-f8228ebe7b93/scratchpad/mama_probe.txt","w",encoding="utf-8")
def w(s=''): rep.write(str(s)+"\n")
tab = "Msg_" + hashlib.md5(b"laurawang001").hexdigest()
w("妈妈表名 md5(laurawang001): "+tab)
try: import zstandard as zstd; dctx=zstd.ZstdDecompressor()
except Exception: dctx=None

def unzstd(b):
    if not dctx or not b: return b
    for kw in ({},{ "max_output_size":1<<22}):
        try: return dctx.decompress(b, **kw)
        except Exception: pass
    return b

best=None
for db in sorted(outdir.glob("message_*_plain.db")):
    con=sqlite3.connect(db); 
    has=[r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?",(tab,))]
    if has:
        n=con.execute(f"SELECT COUNT(*) FROM '{tab}'").fetchone()[0]
        w(f"  {db.name}: {tab} => {n} 行")
        if not best or n>best[1]: best=(db,n)
    con.close()

if best:
    db,n=best; w(f"\n=== 最大分片 {db.name} ({n}行) 结构分析 ===")
    con=sqlite3.connect(db); con.row_factory=sqlite3.Row
    types={r[0]:r[1] for r in con.execute(f"SELECT local_type,COUNT(*) FROM '{tab}' GROUP BY local_type")}
    w("local_type分布: "+json.dumps(types))
    for t,lab in [(34,"语音"),(43,"视频"),(3,"图片")]:
        row=con.execute(f"SELECT * FROM '{tab}' WHERE local_type=? ORDER BY create_time LIMIT 1",(t,)).fetchone()
        if not row: w(f"\n[{lab} type={t}] 无样本"); continue
        w(f"\n========== [{lab} local_type={t}] ==========")
        for col in row.keys():
            v=row[col]
            if isinstance(v,bytes):
                dec=unzstd(v); silk=(b'#!SILK' in dec)
                w(f"  {col}: BYTES len={len(v)} (unzstd={len(dec)}) SILK={silk}")
                w(f"    hex前48: {dec[:48].hex()}")
                w(f"    text: {dec[:600].decode('utf-8','replace')}")
            else:
                w(f"  {col}: {v}")
    con.close()
rep.close(); print("done")
