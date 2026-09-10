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

const CACHE_CONTROL_REVALIDATE = "no-cache, must-revalidate";

// These statuses are defined as body-less, and the Response constructor throws a
// TypeError if a body is attached to one of them. "no-cache" makes conditional
// requests (and therefore 304s) the normal case, so this path is hot, not rare.
const NULL_BODY_STATUS = new Set([
  101, 204, 205, 304
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

// python -m http.server sends no Cache-Control, so browsers fall back to
// heuristic freshness (10% of the Last-Modified age) and Cloudflare caches .js
// by extension. After a rebuild both keep serving the old page, which also means
// the fix (sw.js) can't reach the user. Only these three path classes get a
// header; everything else stays exactly as the origin sent it.
function pathNeedsRevalidation(pathname) {
  if (pathname === "/" || pathname.endsWith(".html")) {
    return true;
  }
  if (pathname === "/sw.js") {
    return true;
  }
  if (pathname.startsWith("/data/") && pathname.endsWith(".json")) {
    return true;
  }
  return false;
}

// "no-cache" rather than "no-store" on purpose: the browser keeps its copy and
// revalidates, so avatar.html (387KB) can come back as a 304 instead of being
// re-downloaded in full on the user's mobile data.
function withRevalidation(response) {
  // Headers on a fetched Response are immutable, and a Response built from the
  // original body is the only mutable copy we get.
  const body = NULL_BODY_STATUS.has(response.status) ? null : response.body;
  const rewritten = new Response(body, response);
  rewritten.headers.set("Cache-Control", CACHE_CONTROL_REVALIDATE);
  return rewritten;
}

export default {
  async fetch(request) {
    try {
      // Parsed before the fetch because it decides whether the edge cache needs
      // bypassing; a parse failure must not skip the fetch itself.
      let pathname = "";
      try {
        pathname = new URL(request.url).pathname;
      } catch (e) {
        pathname = "";
      }
      const revalidate = pathNeedsRevalidation(pathname);

      // A navigation is never the "load sw.js" fetch we are trying to fix, and
      // a rebuild of it is the one thing that must not happen here.
      const isNavigation =
        request.mode === "navigate" ||
        request.headers.get("Sec-Fetch-Mode") === "navigate";

      // Only /sw.js gets the cf override, because .js is the only one of the
      // three revalidated path classes that is on Cloudflare's default
      // cache-by-extension list; .html and /data/*.json are not cached at the
      // edge at all, so a cf override there would be pure risk for no effect.
      // Every other request keeps the single-argument fetch(request) call:
      // passing an init rebuilds the request via `new Request(request, init)`,
      // which downgrades mode "navigate" to "same-origin" and changes redirect
      // handling. Access answers a signed-out visit with a 302, and it is the
      // untouched incoming request (redirect "manual") that lets that 302 reach
      // the browser; rebuilding it risks a throw that lands in the outer catch
      // and shows the offline page instead of the Access login page.
      const edgeBypass = pathname === "/sw.js" && !isNavigation;
      const response = edgeBypass
        ? await fetch(request, { cf: { cacheTtl: 0 } })
        : await fetch(request);

      if (ORIGIN_DOWN_STATUS.has(response.status)) {
        return buildOfflineResponse(request.url);
      }

      // 3xx, 401 and 403 are Cloudflare Access's login flow, not cacheable
      // content: rewriting their headers could break the round trip that gets a
      // signed-out visitor to the login page and back, so they pass through
      // untouched. 304 must stay out of this gate — under "no-cache" it is the
      // ordinary answer to a revalidation, and leaving it unrewritten would drop
      // the header on the most frequently served response of all.
      if (
        !revalidate ||
        ((response.status >= 300 && response.status < 400) && response.status !== 304) ||
        response.status === 401 ||
        response.status === 403
      ) {
        return response;
      }

      // The header rewrite is cosmetic next to site availability: if it throws,
      // hand back the untouched origin response instead of a Worker error page.
      try {
        return withRevalidation(response);
      } catch (e) {
        return response;
      }
    } catch (e) {
      return buildOfflineResponse(request.url);
    }
  }
};
