/**
 * NOTE: This offline page is duplicated in people/mama_for_father/site/offline.html
 * and the two must be kept in sync.
 */

const OFFLINE_HTML = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>她今天不在</title>
<style>
  :root {
    color-scheme: light dark;
    --bg: #faf6f0;
    --fg: #4a4238;
    --btn-bg: #e8dfd4;
    --btn-fg: #4a4238;
    --border: #c9bfb2;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #2e2a26;
      --fg: #d9cfc4;
      --btn-bg: #4a423c;
      --btn-fg: #e0d6cb;
      --border: #5a524a;
    }
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { height: 100%; }
  body {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: max(1rem, env(safe-area-inset-top)) max(1rem, env(safe-area-inset-right)) max(1rem, env(safe-area-inset-bottom)) max(1rem, env(safe-area-inset-left));
    background: var(--bg);
    color: var(--fg);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    line-height: 1.8;
  }
  main {
    max-width: 34rem;
    width: 100%;
    text-align: center;
    padding: 2rem 1.5rem;
  }
  h1 {
    font-size: clamp(2rem, 8vw, 3rem);
    font-weight: 700;
    margin-bottom: 1.5rem;
    line-height: 1.3;
  }
  p {
    font-size: clamp(1.25rem, 4.5vw, 1.5rem);
    line-height: 1.8;
  }
  button {
    margin-top: 2rem;
    min-height: 3rem;
    min-height: 48px;
    font-size: 1.125rem;
    font-size: 18px;
    line-height: 1.4;
    padding: 0 2rem;
    background: var(--btn-bg);
    color: var(--btn-fg);
    border: 1px solid var(--border);
    border-radius: 0.75rem;
    cursor: pointer;
    font-family: inherit;
  }
  .fine-print {
    margin-top: 3rem;
    font-size: clamp(0.875rem, 3vw, 1rem);
    line-height: 1.6;
    opacity: 0.7;
  }
</style>
</head>
<body>
<main>
  <h1>她今天不在</h1>
  <p>等电脑醒过来，她就回来了。</p>
  <p>明天再来看看吧。</p>
  <button type="button" onclick="location.reload()">再试一次</button>
  <p class="fine-print">这是家里那台电脑的事，不是她走了。</p>
</main>
<script>
(function () {
  function probe() {
    if (document.visibilityState !== 'visible') return;
    fetch('/companion.html', { method: 'HEAD', cache: 'no-store' })
      .then(function (response) {
        if (response.ok) {
          location.replace('/companion.html');
        }
      })
      .catch(function () {});
  }
  try { probe(); } catch (e) {}
  setInterval(function () {
    try { probe(); } catch (e) {}
  }, 60000);
})();
</script>
</body>
</html>`;

const JSON_BODY = JSON.stringify({ error: "origin_unavailable" });

const API_PATHS = new Set([
  "/v1/chat/completions",
  "/tts",
  "/health",
  "/session"
]);

const ORIGIN_DOWN_STATUS = new Set([
  502, 503, 504, 521, 522, 523, 524, 530
]);

function buildOfflineResponse(url) {
  const pathname = new URL(url).pathname;
  const status = 503;
  if (API_PATHS.has(pathname)) {
    return new Response(JSON_BODY, {
      status: status,
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store"
      }
    });
  }
  const headers = new Headers();
  headers.set("Content-Type", "text/html; charset=utf-8");
  headers.set("Cache-Control", "no-store");
  headers.set("Retry-After", "300");
  return new Response(OFFLINE_HTML, { status: status, headers: headers });
}

export default {
  async fetch(request) {
    try {
      const response = await fetch(request);
      if (ORIGIN_DOWN_STATUS.has(response.status)) {
        return buildOfflineResponse(request.url);
      }
      return response;
    } catch (e) {
      return buildOfflineResponse(request.url);
    }
  }
};
