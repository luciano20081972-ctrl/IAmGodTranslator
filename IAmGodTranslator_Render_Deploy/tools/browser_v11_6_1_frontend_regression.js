const http = require("http");
const fs = require("fs");
const path = require("path");
const {chromium} = require("playwright");

const root = path.resolve(__dirname, "..");
const indexHtml = fs.readFileSync(path.join(root, "templates", "index.html"), "utf8");
const staticRoot = path.join(root, "static");

const longTitle = "Lord Of The Frozen Winter Starting With Daily Intelligence Reports";
const chapters = Array.from({length: 50}, (_, index) => ({
  chapter_number: index + 1,
  title: `Chapter ${index + 1}`,
  english_title: "",
  has_original: true,
  has_reference: false,
  has_ai: false,
  has_english: true,
  translation_status: "translated",
}));

function json(response, payload, delay = 0) {
  setTimeout(() => {
    response.writeHead(200, {"Content-Type": "application/json", "Cache-Control": "no-store"});
    response.end(JSON.stringify(payload));
  }, delay);
}

function createServer() {
  const requests = [];
  const server = http.createServer((request, response) => {
    const url = new URL(request.url, "http://127.0.0.1");
    requests.push(url.pathname + url.search);
    if (url.pathname === "/api/auth/config") return json(response, {ok: true, configured: false}, 30000);
    if (url.pathname === "/api/account/me") return json(response, {ok: true, authenticated: false, role: "guest"});
    if (url.pathname === "/api/admin/session") return json(response, {ok: true, admin: false, role: "guest"});
    if (url.pathname === "/api/novels") {
      return json(response, {
        ok: true,
        novels: [{
          id: "i-am-god",
          title: longTitle,
          summary: "A long-title fixture used for mobile layout regression.",
          author: "Fixture",
          status: "active",
          chapter_count: 908,
          english_count: 908,
          readable_count: 908,
          updated_at: "2026-08-30T00:00:00Z",
          is_archived: false,
        }],
      });
    }
    if (url.pathname === "/api/novels/i-am-god") {
      return json(response, {
        ok: true,
        novel: {id: "i-am-god", title: longTitle, summary: "Fixture", status: "active"},
        counts: {total: 908, original: 908, reference: 0, ai: 0, english: 908, needs_translation: 0},
      });
    }
    if (url.pathname === "/api/novels/i-am-god/library") {
      return json(response, {ok: true, novel: {id: "i-am-god", title: longTitle}, total: 908, chapters});
    }
    if (url.pathname === "/api/novels/i-am-god/chapters/1/english") {
      return json(response, {
        ok: true,
        novel_id: "i-am-god",
        chapter_number: 1,
        title: "Chapter 1",
        text: "Chapter 1 fixture paragraph.\n\nSecond fixture paragraph for the reader.",
        source: "english",
        neighbors: {previous: null, next: 2},
        content_hash: "fixture-hash-1",
      });
    }
    if (url.pathname === "/manifest.webmanifest") {
      response.writeHead(200, {"Content-Type": "application/manifest+json"});
      return response.end(JSON.stringify({name: "IAmGodTranslator", start_url: "/"}));
    }
    if (url.pathname === "/sw.js") {
      response.writeHead(200, {"Content-Type": "text/javascript"});
      return response.end("");
    }
    if (url.pathname.startsWith("/static/")) {
      const clean = url.pathname.replace(/^\/static\//, "");
      const filePath = path.join(staticRoot, clean);
      if (!filePath.startsWith(staticRoot) || !fs.existsSync(filePath)) {
        response.writeHead(404);
        return response.end("not found");
      }
      const type = filePath.endsWith(".css") ? "text/css" : filePath.endsWith(".js") ? "text/javascript" : "application/octet-stream";
      response.writeHead(200, {"Content-Type": type});
      return response.end(fs.readFileSync(filePath));
    }
    response.writeHead(200, {"Content-Type": "text/html"});
    response.end(indexHtml);
  });
  return {server, requests};
}

function fail(message, details = {}) {
  const error = new Error(message);
  error.details = details;
  throw error;
}

async function run() {
  const {server, requests} = createServer();
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const baseUrl = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({headless: true});
  const context = await browser.newContext({viewport: {width: 390, height: 844}, isMobile: true});
  const page = await context.newPage();
  const consoleErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  const start = Date.now();
  await page.goto(`${baseUrl}/#/home`, {waitUntil: "domcontentloaded"});
  await page.getByText(longTitle).first().waitFor({timeout: 1800});
  const homeUsefulMs = Date.now() - start;
  if (homeUsefulMs > 1800) fail("Home waited for slow auth bootstrap", {homeUsefulMs});

  const coverBox = await page.locator(".continue-cover").first().boundingBox();
  const titleBox = await page.locator(".continue-card h1").first().boundingBox();
  if (!coverBox || !titleBox) fail("Continue card boxes missing");
  if (titleBox.x < coverBox.x + coverBox.width - 1 && titleBox.y < coverBox.y + coverBox.height) {
    fail("Continue Reading title overlaps cover", {coverBox, titleBox});
  }

  const beforeLibraryRequests = requests.length;
  const libraryStart = Date.now();
  await page.goto(`${baseUrl}/#/library`, {waitUntil: "domcontentloaded"});
  await page.locator(".novel-card h2").first().waitFor({timeout: 700});
  const libraryUsefulMs = Date.now() - libraryStart;
  const newLibraryNovelRequests = requests.slice(beforeLibraryRequests).filter((item) => item === "/api/novels").length;
  if (libraryUsefulMs > 700) fail("Library did not use in-memory public novel cache", {libraryUsefulMs});
  if (newLibraryNovelRequests > 0) fail("Library forced duplicate /api/novels request", {newLibraryNovelRequests});

  await page.goto(`${baseUrl}/#/reader/i-am-god/1/english`, {waitUntil: "domcontentloaded"});
  await page.getByText("Chapter 1 fixture paragraph.").waitFor({timeout: 1200});

  await page.goto(`${baseUrl}/#/settings/appearance`, {waitUntil: "domcontentloaded"});
  await page.locator('input[data-pref="theme"][value="forest"]').check({force: true});
  await page.locator('input[data-pref="density"][value="compact"]').check({force: true});
  const themeState = await page.evaluate(() => ({
    theme: document.body.dataset.theme,
    density: document.body.dataset.density,
    bg: getComputedStyle(document.body).getPropertyValue("--bg").trim(),
    gap: getComputedStyle(document.body).getPropertyValue("--dh-section-gap").trim(),
  }));
  if (themeState.theme !== "forest" || themeState.density !== "compact") fail("Appearance preferences did not apply", themeState);
  if (!themeState.bg || !themeState.gap) fail("Theme/density tokens missing", themeState);

  const switchBox = await page.locator(".pref-switch").first().boundingBox();
  if (!switchBox || switchBox.height < 28 || switchBox.width < 48) fail("Switch geometry is too small", {switchBox});

  const navBoxes = await page.locator(".mobile-bottom-nav a, .mobile-bottom-nav button").evaluateAll((items) => items.map((item) => {
    const box = item.getBoundingClientRect();
    const style = getComputedStyle(item);
    return {width: box.width, height: box.height, display: style.display, alignItems: style.alignItems, justifyItems: style.justifyItems, textAlign: style.textAlign};
  }));
  if (navBoxes.length !== 4 || navBoxes.some((box) => box.height < 44 || box.textAlign !== "center")) {
    fail("Mobile bottom nav items are not centered touch targets", {navBoxes});
  }

  await page.reload({waitUntil: "domcontentloaded"});
  const persisted = await page.evaluate(() => ({theme: document.body.dataset.theme, density: document.body.dataset.density}));
  if (persisted.theme !== "forest" || persisted.density !== "compact") fail("Appearance preferences did not persist after reload", persisted);

  await browser.close();
  server.close();
  const accountRequests = requests.filter((item) => item === "/api/account/me").length;
  const result = {
    ok: consoleErrors.length === 0,
    home_useful_ms_with_30s_auth_config: homeUsefulMs,
    library_useful_ms_from_public_cache: libraryUsefulMs,
    duplicate_account_requests: accountRequests,
    console_errors: consoleErrors,
    total_requests: requests.length,
  };
  if (!result.ok) fail("Console errors detected", result);
  return result;
}

run()
  .then((result) => {
    console.log(JSON.stringify(result, null, 2));
  })
  .catch((error) => {
    console.error(JSON.stringify({ok: false, error: error.message, details: error.details || {}}, null, 2));
    process.exit(1);
  });
