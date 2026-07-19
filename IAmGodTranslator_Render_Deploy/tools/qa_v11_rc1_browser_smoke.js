const {chromium} = require("playwright");

const baseUrl = process.env.GT_RC1_BASE_URL || "http://127.0.0.1:8000";
const viewports = [
  {width: 1366, height: 768, name: "1366x768"},
  {width: 1920, height: 1080, name: "1920x1080"},
  {width: 390, height: 844, name: "390x844"},
  {width: 360, height: 800, name: "360x800"},
  {width: 820, height: 1180, name: "820x1180"},
];

function requireCheck(label, condition) {
  if (!condition) throw new Error(label);
}

async function assertNoOverflow(page, label) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  requireCheck(`${label} horizontal overflow ${overflow}`, overflow <= 1);
}

async function waitForRoute(page, selector, label) {
  for (let attempt = 0; attempt < 80; attempt += 1) {
    if (await page.locator(selector).count()) return;
    await page.waitForTimeout(250);
  }
  const appText = await page.locator("#app").innerText({timeout: 1000}).catch(() => "");
  throw new Error(`${label} did not render ${selector}. Current app text: ${appText.slice(0, 500)}`);
}

async function run() {
  const results = [];
  for (const viewport of viewports) {
    const browser = await chromium.launch({headless: true});
    try {
      const context = await browser.newContext({
        viewport: {width: viewport.width, height: viewport.height},
        reducedMotion: viewport.width <= 390 ? "reduce" : "no-preference",
      });
      const page = await context.newPage();
      const errors = [];
      page.on("pageerror", (err) => errors.push(err.message));
      page.on("console", (message) => {
        if (message.type() === "error") errors.push(message.text());
      });
      page.on("requestfailed", (request) => {
        if (!request.url().includes("/api/account/")) errors.push(`request failed: ${request.url()}`);
      });

      await page.goto(`${baseUrl}/#/home`, {waitUntil: "domcontentloaded"});
      await waitForRoute(page, ".home-hero h1", `home ${viewport.name}`);
      await assertNoOverflow(page, `home ${viewport.name}`);
      await page.keyboard.press(process.platform === "darwin" ? "Meta+K" : "Control+K");
      await page.waitForSelector("#commandDialog[open]");
      const namedControls = await page.locator("button, a, input, select, textarea").evaluateAll((nodes) => nodes.filter((node) => {
        const element = node;
        const label = element.getAttribute("aria-label") || element.getAttribute("title") || element.textContent || element.getAttribute("placeholder") || "";
        return !label.trim();
      }).length);
      requireCheck(`interactive controls have names on ${viewport.name}`, namedControls === 0);
      await page.keyboard.press("Escape");

      await page.goto(`${baseUrl}/#/library`, {waitUntil: "domcontentloaded"});
      await waitForRoute(page, "#novelGrid", `library ${viewport.name}`);
      await assertNoOverflow(page, `library ${viewport.name}`);

      await page.goto(`${baseUrl}/#/novel/partial-novel`, {waitUntil: "domcontentloaded"});
      await waitForRoute(page, ".novel-hero h1", `novel ${viewport.name}`);
      await assertNoOverflow(page, `novel ${viewport.name}`);

      await page.goto(`${baseUrl}/#/reader/partial-novel/1/original`, {waitUntil: "domcontentloaded"});
      await waitForRoute(page, ".reader-text", `reader ${viewport.name}`);
      await assertNoOverflow(page, `reader ${viewport.name}`);
      requireCheck("Reference hidden for guest", await page.locator(".reader-source-switch button", {hasText: "Reference"}).count() === 0);
      requireCheck("Reader controls present", await page.locator("#openChapterDrawer").count() === 1);

      await page.goto(`${baseUrl}/#/settings/accessibility`, {waitUntil: "domcontentloaded"});
      await waitForRoute(page, ".settings-layout", `settings ${viewport.name}`);
      await assertNoOverflow(page, `settings ${viewport.name}`);

      requireCheck(`no console errors on ${viewport.name}`, errors.length === 0);
      results.push({viewport: viewport.name, home: true, library: true, novel: true, reader: true, settings: true, noOverflow: true, namedControls: true});
      await context.close();
    } finally {
      await browser.close();
    }
  }
  console.log(JSON.stringify({ok: true, results}, null, 2));
}

run().catch((error) => {
  console.error(error.stack || error.message);
  process.exit(1);
});
