from pathlib import Path
p = Path(r"C:/Users/justin/AppData/Local/chatlog-keeper/data/secrets/wechat_db.key")
print("exists:", p.exists())
raw = p.read_bytes()
print("raw len:", len(raw), "first bytes:", raw[:8])
text = p.read_text(encoding="utf-8").strip()
print("text len:", len(text), "repr:", repr(text[:20]))
hexset = "0123456789abcdefABCDEF"
print("all hex:", all(c in hexset for c in text))
print("len==64:", len(text)==64)
