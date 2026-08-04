import os, sqlite3, glob
os.environ["CHATLOG_KEEPER_DATA_DIR"] = r"C:/Users/justin/ck-data"
os.environ["CHATLOG_WECHAT_DATA_ROOT"] = r"C:/Users/justin/ck-mirror"
import chatlog_keeper.wechat_db as w
from pathlib import Path

key = w.load_cached_wechat_key()
mirror = Path(r"C:/Users/justin/ck-mirror/justzheng525_6e59/db_storage/message")
outdir = Path(r"C:/Users/justin/ck-decrypted"); outdir.mkdir(exist_ok=True)

# 解密所有 message_*.db (妈妈消息可能分布在多个分片)
for db in sorted(mirror.glob("message_*.db")):
    if db.name.endswith("_fts.db") or "resource" in db.name: continue
    outp = outdir / (db.stem + "_plain.db")
    ok = w._decrypt_db_v4(db, key, outp)
    if not ok: print("decrypt failed:", db.name); continue
    con = sqlite3.connect(outp); con.row_factory = sqlite3.Row
    tabs = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    # 找含消息的表(通常 Msg / MSG / name_msg)
    msgtabs = [t for t in tabs if 'msg' in t.lower() or 'Msg' in t]
    print(f"\n### {db.name}: {len(tabs)}张表; 疑似消息表: {msgtabs[:6]}")
    for t in msgtabs[:3]:
        cols = [c[1] for c in con.execute(f"PRAGMA table_info('{t}')")]
        # 是否有 laurawang001 的消息 + 语音(34)/视频(43)
        has_type = 'local_type' in cols or 'type' in cols or 'MsgType' in cols
        print(f"  表 {t} 列: {cols[:20]}")
    con.close()
