import os, sqlite3, hashlib, glob
from pathlib import Path
outdir = Path(r"C:/Users/justin/ck-decrypted")
tab = "Msg_" + hashlib.md5(b"laurawang001").hexdigest()
print("妈妈的表名:", tab)
try: import zstandard as zstd; dctx=zstd.ZstdDecompressor()
except: dctx=None

for db in sorted(outdir.glob("message_*_plain.db")):
    con = sqlite3.connect(db); con.row_factory=sqlite3.Row
    names=[r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?",(tab,))]
    if not names: con.close(); continue
    n=con.execute(f"SELECT COUNT(*) FROM '{tab}'").fetchone()[0]
    print(f"\n找到! {db.name} 表 {tab}: {n} 行")
    # 类型分布
    types={}
    for r in con.execute(f"SELECT local_type,COUNT(*) c FROM '{tab}' GROUP BY local_type"):
        types[r[0]]=r['c']
    print("  local_type分布:", types)
    def dump(t, label):
        row=con.execute(f"SELECT * FROM '{tab}' WHERE local_type=? LIMIT 1",(t,)).fetchone()
        if not row: print(f"  [{label}] 无"); return
        print(f"  === [{label}] local_type={t} 样本 ===")
        for col in ['message_content','compress_content','packed_info_data']:
            v=row[col] if col in row.keys() else None
            if v is None: continue
            b=v if isinstance(v,bytes) else str(v).encode()
            # 试 zstd 解压
            dec=None
            if dctx:
                try: dec=dctx.decompress(b)
                except: 
                    try: dec=dctx.decompress(b, max_output_size=1<<20)
                    except: dec=None
            show=dec if dec else b
            silk = b'#!SILK' in show or b'\x02#!SILK' in show
            print(f"    {col}: len={len(b)} zstd={'y' if dec else 'n'} SILK={silk}")
            txt = show[:300].decode('utf-8','replace')
            print(f"      内容: {txt}")
    dump(34,"语音"); dump(43,"视频"); dump(3,"图片")
    con.close()
