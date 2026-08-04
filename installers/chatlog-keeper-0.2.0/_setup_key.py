import os
from pathlib import Path
# 全新的、普通权限可写的数据目录（repo外，避免提交泄露）
base = Path.home() / "ck-data"
os.environ["CHATLOG_KEEPER_DATA_DIR"] = str(base)
os.environ["CHATLOG_WECHAT_DATA_ROOT"] = r"C:/Users/justin/xwechat_files"

secrets = base / "secrets"
secrets.mkdir(parents=True, exist_ok=True)
keyfile = secrets / "wechat_db.key"
keyfile.write_text("ba39a535ee404532b9660d117d9aa29e2c5eba6ce20444e89c91d4fda266cd86", encoding="utf-8")
print("key written to:", keyfile, "readable:", keyfile.read_text(encoding="utf-8")[:12]+"...")

# 验证 chatlog-keeper 现在能读到并解锁
import chatlog_keeper.wechat_db as w
from chatlog_keeper.core._path_resolver import data_dir
print("data_dir now:", data_dir())
cached = w.load_cached_wechat_key()
print("cached loaded:", None if cached is None else cached.hex()[:12]+"... len="+str(len(cached)))
root = w.find_weixin_data_root()
dbs = w.find_msg_databases(w.find_wxid_dirs(root)[0])
print("dbs:", len(dbs))
if cached:
    okc = 0
    for db in dbs:
        p1 = w._read_stable_page1(db)
        if p1 and w._verify_key_v4(cached, p1): okc += 1
    print(f"UNLOCKED {okc}/{len(dbs)} dbs with cached key")
