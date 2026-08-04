import os, sqlite3
from pathlib import Path
os.environ["CHATLOG_KEEPER_DATA_DIR"]=r"C:/Users/justin/ck-data"
import chatlog_keeper.wechat_db as w
key=w.load_cached_wechat_key()
mirror=Path(r"C:/Users/justin/ck-mirror/justzheng525_6e59/db_storage/message")
outdir=Path(r"C:/Users/justin/ck-decrypted")
rep=open(r"C:/Users/justin/AppData/Local/Temp/claude/C--Users-justin-Documents-I-MISS-U/a94cbf27-efc4-4b96-a136-f8228ebe7b93/scratchpad/media_probe.txt","w",encoding="utf-8")
def wr(s=''): rep.write(str(s)+"\n")
for mdb in sorted(mirror.glob("media_*.db")):
    outp=outdir/(mdb.stem+"_plain.db")
    if not w._decrypt_db_v4(mdb,key,outp): wr(f"{mdb.name}: 解密失败"); continue
    con=sqlite3.connect(outp); con.row_factory=sqlite3.Row
    tabs=[r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    wr(f"\n### {mdb.name}: 表={tabs[:15]}")
    for t in tabs:
        if t.startswith("sqlite_"): continue
        cols=[c[1] for c in con.execute(f"PRAGMA table_info('{t}')")]
        try: cnt=con.execute(f"SELECT COUNT(*) FROM '{t}'").fetchone()[0]
        except: cnt='?'
        wr(f"  表 {t} ({cnt}行) 列={cols}")
        # 找含 SILK 的 blob 列
        for c in cols:
            try:
                row=con.execute(f"SELECT \"{c}\" FROM '{t}' WHERE typeof(\"{c}\")='blob' LIMIT 1").fetchone()
            except: continue
            if row and row[0]:
                b=row[0]
                if b'#!SILK' in b[:64] or b'\x02#!SILK' in b[:8] or b'SILK' in b[:16]:
                    wr(f"    ★ 列 {c} 含 SILK! len={len(b)} hex前16={b[:16].hex()}")
                    # dump 整行其他列(找join key)
                    full=con.execute(f"SELECT * FROM '{t}' LIMIT 1").fetchone()
                    wr(f"      同行其他列: "+", ".join(f"{k}={full[k] if not isinstance(full[k],bytes) else 'BYTES'+str(len(full[k]))}" for k in full.keys()))
    con.close()
rep.close(); print("done")
