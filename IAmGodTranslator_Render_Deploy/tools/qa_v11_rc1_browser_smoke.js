const {chromium} = require("playwright");
const path = require("node:path");

const baseUrl = process.env.GT_RC1_BASE_URL || "http://127.0.0.1:8000";
const fixtureEvidence = process.env.GT_VERIFY_SCREENSHOTS;
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

function collectErrors(page, errors) {
  page.on("pageerror", (err) => errors.push(err.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(`${message.text()} (${message.location().url})`);
  });
  page.on("requestfailed", (request) => {
    if (!request.url().includes("/api/account/")) errors.push(`request failed: ${request.url()}`);
  });
}

async function checkGuestStartup(page) {
  const [account, session] = await Promise.all([
    page.waitForResponse((response) => new URL(response.url()).pathname === "/api/account/me"),
    page.waitForResponse((response) => new URL(response.url()).pathname === "/api/admin/session"),
    page.goto(`${baseUrl}/#/home`, {waitUntil: "domcontentloaded"}),
  ]);
  requireCheck("guest account request completed", account.ok() && (await account.json()).authenticated === false);
  requireCheck("guest session request completed", session.ok() && (await session.json()).role === "guest");
  await page.locator("#accountBtn span:last-child").filter({hasText: /^Guest$/}).waitFor({state: "attached"});
  requireCheck("guest activity button hidden", await page.locator("#jobCenterBtn").getAttribute("hidden") !== null);
  requireCheck("guest activity banner hidden", await page.locator("#activityBanner").getAttribute("hidden") !== null);
}

async function checkTranslatorActivity(context, errors) {
  const page = await context.newPage();
  collectErrors(page, errors);
  try {
    await page.route("**/api/account/me", (route) => route.fulfill({
      json: {ok: true, authenticated: true, user: {display_name: "Fixture Translator", role: "translator"}},
    }));
    await page.route("**/api/admin/session", (route) => route.fulfill({
      json: {ok: true, admin: false, role: "translator"},
    }));
    await page.route("**/api/account/home", (route) => route.fulfill({json: {ok: true}}));
    await page.route(/\/api\/translation\/jobs(?:\?|$)/, (route) => route.fulfill({
      json: {ok: true, jobs: [{id: "fixture-job", status: "queued", novel_id: "partial-novel"}]},
    }));
    await page.goto(`${baseUrl}/#/home`, {waitUntil: "domcontentloaded"});
    await page.locator("#accountBtn span:last-child").filter({hasText: /^Fixture Translator$/}).waitFor();
    await page.locator("#jobCenterBtn").filter({hasText: /^Activity 1$/}).waitFor();
    await page.locator("#activityBanner").getByText("1 active translation job", {exact: true}).waitFor();
    await waitForRoute(page, ".home-hero h1", "translator home");
  } finally {
    await page.close();
  }
}

async function run() {
  const results = [];
  const selectedViewports = fixtureEvidence && process.env.GT_VERIFY_DESKTOP_ONLY === "1"
    ? viewports.slice(0, 1) : viewports;
  for (const viewport of selectedViewports) {
    const browser = await chromium.launch({
      headless: true,
      ...(fixtureEvidence ? {executablePath: process.env.GT_VERIFY_CHROMIUM} : {}),
    });
    try {
      const context = await browser.newContext({
        viewport: {width: viewport.width, height: viewport.height},
        reducedMotion: viewport.width <= 390 ? "reduce" : "no-preference",
        ...(fixtureEvidence ? {serviceWorkers: "block"} : {}),
      });
      if (fixtureEvidence) {
        await context.route("**/*", (route) => {
          const url = new URL(route.request().url());
          if (url.origin === new URL(baseUrl).origin) return route.continue();
          // Guest fixtures do not use Supabase. Fulfill its script locally so this
          // run has no external CDN traffic and no expected console error.
          if (url.href === "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2") {
            return route.fulfill({contentType: "application/javascript", body: ""});
          }
          return route.abort();
        });
      }
      const page = await context.newPage();
      const errors = [];
      collectErrors(page, errors);

      if (fixtureEvidence) await checkGuestStartup(page);
      else await page.goto(`${baseUrl}/#/home`, {waitUntil: "domcontentloaded"});
      await waitForRoute(page, ".home-hero h1", `home ${viewport.name}`);
      const measuredViewport = await page.evaluate(() => ({width: window.innerWidth, height: window.innerHeight}));
      requireCheck(`viewport measured at ${viewport.name}`, measuredViewport.width === viewport.width && measuredViewport.height === viewport.height);
      if (fixtureEvidence && [1366, 390].includes(viewport.width)) {
        const variant = viewport.width === 390 ? "mobile" : "desktop";
        await page.screenshot({path: path.join(fixtureEvidence, `browser-home-${variant}.png`)});
      }
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
      requireCheck("Reader menu control present", await page.locator("#readerMenuToggle").count() === 1);

      await page.goto(`${baseUrl}/#/settings/accessibility`, {waitUntil: "domcontentloaded"});
      await waitForRoute(page, ".settings-root, .settings-subpage", `settings ${viewport.name}`);
      await assertNoOverflow(page, `settings ${viewport.name}`);

      const translatorActivity = Boolean(fixtureEvidence && viewport.width === 1366);
      if (translatorActivity) await checkTranslatorActivity(context, errors);
      requireCheck(`no console errors on ${viewport.name}: ${errors.join("; ")}`, errors.length === 0);
      results.push({viewport: viewport.name, measuredViewport, consoleErrors: errors,
        guestStartup: Boolean(fixtureEvidence), translatorActivity,
        home: true, library: true, novel: true, reader: true, settings: true, noOverflow: true, namedControls: true});
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
