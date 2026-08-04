import pysilk, wave
from pathlib import Path
silk = Path(r"C:/Users/justin/ck-decrypted/sample_mama_voice.silk").read_bytes()
print("silk 首字节:", silk[:12].hex(), "len:", len(silk))
# 微信 silk 首字节是 0x02, 需剥离; pysilk 期望以 #!SILK_V3 开头
payload = silk[1:] if silk[:1]==b'\x02' else silk
print("剥离后首:", payload[:10])
# pysilk-mod API: decode(input_bytes, sample_rate) -> pcm bytes
try:
    pcm = pysilk.decode(payload, 24000)
except Exception as e:
    print("decode(payload,24000) 失败:", e)
    pcm = pysilk.decode(silk, 24000)  # 试不剥离
print("PCM 字节:", len(pcm))
outp = Path(r"C:/Users/justin/ck-decrypted/sample_mama_voice.wav")
with wave.open(str(outp),'wb') as wf:
    wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(24000); wf.writeframes(pcm)
print("WAV 已写:", outp, outp.stat().st_size, "字节, 时长≈", round(len(pcm)/2/24000,1), "秒")
