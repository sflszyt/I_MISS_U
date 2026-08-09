"""Streaming DeepSeek caller — survives connection-killing middleboxes.

Usage: python scripts/deepseek_call.py <spec_file> <out_file> <max_tokens> [api_key]
Reads DEEPSEEK_API_KEY from env; optional 4th argument overrides it.
Exit codes: 0 ok, 1 all attempts failed, 3 output truncated by max_tokens.
"""
import json
import os
import sys
import time
import urllib.request

SPEC, OUT, MAXTOK = sys.argv[1], sys.argv[2], int(sys.argv[3])
KEY = os.environ.get("DEEPSEEK_API_KEY") or (sys.argv[4] if len(sys.argv) > 4 else None)
if not KEY:
    sys.exit("DEEPSEEK_API_KEY not set")

SYSTEM = (
    "You are an expert software engineer acting as the code-writing engine inside a larger, "
    "Claude-orchestrated workflow. Implement exactly what the specification asks. Output the "
    "requested code with correct file paths and nothing else - no preamble, no explanation, "
    "no summary - unless the spec explicitly asks for it. Prefer complete, runnable code over snippets."
)

payload = {
    "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
    "messages": [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": open(SPEC, encoding="utf-8").read()},
    ],
    "max_tokens": MAXTOK,
    "stream": True,
}
# DEEPSEEK_NOTHINK=1 关闭推理链：大文件生成时推理会烧光 max_tokens（实测 60k 中 59k 是推理）
if os.environ.get("DEEPSEEK_NOTHINK") == "1":
    payload["thinking"] = {"type": "disabled"}
body = json.dumps(payload).encode("utf-8")

for attempt in range(1, 4):
    try:
        req = urllib.request.Request(
            "https://api.deepseek.com/chat/completions",
            data=body,
            headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
        )
        content, reasoning_n, finish = [], 0, None
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=120) as resp:
            for raw in resp:
                line = raw.decode("utf-8").strip()
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload == "[DONE]":
                    break
                chunk = json.loads(payload)
                ch = chunk.get("choices") or []
                if not ch:
                    continue
                delta = ch[0].get("delta") or {}
                if delta.get("reasoning_content"):
                    reasoning_n += 1
                if delta.get("content"):
                    content.append(delta["content"])
                if ch[0].get("finish_reason"):
                    finish = ch[0]["finish_reason"]
        text = "".join(content)
        if not text:
            raise RuntimeError(f"empty content (finish={finish})")
        with open(OUT, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print(f"[ok] attempt {attempt}: {len(text)} chars, finish={finish}, "
              f"reasoning_chunks={reasoning_n}, {time.time()-t0:.0f}s -> {OUT}")
        if finish == "length":
            print("[warn] truncated by max_tokens — rerun with higher limit")
            sys.exit(3)
        sys.exit(0)
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(f"[warn] attempt {attempt}/3 failed: {e}", file=sys.stderr)
        time.sleep(5 * attempt)
sys.exit(1)
