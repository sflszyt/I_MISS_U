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
});