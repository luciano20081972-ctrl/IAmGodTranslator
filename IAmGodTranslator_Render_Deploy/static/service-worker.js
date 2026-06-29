const CACHE_NAME = "iamgodtranslator-v8-static";
const STATIC_ASSETS = [
  "/manifest.json",
  "/static/icons/icon.svg",
];

const NETWORK_FIRST_PATHS = new Set([
  "/",
  "/index.html",
  "/static/app.js",
  "/static/styles.css",
]);

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);

  if (request.method !== "GET" || url.origin !== self.location.origin || url.pathname.startsWith("/api/")) {
    return;
  }

  if (request.mode === "navigate" || NETWORK_FIRST_PATHS.has(url.pathname)) {
    event.respondWith(networkFirst(request, shouldCacheShellAsset(url.pathname)));
    return;
  }

  event.respondWith(cacheFirst(request));
});

function shouldCacheShellAsset(pathname) {
  return pathname === "/static/app.js" || pathname === "/static/styles.css";
}

async function networkFirst(request, shouldCache) {
  try {
    const response = await fetch(request, { cache: "no-store" });

    if (shouldCache && response.ok) {
      const cache = await caches.open(CACHE_NAME);
      await cache.put(request, response.clone());
    }

    return response;
  } catch (_error) {
    const cached = await caches.match(request);

    if (cached) {
      return cached;
    }

    throw _error;
  }
}

async function cacheFirst(request) {
  const cached = await caches.match(request);

  if (cached) {
    return cached;
  }

  const response = await fetch(request);

  if (response.ok) {
    const cache = await caches.open(CACHE_NAME);
    await cache.put(request, response.clone());
  }

  return response;
}
