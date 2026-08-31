const http = require("http");
const fs = require("fs");
const path = require("path");
const {chromium, webkit} = require("playwright");

const root = path.resolve(__dirname, "..");
const indexHtml = fs.readFileSync(path.join(root, "templates", "index.html"), "utf8");
const staticRoot = path.join(root, "static");
const outputDir = path.join(root, "qa_screenshots_v11_6_1_mobile_home");
const longTitle = "Lord Of The Frozen Winter Starting With Daily Intelligence Reports";

function json(response, payload, delay = 0) {
  setTimeout(() => {
    response.writeHead(200, {"Content-Type": "application/json", "Cache-Control": "no-store"});
    response.end(JSON.stringify(payload));
  }, delay);
}

function createServer() {
  const server = http.createServer((request, response) => {
    const url = new URL(request.url, "http://127.0.0.1");
    if (url.pathname === "/api/auth/config") return json(response, {ok: true, configured: false}, 30000);
    if (url.pathname === "/api/account/me") return json(response, {ok: true, authenticated: false, role: "guest"});
    if (url.pathname === "/api/admin/session") return json(response, {ok: true, admin: false, role: "guest"});
    if (url.pathname === "/api/novels") {
      return json(response, {
        ok: true,
        novels: [{
          id: "long-title",
          title: longTitle,
          summary: "Mobile overlap regression fixture.",
          author: "A Very Long Author Name That Should Wrap Without Breaking The Layout",
          status: "active",
          chapter_count: 475,
          english_count: 475,
          readable_count: 475,
          updated_at: "2026-08-31T00:00:00Z",
          is_archived: false,
        }],
      }, 100);
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
      const filePath = path.join(staticRoot, url.pathname.replace(/^\/static\//, ""));
      if (!filePath.startsWith(staticRoot) || !fs.existsSync(filePath)) {
        response.writeHead(404);
        return response.end("not found");
      }
      response.writeHead(200, {"Content-Type": filePath.endsWith(".css") ? "text/css" : "text/javascript"});
      return response.end(fs.readFileSync(filePath));
    }
    response.writeHead(200, {"Content-Type": "text/html"});
    response.end(indexHtml);
  });
  return server;
}

function intersects(a, b) {
  return !(a.right <= b.left || b.right <= a.left || a.bottom <= b.top || b.bottom <= a.top);
}

async function runBrowser(browserType, baseUrl, widths) {
  const browser = await browserType.launch({headless: true});
  const results = [];
  for (const width of widths) {
    const context = await browser.newContext({viewport: {width, height: 700}, isMobile: true});
    const page = await context.newPage();
    const consoleErrors = [];
    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });
    await page.goto(`${baseUrl}/#/home`, {waitUntil: "domcontentloaded"});
    await page.locator(".continue-card h1").getByText(longTitle).waitFor({timeout: 1800});
    const metrics = await page.evaluate(() => {
      const rect = (selector) => {
        const node = document.querySelector(selector);
        if (!node) return null;
        const box = node.getBoundingClientRect();
        return {left: box.left, right: box.right, top: box.top, bottom: box.bottom, width: box.width, height: box.height};
      };
      return {
        title: rect(".continue-card h1"),
        actions: rect(".continue-card .actions"),
        search: rect(".continue-card .actions [data-home-search]"),
        cover: rect(".continue-card .continue-cover"),
        cta: rect(".continue-card .actions .button.primary"),
        card: rect(".continue-card"),
        horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
        startupMetrics: window.__IAGT_STARTUP_METRICS || [],
      };
    });
    if (!metrics.title || !metrics.search || !metrics.actions || !metrics.cover || !metrics.cta) {
      throw new Error(`${browserType.name()} ${width}: missing Home geometry`);
    }
    const screenshotPath = path.join(outputDir, `${browserType.name()}-home-${width}.png`);
    await page.screenshot({path: screenshotPath, fullPage: true});
    results.push({browser: browserType.name(), width, ...metrics, screenshot: screenshotPath, consoleErrors});
    if (intersects(metrics.title, metrics.search)) throw new Error(`${browserType.name()} ${width}: Search overlaps Continue title`);
    if (intersects(metrics.title, metrics.cta)) throw new Error(`${browserType.name()} ${width}: CTA overlaps Continue title`);
    if (intersects(metrics.cover, metrics.title)) throw new Error(`${browserType.name()} ${width}: Cover overlaps Continue title`);
    if (metrics.horizontalOverflow) throw new Error(`${browserType.name()} ${width}: horizontal overflow`);
    if (consoleErrors.length) throw new Error(`${browserType.name()} ${width}: console errors ${consoleErrors.join("; ")}`);
    await context.close();
  }
  await browser.close();
  return results;
}

async function main() {
  fs.mkdirSync(outputDir, {recursive: true});
  const server = createServer();
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const baseUrl = `http://127.0.0.1:${server.address().port}`;
  const widths = [320, 375, 390, 430];
  try {
    const chromiumResults = await runBrowser(chromium, baseUrl, widths);
    let webkitResults = [];
    try {
      webkitResults = await runBrowser(webkit, baseUrl, [390]);
    } catch (error) {
      webkitResults = [{browser: "webkit", skipped: true, reason: error.message}];
    }
    console.log(JSON.stringify({ok: true, chromium: chromiumResults, webkit: webkitResults}, null, 2));
  } finally {
    server.close();
  }
}

main().catch((error) => {
  console.error(JSON.stringify({ok: false, error: error.message}, null, 2));
  process.exit(1);
});
