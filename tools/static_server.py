"""python -m http.server 的替身：唯一的区别是会发 Cache-Control 头。

为什么存在：
    原本用 `python -m http.server` 提供静态文件，它不发 Cache-Control，
    浏览器按启发式（(now - Last-Modified) 的 10%）缓存 HTML，
    站点重建后用户看到的仍是旧页面。这里不改其它任何行为，只补上缓存头。

被谁调用：
    scripts/start_services.ps1（PowerShell 编排脚本），形如：
        python.exe tools\\static_server.py --port 8020 --directory <dir>
        python.exe tools\\static_server.py --port 8021 --bind 127.0.0.1 --directory <dir>

缓存策略（唯一新增行为，三条规则）：
    1. HTML 文档：路径为 '/' 或以 '.html' 结尾（不区分大小写）
    2. Service Worker：路径为 '/sw.js'
    3. 数据文件：路径以 '/data/' 开头且以 '.json' 结尾
    以上发 `Cache-Control: no-cache, must-revalidate`（是 no-cache 不是 no-store，
    保留副本以便走 If-Modified-Since → 304，省流量）。
    其余路径不发 Cache-Control，与 http.server 现状一致。
"""

import argparse
import functools
import http.server
from urllib.parse import urlsplit


class CacheControlHandler(http.server.SimpleHTTPRequestHandler):
    """与 SimpleHTTPRequestHandler 完全一致，仅在 end_headers() 补一个头。

    send_head() 与 If-Modified-Since → 304 逻辑一律不动；
    304 响应同样会经过 end_headers()，因此也会带上 Cache-Control。
    """

    def end_headers(self):
        if self._wants_no_cache():
            self.send_header("Cache-Control", "no-cache, must-revalidate")
        super().end_headers()

    def _wants_no_cache(self):
        path = urlsplit(self.path).path.lower()  # 先剥掉 query / fragment
        return (
            path == "/"
            or path.endswith(".html")
            or path == "/sw.js"
            or (path.startswith("/data/") and path.endswith(".json"))
        )


def main():
    parser = argparse.ArgumentParser(
        description="http.server 的替身，额外发送 Cache-Control 头。"
    )
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--bind")  # 不给就绑所有接口
    parser.add_argument("--directory", required=True)
    args = parser.parse_args()

    handler = functools.partial(CacheControlHandler, directory=args.directory)
    with http.server.ThreadingHTTPServer((args.bind or "", args.port), handler) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
