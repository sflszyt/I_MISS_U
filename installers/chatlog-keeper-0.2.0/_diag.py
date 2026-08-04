import os
os.environ["CHATLOG_WECHAT_DATA_ROOT"] = r"C:/Users/justin/xwechat_files"
import chatlog_keeper.wechat_db as w
from chatlog_keeper.core._path_resolver import data_dir
print("data_dir():", data_dir())
print("persistent cache path:", w._persistent_wechat_key_cache_path())
root = w.find_weixin_data_root()
print("resolved data root:", root)
wxids = w.find_wxid_dirs(root) if root else []
print("wxid dirs:", [str(x) for x in wxids])
dbs = w.find_msg_databases(wxids[0]) if wxids else []
print("msg dbs found:", len(dbs))
cached = w.load_cached_wechat_key()
print("cached key loaded:", None if cached is None else cached.hex(), "len:", None if cached is None else len(cached))
if cached and dbs:
    for db in dbs[:3]:
        p1 = w._read_stable_page1(db)
        ok = w._verify_key_v4(cached, p1) if p1 else None
        print(f"  verify {os.path.basename(str(db))}: page1={'ok' if p1 else 'NONE'} verify={ok}")
