// Exercise the worker's registered event handlers with synthetic Fetch and Cache Storage.
const {test} = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
const path = require("node:path");
const script = fs.readFileSync(path.join(__dirname, "../static/sw.js"), "utf8");
const origin = "https://fixture.invalid";

function fixture() {
  const stores = new Map();
  const handlers = new Map();
  const state = {skips: 0, claims: 0};
  const caches = {
    keys: async () => [...stores.keys()],
    delete: async (key) => stores.delete(key),
    async open(key) {
      if (!stores.has(key)) stores.set(key, new Map());
      return {put: async (path, value) => stores.get(key).set(path, value)};
    },
    match: async (path, {cacheName}) => stores.get(cacheName)?.get(path),
  };
  const self = {
    location: {origin}, addEventListener: (name, handler) => handlers.set(name, handler),
    skipWaiting: async () => { state.skips++; },
    clients: {claim: async () => { state.claims++; }},
  };
  const context = vm.createContext({URL, Response, self, caches, fetch: async (url, options) => {
    assert.match(options.integrity, /^sha256-[A-Za-z0-9+/]{43}=$/);
    assert.equal(options.credentials, "omit");
    assert.equal(options.redirect, "error");
    assert.equal(options.cache, "no-store");
    const types = {css: "text/css", js: "text/javascript", svg: "image/svg+xml", webmanifest: "application/json"};
    const mime = url.pathname === "/" ? "text/html" : types[url.pathname.split(".").pop()];
    assert.ok(mime);
    return {url: url.href, type: "basic", status: 200, headers: new Headers({"Content-Type": mime})};
  }});
  vm.runInContext(script, context);
  function dispatch(name, fields = {}) {
    let promise;
    const capture = (value) => { promise = value; };
    handlers.get(name)({waitUntil: capture, respondWith: capture, ...fields});
    return promise;
  }
  function request(path, overrides = {}) {
    return dispatch("fetch", {request: {
      url: new URL(path, origin).href, method: "GET", mode: "navigate", headers: new Headers(), ...overrides,
    }});
  }
  return {context, stores, state, dispatch, request};
}

test("install waits for anonymous shell writes, activate keeps current and unrelated caches", async () => {
  const f = fixture();
  await f.dispatch("install");
  const [current] = f.stores.keys();
  assert.equal(f.stores.get(current).size, 7);
  assert.equal(f.state.skips, 1);
  for (const name of ["other-app", "iagt-reader-cache-v1", "iagt-app-shell-11.6.2"]) f.stores.set(name, new Map());
  await f.dispatch("activate");
  assert.deepEqual([...f.stores.keys()], [current, "other-app", "iagt-reader-cache-v1"]);
  assert.equal(f.state.claims, 1);
  assert.equal(f.dispatch("message", {data: {type: "OTHER"}}), undefined);
  await f.dispatch("message", {data: {type: "SKIP_WAITING"}});
  assert.equal(f.state.skips, 2);
});

for (const [label, changes, headers] of [
  ["404", {status: 404}], ["500", {status: 500}], ["partial", {status: 206}],
  ["opaque", {type: "opaque"}], ["redirect", {redirected: true}], ["different URL", {url: origin + "/other"}],
  ["wrong MIME", {}, {"Content-Type": "application/json"}],
  ["private", {}, {"Cache-Control": "max-age=0, PRIVATE"}], ["no-store", {}, {"Cache-Control": "no-store"}],
  ["cookie variant", {}, {Vary: "Accept-Encoding, Cookie"}], ["authorization variant", {}, {Vary: "Authorization"}],
  ["unknown variant", {}, {Vary: "*"}],
]) {
  test(`install rejects ${label} before writing or advancing the update`, async () => {
    const f = fixture();
    const fetch = f.context.fetch;
    f.context.fetch = async (...args) => {
      const response = await fetch(...args);
      if (args[0].pathname === "/") {
        Object.assign(response, changes);
        for (const [name, value] of Object.entries(headers || {})) response.headers.set(name, value);
      }
      return response;
    };
    await assert.rejects(f.dispatch("install"), /Unsuitable public shell/);
    assert.equal(f.stores.size, 0);
    assert.equal(f.state.skips, 0);
  });
}

test("online responses pass through without writes; offline reads only the installed shell", async () => {
  const f = fixture();
  f.stores.set("unrelated", new Map([["/", "unrelated shell"]]));
  await f.dispatch("install");
  const cache = [...f.stores.values()][1];
  const installed = cache.get("/");
  for (const response of [new Response("error", {status: 503}), new Response("private", {headers: {"Cache-Control": "private"}})]) {
    f.context.fetch = async () => response;
    assert.equal(await f.request("/"), response);
    assert.equal(cache.get("/"), installed);
  }
  f.context.fetch = async () => { throw Error("offline"); };
  assert.equal(await f.request("/"), installed);
  assert.equal(await f.request("/manifest.webmanifest", {mode: "cors"}), cache.get("/manifest.webmanifest"));
  cache.delete("/");
  assert.equal((await f.request("/")).type, "error");
});

test("only exact public shell GETs participate in offline fallback", () => {
  const f = fixture();
  for (const path of ["/api", "/api/novels", "/auth", "/auth/callback", "/admin", "/admin/jobs",
    "/private", "/?account=x", "/static/app.js?v=other", "https://other.invalid/"]) {
    assert.equal(f.request(path), undefined, path);
  }
  for (const overrides of [{method: "POST"}, {headers: new Headers({Authorization: "synthetic"})},
    {headers: new Headers({Range: "bytes=0-4"})}, {cache: "no-store"}]) {
    assert.equal(f.request("/", overrides), undefined);
  }
});
