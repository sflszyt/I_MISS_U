from pathlib import Path
d = Path.home() / "AppData" / "Local" / "chatlog-keeper" / "data" / "secrets"
d.mkdir(parents=True, exist_ok=True)
p = d / "wechat_db.key"
try:
    p.unlink()
except Exception as e:
    print("unlink:", e)
p.write_text("ba39a535ee404532b9660d117d9aa29e2c5eba6ce20444e89c91d4fda266cd86", encoding="utf-8")
print("rewrote:", p)
print("exists now:", p.exists())
print("content:", p.read_text(encoding="utf-8"))
