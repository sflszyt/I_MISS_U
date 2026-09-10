// people/mama_for_father/site/sw.js

var CACHE_NAME = 'imissu-dad-offline-v1';

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(function (cache) {
        return cache.addAll(['/offline.html']);
      })
      .then(function () {
        return self.skipWaiting();
      })
  );
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys()
      .then(function (keys) {
        return Promise.all(keys.map(function (key) {
          if (key.indexOf('imissu-dad-offline-') === 0 && key !== CACHE_NAME) {
            return caches.delete(key);
          }
          return undefined;
        }));
      })
      .then(function () {
        return self.clients.claim();
      })
  );
});

function isOriginDown(response) {
  var down = [502, 503, 504, 521, 522, 523, 524, 530];
  return down.indexOf(response.status) !== -1;
}

function inlineFallback() {
  return new Response(
    '<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">' +
    '<meta name="viewport" content="width=device-width, initial-scale=1">' +
    '<title>她今天不在</title></head><body>' +
    '<h1>她今天不在</h1><p>等电脑醒过来，她就回来了。</p>' +
    '</body></html>',
    {
      status: 200,
      headers: { 'Content-Type': 'text/html; charset=utf-8' }
    }
  );
}

function cachedOffline() {
  // caches.match CAN reject (private mode, eviction). Every path must resolve.
  return caches.match('/offline.html')
    .then(function (response) {
      return response || inlineFallback();
    })
    .catch(function () {
      return inlineFallback();
    });
}

self.addEventListener('fetch', function (event) {
  // Handle ONLY top-level GET navigations. Everything else (HEAD probes from
  // offline.html, /tts, /v1/chat/completions, all assets) goes straight to
  // the network untouched - we must never cache or replay her voice or the
  // persona's replies, and the HEAD probe must see the true origin state.
  if (event.request.mode !== 'navigate' || event.request.method !== 'GET') {
    return;
  }

  event.respondWith(
    fetch(event.request)
      .then(function (response) {
        if (isOriginDown(response)) {
          return cachedOffline();
        }
        // Pass through transparently, including 3xx/401/403 (Cloudflare
        // Access login and all normal traffic).
        return response;
      })
      .catch(function () {
        // Network failure, tunnel down with no Cloudflare answer, etc.
        return cachedOffline();
      })
  );

  // Background warm-up for the two big HTML entry points. The origin server
  // sends no Cache-Control, so the browser falls back to heuristic freshness
  // (10% of now - Last-Modified) and keeps handing back the old page after a
  // site rebuild. A plain fetch(url, { cache: 'no-cache' }) forces a
  // conditional request, which makes the browser's own HTTP cache layer
  // refresh its records for these two URLs with whatever the server has now.
  //
  // These are ordinary fetches built from a URL string, deliberately NOT a
  // rebuilt navigation request: the Fetch spec says that constructing a
  // Request whose mode is 'navigate' together with a non-empty init downgrades
  // mode to 'same-origin', which changes the redirect semantics - the SW would
  // then follow Cloudflare Access' 302 to the login page itself and hand a
  // redirected:true response to respondWith, the browser would throw a
  // TypeError, and she would not be able to get into the site at all. That is
  // also why the main chain above stays a single-argument fetch(event.request)
  // and why event.request is never wrapped or modified.
  //
  // The bodies are discarded on purpose: nothing here touches Cache Storage,
  // and her voice and the persona's replies are never cached or replayed
  // anywhere - offline.html remains the only stored entry. Every fetch has
  // its own .catch so an offline warm-up failure cannot turn this waitUntil
  // into a rejection (which would spew console errors), and the joined
  // Promise.all gets one more .catch for the same reason.
  event.waitUntil(
    Promise.all([
      fetch('/companion.html', { cache: 'no-cache' })
        .catch(function () {}),
      fetch('/avatar.html', { cache: 'no-cache' })
        .catch(function () {})
    ]).catch(function () {})
  );
});
