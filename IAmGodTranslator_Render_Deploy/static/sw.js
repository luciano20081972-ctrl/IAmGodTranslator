// Generated shell inventory.
const GT_CACHE_VERSION = "iagt-app-shell-11.6.2-76887a00f5d488fa799cab40d77eda3645cc8b72468e2b1b115999548f787994";
const APP_SHELL = new Map([
  ["/static/styles.css?v=11.6.2-ee7335cdc6c3f4eec1338d23807dacf04b51e1b34e8a8ddb9663c21273b8fbb2", [["text/css"], "sha256-7nM1zcbD9O7BM40jgH2s8EtR4bNOio3blmPCEnO4+7I="]],
  ["/static/vendor/supabase/supabase-2.119.2.js", [["text/javascript", "application/javascript"], "sha256-iBavBNmRXbuhiC1vhPC0AtxAJoBjpj2cZtJPUvNxwmM="]],
  ["/static/vendor/minisearch/minisearch-7.2.0.min.js?v=7.2.0", [["text/javascript", "application/javascript"], "sha256-igW0J4XbRI8sGeJKaiEHIEyCVWX+T5WqabeWUrryboI="]],
  ["/static/app.js?v=11.6.2-b3b1428f329a2ba2c6ca537e12051ac97c2b26c2a119e8a533f76df6e58ea5cc", [["text/javascript", "application/javascript"], "sha256-s7FCjzKaK6LGylN+EgUayXwrJsKhGeilM/dt9uWOpcw="]],
  ["/manifest.webmanifest", [["application/json", "application/manifest+json"], "sha256-TZTBJSvvTWmYQCClMIeQF3kx1KVNI5/czNYZ+JHENqE="]],
  ["/static/icons/dark-hour-icon.svg", [["image/svg+xml"], "sha256-pNZ4F3BV9xDrmvU+LLspwzyK/gQ3dtQdic+qLWUZeHE="]],
  ["/", [["text/html"], "sha256-pqhFo5eeRB/AZ7SO5EOqbnGCT8GsVKCyppNNo9Di5Fk="]]
]);
// End shell inventory.

async function fetchShellAsset([path, [mediaTypes, integrity]]) {
  const url = new URL(path, self.location.origin);
  const response = await fetch(url, {
    credentials: "omit", mode: "same-origin", redirect: "error", cache: "no-store", integrity,
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
