const GT_CACHE_VERSION = "iagt-app-shell-11.6.2-a2-1";
const APP_SHELL = new Map([
  ["/", ["text/html"]],
  ["/static/styles.css?v=11.6.2-v11.6.1-mobile-home-20260831", ["text/css"]],
  ["/static/app.js?v=11.6.2-v11.6.1-mobile-home-20260831", ["text/javascript", "application/javascript"]],
  ["/static/vendor/minisearch/minisearch-7.2.0.min.js?v=7.2.0", ["text/javascript", "application/javascript"]],
  ["/manifest.webmanifest", ["application/json", "application/manifest+json"]],
  ["/static/icons/dark-hour-icon.svg", ["image/svg+xml"]],
]);

async function fetchShellAsset([path, mediaTypes]) {
  const url = new URL(path, self.location.origin);
  const response = await fetch(url, {
    credentials: "omit", mode: "same-origin", redirect: "error", cache: "no-store",
  });
  const type = (response.headers.get("Content-Type") || "").split(";")[0].trim().toLowerCase();
  const policy = response.headers.get("Cache-Control") || "";
  const vary = (response.headers.get("Vary") || "").toLowerCase().split(",");
  if (response.type !== "basic" || response.status !== 200 || response.redirected ||
      response.url !== url.href || !mediaTypes.includes(type) ||
      /\b(private|no-store)\b/i.test(policy) || response.headers.has("Content-Range") ||
      vary.some((field) => field.trim() && field.trim() !== "accept-encoding")) {
    throw new Error(`Unsuitable public shell response for ${path}`);
  }
  return [path, response];
}

async function installShell() {
  const assets = await Promise.all(Array.from(APP_SHELL, fetchShellAsset));
  const cache = await caches.open(GT_CACHE_VERSION);
  await Promise.all(assets.map(([path, response]) => cache.put(path, response)));
  await self.skipWaiting();
}

self.addEventListener("install", (event) => event.waitUntil(installShell()));

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys
        .filter((key) => /^iagt-app-shell-\d+\.\d+\.\d+(?:-[a-z\d.-]+)?$/.test(key) && key !== GT_CACHE_VERSION)
        .map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") event.waitUntil(self.skipWaiting());
});

async function networkOrPublicShell(request, path) {
  try {
    return await fetch(request);
  } catch {
    const cached = await caches.match(path, {cacheName: GT_CACHE_VERSION});
    return cached || Response.error();
  }
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin ||
      request.headers.has("Authorization") || request.headers.has("Range") || request.cache === "no-store") return;
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/auth/") || url.pathname.startsWith("/admin/")) return;
  const path = url.pathname + url.search;
  if (!APP_SHELL.has(path) || (request.mode === "navigate" && path !== "/")) return;
  event.respondWith(networkOrPublicShell(request, path));
});
