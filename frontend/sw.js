// AIR AI Progressive Web App Service Worker
const CACHE_NAME = "hs-ai-shell-v2";
const STATIC_ASSETS = [
  "/",
  "/welcome",
  "/chat",
  "/dashboard",
  "/static/css/theme.css",
  "/static/js/chat.js",
  "/static/js/portal.js",
  "/static/js/dashboard.js",
  "/manifest.json"
];

// Install: Cache static shell assets
self.addEventListener("install", (evt) => {
  evt.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch((err) => {
        console.warn("[PWA SW] Pre-caching non-fatal warning:", err);
      });
    })
  );
  self.skipWaiting();
});

// Activate: Clean up older cache generations
self.addEventListener("activate", (evt) => {
  evt.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
      );
    })
  );
  self.clients.claim();
});

// Fetch: Network-first policy. NEVER cache sensitive AI responses or WebSockets
self.addEventListener("fetch", (evt) => {
  const url = new URL(evt.request.url);

  // Bypass caching completely for AI chat, WebSocket, uploads, and APIs
  if (
    url.pathname.startsWith("/api/") ||
    url.pathname.startsWith("/ws/") ||
    url.pathname.startsWith("/generate_204") ||
    url.pathname.startsWith("/hotspot-detect") ||
    evt.request.method !== "GET"
  ) {
    return; // Pass through to live network
  }

  evt.respondWith(
    fetch(evt.request)
      .then((networkRes) => {
        // Clone and cache successful GET responses for static assets
        if (networkRes && networkRes.status === 200 && networkRes.type === "basic") {
          const resClone = networkRes.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(evt.request, resClone));
        }
        return networkRes;
      })
      .catch(() => {
        // Offline fallback to cached shell
        return caches.match(evt.request).then((cached) => {
          if (cached) return cached;
          if (evt.request.headers.get("accept")?.includes("text/html")) {
            return caches.match("/chat");
          }
        });
      })
  );
});

