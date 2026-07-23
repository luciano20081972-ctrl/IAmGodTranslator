const app = document.querySelector("#app");
const nav = document.querySelector("#primaryNav");
const commandDialog = document.querySelector("#commandDialog");
const commandInput = document.querySelector("#commandInput");
const commandResults = document.querySelector("#commandResults");
const accountBtn = document.querySelector("#accountBtn");
const profileMenu = document.querySelector("#profileMenu");
const profileMenuItems = document.querySelector("#profileMenuItems");
const activityBanner = document.querySelector("#activityBanner");
const notificationCenter = document.querySelector("#notificationCenter");
const mobileBottomNav = document.querySelector("#mobileBottomNav");

const CACHE_TTL_MS = 45_000;
const APP_BRAND = loadBrandConfig();
const APP_VERSION = "11.1.0";
let activeRouteKey = window.location.hash || "#/home";
let connectionInterrupted = false;
let readerScrollHandler = null;
let readerChromeHandler = null;
let readerAbortController = null;
let lastReaderScrollY = 0;
let activityIndicatorRequest = 0;
let commandPaletteOpenFromHistory = false;
let commandPaletteClosingFromPop = false;
let commandTouchStartY = 0;
let paragraphTouchTimer = null;
const notificationSessionStartedAt = Date.now();
const readerRequestMap = new Map();
const READER_CACHE_LIMIT = 9;

const state = {
  novels: [],
  currentNovelId: localStorage.getItem("gt-current-novel") || "",
  chapters: [],
  chapterTotal: 0,
  chapterView: "all",
  chapterSearch: "",
  chapterOffset: 0,
  pageSize: 50,
  source: ["english", "ai", "original"].includes(localStorage.getItem("gt-reader-source")) ? (localStorage.getItem("gt-reader-source") === "ai" ? "english" : localStorage.getItem("gt-reader-source")) : "english",
  fontSize: Number(localStorage.getItem("gt-reader-font") || 20),
  zen: false,
  admin: false,
  role: "guest",
  authConfig: null,
  account: null,
  personal: null,
  supabaseClient: null,
  lastEstimate: null,
  preferences: loadPreferences(),
  libraryView: readStored("gt-library-view", {search: "", filter: "active", sort: "updated", view: "grid", collection: ""}),
  recent: readStored("gt-recent", {novels: [], chapters: [], jobs: [], searches: [], admin: []}),
  notifications: readStored("gt-notifications", []),
  cache: new Map(),
};

const sourceLabels = {english: "English", ai: "English", reference: "Reference", original: "Original"};
const chapterViews = [
  ["all", "All"],
  ["translated", "Translated"],
  ["needs", "Needs Translation"],
  ["missing-original", "Missing Original"],
  ["missing-reference", "Missing Reference"],
  ["errors", "Has Errors"],
];

function loadBrandConfig() {
  const defaults = {
    name: "I Am God Reader",
    shortName: "IAG Reader",
    subtitle: "Novel Library",
    tagline: "Novel Library",
    mark: "book-portal",
    browserTitle: "I Am God Reader",
    accessibleLogoLabel: "I Am God Reader home",
  };
  const configNode = document.querySelector("#appBrandConfig");
  if (!configNode) return defaults;
  try {
    const parsed = JSON.parse(configNode.textContent || "{}");
    return {...defaults, ...parsed};
  } catch {
    return defaults;
  }
}

async function api(path, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      return await apiOnce(path, options);
    } catch (error) {
      if (error.name === "AbortError") throw error;
      const retryable = method === "GET" && (error.network || [502, 503, 504].includes(error.status));
      if (!retryable || attempt === 2) throw error;
      if (!connectionInterrupted) {
        connectionInterrupted = true;
        toast("Connection interrupted. Retrying...");
      }
      await delay(350 * (attempt + 1) + Math.random() * 250);
    }
  }
}

async function apiOnce(path, options = {}) {
  const token = await getAccessToken();
  let response;
  try {
    response = await fetch(path, {
      credentials: "same-origin",
      headers: {"Accept": "application/json", ...(token ? {"Authorization": `Bearer ${token}`} : {}), ...(options.headers || {})},
      ...options,
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    error.network = true;
    throw error;
  }
  const text = await response.text();
  let payload = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    const error = new Error(`HTTP ${response.status}: The server returned a non-JSON response for ${path}.`);
    error.status = response.status;
    error.nonJson = true;
    throw error;
  }
  if (!response.ok) {
    const serverError = payload?.error || {};
    const detail = serverError.message || payload?.message || payload?.detail || `Request failed: ${response.status}`;
    const stage = serverError.stage || payload?.stage;
    const code = serverError.code || payload?.code;
    const detailParts = [`HTTP ${response.status}`, detail];
    if (stage) detailParts.push(`Stage: ${stage}`);
    if (code) detailParts.push(`Code: ${code}`);
    const error = new Error(detailParts.join(" · "));
    error.status = response.status;
    error.stage = stage || "";
    error.code = code || "";
    error.payload = payload;
    throw error;
  }
  if (connectionInterrupted) {
    connectionInterrupted = false;
    toast("Reconnected.");
  }
  return payload;
}

async function cachedApi(path, ttl = CACHE_TTL_MS) {
  const cached = state.cache.get(path);
  if (cached && Date.now() - cached.time < ttl) return cached.payload;
  const payload = await api(path);
  rememberCachePayload(path, payload);
  return payload;
}

function rememberCachePayload(path, payload) {
  state.cache.set(path, {time: Date.now(), payload});
  const readerKeys = [...state.cache.keys()].filter((key) => key.includes("/chapters/"));
  while (readerKeys.length > READER_CACHE_LIMIT) {
    state.cache.delete(readerKeys.shift());
  }
}

function invalidateCache(prefix = "") {
  for (const key of [...state.cache.keys()]) {
    if (!prefix || key.startsWith(prefix)) state.cache.delete(key);
  }
}

function route() {
  const [path, query = ""] = (window.location.hash || "#/home").replace(/^#\/?/, "").split("?");
  const parts = path.split("/").filter(Boolean);
  const params = new URLSearchParams(query);
  if ((parts[0] || "home") !== "reader") clearToasts();
  updateNav(parts[0] || "home");
  if (!parts.length || parts[0] === "home") return openHome();
  if (parts[0] === "library") {
    const filter = params.get("filter");
    if (["active", "all", "favorites", "pinned", "completed", "in-progress", "want-to-read", "paused", "collection", "archived"].includes(filter)) {
      state.libraryView = {...state.libraryView, filter};
      writeStored("gt-library-view", state.libraryView);
    }
    const collection = params.get("collection");
    if (collection) {
      state.libraryView = {...state.libraryView, filter: "collection", collection};
      writeStored("gt-library-view", state.libraryView);
    }
    return openLibrary();
  }
  if (parts[0] === "continue") return openContinueReading();
  if (parts[0] === "reader" && parts[1] && parts[2]) return openReader(parts[1], Number(parts[2]), parts[3] || state.source);
  if (parts[0] === "novel" && parts[1]) return openNovelDetail(parts[1]);
  if (parts[0] === "compare" && parts[1] && parts[2]) return openCompare(parts[1], Number(parts[2]));
  if (parts[0] === "activity") return openActivityCenter(parts[1] || "");
  if (parts[0] === "jobs") return openJobCenter(parts[1] || "");
  if (parts[0] === "chapters" && parts[1]) return openChapters(parts[1]);
  if (parts[0] === "translate") return openTranslate(parts[1] || state.currentNovelId, params);
  if (parts[0] === "recovery") return openRecovery(parts[1] || state.currentNovelId);
  if (parts[0] === "novels") return openNovels(parts[1] || "");
  if (parts[0] === "history") return openHistory();
  if (parts[0] === "bookmarks") return openBookmarks();
  if (parts[0] === "settings") return openSettings(parts[1] || "");
  if (["account", "login", "signup", "forgot-password", "reset-password"].includes(parts[0])) return openSettings("account", parts[0]);
  if (parts[0] === "notifications") return openNotifications();
  if (parts[0] === "admin") return openAdmin(parts[1] || localStorage.getItem("gt-last-admin-tab") || "overview");
  return openHome();
}

function updateNav(active) {
  document.body.dataset.route = active || "home";
  if (!nav) return;
  renderNav();
  nav.querySelectorAll("a").forEach((link) => {
    const target = link.getAttribute("href").replace("#/", "").split("/")[0];
    const isActive = target === active || (active === "reader" && link.dataset.nav === "continue");
    link.classList.toggle("active", isActive);
    if (isActive) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
}

function renderNav() {
  if (!nav) return;
  const continueHref = continueReadingHref();
  const links = [
    ["home", "Home", "#/home", true],
    ["library", "Library", "#/library", true],
    ["continue", "Continue Reading", continueHref, true],
  ];
  nav.innerHTML = links.filter(([, , , allowed]) => allowed).map(([key, label, href]) => `<a data-nav="${key}" href="${href}">${label}</a>`).join("");
  if (accountBtn) {
    accountBtn.innerHTML = `<span class="avatar-mini">${escapeHtml(initials(state.account?.display_name || state.account?.email || (state.admin ? "Admin" : "Guest")))}</span><span>${escapeHtml(profileLabel())}</span>`;
  }
  renderProfileMenu();
  renderMobileBottomNav(activeRouteName());
  const jobButton = document.querySelector("#jobCenterBtn");
  if (jobButton) {
    jobButton.textContent = activityLabel();
    jobButton.hidden = !canTranslate();
    jobButton.dataset.relevant = canTranslate() ? "true" : "false";
  }
  refreshActivityIndicator();
}

function profileLabel() {
  if (state.account?.display_name) return state.account.display_name;
  if (state.account?.email) return state.account.email;
  if (state.admin) return "Admin Mode";
  return "Guest";
}

function renderProfileMenu() {
  if (!profileMenuItems) return;
  const signedIn = Boolean(state.account);
  const continueHref = continueReadingHref();
  const hasLocalHistory = (state.recent.chapters || []).length > 0;
  const hasLocalBookmarks = localBookmarks().length > 0;
  const guestItems = [
    ["Continue Reading", continueHref],
    ["Library", "#/library", true],
    ["Settings", "#/settings", true],
    ...(hasLocalBookmarks ? [["Bookmarks", "#/bookmarks", true]] : []),
    ...(hasLocalHistory ? [["History", "#/history", true]] : []),
    ["Sign In", "#/account", true],
  ];
  const accountItems = signedIn ? [
    ["Account", "#/account", true],
    ["History", "#/history", true],
    ["Favorites", "#/library?filter=favorites", true],
    ["Collections", "#/library?filter=collection", true],
    ["Preferences", "#/settings", true],
    ["Notifications", "#/notifications", true],
  ] : [];
  const workItems = [
    ["Desktop Sync", "#/settings/advanced", canTranslate() || state.admin],
    ["Translator Workspace", `#/translate/${state.currentNovelId}`, canTranslate()],
    ["Admin", "#/admin", state.admin],
  ].filter(([, , visible]) => visible);
  const adminExit = state.admin ? `<button type="button" id="profileExitAdmin">Exit Admin Mode</button>` : "";
  const accountExit = signedIn ? `<button type="button" id="profileSignOut">Sign Out</button>` : "";
  const group = (label, items) => items.length ? `<div class="profile-menu-group"><span>${escapeHtml(label)}</span>${items.map(([text, href]) => `<a href="${escapeAttr(href)}">${escapeHtml(text)}</a>`).join("")}</div>` : "";
  profileMenuItems.innerHTML = `
    <div class="profile-menu-header"><div><strong>${escapeHtml(profileLabel())}</strong><span>${signedIn ? "Signed in" : state.admin ? "Admin mode" : "Reading as guest"}</span></div><button type="button" id="profileMenuClose" aria-label="Close menu">Close</button></div>
    ${signedIn ? group("Account", accountItems) : group("Menu", guestItems)}
    ${signedIn ? group("Workspace", workItems) : ""}
    ${accountExit || adminExit ? `<div class="profile-menu-divider"></div>` : ""}
    ${accountExit}
    ${adminExit}`;
  profileMenuItems.querySelectorAll("a").forEach((link) => link.addEventListener("click", () => { if (profileMenu) profileMenu.open = false; }));
  profileMenuItems.querySelector("#profileMenuClose")?.addEventListener("click", () => { if (profileMenu) profileMenu.open = false; accountBtn?.focus(); });
  profileMenuItems.querySelector("#profileSignOut")?.addEventListener("click", () => { if (profileMenu) profileMenu.open = false; signOut(); });
  profileMenuItems.querySelector("#profileExitAdmin")?.addEventListener("click", () => { if (profileMenu) profileMenu.open = false; exitAdminMode(); });
}

function activeRouteName() {
  return (window.location.hash || "#/home").replace(/^#\/?/, "").split(/[/?]/)[0] || "home";
}

function renderMobileBottomNav(active = activeRouteName()) {
  if (!mobileBottomNav) return;
  const items = [
    ["home", "Home", "#/home"],
    ["library", "Library", "#/library"],
    ["continue", "Read", "#/continue"],
    ["menu", "Menu", ""],
  ];
  mobileBottomNav.innerHTML = items
    .map(([key, label, href]) => key === "menu"
      ? `<button type="button" data-mobile-menu aria-label="Open menu" title="Menu">${escapeHtml(label)}</button>`
      : `<a href="${escapeAttr(href)}" title="${escapeAttr(label.replace(/\s+\d+$/, ""))}" aria-label="${escapeAttr(label)}" ${active === key || (active === "reader" && key === "continue") ? `aria-current="page"` : ""} class="${active === key || (active === "reader" && key === "continue") ? "active" : ""}">${escapeHtml(label)}</a>`)
    .join("");
  mobileBottomNav.querySelector("[data-mobile-menu]")?.addEventListener("click", () => {
    if (profileMenu) {
      profileMenu.open = true;
      profileMenu.querySelector("a, button")?.focus();
    }
  });
}

function pushNotification(type, title, message, href = "") {
  if (!notificationsEnabled(type)) return;
  const item = {id: `note-${Date.now()}-${Math.random().toString(16).slice(2)}`, type, title, message, href, read: false, created_at: new Date().toISOString()};
  state.notifications = [item, ...state.notifications].slice(0, 60);
  writeStored("gt-notifications", state.notifications);
  renderMobileBottomNav();
  toast(title, href ? "Open" : "", href ? () => { window.location.hash = href; } : null);
}

function notificationsEnabled(type) {
  const pref = state.preferences || {};
  if (pref.quietNotifications && !["backup", "recovery"].includes(type)) return false;
  if (type === "translation") return pref.notifyJobs !== false && pref.notifyTranslation !== false;
  if (type === "import") return pref.notifyImports !== false;
  if (type === "backup") return pref.notifyBackups !== false;
  if (type === "recovery") return pref.notifyImports !== false && pref.notifyRecovery !== false;
  if (type === "desktop") return pref.desktopSyncPrompts !== false && pref.notifyDesktop !== false;
  if (type === "new-chapters") return pref.notifyNewChapters !== false;
  return true;
}

function notifyOnce(key, type, title, message, href = "") {
  const storageKey = `gt-notified:${key}`;
  if (sessionStorage.getItem(storageKey)) return;
  if (!notificationsEnabled(type)) return;
  sessionStorage.setItem(storageKey, "1");
  pushNotification(type, title, message, href);
}

function updatedDuringNotificationSession(item) {
  const timestamp = Date.parse(item?.updated_at || item?.completed_at || item?.created_at || "");
  return Number.isFinite(timestamp) && timestamp >= notificationSessionStartedAt - 5_000;
}

function markNotificationsRead() {
  state.notifications = state.notifications.map((item) => ({...item, read: true}));
  writeStored("gt-notifications", state.notifications);
  renderMobileBottomNav();
}

function clearNotifications() {
  state.notifications = [];
  writeStored("gt-notifications", state.notifications);
  renderMobileBottomNav();
  openNotifications();
}

function canTranslate() {
  return state.admin || state.role === "translator";
}

function canViewReference() {
  return canTranslate();
}

function applyBranding() {
  document.title = APP_BRAND.browserTitle || APP_BRAND.name;
  document.querySelectorAll("[data-brand-name]").forEach((node) => { node.textContent = APP_BRAND.name; });
  document.querySelectorAll("[data-brand-mark]").forEach((node) => {
    node.innerHTML = brandMarkSvg();
    node.setAttribute("aria-label", APP_BRAND.accessibleLogoLabel || APP_BRAND.name);
  });
  document.querySelectorAll("[data-brand-tagline]").forEach((node) => { node.textContent = APP_BRAND.subtitle || APP_BRAND.tagline; });
  document.querySelectorAll("[data-brand-home]").forEach((node) => { node.setAttribute("aria-label", APP_BRAND.accessibleLogoLabel || `${APP_BRAND.name} Home`); });
}

function brandMarkSvg() {
  return `<svg class="brand-mark-svg" viewBox="0 0 64 64" role="img" aria-hidden="true" focusable="false">
    <path class="mark-page-left" d="M12 14c8.7 0 15 2.7 20 8.1v28.8c-5.4-4.5-11.9-6.7-20-6.7V14Z"/>
    <path class="mark-page-right" d="M52 14c-8.7 0-15 2.7-20 8.1v28.8c5.4-4.5 11.9-6.7 20-6.7V14Z"/>
    <path class="mark-portal" d="M23 19.8c3.4 1.3 6.4 3.5 9 6.6 2.6-3.1 5.6-5.3 9-6.6v25.1c-3.3 1-6.2 2.8-9 5.5-2.8-2.7-5.7-4.5-9-5.5V19.8Z"/>
    <path class="mark-spine" d="M32 22v29"/>
  </svg>`;
}

function setLoading(label = "Loading...") {
  app.innerHTML = `<section class="state-card"><div class="spinner"></div><p>${escapeHtml(label)}</p></section>`;
}

function setError(message, action = `<a class="button" href="#/home">Back Home</a>`) {
  app.innerHTML = `<section class="state-card error"><h2>Something needs attention</h2><p>${escapeHtml(message)}</p><div class="actions">${action}</div></section>`;
}

async function refreshSession() {
  try {
    const payload = await api("/api/admin/session");
    state.admin = Boolean(payload.admin);
    state.role = payload.role || (state.admin ? "admin" : "guest");
  } catch {
    state.admin = false;
    state.role = "guest";
  }
  renderNav();
}

async function loadAuth() {
  try {
    state.authConfig = await api("/api/auth/config");
    if (state.authConfig.configured && window.supabase?.createClient) {
      state.supabaseClient = window.supabase.createClient(state.authConfig.supabase_url, state.authConfig.supabase_publishable_key);
      state.supabaseClient.auth.onAuthStateChange(() => refreshAccount());
    }
    await refreshAccount();
  } catch {
    state.authConfig = {configured: false};
  }
}

async function refreshAccount() {
  try {
    const payload = await api("/api/account/me");
    state.account = payload.authenticated ? payload.user : null;
    state.personal = null;
    if (payload.preferences && Object.keys(payload.preferences).length) {
      state.preferences = {...state.preferences, ...payload.preferences};
      localStorage.setItem("gt-preferences", JSON.stringify(state.preferences));
      applyPreferences();
    }
  } catch {
    state.account = null;
  }
}

async function loadPersonalHome(force = false) {
  if (!state.account) return null;
  if (!force && state.personal) return state.personal;
  try {
    state.personal = await api("/api/account/home");
    return state.personal;
  } catch {
    state.personal = null;
    return null;
  }
}

async function getAccessToken() {
  if (!state.supabaseClient) return null;
  try {
    const {data} = await state.supabaseClient.auth.getSession();
    return data?.session?.access_token || null;
  } catch {
    return null;
  }
}

async function loadNovels(force = false) {
  if (!force && state.novels.length) return state.novels;
  const payload = force ? await api("/api/novels") : await cachedApi("/api/novels");
  state.novels = payload.novels || [];
  if (!state.novels.some((novel) => novel.id === state.currentNovelId) && state.novels[0]) {
    state.currentNovelId = state.novels[0].id;
    localStorage.setItem("gt-current-novel", state.currentNovelId);
  }
  return state.novels;
}

async function openHome() {
  setLoading("Opening home...");
  try {
    const novels = await loadNovels(true);
    const personal = await loadPersonalHome(true);
    const operations = await loadHomeOperations();
    const activeNovels = novels.filter((novel) => !novel.is_archived);
    const continueItem = normalizedContinueReading(personal?.continue_reading || latestLocalReading());
    const spotlight = activeNovels[0] || novels[0] || null;
    const recentRead = dedupeRecentReading(personal?.history?.length ? personal.history : state.recent.chapters || []).slice(0, 5);
    const shelfNovels = orderHomeNovels(activeNovels).slice(0, 6);
    const savedChapters = state.account ? (personal?.bookmarks || []) : localBookmarks();
    app.innerHTML = `
      <section class="home-hero reading-home-hero">
        ${renderContinueReading(continueItem, spotlight)}
      </section>
      <section class="home-section">
        <div class="section-heading">
          <div><p class="eyebrow">Library</p><h2>Available novels</h2></div>
          <a class="button" href="#/library">Open Library</a>
        </div>
        <div class="home-library-shelf">${shelfNovels.map(renderHomeNovelTile).join("") || renderHomeEmptyLibrary()}</div>
      </section>
      <section class="home-grid home-primary-grid">
        ${renderRecentlyRead(recentRead)}
        ${savedChapters.length ? renderHomeBookmarks(savedChapters) : ""}
      </section>
      ${state.account ? `<section class="home-grid home-secondary-grid">${renderHomeFavorites(personal?.favorites || [])}</section>` : ""}
      ${renderReaderDiscovery(spotlight)}
      ${canTranslate() || state.admin ? `<details class="home-secondary"><summary>Operations</summary><div class="home-grid">${renderHomeOperations(operations)}</div></details>` : ""}`;
    bindCopyLinks(app);
    document.querySelectorAll("[data-home-search]").forEach((button) => button.addEventListener("click", openCommandPalette));
    restoreScrollPosition();
  } catch (error) {
    setError(error.message);
  }
}

function orderHomeNovels(novels) {
  const pinned = pinnedIds();
  return [...novels].sort((a, b) => {
    const pinDelta = Number(pinned.has(b.id)) - Number(pinned.has(a.id));
    if (pinDelta) return pinDelta;
    return String(b.updated_at || b.created_at || "").localeCompare(String(a.updated_at || a.created_at || ""));
  });
}

function renderHomeNovelTile(novel) {
  const title = displayNovelTitle(novel);
  const status = titleCase(readingStatus(novel.id));
  const chapterCount = Number(novel.chapter_count || 0);
  const readableCount = readableChapterCount(novel);
  const chapterText = readableCount
    ? `${readableCount} readable chapter${readableCount === 1 ? "" : "s"}`
    : chapterCount
      ? `${chapterCount} chapter${chapterCount === 1 ? "" : "s"} in library`
      : "No chapters imported yet";
  return `<article class="home-novel-tile">
    <a class="mini-cover book-cover" href="#/novel/${encodeURIComponent(novel.id)}">${renderCoverArt(novel, title)}</a>
    <div>
      <span class="badge">${escapeHtml(status)}</span>
      <h3>${escapeHtml(title)}</h3>
      ${novel.author ? `<p class="muted">${escapeHtml(novel.author)}</p>` : ""}
      <p>${escapeHtml(chapterText)}</p>
      <div class="actions"><a class="button primary" href="#/reader/${encodeURIComponent(novel.id)}/1/${safeReaderSource()}">Read</a><a class="button" href="#/novel/${encodeURIComponent(novel.id)}">Details</a></div>
    </div>
  </article>`;
}

function renderHomeEmptyLibrary() {
  return `<section class="empty-state home-empty"><h2>No novels available yet</h2><p>Imported novels will appear here with covers, progress, and reading actions.</p><a class="button" href="#/library">Open Library</a></section>`;
}

function renderReaderDiscovery(spotlight) {
  return `<section class="home-discovery">
    <div><p class="eyebrow">Discover</p><h2>Find your next chapter</h2><p class="muted">Search the library or browse the chapter list.</p></div>
    <div class="actions"><button data-home-search type="button">Search Library</button>${spotlight ? `<a class="button" href="#/chapters/${encodeURIComponent(spotlight.id)}">Browse Chapters</a>` : ""}</div>
  </section>`;
}

async function loadHomeOperations() {
  if (!canTranslate() && !state.admin) return {};
  const safe = async (promise) => {
    try { return await promise; } catch { return null; }
  };
  const jobsPromise = canTranslate() ? safe(api(`/api/translation/jobs?novel_id=${encodeURIComponent(state.currentNovelId)}`)) : Promise.resolve(null);
  const importsPromise = state.admin ? safe(api(`/api/import-jobs?novel_id=${encodeURIComponent(state.currentNovelId)}`)) : Promise.resolve(null);
  const backupPromise = state.admin ? safe(api("/api/admin/backups/manifest")) : Promise.resolve(null);
  const desktopPromise = state.admin ? safe(api(`/api/desktop/sync/status?novel_id=${encodeURIComponent(state.currentNovelId)}`)) : Promise.resolve(null);
  const [jobs, imports, backup, desktop] = await Promise.all([jobsPromise, importsPromise, backupPromise, desktopPromise]);
  return {jobs, imports, backup, desktop};
}

function renderLibrarySpotlight(novel) {
  if (!novel) return `<section class="panel"><h2>Library Spotlight</h2><p class="empty-state">Add a novel from Admin to begin building the catalog.</p></section>`;
  const pct = progress(novel);
  const coverageTotal = coverageDenominator(novel);
  const coverageLabel = coverageBasisLabel(novel);
  const title = displayNovelTitle(novel);
  return `<section class="panel spotlight-card">
    <h2>Library Spotlight</h2>
    <div class="spotlight-row">
      <a class="mini-cover book-cover" href="#/novel/${encodeURIComponent(novel.id)}">${renderCoverArt(novel, title)}</a>
      <div><h3>${escapeHtml(title)}</h3>${novel.author ? `<p class="muted">${escapeHtml(novel.author)}</p>` : ""}<div class="mini-progress"><span style="width:${pct}%"></span></div><p class="muted">${novel.english_count ?? novel.ai_count ?? 0}/${coverageTotal} English chapters across ${escapeHtml(coverageLabel)}.</p><div class="actions"><a class="button primary" href="#/novel/${encodeURIComponent(novel.id)}">Open Novel</a><a class="button" href="#/reader/${encodeURIComponent(novel.id)}/1/${safeReaderSource()}">Start Reading</a></div></div>
    </div>
  </section>`;
}

function renderRecentlyRead(items) {
  return `<section class="panel"><h2>Recently Read</h2><div class="stack-list">${items.map((item) => {
    const normalized = normalizedContinueReading(item);
    return normalized ? `<a class="list-row" href="${escapeAttr(continueReadingHref(normalized))}"><strong>${escapeHtml(normalized.novel_title)}</strong><span>Chapter ${normalized.chapter_number} · ${escapeHtml(sourceLabels[normalized.source] || normalized.source)}</span></a>` : "";
  }).join("") || `<p class="empty-state">Open a chapter to build a recent reading trail.</p>`}</div></section>`;
}

function renderHomeFavorites(items) {
  const favorites = (items || []).slice(0, 5);
  if (!favorites.length && !state.account) return "";
  return `<section class="panel"><h2>Favorites</h2><div class="stack-list">${favorites.map((item) => `<a class="list-row" href="#/novel/${encodeURIComponent(item.novel_id || item.id)}"><strong>${escapeHtml(displayNovelTitle({id: item.novel_id || item.id, title: item.title || item.novel_title}))}</strong><span>${escapeHtml(item.author || "Favorite")}</span></a>`).join("") || `<p class="empty-state">Favorite novels to keep them close.</p>`}</div></section>`;
}

function renderHomeBookmarks(items) {
  const bookmarks = (items || []).slice(0, 5);
  return `<section class="panel saved-chapters-panel"><h2>Saved Chapters</h2><div class="stack-list">${bookmarks.map((item) => `<a class="list-row" href="#/reader/${encodeURIComponent(item.novel_id)}/${item.chapter_number}/${safeReaderSource(item.source)}"><strong>${escapeHtml(displayNovelTitle({id: item.novel_id, title: item.novel_title}))}</strong><span>Chapter ${item.chapter_number}</span></a>`).join("") || `<p class="empty-state">Bookmark a paragraph or chapter from the Reader and it will appear here.</p>`}</div></section>`;
}

function renderReadingStats(novels, personal) {
  const history = personal?.history || state.recent.chapters || [];
  const bookmarks = personal?.bookmarks || [];
  const favorites = personal?.favorites || [];
  const readable = sum(novels, "english_count") || sum(novels, "ai_count") || 0;
  const accountMetrics = state.account ? `${metric("Bookmarks", bookmarks.length)}${metric("Favorites", favorites.length)}` : "";
  return `<section class="panel compact-panel reading-progress-panel"><h2>Reading Progress</h2><div class="metric-grid">${metric("Readable Chapters", readable)}${metric("Recent Reads", history.length)}${accountMetrics}</div></section>`;
}

function renderRecentUpdates(novels) {
  return `<section class="panel"><h2>Recent Updates</h2><div class="stack-list">${novels.map((novel) => `<a class="list-row" href="#/novel/${encodeURIComponent(novel.id)}"><strong>${escapeHtml(novel.title || novel.id)}</strong><span>${novel.english_count ?? novel.ai_count ?? 0} English / ${novel.original_count || 0} Original · ${timeAgo(novel.updated_at)}</span></a>`).join("") || `<p class="empty-state">No catalog updates yet.</p>`}</div></section>`;
}

function renderRecentlyAdded(novels) {
  return `<section class="panel"><h2>Recently Added</h2><div class="stack-list">${novels.map((novel) => `<a class="list-row" href="#/novel/${encodeURIComponent(novel.id)}"><strong>${escapeHtml(novel.title || novel.id)}</strong><span>${escapeHtml(novel.author || "Catalog")} · ${timeAgo(novel.created_at || novel.updated_at)}</span></a>`).join("") || `<p class="empty-state">New imports will appear here.</p>`}</div></section>`;
}

function renderHomeOperations(operations) {
  if (!canTranslate() && !state.admin) return "";
  const activeJobs = (operations.jobs?.jobs || []).filter((job) => ["queued", "running", "paused"].includes(job.status));
  const failedJobs = (operations.jobs?.jobs || []).filter((job) => job.status === "failed" || job.error);
  const importJobs = operations.imports?.jobs || [];
  const backup = operations.backup?.manifest;
  const desktop = operations.desktop?.sync || {};
  return `<section class="panel operations-panel"><h2>Operations</h2><div class="metric-grid">
    ${canTranslate() ? metric("Running Jobs", activeJobs.length) : ""}
    ${canTranslate() ? metric("Needs Attention", failedJobs.length) : ""}
    ${state.admin ? metric("Imports", importJobs.length) : ""}
    ${state.admin ? metric("Backup", backup ? "Manifest Ready" : "Unavailable") : ""}
    ${state.admin ? metric("Desktop Sync", desktop.status || "Ready") : ""}
  </div><div class="actions">${canTranslate() ? `<a class="button primary" href="#/activity">Open Activity</a><a class="button" href="#/translate/${state.currentNovelId}">Translate</a>` : ""}${state.admin ? `<a class="button" href="#/admin/backups">Backups</a><a class="button" href="#/admin/imports">Imports</a>` : ""}</div></section>`;
}

function renderNextAction(continueItem, spotlight) {
  if (continueItem) return `<p class="muted">Resume the latest saved or local reading position.</p><a class="button primary" href="${escapeAttr(continueReadingHref(continueItem))}">Continue Chapter ${continueItem.chapter_number}</a>`;
  if (spotlight) return `<p class="muted">Start with the first chapter, then ${escapeHtml(APP_BRAND.shortName)} will remember where you left off.</p><a class="button primary" href="#/reader/${encodeURIComponent(spotlight.id)}/1/${safeReaderSource()}">Start Reading</a>`;
  return `<p class="muted">No novels are available yet.</p>${state.admin ? `<a class="button primary" href="#/admin/novels">Add Novel</a>` : `<a class="button" href="#/library">Open Library</a>`}`;
}

function normalizedContinueReading(item) {
  if (!item) return null;
  const novelId = item.novel_id || item.id;
  const chapterNumber = Number(item.chapter_number);
  if (!novelId || !chapterNumber) return null;
  const novel = state.novels.find((entry) => entry.id === novelId) || {};
  return {
    novel_id: novelId,
    novel_title: item.novel_title || item.title || novel.title || novelId,
    chapter_number: chapterNumber,
    chapter_title: item.chapter_title || item.label || `Chapter ${chapterNumber}`,
    source: safeReaderSource(item.source),
    scroll_percent: Number(item.scroll_percent || item.progress_percent || 0),
  };
}

function latestLocalReading() {
  return (state.recent.chapters || [])[0] || null;
}

function continueReadingHref(item = normalizedContinueReading(state.personal?.continue_reading || latestLocalReading())) {
  const progress = normalizedContinueReading(item);
  if (!progress) return "#/continue";
  return `#/reader/${encodeURIComponent(progress.novel_id)}/${progress.chapter_number}/${safeReaderSource(progress.source)}`;
}

async function openContinueReading() {
  if (document.body.dataset.route === "reader" && state.lastReaderHref) {
    history.replaceState(null, "", state.lastReaderHref);
    return;
  }
  const href = continueReadingHref();
  if (window.location.hash.startsWith("#/reader/")) return;
  if (href !== "#/continue") {
    window.location.hash = href;
    return;
  }
  updateNav("continue");
  if (!state.novels.length) await loadNovels().catch(() => {});
  const novels = state.novels.filter((novel) => !novel.is_archived);
  const recent = dedupeRecentReading(state.recent.chapters || []).slice(0, 5);
  app.innerHTML = `
    <section class="read-select">
      <div>
        <p class="eyebrow">Read</p>
        <h1>Choose where to begin</h1>
        <p class="muted">Open a recent chapter, or start from the available novels. Your next tap on Read will return to the exact saved chapter.</p>
      </div>
      ${recent.length ? `<section class="read-select-section"><h2>Recently Read</h2><div class="stack-list">${recent.map((item) => `<a class="list-row" href="${escapeAttr(continueReadingHref(item))}"><strong>${escapeHtml(item.novel_title || item.label || item.novel_id)}</strong><span>Chapter ${item.chapter_number || ""}</span></a>`).join("")}</div></section>` : ""}
      <section class="read-select-section"><h2>Start Reading</h2><div class="home-library-shelf">${novels.slice(0, 6).map(renderHomeNovelTile).join("") || renderHomeEmptyLibrary()}</div></section>
      <div class="actions"><button type="button" data-home-search>Search Library</button><a class="button" href="#/library">Open Library</a></div>
    </section>`;
  document.querySelectorAll("[data-home-search]").forEach((button) => button.addEventListener("click", openCommandPalette));
  restoreScrollPosition();
}

function activityLabel() {
  return "Activity";
}

async function refreshActivityIndicator() {
  const requestId = ++activityIndicatorRequest;
  const jobButton = document.querySelector("#jobCenterBtn");
  if (!canTranslate()) {
    if (jobButton) jobButton.hidden = true;
    if (activityBanner) {
      activityBanner.hidden = true;
      activityBanner.innerHTML = "";
    }
    return;
  }
  try {
    const payload = await cachedApi("/api/translation/jobs", 15_000);
    if (requestId !== activityIndicatorRequest) return;
    const jobs = payload.jobs || [];
    const active = jobs.filter((job) => ["queued", "running", "paused"].includes(job.status));
    const attention = jobs.filter((job) => job.status === "failed" || job.error || Number(job.failed_items || 0) > 0);
    attention.filter(updatedDuringNotificationSession).slice(0, 3).forEach((job) => {
      notifyOnce(`translation-attention:${job.id}`, "translation", "Job needs attention", `${jobNovelTitle(job)} has ${Number(job.failed_items || 0)} failed item${Number(job.failed_items || 0) === 1 ? "" : "s"}.`, `#/jobs/${job.id}`);
    });
    jobs.filter((job) => job.status === "completed" && updatedDuringNotificationSession(job)).slice(0, 3).forEach((job) => {
      notifyOnce(`translation-completed:${job.id}`, "translation", "Translation completed", `${jobNovelTitle(job)} finished ${Number(job.completed_items || job.total_items || 0)} chapter item${Number(job.completed_items || job.total_items || 0) === 1 ? "" : "s"}.`, `#/jobs/${job.id}`);
    });
    if (jobButton) {
      jobButton.hidden = false;
      jobButton.textContent = active.length ? `Activity ${active.length}` : "Activity";
      jobButton.title = attention.length ? `${attention.length} job needs attention` : "Activity";
      jobButton.dataset.relevant = active.length || attention.length ? "true" : "false";
    }
    if (!activityBanner) return;
    if (!active.length && !attention.length) {
      activityBanner.hidden = true;
      activityBanner.innerHTML = "";
      return;
    }
    const primary = active[0] || attention[0];
    const throughput = primary ? jobThroughput(primary).summary : "";
    activityBanner.hidden = false;
    activityBanner.innerHTML = `<strong>${active.length ? `${active.length} active translation job${active.length === 1 ? "" : "s"}` : `${attention.length} translation job${attention.length === 1 ? "" : "s"} need attention`}</strong><span>${escapeHtml(jobNovelTitle(primary))} · ${escapeHtml(primary?.status || "unknown")} · ${escapeHtml(throughput)}</span><a class="button" href="#/activity">Open Activity</a>`;
  } catch {
    if (activityBanner) {
      activityBanner.hidden = true;
      activityBanner.innerHTML = "";
    }
  }
}

function safeReaderSource(source = state.source) {
  if (source === "reference" && canViewReference()) return "reference";
  if (source === "original" && canViewReference()) return "original";
  return "english";
}

function readerSourceOptions() {
  return canViewReference() ? ["english", "original", "reference"] : ["english"];
}

async function openLibrary() {
  setLoading("Opening library...");
  try {
    const novels = await loadNovels(true);
    if (!state.admin && state.libraryView.filter === "archived") {
      state.libraryView = {...state.libraryView, filter: "active"};
      writeStored("gt-library-view", state.libraryView);
    }
    const active = novels.filter((novel) => !novel.is_archived);
    const showOperationalCatalog = canTranslate() || state.admin;
    app.innerHTML = `
      ${pageHeader("Library", "Browse novels, find your place, and open the next chapter.", showOperationalCatalog ? libraryStats(novels) : [])}
      <section class="library-intro">
        <div>
          <p class="eyebrow">Library</p>
          <h2>${novels.length === 1 ? "One title, ready to read." : "Choose a story and continue reading."}</h2>
          <p class="muted">Search by title or author, then open a chapter without leaving the reading flow.</p>
        </div>
        ${showOperationalCatalog ? `<div class="library-mini-stats">
          ${metric("Active", active.length)}
          ${metric("Archived", novels.length - active.length)}
        </div>` : `<button data-home-search type="button">Search Library</button>`}
      </section>
      ${state.account ? renderCollectionShelf() : ""}
      <section class="toolbar">
        <input class="search" id="librarySearch" type="search" value="${escapeAttr(state.libraryView.search)}" placeholder="Search novels">
        <select id="libraryFilter"><option value="active" ${state.libraryView.filter === "active" ? "selected" : ""}>Available</option><option value="all" ${state.libraryView.filter === "all" ? "selected" : ""}>All</option><option value="favorites" ${state.libraryView.filter === "favorites" ? "selected" : ""}>Favorites</option><option value="pinned" ${state.libraryView.filter === "pinned" ? "selected" : ""}>Pinned</option><option value="completed" ${state.libraryView.filter === "completed" ? "selected" : ""}>Completed</option><option value="in-progress" ${state.libraryView.filter === "in-progress" ? "selected" : ""}>In Progress</option><option value="want-to-read" ${state.libraryView.filter === "want-to-read" ? "selected" : ""}>Want to Read</option><option value="paused" ${state.libraryView.filter === "paused" ? "selected" : ""}>Paused</option>${state.account ? `<option value="collection" ${state.libraryView.filter === "collection" ? "selected" : ""}>Collection</option>` : ""}${state.admin ? `<option value="archived" ${state.libraryView.filter === "archived" ? "selected" : ""}>Archived</option>` : ""}</select>
        <select id="librarySort"><option value="updated" ${state.libraryView.sort === "updated" ? "selected" : ""}>Recently updated</option><option value="title" ${state.libraryView.sort === "title" ? "selected" : ""}>Title</option><option value="progress" ${state.libraryView.sort === "progress" ? "selected" : ""}>Reading progress</option></select>
        <select id="libraryViewMode"><option value="grid" ${libraryViewMode() === "grid" ? "selected" : ""}>Grid</option><option value="compact" ${libraryViewMode() === "compact" ? "selected" : ""}>Compact</option><option value="list" ${libraryViewMode() === "list" ? "selected" : ""}>List</option><option value="covers" ${libraryViewMode() === "covers" ? "selected" : ""}>Covers</option></select>
        <button id="resetLibraryFilters" type="button">Reset Filters</button>
      </section>
      <section class="novel-grid ${libraryViewClass()}" id="novelGrid"></section>
    `;
    ["librarySearch", "libraryFilter", "librarySort", "libraryViewMode"].forEach((id) => document.querySelector(`#${id}`).addEventListener("input", renderLibraryCards));
    document.querySelector("#resetLibraryFilters").addEventListener("click", () => {
      state.libraryView = {search: "", filter: "active", sort: "updated", view: "grid", collection: ""};
      writeStored("gt-library-view", state.libraryView);
      openLibrary();
    });
    bindCollectionControls();
    document.querySelectorAll("[data-home-search]").forEach((button) => button.addEventListener("click", openCommandPalette));
    renderLibraryCards();
    restoreScrollPosition();
  } catch (error) {
    setError(error.message);
  }
}

function renderLibraryCards() {
  const grid = document.querySelector("#novelGrid");
  if (!grid) return;
  const rawQuery = document.querySelector("#librarySearch").value.trim();
  const query = rawQuery.toLowerCase();
  const filter = document.querySelector("#libraryFilter").value;
  const sort = document.querySelector("#librarySort").value;
  const view = document.querySelector("#libraryViewMode").value;
  if (filter === "collection" && !state.libraryView.collection && collections()[0]) {
    state.libraryView.collection = collections()[0].id;
  }
  state.libraryView = {...state.libraryView, search: rawQuery, filter, sort, view};
  writeStored("gt-library-view", state.libraryView);
  if (query) rememberRecent("searches", {label: query, href: "#/library", at: new Date().toISOString()});
  grid.className = `novel-grid ${libraryViewClass()}`;
  let novels = state.novels.filter((novel) => {
    if (filter === "active" && novel.is_archived) return false;
    if (filter === "archived" && (!state.admin || !novel.is_archived)) return false;
    if (filter === "favorites" && !favoriteIds().has(novel.id)) return false;
    if (filter === "pinned" && !pinnedIds().has(novel.id)) return false;
    if (["completed", "in-progress", "want-to-read", "paused"].includes(filter) && readingStatus(novel.id) !== filter) return false;
    if (filter === "collection" && !collectionNovelIds(state.libraryView.collection).has(novel.id)) return false;
    if (!query) return true;
    return `${displayNovelTitle(novel)} ${novel.author || ""} ${novel.id || ""}`.toLowerCase().includes(query);
  });
  novels = novels.sort((a, b) => {
    if (sort === "title") return displayNovelTitle(a).localeCompare(displayNovelTitle(b));
    if (sort === "progress") return progress(b) - progress(a);
    return String(b.updated_at || "").localeCompare(String(a.updated_at || ""));
  });
  grid.innerHTML = novels.map(renderNovelCard).join("") || `<div class="empty-state">No novels match this view.</div>`;
  grid.querySelectorAll("[data-favorite]").forEach((button) => button.addEventListener("click", toggleFavorite));
  grid.querySelectorAll("[data-pin]").forEach((button) => button.addEventListener("click", togglePinnedNovel));
  bindCopyLinks(grid);
}

function libraryViewMode() {
  return ["grid", "compact", "list", "covers"].includes(state.libraryView.view) ? state.libraryView.view : "grid";
}

function libraryViewClass() {
  return `library-view-${libraryViewMode()}`;
}

function pinnedIds() {
  return new Set(Array.isArray(state.preferences.pinnedNovels) ? state.preferences.pinnedNovels : []);
}

function readingStatus(novelId) {
  return state.preferences.readingStatuses?.[novelId] || "in-progress";
}

function collections() {
  return Array.isArray(state.preferences.collections) ? state.preferences.collections : [];
}

function collectionNovelIds(collectionId) {
  const collection = collections().find((item) => item.id === collectionId);
  return new Set(collection?.novel_ids || []);
}

function persistPreferenceState(message = "Preferences saved.") {
  localStorage.setItem("gt-preferences", JSON.stringify(state.preferences));
  applyPreferences();
  saveRemotePreferences();
  if (message) toast(message);
}

function renderCollectionShelf() {
  const items = collections();
  return `<section class="collection-shelf">
    <div><h2>Collections</h2><p class="muted">Create shelves for favorites, catch-up lists, and reading plans.</p></div>
    <form id="createCollectionForm" class="collection-create"><input id="newCollectionName" placeholder="New collection name"><button type="submit">Create</button></form>
    <div class="collection-links">${items.map((item) => `<a class="${state.libraryView.collection === item.id ? "active" : ""}" href="#/library?collection=${encodeURIComponent(item.id)}">${escapeHtml(item.name)} <span>${(item.novel_ids || []).length}</span></a>`).join("") || `<span class="muted">No collections yet.</span>`}</div>
  </section>`;
}

function bindCollectionControls() {
  document.querySelector("#createCollectionForm")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const name = document.querySelector("#newCollectionName")?.value.trim();
    if (!name) return toast("Name the collection first.");
    const existing = collections();
    const id = collectionIdFor(name, existing);
    state.preferences.collections = [...existing, {id, name, novel_ids: []}];
    persistPreferenceState("Collection created.");
    openLibrary();
  });
}

function collectionIdFor(name, existing) {
  const base = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "collection";
  let id = base;
  let suffix = 2;
  const used = new Set(existing.map((item) => item.id));
  while (used.has(id)) {
    id = `${base}-${suffix}`;
    suffix += 1;
  }
  return id;
}

function renderContinueReading(progress, fallbackNovel = null) {
  progress = normalizedContinueReading(progress);
  const fallbackTitle = fallbackNovel ? displayNovelTitle(fallbackNovel) : "";
  if (!progress) {
    return `<section class="continue-card home-continue-card">
      <div class="continue-cover mini-cover book-cover">${fallbackNovel ? renderCoverArt(fallbackNovel, fallbackTitle) : renderFallbackCover(APP_BRAND.shortName)}</div>
      <div><p class="eyebrow">Continue Reading</p><h1>${fallbackNovel ? escapeHtml(fallbackTitle) : "Choose a novel"}</h1><p class="muted">${fallbackNovel ? "Start a chapter and your place will stay on this Home page." : "Your current chapter will appear here once you begin reading."}</p></div>
      <div class="actions">${fallbackNovel ? `<a class="button primary" href="#/reader/${encodeURIComponent(fallbackNovel.id)}/1/${safeReaderSource()}">Start Reading</a>` : `<a class="button primary" href="#/library">Open Library</a>`}<button data-home-search type="button">Search</button></div>
    </section>`;
  }
  const novel = state.novels.find((item) => item.id === progress.novel_id) || {};
  const title = displayNovelTitle({id: progress.novel_id, title: progress.novel_title});
  const progressText = progress.scroll_percent ? `${Math.round(progress.scroll_percent)}% through Chapter ${progress.chapter_number}` : `Chapter ${progress.chapter_number}`;
  return `<section class="continue-card">
    <div class="continue-cover mini-cover book-cover">${renderCoverArt(novel, title)}</div>
    <div><p class="eyebrow">Continue Reading</p><h1>${escapeHtml(title)}</h1><p>Chapter ${progress.chapter_number}: ${escapeHtml(progress.chapter_title)}</p><p class="muted">${escapeHtml(progressText)}</p></div>
    <a class="button primary" href="#/reader/${encodeURIComponent(progress.novel_id)}/${progress.chapter_number}/${progress.source}">Continue</a>
  </section>`;
}

function readableChapterCount(novel) {
  return Number(novel.readable_count ?? novel.english_count ?? novel.ai_count ?? 0);
}

function renderCoverArt(novel, title = displayNovelTitle(novel || {})) {
  if (novel?.cover_url) return `<img src="${escapeAttr(novel.cover_url)}" alt="">`;
  return renderFallbackCover(title);
}

function renderFallbackCover(title = APP_BRAND.shortName) {
  const cleanTitle = String(title || APP_BRAND.shortName).trim();
  return `<span class="cover-fallback-art" aria-label="${escapeAttr(cleanTitle)} cover"><span class="cover-pages"></span><span class="cover-title" aria-hidden="true"></span></span>`;
}

function favoriteIds() {
  return new Set((state.personal?.favorites || []).map((item) => item.novel_id));
}

async function toggleFavorite(event) {
  event.preventDefault();
  event.stopPropagation();
  if (!state.account) return toast("Sign in to favorite novels.");
  const novelId = event.currentTarget.dataset.favorite;
  const next = !favoriteIds().has(novelId);
  const previous = [...(state.personal?.favorites || [])];
  const novel = state.novels.find((item) => item.id === novelId) || {id: novelId};
  state.personal = state.personal || {};
  state.personal.favorites = next ? [{novel_id: novelId, title: novel.title}, ...previous] : previous.filter((item) => item.novel_id !== novelId);
  renderLibraryCards();
  try {
    await api(`/api/account/favorites/${encodeURIComponent(novelId)}`, {method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify({favorite: next})});
    await loadPersonalHome(true);
    renderLibraryCards();
    if (!next) {
      toast("Favorite removed.", "Undo", async () => {
        await api(`/api/account/favorites/${encodeURIComponent(novelId)}`, {method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify({favorite: true})});
        await loadPersonalHome(true);
        renderLibraryCards();
      });
    } else {
      toast("Favorite saved.");
    }
  } catch (error) {
    state.personal.favorites = previous;
    renderLibraryCards();
    toast(error.message || "Favorite change failed.");
  }
}

function togglePinnedNovel(event) {
  event.preventDefault();
  event.stopPropagation();
  const novelId = event.currentTarget.dataset.pin;
  const current = pinnedIds();
  state.preferences.pinnedNovels = current.has(novelId)
    ? [...current].filter((id) => id !== novelId)
    : [novelId, ...current];
  persistPreferenceState(current.has(novelId) ? "Novel unpinned." : "Novel pinned.");
  renderLibraryCards();
}

function setNovelReadingStatus(novelId, status) {
  const allowed = new Set(["completed", "in-progress", "want-to-read", "paused"]);
  state.preferences.readingStatuses = state.preferences.readingStatuses || {};
  state.preferences.readingStatuses[novelId] = allowed.has(status) ? status : "in-progress";
  persistPreferenceState("Reading status saved.");
}

function renderNovelCard(novel) {
  const favorite = favoriteIds().has(novel.id);
  const pinned = pinnedIds().has(novel.id);
  const status = readingStatus(novel.id);
  const title = displayNovelTitle(novel);
  const chapterCount = Number(novel.chapter_count || 0);
  const readLabel = latestChapterForNovel(novel.id) ? "Continue" : chapterCount ? "Start Reading" : "Details";
  const missingEnglish = novel.missing_counts_known === false ? "Unknown" : novel.missing_english_count ?? novel.remaining_count;
  const metadata = novel.metadata || {};
  const tags = Array.isArray(metadata.tags) ? metadata.tags.slice(0, 4) : [];
  const metaLine = [novel.genre || metadata.genre, novel.language || metadata.language].filter(Boolean);
  const readerProgress = readerProgressForNovel(novel);
  const operationalMetrics = canTranslate() || state.admin;
  return `
    <article class="novel-card">
      <a class="cover book-cover" href="#/novel/${encodeURIComponent(novel.id)}">${renderCoverArt(novel, title)}</a>
      <div class="novel-card-body">
        <div class="status-row reader-status-row"><span class="badge">${titleCase(status)}</span>${pinned ? `<span class="badge ok">Pinned</span>` : ""}${state.account ? `<button class="ghost-btn" data-favorite="${escapeAttr(novel.id)}">${favorite ? "Favorited" : "Favorite"}</button>` : ""}<button class="ghost-btn" data-pin="${escapeAttr(novel.id)}">${pinned ? "Unpin" : "Pin"}</button></div>
        <h2>${escapeHtml(title)}</h2>
        ${novel.author ? `<p class="muted">${escapeHtml(novel.author)}</p>` : ""}
        ${novel.summary ? `<p class="card-summary">${escapeHtml(novel.summary)}</p>` : ""}
        ${metaLine.length ? `<p class="muted">${metaLine.map(escapeHtml).join(" · ")}</p>` : ""}
        ${tags.length ? `<p class="tag-row">${tags.map((tag) => `<span>${escapeHtml(tag)}</span>`).join("")}</p>` : ""}
        <p class="library-reading-line">${escapeHtml(readerProgress)}</p>
        ${operationalMetrics ? `<div class="mini-progress"><span style="width:${progress(novel)}%"></span></div>
        <div class="metric-grid">
          ${metric("Chapters", novel.chapter_count)}
          ${metric("Original", novel.original_count)}
          ${canViewReference() ? metric("Reference", novel.reference_count) : ""}
          ${metric("English", novel.english_count ?? novel.ai_count)}
          ${metric("Missing English", missingEnglish)}
        </div>` : ""}
        ${chapterCount === 0 ? `<p class="muted">No chapters imported yet. ${escapeHtml(novel.missing_unknown_label || "Import chapter files or a reader pack to create the first chapter rows.")}</p>` : ""}
        <div class="actions">
          <a class="button primary" href="${escapeAttr(primaryReadingHref(novel))}">${readLabel}</a>
          <a class="button" href="#/novel/${encodeURIComponent(novel.id)}">Details</a>
          ${canTranslate() ? `<a class="button" href="#/translate/${encodeURIComponent(novel.id)}">Translate</a>` : ""}
          ${canTranslate() || state.admin ? `<details class="more-menu"><summary>More</summary><button type="button" data-copy-link="#/novel/${encodeURIComponent(novel.id)}">Copy Link</button>${state.admin ? `<a class="button" href="#/novels">Admin Edit</a>` : ""}</details>` : ""}
        </div>
      </div>
    </article>`;
}

function latestChapterForNovel(novelId) {
  return (state.recent.chapters || []).find((item) => (item.novel_id || item.id) === novelId) || null;
}

function primaryReadingHref(novel) {
  const recent = latestChapterForNovel(novel.id);
  if (recent) return continueReadingHref(recent);
  if (Number(novel.chapter_count || 0) <= 0) return `#/novel/${encodeURIComponent(novel.id)}`;
  return `#/reader/${encodeURIComponent(novel.id)}/1/${safeReaderSource()}`;
}

function readerProgressForNovel(novel) {
  const recent = latestChapterForNovel(novel.id);
  if (recent) {
    const pct = Number(recent.scroll_percent || recent.progress_percent || 0);
    return pct ? `${Math.round(pct)}% through Chapter ${recent.chapter_number}` : `Last read Chapter ${recent.chapter_number}`;
  }
  const readable = readableChapterCount(novel);
  if (readable) return `${readable} readable chapter${readable === 1 ? "" : "s"}`;
  const chapters = Number(novel.chapter_count || 0);
  if (chapters) return `${chapters} chapter${chapters === 1 ? "" : "s"} available`;
  return "No chapters imported yet";
}

function libraryStats(novels) {
  const stats = [
    ["Novels", novels.length],
    ["Chapters", sum(novels, "chapter_count")],
    ["Original", sum(novels, "original_count")],
    ["English", sum(novels, "english_count")],
  ];
  if (canViewReference()) stats.splice(3, 0, ["Reference", sum(novels, "reference_count")]);
  return stats;
}

async function openNovelDetail(novelId) {
  setLoading("Opening novel...");
  try {
    state.currentNovelId = novelId;
    localStorage.setItem("gt-current-novel", novelId);
    state.lastEstimate = null;
    await loadNovels();
    const detail = await api(`/api/novels/${encodeURIComponent(novelId)}`);
    const library = await api(`/api/novels/${encodeURIComponent(novelId)}/library?limit=8`);
    const translationJobs = canTranslate() ? await api(`/api/translation/jobs?novel_id=${encodeURIComponent(novelId)}`).catch(() => null) : null;
    const listNovel = state.novels.find((item) => item.id === novelId) || {};
    const baseNovel = {...listNovel, ...(detail.novel || {})};
    const detailCounts = detail.counts || {};
    const novel = {
      ...baseNovel,
      chapter_count: detailCounts.total ?? baseNovel.chapter_count,
      original_count: detailCounts.original ?? baseNovel.original_count,
      reference_count: detailCounts.reference ?? baseNovel.reference_count,
      ai_count: detailCounts.ai ?? baseNovel.ai_count,
      english_count: detailCounts.english ?? baseNovel.english_count ?? baseNovel.ai_count,
      missing_original_count: baseNovel.missing_original_count,
      missing_english_count: baseNovel.missing_english_count ?? detailCounts.needs_translation ?? baseNovel.remaining_count,
      missing_reference_count: baseNovel.missing_reference_count,
      remaining_count: detailCounts.needs_translation ?? baseNovel.remaining_count,
    };
    const pct = progress(novel);
    const noChapterInventory = Number(novel.chapter_count || 0) === 0;
    const personal = await loadPersonalHome(true);
    const current = personal?.continue_reading?.novel_id === novelId ? personal.continue_reading : null;
    const stats = noChapterInventory ? [
      metric("Chapters", novel.chapter_count),
      metric("Expected Range", novel.expected_range_configured ? novel.expected_range_label : "Expected range not set"),
      metric("Original", novel.missing_counts_known === false ? "Unknown" : novel.original_count),
      metric("English", novel.missing_counts_known === false ? "Unknown" : novel.english_count ?? novel.ai_count),
      canViewReference() ? metric("Reference", novel.missing_counts_known === false ? "Unknown" : novel.reference_count) : "",
    ].join("") : [
      metric("Chapters", novel.chapter_count),
      metric("Original", novel.original_count),
      canViewReference() ? metric("Reference", novel.reference_count) : "",
      metric("English", novel.english_count ?? novel.ai_count),
      metric("Missing Original", novel.missing_counts_known === false ? "Unknown" : novel.missing_original_count ?? 0),
      metric("Missing English", novel.missing_counts_known === false ? "Unknown" : novel.missing_english_count ?? novel.remaining_count),
      canViewReference() ? metric("Missing Reference", novel.missing_counts_known === false ? "Unknown" : novel.missing_reference_count ?? 0) : "",
    ].join("");
    const primaryActions = noChapterInventory && state.admin ? `
      <a class="button primary" href="#/admin/imports">Import First Chapters</a>
      <a class="button" href="#/chapters/${novel.id}">Chapters</a>
      <button type="button" data-copy-link="#/novel/${encodeURIComponent(novel.id)}">Copy Link</button>
    ` : `
      <a class="button primary" href="${current ? `#/reader/${current.novel_id}/${current.chapter_number}/${safeReaderSource(current.source)}` : `#/reader/${novel.id}/1/${safeReaderSource()}`}">Continue Reading</a>
      <a class="button" href="#/reader/${novel.id}/1/${safeReaderSource()}">Start Reading</a>
      <a class="button" href="#/chapters/${novel.id}">Chapters</a>
      <button type="button" data-copy-link="#/novel/${encodeURIComponent(novel.id)}">Copy Link</button>
    `;
    rememberRecent("novels", {id: novelId, label: novel.title || novelId, href: `#/novel/${encodeURIComponent(novelId)}`, at: new Date().toISOString()});
    app.innerHTML = `
      <section class="novel-hero">
        <div class="hero-cover">${novel.cover_url ? `<img src="${escapeAttr(novel.cover_url)}" alt="">` : `<span>${escapeHtml(initials(novel.title || novel.id))}</span>`}</div>
        <div class="hero-copy">
          <p class="eyebrow">${escapeHtml(novel.status || "Active")}</p>
          <h1>${escapeHtml(novel.title || novel.id)}</h1>
          ${novel.author ? `<p class="muted">${escapeHtml(novel.author)}</p>` : ""}
          <p>${escapeHtml(novel.summary || `A database-first ${APP_BRAND.name} novel workspace.`)}</p>
          <div class="mini-progress"><span style="width:${pct}%"></span></div>
          <div class="metric-grid">${stats}</div>
          <div class="actions">${primaryActions}</div>
        </div>
      </section>
      <nav class="section-tabs"><a class="active" href="#/novel/${encodeURIComponent(novel.id)}">Overview</a><a href="#/chapters/${encodeURIComponent(novel.id)}">Chapters</a>${canTranslate() ? `<a href="#/translate/${encodeURIComponent(novel.id)}">Translation</a>` : ""}${state.admin ? `<a href="#/admin/novels">Admin Tools</a>` : ""}</nav>
      ${renderNovelDashboardControls(novel)}
      ${renderNovelInventoryNotice(novel)}
      <section class="split-panels">
        <div class="panel"><h2>Overview</h2><p>Reading coverage is ${novel.reading_coverage ?? pct}% and translation coverage is ${novel.translation_coverage ?? pct}% based on ${escapeHtml(coverageBasisLabel(novel))}.</p>${Array.isArray(novel.metadata?.tags) && novel.metadata.tags.length ? `<p class="tag-row">${novel.metadata.tags.map((tag) => `<span>${escapeHtml(tag)}</span>`).join("")}</p>` : ""}${renderTranslationSummary(novel, translationJobs)}</div>
        <div class="panel"><h2>Recent Chapters</h2>${(library.chapters || []).map((chapter) => `<a class="chapter-link" href="#/reader/${novel.id}/${chapter.chapter_number}/${safeReaderSource()}"><strong>Chapter ${chapter.chapter_number}</strong><span>${escapeHtml(chapter.title)}</span></a>`).join("") || `<p class="empty-state">No chapters found.</p>`}</div>
      </section>`;
    bindCopyLinks(app);
    bindNovelDashboardControls(novel.id);
    restoreScrollPosition();
  } catch (error) {
    setError(error.message);
  }
}

function renderNovelDashboardControls(novel) {
  const pinned = pinnedIds().has(novel.id);
  const status = readingStatus(novel.id);
  const collectionOptions = collections();
  const selected = collectionOptions.find((item) => collectionNovelIds(item.id).has(novel.id))?.id || "";
  return `<section class="novel-dashboard-controls">
    <label>Reading Status<select id="novelReadingStatus">${["in-progress", "want-to-read", "completed", "paused"].map((item) => `<option value="${item}" ${status === item ? "selected" : ""}>${titleCase(item)}</option>`).join("")}</select></label>
    <button id="pinNovelBtn" type="button">${pinned ? "Unpin Novel" : "Pin Novel"}</button>
    <label>Collection<select id="novelCollection"><option value="">No collection</option>${collectionOptions.map((item) => `<option value="${escapeAttr(item.id)}" ${selected === item.id ? "selected" : ""}>${escapeHtml(item.name)}</option>`).join("")}</select></label>
    <button id="saveNovelCollectionBtn" type="button" ${collectionOptions.length ? "" : "disabled"} title="${collectionOptions.length ? "Save collection" : "Create a collection from Library first"}">Save Collection</button>
  </section>`;
}

function renderTranslationSummary(novel, translationJobs = null) {
  const completed = Number(novel.english_count ?? novel.ai_count ?? 0);
  const remaining = Number(novel.missing_english_count ?? novel.remaining_count ?? 0);
  const total = completed + remaining;
  if (!total) return "";
  const jobs = translationJobs?.jobs || [];
  const active = jobs.find((job) => ["queued", "running", "paused"].includes(job.status));
  const recent = jobs.find((job) => job.status === "completed") || jobs[0];
  const activeProgress = active ? `${titleCase(active.status)} ${active.completed_items || 0}/${active.total_items || 0}` : "None";
  const throughput = active ? jobThroughput(active).summary : recent ? jobThroughput(recent).summary : "Measure in Activity";
  const time = active ? jobThroughput(active).remaining : "Estimate in Translate";
  const cost = active ? `$${Number(active.estimated_cost || 0).toFixed(4)}` : "Estimate in Translate";
  return `<div class="metric-grid">${metric("Translated", completed)}${metric("Remaining", remaining)}${metric("Estimated Cost", cost)}${metric("Estimated Time", time)}${metric("Active Job", activeProgress)}${metric("Recent Throughput", throughput)}</div>`;
}

function bindNovelDashboardControls(novelId) {
  document.querySelector("#novelReadingStatus")?.addEventListener("change", (event) => setNovelReadingStatus(novelId, event.target.value));
  document.querySelector("#pinNovelBtn")?.addEventListener("click", () => {
    const current = pinnedIds();
    state.preferences.pinnedNovels = current.has(novelId) ? [...current].filter((id) => id !== novelId) : [novelId, ...current];
    persistPreferenceState(current.has(novelId) ? "Novel unpinned." : "Novel pinned.");
    openNovelDetail(novelId);
  });
  document.querySelector("#saveNovelCollectionBtn")?.addEventListener("click", () => {
    const collectionId = document.querySelector("#novelCollection")?.value || "";
    state.preferences.collections = collections().map((item) => {
      const ids = new Set(item.novel_ids || []);
      ids.delete(novelId);
      if (item.id === collectionId) ids.add(novelId);
      return {...item, novel_ids: [...ids]};
    });
    persistPreferenceState(collectionId ? "Collection updated." : "Collection cleared.");
    openNovelDetail(novelId);
  });
}

async function openNovels(mode = "") {
  setLoading("Loading novels...");
  try {
    await refreshSession();
    const novels = await loadNovels(true);
    app.innerHTML = `
      ${pageHeader("Novels", "Manage titles, metadata, covers, and archive status.", [["Total", novels.length], ["Active", novels.filter((n) => !n.is_archived).length], ["Archived", novels.filter((n) => n.is_archived).length]])}
      ${state.admin ? renderNovelManagement(novels, mode) : adminNotice()}`;
    document.querySelector("#novelForm")?.addEventListener("submit", saveNovelForm);
    document.querySelector("#novelForm")?.addEventListener("input", () => {
      writeStored("gt-novel-form-draft", Object.fromEntries(new FormData(document.querySelector("#novelForm")).entries()));
      document.querySelector("#novelDraftStatus").textContent = "Draft saved just now";
    });
    document.querySelector("#discardNovelDraft")?.addEventListener("click", () => { localStorage.removeItem("gt-novel-form-draft"); openNovels(); });
    document.querySelectorAll("[data-archive]").forEach((button) => button.addEventListener("click", archiveNovel));
    bindCopyLinks(app);
    restoreScrollPosition();
  } catch (error) {
    setError(error.message);
  }
}

function renderNovelManagement(novels, mode = "") {
  const showForm = mode === "add";
  return `<section class="management-header"><div><h2>Novel Management</h2><p class="muted">Catalog-first administration for covers, status, translation progress, and metadata.</p></div><div class="actions management-actions"><a class="button primary" href="#/novels/add">Add Novel</a><a class="button" href="#/library">Open Public Library</a></div></section>
    ${showForm ? renderNovelForm() : ""}
    <section class="management-grid">${novels.map((novel) => {
      const pct = progress(novel);
      const coverageTotal = coverageDenominator(novel);
      const coverageLabel = coverageBasisLabel(novel);
      return `<article class="management-card">
        <div class="mini-cover">${novel.cover_url ? `<img src="${escapeAttr(novel.cover_url)}" alt="">` : `<span>${escapeHtml(initials(novel.title || novel.id))}</span>`}</div>
        <div class="management-card-copy"><div><h3>${escapeHtml(novel.title || novel.id)}</h3>${novel.author ? `<p class="muted">${escapeHtml(novel.author)}</p>` : ""}<p><span class="badge ${novel.is_archived ? "missing" : "ok"}">${novel.is_archived ? "Archived" : "Active"}</span></p></div><div><div class="mini-progress"><span style="width:${pct}%"></span></div><p class="muted">English coverage: ${pct}% · ${novel.english_count ?? novel.ai_count ?? 0}/${coverageTotal} ${escapeHtml(coverageLabel)}.</p><p class="muted">${novel.chapter_count || 0} chapters · updated ${timeAgo(novel.updated_at)}</p></div><div class="actions management-card-actions"><a class="button primary" href="#/novel/${encodeURIComponent(novel.id)}">Open</a><a class="button" href="#/novels/add">Edit</a><button data-archive="${novel.id}" data-value="${novel.is_archived ? "false" : "true"}">${novel.is_archived ? "Unarchive" : "Archive"}</button><a class="button" href="#/admin/novels">Admin Tools</a></div></div>
      </article>`;
    }).join("") || `<p class="empty-state">No novels exist yet.</p>`}</section>`;
}

function renderNovelForm() {
  const draft = readStored("gt-novel-form-draft", {});
  return `<form class="panel form-grid" id="novelForm">
    <h2>Create or Update Novel</h2>
    <p class="muted wide" id="novelDraftStatus">${Object.keys(draft).length ? "Draft restored" : "No saved draft"}</p>
    <label>ID / slug<input name="id" required placeholder="my-novel" value="${escapeAttr(draft.id || "")}"></label>
    <label>Title<input name="title" required value="${escapeAttr(draft.title || "")}"></label>
    <label>Author<input name="author" value="${escapeAttr(draft.author || "")}"></label>
    <label>Status<input name="status" value="${escapeAttr(draft.status || "active")}"></label>
    <label>Cover URL<input name="cover_url" value="${escapeAttr(draft.cover_url || "")}"></label>
    <label>Source URL<input name="source_url" value="${escapeAttr(draft.source_url || "")}"></label>
    <label>Reference Source URL<input name="reference_source_url" value="${escapeAttr(draft.reference_source_url || "")}"></label>
    <label>Reference target start<input name="reference_target_start" type="number" min="1" placeholder="1" value="${escapeAttr(draft.reference_target_start || "")}"></label>
    <label>Reference target end<input name="reference_target_end" type="number" min="1" placeholder="Last chapter" value="${escapeAttr(draft.reference_target_end || "")}"></label>
    <label>Default model<input name="model" value="${escapeAttr(draft.model || "gpt-4o-mini")}"></label>
    <label class="wide">Summary<textarea name="summary" rows="3">${escapeHtml(draft.summary || "")}</textarea></label>
    <div class="actions wide"><button id="discardNovelDraft" type="button" ${Object.keys(draft).length ? "" : "disabled"}>Discard Draft</button></div>
    <button class="primary" type="submit">Save Novel</button>
  </form>`;
}

async function saveNovelForm(event) {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.currentTarget).entries());
  try {
    await api("/api/novels", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data)});
    localStorage.removeItem("gt-novel-form-draft");
    state.novels = [];
    invalidateCache("/api/novels");
    openNovels();
  } catch (error) {
    toast(error.message || "Novel could not be saved.");
  }
}

async function archiveNovel(event) {
  const button = event.currentTarget;
  await api(`/api/novels/${button.dataset.archive}/archive`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({archived: button.dataset.value === "true"})});
  state.novels = [];
  invalidateCache("/api/novels");
  openNovels();
}

async function openChapters(novelId) {
  restoreChapterState(novelId);
  if (!state.admin && state.chapterView === "missing-reference") state.chapterView = "all";
  state.currentNovelId = novelId;
  localStorage.setItem("gt-current-novel", novelId);
  setLoading("Loading chapters...");
  try {
    const payload = await loadChapters(novelId);
    renderChapters(payload);
  } catch (error) {
    setError(error.message);
  }
}

async function loadChapters(novelId) {
  const path = `/api/novels/${encodeURIComponent(novelId)}/library?limit=${state.pageSize}&offset=${state.chapterOffset}&view=${encodeURIComponent(state.chapterView)}&search=${encodeURIComponent(state.chapterSearch)}`;
  const payload = await cachedApi(path);
  state.chapters = payload.chapters || [];
  state.chapterTotal = payload.total || 0;
  return payload;
}

function renderChapters(payload) {
  const novel = payload.novel;
  const showReference = canViewReference();
  const canSwitchNovels = state.novels.length > 1;
  const currentProgress = normalizedContinueReading(state.personal?.continue_reading || latestLocalReading());
  const currentChapter = currentProgress?.novel_id === novel.id ? Number(currentProgress.chapter_number) : 0;
  rememberRecent("novels", {id: novel.id, label: novel.title || novel.id, href: `#/chapters/${encodeURIComponent(novel.id)}`, at: new Date().toISOString()});
  app.innerHTML = `
    <section class="chapter-list-header">
      <div><p class="eyebrow">Chapter List</p><h1>${escapeHtml(novel.title || novel.id)}</h1><p class="muted">Search and open a chapter directly.</p></div>
      ${canSwitchNovels ? `<select id="chapterNovel">${state.novels.map((n) => `<option value="${n.id}" ${n.id === novel.id ? "selected" : ""}>${escapeHtml(n.title)}</option>`).join("")}</select>` : ""}
    </section>
    <section class="chapter-list-tools">
      <input class="search" id="chapterSearch" type="search" value="${escapeAttr(state.chapterSearch)}" placeholder="Search chapter number or title">
      <select id="chapterView">${visibleChapterViews().map(([value, label]) => `<option value="${value}" ${value === state.chapterView ? "selected" : ""}>${label}</option>`).join("")}</select>
      ${canTranslate() ? `<a class="button" href="#/translate/${novel.id}">Translate</a>` : ""}${state.admin ? `<a class="button" href="#/admin/recovery">Novel Recovery</a>` : ""}
    </section>
    <section class="chapter-list">
      <div class="table-meta">Showing ${state.chapterTotal ? state.chapterOffset + 1 : 0}-${Math.min(state.chapterOffset + state.pageSize, state.chapterTotal)} of ${state.chapterTotal} chapters</div>
      <div class="chapter-row-list">
        ${state.chapters.map((chapter) => {
          const current = chapter.chapter_number === currentChapter;
          const status = chapterStatusLabel(chapter, current);
          const rowTitle = displayChapterTitle(chapter, safeReaderSource());
          const baseTitle = `Chapter ${chapter.chapter_number}`;
          const secondaryTitle = rowTitle && rowTitle !== baseTitle ? rowTitle : "";
          return `<a class="chapter-row ${current ? "current" : ""}" href="#/reader/${encodeURIComponent(novel.id)}/${chapter.chapter_number}/${safeReaderSource()}"><span class="chapter-row-number">${chapter.chapter_number}</span><span class="chapter-row-copy"><strong>${escapeHtml(baseTitle)}</strong>${secondaryTitle ? `<span>${escapeHtml(secondaryTitle)}</span>` : ""}</span>${status ? `<small>${escapeHtml(status)}</small>` : ""}</a>`;
        }).join("") || `<div class="empty-state compact">No chapters match this view.</div>`}
      </div>
      <div class="pager chapter-pager"><button id="prevPage" ${state.chapterOffset <= 0 ? "disabled" : ""}>Previous</button><span>Page ${currentChapterPage()} of ${totalChapterPages()}</span><button id="nextPage" ${state.chapterOffset + state.pageSize >= state.chapterTotal ? "disabled" : ""}>Next</button></div>
    </section>`;
  document.querySelector("#chapterNovel")?.addEventListener("change", (e) => { window.location.hash = `#/chapters/${e.target.value}`; });
  document.querySelector("#chapterSearch").addEventListener("input", debounce((e) => { state.chapterSearch = e.target.value; state.chapterOffset = 0; persistChapterState(novel.id); openChapters(novel.id); }, 250));
  document.querySelector("#chapterView").addEventListener("change", (e) => { state.chapterView = e.target.value; state.chapterOffset = 0; persistChapterState(novel.id); openChapters(novel.id); });
  document.querySelector("#prevPage").addEventListener("click", () => { state.chapterOffset = Math.max(0, state.chapterOffset - state.pageSize); persistChapterState(novel.id); openChapters(novel.id); });
  document.querySelector("#nextPage").addEventListener("click", () => { state.chapterOffset += state.pageSize; persistChapterState(novel.id); openChapters(novel.id); });
  bindCopyLinks(app);
  restoreScrollPosition();
}

function visibleChapterViews() {
  return state.admin ? chapterViews : chapterViews.filter(([value]) => value !== "missing-reference");
}

function currentChapterPage() {
  return Math.floor(Number(state.chapterOffset || 0) / Number(state.pageSize || 50)) + 1;
}

function totalChapterPages() {
  return Math.max(1, Math.ceil(Number(state.chapterTotal || 0) / Number(state.pageSize || 50)));
}

function chapterStatusLabel(chapter, current = false) {
  if (current) return "Current";
  if (isBookmarkedLocally(state.currentNovelId, chapter.chapter_number)) return "Bookmarked";
  if (!chapter.has_english && !chapter.has_ai && !chapter.has_original && !chapter.has_reference) return "Unavailable";
  if (!chapter.has_english && !chapter.has_ai && chapter.has_original) return "Untranslated";
  return "";
}

function displayChapterTitle(chapter, source = state.source) {
  const number = Number(chapter?.chapter_number || 0);
  const fallback = number ? `Chapter ${number}` : "Chapter";
  if (source === "original" && canViewReference()) return String(chapter?.title || chapter?.original_title || fallback).trim() || fallback;
  const englishTitle = String(chapter?.english_title || chapter?.translated_title || chapter?.ai_title || chapter?.title_english || "").trim();
  if (englishTitle) return englishTitle;
  return fallback;
}

async function openReader(novelId, chapterNumber, requestedSource) {
  setLoading("Opening reader...");
  try {
    if (!state.chapters.length || state.currentNovelId !== novelId) {
      state.currentNovelId = novelId;
      state.chapterOffset = Math.max(0, chapterNumber - 25);
      await loadChapters(novelId);
      state.chapterOffset = 0;
      await cachedApi(`/api/novels/${novelId}/library?limit=5000`, 120_000).then((payload) => { state.chapters = payload.chapters || []; });
    }
    const chapter = state.chapters.find((item) => item.chapter_number === chapterNumber);
    const requested = ["english", "ai", "reference", "original"].includes(requestedSource) ? (requestedSource === "ai" ? "english" : requestedSource) : preferredSource(chapter);
    const source = readerSourceOptions().includes(requested) ? requested : safeReaderSource(preferredSource(chapter));
    state.source = source;
    localStorage.setItem("gt-reader-source", source);
    state.lastReaderHref = `#/reader/${encodeURIComponent(novelId)}/${chapterNumber}/${source}`;
    const payload = await fetchReaderChapter(novelId, chapterNumber, source);
    renderReader(novelId, chapterNumber, source, payload);
    prefetchNeighborChapters(novelId, chapterNumber, source);
  } catch (error) {
    if (error.name === "AbortError") return;
    setError(error.message);
  }
}

function renderReader(novelId, chapterNumber, source, payload) {
  const previous = neighborChapter(chapterNumber, -1);
  const next = neighborChapter(chapterNumber, 1);
  const novel = state.novels.find((item) => item.id === novelId) || {};
  const options = readerSourceOptions();
  const metrics = readerMetrics(payload, chapterNumber);
  const bookmarkLabel = isBookmarkedLocally(novelId, chapterNumber) ? "Bookmarked" : "Bookmark";
  const novelTitle = displayNovelTitle(novel);
  const chapterLabel = `Chapter ${chapterNumber}`;
  const detailedTitle = String(payload?.title || "").trim();
  const showTitleDetail = detailedTitle && detailedTitle.toLowerCase() !== chapterLabel.toLowerCase();
  const savedPercent = Number(localStorage.getItem(readerScrollKey(novelId, chapterNumber, source)) || 0);
  const restoreNote = Number.isFinite(savedPercent) && savedPercent >= 8 ? `<p class="reader-restore-note">Continue where you stopped · ${Math.round(savedPercent)}%</p>` : "";
  rememberRecent("chapters", {novel_id: novelId, chapter_number: chapterNumber, source, label: `Chapter ${chapterNumber}`, href: `#/reader/${encodeURIComponent(novelId)}/${chapterNumber}/${source}`, at: new Date().toISOString()});
  document.documentElement.style.setProperty("--reader-font", `${state.fontSize}px`);
  document.body.dataset.zen = state.zen ? "on" : "off";
  app.innerHTML = `
    <section class="reader-panel ${state.zen ? "zen" : ""}" aria-labelledby="readerChapterHeading">
      <div class="reader-toolbar reader-chrome"><a class="reader-back-link" href="#/novel/${novelId}">Back</a><strong><span>${escapeHtml(novelTitle)}</span><small>${escapeHtml(chapterLabel)}</small></strong><button id="readerMenuToggle" type="button" aria-haspopup="dialog" aria-controls="readerMenuPanel">Menu</button></div>
      <button id="readerFocusExit" class="reader-focus-exit" type="button" ${state.zen ? "" : "hidden"}>Exit Focus</button>
      <div class="reader-backdrop chapter-drawer-backdrop" id="chapterDrawerBackdrop" hidden></div>
      <div class="reader-backdrop reader-menu-backdrop" id="readerMenuBackdrop" hidden></div>
      ${renderChapterDrawer(novelId, chapterNumber, source)}
      ${renderReaderMenuPanel(novelId, chapterNumber, source, payload, metrics, previous, next, bookmarkLabel)}
      ${renderParagraphActionMenu(novelId, chapterNumber, source)}
      <header class="reader-heading">
        <div class="reader-kicker"><a href="#/novel/${encodeURIComponent(novelId)}">${escapeHtml(novelTitle)}</a></div>
        <h1 id="readerChapterHeading">${escapeHtml(chapterLabel)}</h1>
        ${restoreNote}
      </header>
      <article class="reader-text" tabindex="-1" aria-live="polite">${renderReaderText(payload, source)}</article>
      <nav class="reader-bottom-nav" aria-label="Chapter navigation">
        <a class="button" href="${previous ? `#/reader/${encodeURIComponent(novelId)}/${previous}/${source}` : "#"}" ${previous ? "" : "aria-disabled=\"true\""}>Previous Chapter</a>
        <button id="readerBottomChapterList" type="button">Chapter List</button>
        <a class="button primary" href="${next ? `#/reader/${encodeURIComponent(novelId)}/${next}/${source}` : "#"}" ${next ? "" : "aria-disabled=\"true\""}>Next Chapter</a>
      </nav>
    </section>`;
  document.querySelectorAll("[data-go]").forEach((button) => button.addEventListener("click", () => { if (button.dataset.go) window.location.hash = `#/reader/${novelId}/${button.dataset.go}/${state.source}`; }));
  document.querySelectorAll("[data-source]").forEach((button) => button.addEventListener("click", () => { window.location.hash = `#/reader/${novelId}/${chapterNumber}/${button.dataset.source}`; }));
  document.querySelector("#readerMenuFontSize")?.addEventListener("input", (event) => {
    state.fontSize = Number(event.target.value);
    state.preferences.readerFontSize = state.fontSize;
    localStorage.setItem("gt-reader-font", String(state.fontSize));
    localStorage.setItem("gt-preferences", JSON.stringify(state.preferences));
    document.documentElement.style.setProperty("--reader-font", `${state.fontSize}px`);
    const label = document.querySelector("#readerMenuFontSizeValue");
    if (label) label.textContent = `${state.fontSize}px`;
    saveRemotePreferencesQuiet();
  });
  document.querySelector("#readerMenuToggle")?.addEventListener("click", openReaderMenu);
  document.querySelector("#closeReaderMenu")?.addEventListener("click", closeReaderMenu);
  document.querySelector("#readerMenuBackdrop")?.addEventListener("click", closeReaderMenu);
  document.querySelector("#menuChapterDrawer")?.addEventListener("click", () => { closeReaderMenu(false); openChapterDrawer(); });
  document.querySelector("#menuBookmark")?.addEventListener("click", () => saveBookmark(novelId, chapterNumber));
  document.querySelector("#menuCopyLink")?.addEventListener("click", () => copyLink(`#/reader/${encodeURIComponent(novelId)}/${chapterNumber}/${source}`));
  document.querySelector("#menuZenToggle")?.addEventListener("click", () => toggleFocusReading(novelId, chapterNumber, source, payload));
  document.querySelector("#readerFocusExit")?.addEventListener("click", () => toggleFocusReading(novelId, chapterNumber, source, payload, false));
  document.querySelector("#readerBottomChapterList")?.addEventListener("click", openChapterDrawer);
  document.querySelector("#chapterSearch")?.addEventListener("input", filterChapterDrawer);
  document.querySelector("#closeChapterDrawer")?.addEventListener("click", closeChapterDrawer);
  document.querySelector("#chapterDrawerBackdrop")?.addEventListener("click", closeChapterDrawer);
  document.querySelectorAll("#readerMenuPanel [data-pref]").forEach((field) => field.addEventListener("input", saveReaderPreferenceFromField));
  document.querySelectorAll("#readerMenuPanel .pref-switch").forEach((field) => field.addEventListener("keydown", handleSwitchKeydown));
  document.querySelector("#readerTextSearch")?.addEventListener("input", searchReaderText);
  document.querySelector("#readerRetry")?.addEventListener("click", route);
  bindParagraphInteractions(novelId, chapterNumber, source);
  document.querySelector("#menuBackToTop")?.addEventListener("click", () => window.scrollTo({top: 0, behavior: state.preferences.reduceMotion ? "auto" : "smooth"}));
  bindCopyLinks(app);
  bindReaderProgress(novelId, chapterNumber, source);
  bindReaderChrome();
  bindFocusReaderSurface();
  restoreReaderScroll(novelId, chapterNumber, source);
  updateBackToTop();
  updateReaderProgressUi();
}

function toggleFocusReading(novelId, chapterNumber, source, payload, force = null) {
  state.zen = force === null ? !state.zen : Boolean(force);
  renderReader(novelId, chapterNumber, source, payload);
  if (state.zen) revealFocusExit();
}

function revealFocusExit() {
  const button = document.querySelector("#readerFocusExit");
  if (!button || !state.zen) return;
  button.hidden = false;
  button.classList.add("visible");
  clearTimeout(revealFocusExit.timer);
  revealFocusExit.timer = setTimeout(() => {
    button.classList.remove("visible");
    window.setTimeout(() => {
      if (state.zen && !button.classList.contains("visible")) button.hidden = true;
    }, 180);
  }, 1900);
}

function bindFocusReaderSurface() {
  const panel = document.querySelector(".reader-panel");
  if (!panel) return;
  panel.addEventListener("click", (event) => {
    if (!state.zen) return;
    if (event.target.closest("#readerFocusExit") || event.target.closest("#paragraphActionMenu")) return;
    revealFocusExit();
  });
}

function renderReaderText(payload, source) {
  if (!payload.ok) return `<div class="empty-state"><h2>Chapter unavailable</h2><p>${escapeHtml(readerMissingMessage(payload, source))}</p><button id="readerRetry" type="button">Retry</button></div>`;
  const lines = paragraphs(payload.text);
  if (lines.length && isDuplicateChapterHeading(lines[0], payload)) lines.shift();
  return lines.map((line, index) => {
    const clean = line.replace(/^#{1,6}\s*/, "");
    return `<p data-reader-paragraph="${escapeAttr(clean)}" data-paragraph-index="${index}" tabindex="0"><span>${escapeHtml(clean)}</span></p>`;
  }).join("");
}

function renderReaderMenuPanel(novelId, chapterNumber, source, payload, metrics, previous, next, bookmarkLabel) {
  const pref = state.preferences;
  const sourceOptions = readerSourceOptions();
  const sourceSwitch = sourceOptions.length > 1
    ? `<div class="segmented reader-source-switch" aria-label="Reader source">${sourceOptions.map((item) => `<button data-source="${item}" class="${item === source ? "active" : ""}" aria-pressed="${item === source ? "true" : "false"}">${sourceLabels[item]}</button>`).join("")}</div>`
    : `<p class="muted">${escapeHtml(sourceLabels[source] || "English")}</p>`;
  const themeOptions = [
    ["dark", "Dark"],
    ["paper", "Light"],
    ["sepia", "Sepia"],
    ["oled", "AMOLED"],
    ["midnight", "Midnight"],
    ["green-night", "Green Night"],
  ];
  const themePicker = `<div class="reader-theme-grid" role="radiogroup" aria-label="Theme">${themeOptions.map(([value, label]) => `<label class="reader-theme-choice"><input data-pref="readerTone" type="radio" name="readerMenuTone" value="${value}" ${pref.readerTone === value ? "checked" : ""}>${label}</label>`).join("")}</div>`;
  return `<section class="reader-menu-panel" id="readerMenuPanel" role="dialog" aria-modal="true" aria-labelledby="readerMenuTitle" hidden>
    <div class="sheet-header reader-menu-header"><div><p class="eyebrow">Reader Menu</p><h2 id="readerMenuTitle">Chapter tools</h2></div><button id="closeReaderMenu" type="button">Close</button></div>
    <div class="reader-menu-section reader-menu-compact">
      <h3>Chapter</h3>
      <div class="reader-menu-actions reader-menu-quick">
        <button id="menuChapterDrawer" type="button">Table of Contents</button>
        <button data-go="${previous || ""}" ${previous ? "" : "disabled"} type="button">Previous</button>
        <button data-go="${next || ""}" ${next ? "" : "disabled"} type="button">Next</button>
        <button id="menuBackToTop" type="button">Back to Top</button>
      </div>
    </div>
    <div class="reader-menu-section">
      <div class="reader-menu-row"><h3>Text Size</h3><span id="readerMenuFontSizeValue">${state.fontSize}px</span></div>
      <input id="readerMenuFontSize" type="range" min="16" max="27" value="${state.fontSize}" aria-label="Reader text size">
      <h3>Theme</h3>
      ${themePicker}
      <div class="reader-menu-source"><h3>Source</h3>${sourceSwitch}</div>
    </div>
    <div class="reader-menu-section">
      <h3>Actions</h3>
      <div class="reader-menu-actions">
        <button id="menuBookmark" type="button" aria-pressed="${bookmarkLabel === "Bookmarked" ? "true" : "false"}">${escapeHtml(bookmarkLabel)}</button>
        <button id="menuCopyLink" type="button">Copy Link</button>
        <button id="menuZenToggle" type="button">${state.zen ? "Exit Focus Mode" : "Focus Mode"}</button>
      </div>
    </div>
    <div class="reader-menu-section">
      <h3>Find in Chapter</h3>
      <label class="reader-find-row">Search<input id="readerTextSearch" type="search" placeholder="Find text in this chapter"></label>
      <span id="readerSearchCount" class="muted">No search active</span>
    </div>
    <div class="reader-menu-section">
      <a class="button reader-menu-preferences" href="#/settings/reader">Reading Preferences</a>
    </div>
    <details class="reader-menu-section reader-menu-details">
      <summary>Accessibility</summary>
      <div class="reader-menu-toggles">
        ${radioToggle("reduceMotion", pref.reduceMotion, "Reduce motion", "Calmer transitions")}
        ${radioToggle("contrastFocus", pref.contrastFocus, "High contrast focus", "Stronger keyboard focus")}
        ${radioToggle("accessibilityComfort", pref.accessibilityComfort, "Comfort reading", "Stable spacing and softer reader chrome")}
      </div>
    </details>
    <details class="reader-menu-section reader-menu-details">
      <summary>Reader Information</summary>
      <div class="reader-menu-info">${metric("Read Time", metrics.readTime)}${metric("Novel Progress", metrics.chapterProgress)}<div class="metric"><span>Position</span><strong id="readerProgressText">0%</strong></div>${metric("Source", sourceLabels[source] || source)}</div>
      ${payload?.title ? `<p class="muted"><strong>Title details:</strong> ${escapeHtml(payload.title)}</p>` : ""}
      <div class="reader-progress menu-progress" aria-hidden="true"><span id="readerScrollProgress" style="width:0%"></span></div>
      ${renderReaderEditionNotice(payload, source)}
    </details>
  </section>`;
}

function renderParagraphActionMenu(novelId, chapterNumber, source) {
  return `<div class="reader-paragraph-menu" id="paragraphActionMenu" role="menu" hidden data-novel-id="${escapeAttr(novelId)}" data-chapter-number="${escapeAttr(chapterNumber)}" data-source="${escapeAttr(source)}">
    <button type="button" role="menuitem" data-paragraph-action="copy">Copy paragraph</button>
    <button type="button" role="menuitem" data-paragraph-action="bookmark">Bookmark here</button>
    <button type="button" role="menuitem" data-paragraph-action="highlight">Highlight</button>
    <button type="button" role="menuitem" data-paragraph-action="report">Report translation issue</button>
    ${canViewReference() ? `<button type="button" role="menuitem" data-paragraph-action="original">View Original</button>` : ""}
  </div>`;
}

function readerMissingMessage(payload, source) {
  if (payload?.status === "english_missing" && canViewReference()) return "English can be filled from Reference in the Admin Build English Coverage workflow when Reference is available.";
  if (payload?.status === "english_missing") return "This chapter is not available in English yet.";
  if (payload?.status === "reference_missing") return "Reference is not available for this chapter.";
  if (payload?.status === "original_missing") return "Original text is not available for this chapter.";
  return `${sourceLabels[source] || "Chapter"} is not available right now.`;
}

function renderReaderEditionNotice(payload, source) {
  if (!canViewReference() || !payload?.ok || !payload.edition || source !== "english") return "";
  const edition = payload.edition || {};
  return `<aside class="reader-edition-note" aria-label="English edition details">
    <strong>${escapeHtml(edition.edition_type || "English")}</strong>
    <span>${escapeHtml(edition.source_label || "Active English edition")}</span>
  </aside>`;
}

function readerMetrics(payload, chapterNumber) {
  const text = payload?.ok ? String(payload.text || "") : "";
  const wordCount = text.trim() ? text.trim().split(/\s+/).length : 0;
  const minutes = Math.max(1, Math.ceil(wordCount / 250));
  const currentIndex = state.chapters.findIndex((chapter) => chapter.chapter_number === chapterNumber);
  const chapterProgress = currentIndex >= 0 && state.chapters.length ? `${currentIndex + 1}/${state.chapters.length}` : "Unknown";
  return {readTime: `${minutes} min`, chapterProgress};
}

function searchReaderText(event) {
  const query = event.target.value.trim();
  const count = highlightReaderParagraphs(query);
  const target = document.querySelector("#readerSearchCount");
  if (target) target.textContent = query ? `${count} ${count === 1 ? "match" : "matches"}` : "No search active";
}

function highlightReaderParagraphs(query) {
  const paragraphs = [...document.querySelectorAll("[data-reader-paragraph]")];
  const normalized = query.toLowerCase();
  let count = 0;
  paragraphs.forEach((paragraph) => {
    const text = paragraph.dataset.readerParagraph || "";
    const textSpan = paragraph.querySelector("span");
    if (!textSpan) return;
    if (!normalized) {
      textSpan.innerHTML = escapeHtml(text);
      paragraph.hidden = false;
      return;
    }
    const found = text.toLowerCase().includes(normalized);
    paragraph.hidden = !found;
    if (found) {
      count += 1;
      const pattern = new RegExp(`(${escapeRegExp(query)})`, "ig");
      textSpan.innerHTML = escapeHtml(text).replace(pattern, "<mark>$1</mark>");
    }
  });
  return count;
}

function bindParagraphInteractions(novelId, chapterNumber, source) {
  const paragraphs = document.querySelectorAll("[data-reader-paragraph]");
  paragraphs.forEach((paragraph) => {
    paragraph.addEventListener("click", (event) => {
      if (window.getSelection()?.toString()) return;
      if (state.zen) {
        revealFocusExit();
      }
    });
    paragraph.addEventListener("contextmenu", (event) => {
      event.preventDefault();
      openParagraphMenu(paragraph, event.clientX, event.clientY);
    });
    paragraph.addEventListener("keydown", (event) => {
      if (!["Enter", " "].includes(event.key)) return;
      event.preventDefault();
      const rect = paragraph.getBoundingClientRect();
      openParagraphMenu(paragraph, rect.left + Math.min(rect.width, 420) / 2, rect.top + 24);
    });
    paragraph.addEventListener("pointerdown", (event) => {
      if (event.pointerType === "mouse") return;
      clearTimeout(paragraphTouchTimer);
      paragraphTouchTimer = setTimeout(() => openParagraphMenu(paragraph, event.clientX, event.clientY), 520);
    });
    paragraph.addEventListener("pointerup", () => clearTimeout(paragraphTouchTimer));
    paragraph.addEventListener("pointercancel", () => clearTimeout(paragraphTouchTimer));
  });
  document.querySelector("#paragraphActionMenu")?.addEventListener("click", (event) => handleParagraphMenuAction(event, novelId, chapterNumber, source));
}

function openParagraphMenu(paragraph, clientX, clientY) {
  const menu = document.querySelector("#paragraphActionMenu");
  if (!menu || !paragraph) return;
  closeParagraphMenu(false);
  menu.dataset.paragraphIndex = paragraph.dataset.paragraphIndex || "";
  menu.dataset.paragraphText = paragraph.dataset.readerParagraph || "";
  menu.hidden = false;
  menu.classList.add("open");
  paragraph.classList.add("paragraph-selected");
  requestAnimationFrame(() => {
    const rect = menu.getBoundingClientRect();
    const left = clamp(clientX || window.innerWidth / 2, 12, Math.max(12, window.innerWidth - rect.width - 12));
    const top = clamp(clientY || window.innerHeight / 2, 12, Math.max(12, window.innerHeight - rect.height - 12));
    menu.style.left = `${left}px`;
    menu.style.top = `${top}px`;
  });
}

function closeParagraphMenu(restoreFocus = true) {
  const menu = document.querySelector("#paragraphActionMenu");
  if (!menu) return;
  const selected = document.querySelector(".paragraph-selected");
  selected?.classList.remove("paragraph-selected");
  if (restoreFocus && selected) selected.focus({preventScroll: true});
  menu.classList.remove("open");
  menu.hidden = true;
}

async function handleParagraphMenuAction(event, novelId, chapterNumber, source) {
  const button = event.target.closest("[data-paragraph-action]");
  if (!button) return;
  const menu = event.currentTarget;
  const paragraph = [...document.querySelectorAll("[data-paragraph-index]")].find((item) => item.dataset.paragraphIndex === (menu.dataset.paragraphIndex || ""));
  const text = menu.dataset.paragraphText || paragraph?.dataset.readerParagraph || "";
  const action = button.dataset.paragraphAction;
  if (action === "copy") copyParagraphValue(text);
  if (action === "bookmark") await saveBookmark(novelId, chapterNumber);
  if (action === "highlight" && paragraph) {
    paragraph.classList.toggle("reader-highlighted");
    toast(paragraph.classList.contains("reader-highlighted") ? "Paragraph highlighted." : "Highlight removed.");
  }
  if (action === "report") toast("Translation issue noted locally.");
  if (action === "original" && canViewReference()) {
    window.location.hash = `#/reader/${encodeURIComponent(novelId)}/${chapterNumber}/original`;
  }
  closeParagraphMenu(false);
}

function copyParagraphText(event) {
  const paragraph = event.currentTarget.closest("[data-reader-paragraph]");
  const text = paragraph?.dataset.readerParagraph || "";
  copyParagraphValue(text);
}

function copyParagraphValue(text) {
  if (!text) return;
  if (!navigator.clipboard?.writeText) return toast("Clipboard is unavailable in this browser.");
  navigator.clipboard.writeText(text).then(() => toast("Paragraph copied.")).catch(() => toast("Unable to copy paragraph."));
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function toggleReaderTitleDetail(event) {
  const button = event.currentTarget;
  const target = document.querySelector(`#${button.getAttribute("aria-controls")}`);
  if (!target) return;
  const nextHidden = !target.hidden;
  target.hidden = nextHidden;
  button.setAttribute("aria-expanded", nextHidden ? "false" : "true");
  button.textContent = nextHidden ? "Title details" : "Hide title details";
}

function escapeRegExp(value) {
  return String(value || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function renderChapterDrawer(novelId, chapterNumber, source) {
  return `<section class="chapter-drawer" id="chapterDrawer" role="dialog" aria-modal="true" aria-labelledby="chapterDrawerTitle" hidden>
    <div class="sheet-header"><div><p class="eyebrow">Chapter List</p><h2 id="chapterDrawerTitle">Choose a chapter</h2></div><button id="closeChapterDrawer" type="button">Close</button></div>
    <input id="chapterSearch" type="search" placeholder="Search chapters">
    <div class="chapter-drawer-list">${state.chapters.map((chapter) => `<a class="${chapter.chapter_number === chapterNumber ? "current" : ""}" href="#/reader/${novelId}/${chapter.chapter_number}/${source}" data-chapter-row><strong>Chapter ${chapter.chapter_number}</strong><span>${escapeHtml(displayChapterTitle(chapter, source))}</span><small>${chapter.has_english || chapter.has_ai ? "English" : chapter.has_original ? "Original" : "Missing"}</small></a>`).join("")}</div>
  </section>`;
}

function renderReaderSettingsSheet() {
  const pref = state.preferences;
  return `<section class="reader-settings-sheet" id="readerSettingsSheet" role="dialog" aria-modal="true" aria-labelledby="readerSettingsTitle" hidden>
    <div class="sheet-header"><div><p class="eyebrow">Reader Settings</p><h2 id="readerSettingsTitle">Reading surface</h2></div><button id="closeReaderSettings" type="button">Close</button></div>
    <div class="reader-settings-preview"><p>Preview text scale, rhythm, width, and tone without leaving the chapter.</p></div>
    <div class="reader-settings-grid">
      <label>Theme<select data-pref="readerTone"><option value="dark" ${pref.readerTone === "dark" ? "selected" : ""}>Dark</option><option value="paper" ${pref.readerTone === "paper" ? "selected" : ""}>Light</option><option value="sepia" ${pref.readerTone === "sepia" ? "selected" : ""}>Sepia</option><option value="oled" ${pref.readerTone === "oled" ? "selected" : ""}>AMOLED</option></select></label>
      <label>Font<select data-pref="readerFont"><option value="serif" ${pref.readerFont === "serif" ? "selected" : ""}>Serif</option><option value="sans" ${pref.readerFont === "sans" ? "selected" : ""}>Sans</option><option value="system" ${pref.readerFont === "system" ? "selected" : ""}>System</option></select></label>
      <label>Size<input data-pref="readerFontSize" type="range" min="16" max="26" value="${escapeAttr(pref.readerFontSize || state.fontSize)}"></label>
      <label>Line height<input data-pref="readerLineHeight" type="range" min="1.55" max="2.1" step="0.05" value="${escapeAttr(pref.readerLineHeight || 1.86)}"></label>
      <label>Column width<input data-pref="readingWidth" type="range" min="620" max="940" step="20" value="${escapeAttr(pref.readingWidth || 760)}"></label>
      <label>Paragraph spacing<input data-pref="paragraphSpacing" type="range" min="0.85" max="1.6" step="0.05" value="${escapeAttr(pref.paragraphSpacing || 1.22)}"></label>
      <label>Alignment<select data-pref="textAlign"><option value="left" ${pref.textAlign === "left" ? "selected" : ""}>Left</option><option value="justify" ${pref.textAlign === "justify" ? "selected" : ""}>Justified</option></select></label>
      ${radioToggle("reduceMotion", pref.reduceMotion, "Reduce motion", "Calmer transitions")}
      ${radioToggle("contrastFocus", pref.contrastFocus, "High contrast focus", "Stronger focus outlines")}
      ${radioToggle("accessibilityComfort", pref.accessibilityComfort, "Comfort reading", "Stable spacing and softer reader chrome")}
    </div>
    <div class="actions"><a class="button" href="#/settings/reader">Open Studio</a><button id="zenToggleSheet" class="primary" type="button">Toggle Focus</button></div>
  </section>`;
}

function filterChapterDrawer(event) {
  const query = event.target.value.trim().toLowerCase();
  document.querySelectorAll("[data-chapter-row]").forEach((row) => {
    row.hidden = query && !row.textContent.toLowerCase().includes(query);
  });
}

function openChapterDrawer() {
  const drawer = document.querySelector("#chapterDrawer");
  const backdrop = document.querySelector("#chapterDrawerBackdrop");
  if (!drawer) return;
  drawer.hidden = false;
  if (backdrop) backdrop.hidden = false;
  drawer.classList.add("open");
  backdrop?.classList.add("open");
  document.body.dataset.readerOverlay = "open";
  drawer.dataset.restoreFocus = "readerMenuToggle";
  document.querySelector("#chapterSearch")?.focus();
  document.querySelector(".chapter-drawer .current")?.scrollIntoView({block: "center"});
}

function closeChapterDrawer() {
  const drawer = document.querySelector("#chapterDrawer");
  const backdrop = document.querySelector("#chapterDrawerBackdrop");
  if (!drawer) return;
  drawer.classList.remove("open");
  backdrop?.classList.remove("open");
  finishReaderOverlayClose(drawer, backdrop, () => {
    if (document.querySelector("#readerMenuPanel")?.hidden !== false) document.body.dataset.readerOverlay = "closed";
    document.querySelector(`#${drawer.dataset.restoreFocus || "openChapterDrawer"}`)?.focus();
  });
}

function openReaderMenu() {
  const menu = document.querySelector("#readerMenuPanel");
  const backdrop = document.querySelector("#readerMenuBackdrop");
  if (!menu) return;
  menu.hidden = false;
  if (backdrop) backdrop.hidden = false;
  menu.classList.add("open");
  backdrop?.classList.add("open");
  document.body.dataset.readerOverlay = "open";
  menu.dataset.restoreFocus = "readerMenuToggle";
  menu.querySelector("button, a, input, select")?.focus();
}

function closeReaderMenu(restoreFocus = true) {
  const menu = document.querySelector("#readerMenuPanel");
  const backdrop = document.querySelector("#readerMenuBackdrop");
  if (!menu) return;
  menu.classList.remove("open");
  backdrop?.classList.remove("open");
  finishReaderOverlayClose(menu, backdrop, () => {
    if (document.querySelector("#chapterDrawer")?.hidden !== false) document.body.dataset.readerOverlay = "closed";
    if (restoreFocus) document.querySelector(`#${menu.dataset.restoreFocus || "readerMenuToggle"}`)?.focus();
  });
}

function finishReaderOverlayClose(panel, backdrop, afterClose) {
  const complete = () => {
    if (panel.classList.contains("open")) return;
    panel.hidden = true;
    if (backdrop) backdrop.hidden = true;
    afterClose?.();
  };
  if (state.preferences.reduceMotion) {
    complete();
    return;
  }
  window.setTimeout(complete, 155);
}

function isDuplicateChapterHeading(line, payload) {
  const stripped = String(line || "").replace(/^#{1,6}\s*/, "").trim();
  const normalizedLine = stripped.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();
  const normalizedTitle = String(payload.title || "").toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();
  const chapterPrefix = `chapter ${payload.chapter_number || ""}`.trim();
  return /^#{1,6}\s*/.test(line) && (normalizedLine === normalizedTitle || (chapterPrefix && normalizedLine.startsWith(chapterPrefix)));
}

async function saveBookmark(novelId, chapterNumber) {
  if (!state.account) {
    toggleLocalBookmark(novelId, chapterNumber);
    const button = document.querySelector("#bookmarkChapter");
    const menuButton = document.querySelector("#menuBookmark");
    const active = isBookmarkedLocally(novelId, chapterNumber);
    if (button) {
      button.textContent = active ? "Bookmarked" : "Bookmark";
      button.setAttribute("aria-pressed", active ? "true" : "false");
    }
    if (menuButton) {
      menuButton.textContent = active ? "Bookmarked" : "Bookmark";
      menuButton.setAttribute("aria-pressed", active ? "true" : "false");
    }
    return toast(active ? "Bookmark saved on this device." : "Bookmark removed from this device.");
  }
  const note = "";
  await api("/api/account/bookmarks", {method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify({novel_id: novelId, chapter_number: chapterNumber, note})});
  await loadPersonalHome(true);
  toast("Bookmark saved.");
}

function localBookmarkKey(novelId, chapterNumber) {
  return `${novelId}:${Number(chapterNumber)}`;
}

function localBookmarks() {
  return readStored("gt-local-bookmarks", []);
}

function isBookmarkedLocally(novelId, chapterNumber) {
  const key = localBookmarkKey(novelId, chapterNumber);
  return localBookmarks().some((item) => item.key === key);
}

function toggleLocalBookmark(novelId, chapterNumber) {
  const key = localBookmarkKey(novelId, chapterNumber);
  const existing = localBookmarks();
  const novel = state.novels.find((item) => item.id === novelId) || {};
  const chapter = state.chapters.find((item) => item.chapter_number === Number(chapterNumber)) || {};
  const next = existing.some((item) => item.key === key)
    ? existing.filter((item) => item.key !== key)
    : [{key, novel_id: novelId, novel_title: novel.title || novelId, chapter_number: Number(chapterNumber), chapter_title: chapter.title || `Chapter ${chapterNumber}`, created_at: new Date().toISOString()}, ...existing];
  writeStored("gt-local-bookmarks", next.slice(0, 200));
}

const saveProgressDebounced = debounce(async (novelId, chapterNumber, source, scrollPercent) => {
  if (!state.account) return;
  try {
    await api("/api/account/progress", {method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify({novel_id: novelId, chapter_number: chapterNumber, source, scroll_percent: scrollPercent})});
    state.personal = null;
  } catch {
    // Reading should never be interrupted by private progress sync failure.
  }
}, 700);

function readerScrollPercent() {
  const total = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
  return Math.max(0, Math.min(100, window.scrollY / total * 100));
}

async function openHistory() {
  if (!state.account) return openSettings("account");
  setLoading("Loading history...");
  try {
    const payload = await api("/api/account/history");
    app.innerHTML = `${pageHeader("Reading History", `Your recent ${APP_BRAND.shortName} reading sessions.`, [["Items", payload.history.length]])}
      <section class="table-card"><table class="responsive-table"><thead><tr><th>Novel</th><th>Chapter</th><th>Source</th><th>Progress</th><th></th></tr></thead><tbody>
      ${payload.history.map((item) => `<tr><td data-label="Novel">${escapeHtml(item.novel_title)}</td><td data-label="Chapter">Chapter ${item.chapter_number}<br><span>${escapeHtml(item.chapter_title)}</span></td><td data-label="Source">${escapeHtml(sourceLabels[item.source] || item.source)}</td><td data-label="Progress">${Math.round(item.progress_percent || 0)}%</td><td data-label="Actions"><a class="button" href="#/reader/${item.novel_id}/${item.chapter_number}/${item.source}">Continue</a></td></tr>`).join("") || `<tr><td colspan="5">No reading history yet.</td></tr>`}
      </tbody></table><div class="actions"><button id="clearHistory" type="button">Clear History</button></div></section>`;
    document.querySelector("#clearHistory")?.addEventListener("click", async () => { await api("/api/account/history", {method: "DELETE"}); openHistory(); });
  } catch (error) {
    setError(error.message);
  }
}

async function openBookmarks() {
  if (!state.account) return openSettings("account");
  setLoading("Loading bookmarks...");
  try {
    const payload = await api("/api/account/bookmarks");
    app.innerHTML = `${pageHeader("Bookmarks", "Saved chapters and personal notes.", [["Items", payload.bookmarks.length]])}
      <section class="table-card"><table class="responsive-table"><thead><tr><th>Novel</th><th>Chapter</th><th>Note</th><th></th></tr></thead><tbody>
      ${payload.bookmarks.map((item) => `<tr><td data-label="Novel">${escapeHtml(item.novel_title)}</td><td data-label="Chapter">Chapter ${item.chapter_number}<br><span>${escapeHtml(item.chapter_title)}</span></td><td data-label="Note">${escapeHtml(item.note || "")}</td><td data-label="Actions" class="row-actions"><a class="button" href="#/reader/${item.novel_id}/${item.chapter_number}/${state.source}">Read</a><button data-delete-bookmark="${item.novel_id}:${item.chapter_number}">Remove</button></td></tr>`).join("") || `<tr><td colspan="4">No bookmarks yet.</td></tr>`}
      </tbody></table></section>`;
    document.querySelectorAll("[data-delete-bookmark]").forEach((button) => button.addEventListener("click", async () => {
      const [novelId, chapter] = button.dataset.deleteBookmark.split(":");
      const removed = payload.bookmarks.find((item) => item.novel_id === novelId && String(item.chapter_number) === String(chapter));
      await api(`/api/account/bookmarks/${encodeURIComponent(novelId)}/${chapter}`, {method: "DELETE"});
      toast("Bookmark removed.", "Undo", async () => {
        await api("/api/account/bookmarks", {method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify({novel_id: novelId, chapter_number: Number(chapter), note: removed?.note || ""})});
        openBookmarks();
      });
      openBookmarks();
    }));
  } catch (error) {
    setError(error.message);
  }
}

async function openTranslate(novelId, params = new URLSearchParams()) {
  setLoading("Loading translation workspace...");
  try {
    state.currentNovelId = novelId;
    localStorage.setItem("gt-current-novel", novelId);
    await refreshSession();
    await loadNovels();
    if (!canTranslate()) return renderAdminGate("Translate");
    const [jobs, modelRegistry, coveragePreview] = await Promise.all([
      api(`/api/translation/jobs?novel_id=${encodeURIComponent(novelId)}`),
      api("/api/models"),
      state.admin ? api(`/api/admin/novels/${encodeURIComponent(novelId)}/english-coverage/preview`).catch(() => null) : Promise.resolve(null),
    ]);
    const novel = state.novels.find((item) => item.id === novelId) || {};
    const models = modelRegistry.models || [];
    const draft = translateDraft(novelId);
    const englishReady = Number(novel.english_count ?? novel.ai_count ?? 0);
    const translationOptional = englishReady > 0 && Number(novel.remaining_count || 0) === 0;
    const form = params.get("chapter") ? {...draft, selection_mode: "specific", chapters: params.get("chapter"), all_untranslated: false} : draft;
    const mode = form.translation_mode || "simple";
    const selectionMode = form.selection_mode || (form.all_untranslated ? "all-untranslated" : "next-untranslated");
    const speedPreset = form.speed_preset || (mode === "economy" ? "economy" : "balanced");
    const nextPresetValues = ["25", "50", "100", "200", "500", "1000", "all"];
    const nextCountMode = form.next_count_mode || (String(form.next_count || "25").toLowerCase() === "all" ? "all" : (nextPresetValues.includes(String(form.next_count || "25")) ? String(form.next_count || "25") : "custom"));
    const customNextCount = nextCountMode === "custom" ? (form.custom_next_count || form.next_count || "") : "";
    state.lastEstimate = null;
    app.innerHTML = `
      ${renderBreadcrumbs()}
      <section class="translate-hero">
        <div>
          <p class="eyebrow">Translation Workspace</p>
          <h1>Translate</h1>
          <p>${translationOptional ? "Translation is not required because a readable English edition already exists. You can still create an alternative edition or retranslate selected chapters." : "Plan controlled translation jobs from Original text, with Reference as optional guidance when available."}</p>
        </div>
        <div class="translate-hero-summary">
          <span class="badge ok">Current novel</span>
          <strong>${escapeHtml(novel.title || novelId)}</strong>
          <div class="metric-grid">
            ${metric("Default model", novel.model || "gpt-4o-mini")}
            ${metric("English Ready", englishReady)}
            ${metric("Missing English", novel.missing_english_count ?? novel.remaining_count ?? 0)}
          </div>
        </div>
      </section>
      ${translationOptional ? `<section class="panel"><h2>Translation Not Required</h2><p class="muted">English edition already exists for this novel. Use this workspace only when you want to retranslate selected chapters, create an alternative edition, or replace the active edition.</p></section>` : ""}
      ${renderEnglishCoveragePanel(coveragePreview)}
      <section class="draft-bar"><span id="draftStatus">${draft.saved_at ? `Draft saved ${timeAgo(draft.saved_at)}` : "No saved draft"}</span><div class="actions"><button id="restoreTranslateDraft" type="button" ${draft.saved_at ? "" : "disabled"}>Restore Draft</button><button id="discardTranslateDraft" type="button" ${draft.saved_at ? "" : "disabled"}>Discard Draft</button></div></section>
      <section class="translate-workspace">
        <div class="translate-steps" id="translateForm">
          <section class="workspace-panel form-grid"><div class="wide"><h2>1. Mode & Chapters</h2><p class="muted">Simple mode keeps the required choices visible and leaves performance controls hidden.</p></div><label>Mode<select id="translationMode"><option value="simple" ${mode === "simple" ? "selected" : ""}>Simple</option><option value="fast" ${mode === "fast" ? "selected" : ""}>Fast</option><option value="advanced" ${mode === "advanced" ? "selected" : ""}>Advanced</option><option value="economy" ${mode === "economy" ? "selected" : ""}>Economy / Overnight</option></select></label><label>Novel<select id="translateNovel">${state.novels.map((n) => `<option value="${n.id}" ${n.id === novelId ? "selected" : ""}>${escapeHtml(n.title)}</option>`).join("")}</select></label><label>What to translate<select id="selectionMode"><option value="next-untranslated" ${selectionMode === "next-untranslated" ? "selected" : ""}>Next untranslated chapters</option><option value="specific" ${selectionMode === "specific" ? "selected" : ""}>Specific chapters</option><option value="all-untranslated" ${selectionMode === "all-untranslated" ? "selected" : ""}>All untranslated chapters</option></select></label><label id="nextCountLabel">Count<select id="nextCount"><option value="25" ${nextCountMode === "25" ? "selected" : ""}>25</option><option value="50" ${nextCountMode === "50" ? "selected" : ""}>50</option><option value="100" ${nextCountMode === "100" ? "selected" : ""}>100</option><option value="200" ${nextCountMode === "200" ? "selected" : ""}>200</option><option value="500" ${nextCountMode === "500" ? "selected" : ""}>500</option><option value="1000" ${nextCountMode === "1000" ? "selected" : ""}>1000</option><option value="all" ${nextCountMode === "all" ? "selected" : ""}>All</option><option value="custom" ${nextCountMode === "custom" ? "selected" : ""}>Custom</option></select></label><label id="customNextCountLabel">Custom count<input id="customNextCount" type="number" min="1" step="1" value="${escapeAttr(customNextCount)}"><span class="field-error" id="customCountError"></span></label><label id="chapterInputLabel">Chapters<input id="translateChapters" value="${escapeAttr(form.chapters || "")}" placeholder="1-50,75,100-125"><span class="field-error" id="chapterError"></span></label><p class="muted wide" id="chapterPreview">Choose what to translate.</p></section>
          <section class="workspace-panel form-grid"><div class="wide"><h2>2. Translation Profile</h2><p class="muted">Optional style and glossary notes shape the job without changing source data.</p></div><label>Profile<select id="profile"><option ${form.profile === "Default literary translation" ? "selected" : ""}>Default literary translation</option><option ${form.profile === "Reference-guided polish" ? "selected" : ""}>Reference-guided polish</option></select></label><label class="wide">Style guide<textarea id="styleGuide" rows="3">${escapeHtml(form.style_guide || "")}</textarea></label><label class="wide">Glossary notes<textarea id="glossary" rows="3">${escapeHtml(form.glossary || "")}</textarea></label></section>
          <section class="workspace-panel form-grid"><div class="wide"><h2>3. Speed & Model</h2><p class="muted">Each preset maps to concrete worker, retry, and timeout settings while the scheduler keeps global limits bounded.</p></div><label>Speed preset<select id="speedPreset"><option value="careful" ${speedPreset === "careful" ? "selected" : ""}>Careful - lowest pressure</option><option value="balanced" ${speedPreset === "balanced" ? "selected" : ""}>Balanced - recommended</option><option value="fast" ${speedPreset === "fast" ? "selected" : ""}>Fast - higher parallel processing</option><option value="maximum-safe" ${speedPreset === "maximum-safe" ? "selected" : ""}>Maximum Safe - highest safe throughput</option><option value="economy" ${speedPreset === "economy" ? "selected" : ""}>Economy - lowest background pressure</option><option value="overnight" ${speedPreset === "overnight" ? "selected" : ""}>Overnight - unattended low pressure</option><option value="custom" ${speedPreset === "custom" ? "selected" : ""}>Custom - use advanced controls</option></select></label><label>Model<select id="model">${models.map((model) => `<option value="${escapeAttr(model.id)}" ${model.id === (form.model || novel.model || "gpt-4o-mini") ? "selected" : ""}>${escapeHtml(model.display_name)} - ${escapeHtml(model.pricing?.note || "Pricing not configured")}</option>`).join("")}</select></label><label class="inline-check"><input id="autoOptimizeSpeed" type="checkbox" ${speedPreset === "custom" ? "disabled" : ""} ${form.auto_optimize_speed === false || speedPreset === "custom" ? "" : "checked"}> Auto Optimize Speed</label><p class="muted wide" id="speedDescription">Speed is being optimized automatically.</p></section>
          <section class="workspace-panel form-grid"><div class="wide"><h2>4. Budget & Safety</h2><p class="muted">Budget caps are optional; launch stays locked until this form has a current estimate.</p></div><label>Max total budget<input id="maxTotalBudget" type="number" step="0.01" value="${escapeAttr(form.max_total_budget ?? "")}"><span class="field-error" id="budgetError"></span></label><label>Max cost per chapter<input id="maxPerChapterBudget" type="number" step="0.001" value="${escapeAttr(form.max_per_chapter_budget ?? "")}"></label><label class="inline-check"><input id="useReference" type="checkbox" ${form.use_reference === false ? "" : "checked"}> Use Reference when available</label><label class="inline-check"><input id="onlyUntranslated" type="checkbox" ${form.only_untranslated === false ? "" : "checked"}> Only untranslated</label><div class="advanced-settings wide"><h3>Advanced Performance</h3><div class="form-grid"><label>Retry limit<input id="retryCount" type="number" min="0" max="5" value="${escapeAttr(form.retry_count ?? 2)}"></label><label>Queue depth<input id="batchSize" type="number" min="1" max="5000" value="${escapeAttr(form.batch_size ?? 25)}"></label><label>Maximum workers<select id="translationConcurrency"><option value="" ${form.concurrency ? "" : "selected"}>Auto</option><option value="1" ${Number(form.concurrency) === 1 ? "selected" : ""}>1 worker</option><option value="2" ${Number(form.concurrency) === 2 ? "selected" : ""}>2 workers</option><option value="3" ${Number(form.concurrency) === 3 ? "selected" : ""}>3 workers</option><option value="4" ${Number(form.concurrency) === 4 ? "selected" : ""}>4 workers</option><option value="6" ${Number(form.concurrency) === 6 ? "selected" : ""}>6 workers</option><option value="8" ${Number(form.concurrency) === 8 ? "selected" : ""}>8 workers</option></select></label><label>Priority<select id="jobPriority"><option value="normal" ${form.priority === "high" ? "" : "selected"}>Normal</option><option value="high" ${form.priority === "high" ? "selected" : ""}>High</option></select></label><label class="inline-check"><input id="stopOnBudget" type="checkbox" ${form.stop_on_budget === false ? "" : "checked"}> Stop on budget</label></div></div></section>
        </div>
        <aside class="estimate-panel"><h2>5. Estimate</h2><section id="estimateResult"><p class="muted">Run an estimate before creating a job. Estimates are approximate.</p></section><p class="muted" id="launchReason">Run an estimate before Launch Job is available.</p><div class="actions"><button id="estimateBtn" class="primary">Estimate</button><button id="createJobBtn" disabled>Launch Job</button></div></aside>
      </section>
      <section class="table-card"><h2>Recent Jobs</h2>${renderJobsTable(jobs.jobs || [])}</section>`;
    document.querySelector("#translateNovel").addEventListener("change", (e) => { window.location.hash = `#/translate/${e.target.value}`; });
    document.querySelector("#translateChapters").addEventListener("input", renderChapterPreview);
    document.querySelector("#selectionMode").addEventListener("change", renderChapterPreview);
    document.querySelector("#nextCount").addEventListener("change", renderChapterPreview);
    document.querySelector("#customNextCount").addEventListener("input", renderChapterPreview);
    document.querySelector("#translationMode").addEventListener("change", toggleTranslationMode);
    document.querySelector("#speedPreset").addEventListener("change", toggleTranslationMode);
    document.querySelector("#autoOptimizeSpeed").addEventListener("change", updateSpeedDescription);
    document.querySelector("#estimateBtn").addEventListener("click", estimateTranslation);
    document.querySelector("#createJobBtn").addEventListener("click", createTranslationJob);
    document.querySelector("#applyReferenceCoverage")?.addEventListener("click", () => applyReferenceCoverage(novelId));
    document.querySelector("#createCoverageTranslationJob")?.addEventListener("click", () => createCoverageTranslationJob(novelId));
    document.querySelector("#restoreTranslateDraft").addEventListener("click", () => openTranslate(novelId));
    document.querySelector("#discardTranslateDraft").addEventListener("click", () => { localStorage.removeItem(translateDraftKey(novelId)); openTranslate(novelId); });
    document.querySelectorAll("#translateForm input, #translateForm textarea, #translateForm select").forEach((field) => field.addEventListener("input", () => {
      state.lastEstimate = null;
      const result = document.querySelector("#estimateResult");
      if (result) result.innerHTML = `<p class="muted">Run an estimate before creating a job. Estimates are approximate.</p>`;
      saveTranslateDraft();
      validateTranslateForm();
    }));
    renderChapterPreview();
    toggleTranslationMode();
    validateTranslateForm();
    bindJobButtons();
    bindCopyLinks(app);
  } catch (error) {
    setError(error.message);
  }
}

function renderEnglishCoveragePanel(preview) {
  if (!preview || !state.admin) return "";
  const samples = preview.samples || {};
  const referenceSamples = (samples.reference_fill || []).map((item) => `Chapter ${item.chapter_number}`).slice(0, 8).join(", ");
  const aiSamples = (samples.translation_from_original || []).map((item) => `Chapter ${item.chapter_number}`).slice(0, 8).join(", ");
  const blockedSamples = (samples.blocked_missing_source || []).map((item) => `Chapter ${item.chapter_number}`).slice(0, 8).join(", ");
  const referenceCount = Number(preview.reference_fill || preview.reference_promotions || 0);
  const aiCount = Number(preview.translation_from_original || preview.estimated_openai_chapters || 0);
  const disabledReference = referenceCount ? "" : "disabled";
  const disabledAi = aiCount ? "" : "disabled";
  return `<section class="coverage-panel" aria-labelledby="coverageTitle">
    <div class="coverage-heading">
      <div>
        <p class="eyebrow">Build English Coverage</p>
        <h2 id="coverageTitle">Reference-first coverage plan</h2>
        <p class="muted">Reference text is already English. Use the no-cost Reference action before creating any paid Original-based translation job.</p>
      </div>
      <span class="badge ${preview.policy === "reference_first" ? "ok" : ""}">${escapeHtml(titleCase(String(preview.policy || "").replaceAll("_", " ")))}</span>
    </div>
    <div class="metric-grid coverage-metrics">
      ${metric("Total chapters", preview.total_chapters || 0)}
      ${metric("Existing English", preview.existing_english || 0)}
      ${metric("Can fill from Reference", referenceCount)}
      ${metric("Needs AI translation", aiCount)}
      ${metric("Blocked", preview.blocked || preview.blocked_missing_source || 0)}
      ${metric("Reference cost", "$0.00")}
    </div>
    <div class="coverage-breakdown">
      <p><strong>Reference promotions</strong><span>${referenceSamples || "None"}</span></p>
      <p><strong>AI translation candidates</strong><span>${aiSamples || "None"}</span></p>
      <p><strong>Blocked</strong><span>${blockedSamples || "None"}</span></p>
    </div>
    <div class="actions">
      <button id="applyReferenceCoverage" class="primary" type="button" ${disabledReference}>Use Reference for ${referenceCount} chapter${referenceCount === 1 ? "" : "s"}</button>
      <button id="createCoverageTranslationJob" type="button" ${disabledAi}>Create AI job for ${aiCount} chapter${aiCount === 1 ? "" : "s"}</button>
    </div>
  </section>`;
}

async function applyReferenceCoverage(novelId) {
  const button = document.querySelector("#applyReferenceCoverage");
  if (button) button.disabled = true;
  try {
    const result = await api(`/api/admin/novels/${encodeURIComponent(novelId)}/english-coverage/apply-reference`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({})});
    invalidateCache("/api/novels");
    invalidateCache(`/api/novels/${encodeURIComponent(novelId)}`);
    toast(`Reference applied for ${result.promoted_count || 0} chapter${Number(result.promoted_count || 0) === 1 ? "" : "s"}.`);
    openTranslate(novelId);
  } catch (error) {
    if (button) button.disabled = false;
    toast(error.message || "Reference coverage failed.");
  }
}

async function createCoverageTranslationJob(novelId) {
  const button = document.querySelector("#createCoverageTranslationJob");
  if (button) button.disabled = true;
  try {
    const result = await api(`/api/admin/novels/${encodeURIComponent(novelId)}/english-coverage/create-translation-job`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(translatePayload())});
    toast(`Coverage job ${String(result.job.id || "").slice(0, 8)} queued.`);
    window.location.hash = "#/jobs";
  } catch (error) {
    if (button) button.disabled = false;
    toast(error.message || "Coverage job was not created.");
  }
}

function translatePayload() {
  const selectionMode = document.querySelector("#selectionMode").value;
  const translationMode = document.querySelector("#translationMode").value;
  const speedPreset = document.querySelector("#speedPreset").value;
  const useAdvancedControls = translationMode === "advanced" || speedPreset === "custom";
  const nextCountMode = document.querySelector("#nextCount").value;
  const customNextCount = numberOrNull("#customNextCount");
  const nextCount = nextCountMode === "custom" ? customNextCount : (nextCountMode === "all" ? "all" : Number(nextCountMode || 25));
  return {
    novel_id: document.querySelector("#translateNovel").value,
    translation_mode: translationMode,
    speed_preset: speedPreset,
    auto_optimize_speed: document.querySelector("#autoOptimizeSpeed").checked,
    selection_mode: selectionMode,
    next_count: nextCount,
    next_count_mode: nextCountMode,
    custom_next_count: customNextCount,
    chapters: document.querySelector("#translateChapters").value,
    all_untranslated: selectionMode === "all-untranslated" || (selectionMode === "next-untranslated" && nextCountMode === "all"),
    model: document.querySelector("#model").value || "gpt-4o-mini",
    max_total_budget: numberOrNull("#maxTotalBudget"),
    max_per_chapter_budget: numberOrNull("#maxPerChapterBudget"),
    retry_count: numberOrNull("#retryCount"),
    batch_size: useAdvancedControls ? numberOrNull("#batchSize") : null,
    concurrency: useAdvancedControls ? numberOrNull("#translationConcurrency") : null,
    stop_on_budget: document.querySelector("#stopOnBudget").checked,
    use_reference: document.querySelector("#useReference").checked,
    only_untranslated: document.querySelector("#onlyUntranslated").checked,
    priority: document.querySelector("#jobPriority")?.value || "normal",
    profile: document.querySelector("#profile")?.value || "Default literary translation",
    style_guide: document.querySelector("#styleGuide").value,
    glossary: document.querySelector("#glossary")?.value || "",
  };
}

function renderChapterPreview() {
  const target = document.querySelector("#chapterPreview");
  if (!target) return;
  const mode = document.querySelector("#selectionMode")?.value || "next-untranslated";
  const chapterLabel = document.querySelector("#chapterInputLabel");
  const nextLabel = document.querySelector("#nextCountLabel");
  const customLabel = document.querySelector("#customNextCountLabel");
  if (chapterLabel) chapterLabel.hidden = mode !== "specific";
  if (nextLabel) nextLabel.hidden = mode !== "next-untranslated";
  if (customLabel) customLabel.hidden = mode !== "next-untranslated" || document.querySelector("#nextCount")?.value !== "custom";
  if (mode === "all-untranslated") {
    target.textContent = "Preview: all eligible untranslated chapters will be selected from the database when the job is created. Chapters without Original text and existing English editions are skipped unless retranslation is selected.";
    return;
  }
  if (mode === "next-untranslated") {
    const countMode = document.querySelector("#nextCount")?.value || "25";
    const label = countMode === "custom" ? (document.querySelector("#customNextCount")?.value || "custom") : countMode;
    target.textContent = countMode === "all"
      ? "Preview: all eligible untranslated chapters will be selected from the database when the job is created."
      : `Preview: the next ${label} eligible untranslated chapters will be selected from the database when the job is created.`;
    validateTranslateForm();
    return;
  }
  const parsed = parseChapterInputDetailed(document.querySelector("#translateChapters")?.value || "");
  validateTranslateForm();
  target.textContent = parsed.chapters.length
    ? `Preview: ${parsed.chapters.length} chapter${parsed.chapters.length === 1 ? "" : "s"} selected (${parsed.chapters.slice(0, 12).join(", ")}${parsed.chapters.length > 12 ? ", ..." : ""}). ${parsed.duplicatesRemoved ? `${parsed.duplicatesRemoved} duplicate${parsed.duplicatesRemoved === 1 ? "" : "s"} removed. ` : ""}${parsed.invalidTokens.length ? `Invalid: ${parsed.invalidTokens.join(", ")}.` : ""}`
    : "Enter chapters like 26,53,60-70.";
}

function parseChapterInput(value) {
  return parseChapterInputDetailed(value).chapters;
}

function parseChapterInputDetailed(value) {
  const chapters = new Set();
  const invalidTokens = [];
  let rawCount = 0;
  String(value || "").split(",").map((item) => item.trim()).filter(Boolean).forEach((part) => {
    if (/^\d+\s*-\s*\d+$/.test(part)) {
      const [a, b] = part.split("-").map((item) => Number(item.trim()));
      if (a <= 0 || b <= 0) {
        invalidTokens.push(part);
      } else {
        for (let i = Math.min(a, b); i <= Math.max(a, b); i += 1) {
          rawCount += 1;
          chapters.add(i);
        }
      }
    } else if (/^\d+$/.test(part) && Number(part) > 0) {
      rawCount += 1;
      chapters.add(Number(part));
    } else {
      invalidTokens.push(part);
    }
  });
  const ordered = [...chapters].sort((a, b) => a - b);
  return {chapters: ordered, invalidTokens, duplicatesRemoved: Math.max(0, rawCount - ordered.length)};
}

function toggleTranslationMode() {
  const mode = document.querySelector("#translationMode")?.value || "simple";
  const advanced = document.querySelector(".advanced-settings");
  const speedPreset = document.querySelector("#speedPreset");
  if (speedPreset && mode === "economy" && !["economy", "overnight"].includes(speedPreset.value)) speedPreset.value = "economy";
  if (speedPreset && mode === "fast" && speedPreset.value === "careful") speedPreset.value = "fast";
  if (advanced) advanced.hidden = mode !== "advanced" && speedPreset?.value !== "custom";
  updateSpeedDescription();
  renderChapterPreview();
}

function updateSpeedDescription() {
  const mode = document.querySelector("#translationMode")?.value || "simple";
  const preset = document.querySelector("#speedPreset")?.value || "balanced";
  const auto = document.querySelector("#autoOptimizeSpeed")?.checked;
  const descriptions = {
    careful: "Careful uses the lowest server/API pressure.",
    balanced: "Balanced is recommended for most translation jobs.",
    fast: "Fast uses higher parallel processing when capacity allows.",
    "maximum-safe": "Maximum Safe uses the highest safe adaptive throughput currently available.",
    economy: "Economy uses one low-pressure worker for budget-conscious queues.",
    overnight: "Overnight uses low-pressure workers with longer timeouts and additional retries.",
    custom: "Custom uses the advanced worker, queue, retry, and timeout controls supplied with this job.",
  };
  const autoToggle = document.querySelector("#autoOptimizeSpeed");
  if (autoToggle) {
    autoToggle.disabled = preset === "custom";
    if (preset === "custom") autoToggle.checked = false;
  }
  const suffix = preset === "custom" ? " Auto optimization is off so custom controls are honored." : (auto ? " Speed is being optimized automatically." : " Auto optimization is off for this job.");
  const economy = mode === "economy" ? " Economy / Overnight prioritizes low pressure and is not intended for immediate completion. " : "";
  const target = document.querySelector("#speedDescription");
  if (target) target.textContent = `${economy}${descriptions[preset] || descriptions.balanced}${suffix}`;
}

async function estimateTranslation(event) {
  event.preventDefault();
  if (!validateTranslateForm()) return toast("Fix the highlighted fields first.");
  const estimate = await api("/api/translation/estimate", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(translatePayload())});
  state.lastEstimate = estimate;
  const missingOriginal = Number(estimate.missing_original_count ?? Math.max(0, Number(estimate.selected_count || 0) - Number(estimate.original_readable || 0)));
  const referenceMissing = Math.max(0, Number(estimate.selected_count || 0) - Number(estimate.reference_available || 0));
  const tokens = estimate.token_breakdown || {};
  const selection = estimate.selection || {};
  const invalidSummary = [
    ...(estimate.invalid_tokens || []).map((item) => String(item)),
    ...(estimate.invalid_chapter_numbers || []).map((item) => `Chapter ${item}`),
  ];
  const largeWarning = Number(estimate.eligible_count || 0) >= 100
    ? `<div class="warning-panel"><strong>Large-job safety check</strong><p>Chapter count: ${estimate.selected_count}. Eligible count: ${estimate.eligible_count}. Estimated cost: $${Number(estimate.estimated_cost || 0).toFixed(4)}. Estimated duration: ${durationEstimateText(estimate.duration_estimate)}. Selected speed mode: ${titleCase(estimate.speed_preset || "balanced")}. Expected workers: ${estimate.expected_workers || 1}. Budget margin: ${budgetMarginText(estimate)}.</p><p>The existing bounded scheduler will create one persistent job with one item per chapter; workers process items independently and stay within global and per-job concurrency limits.</p></div>`
    : "";
  const allConfirmation = isAllTranslationSelection()
    ? `<label class="inline-check confirmation-check"><input id="confirmAllUntranslated" type="checkbox"> Translate all eligible chapters?</label><p class="muted">Total chapters: ${selection.total_chapters ?? estimate.selected_count}. Eligible: ${estimate.eligible_count}. Estimated cost: $${Number(estimate.estimated_cost || 0).toFixed(4)}. Estimated duration: ${durationEstimateText(estimate.duration_estimate)}. Budget limit: ${numberOrNull("#maxTotalBudget") === null ? "No cap" : `$${Number(numberOrNull("#maxTotalBudget")).toFixed(2)}`}. Speed preset: ${titleCase(estimate.speed_preset || "balanced")}.</p>`
    : "";
  const coverageNote = estimate.reference_fill_count && Number(estimate.eligible_count || 0) <= 0
    ? `<p class="muted">Translation is not required for the selected Reference-fill chapters. Use the Build English Coverage action above.</p>`
    : "";
  document.querySelector("#estimateResult").innerHTML = `<div class="metric-grid">${metric("Selected", estimate.selected_count)}${metric("Existing English", estimate.existing_english_count ?? estimate.already_translated_count ?? 0)}${metric("Can fill from Reference", estimate.reference_fill_count || 0)}${metric("Needs AI translation", estimate.needs_ai_translation_count ?? estimate.eligible_count)}${metric("Blocked", estimate.blocked_missing_source_count || 0)}${metric("Eligible", estimate.eligible_count)}${metric("Missing Original", missingOriginal)}${metric("Invalid chapters", estimate.invalid_chapter_count || 0)}${metric("Duplicates removed", estimate.duplicates_removed || 0)}${metric("Reference available", estimate.reference_available || 0)}${metric("Reference missing", referenceMissing)}${metric("Speed mode", titleCase(estimate.speed_preset || "balanced"))}${metric("Expected workers", estimate.expected_workers || 1)}${metric("Approx time", durationEstimateText(estimate.duration_estimate))}${metric("Approx cost", `$${Number(estimate.estimated_cost || 0).toFixed(4)}`)}${metric("Budget margin", budgetMarginText(estimate))}${metric("Original tokens", tokens.original_tokens ?? estimate.approx_input_tokens ?? 0)}${metric("Reference tokens", tokens.reference_tokens ?? 0)}${metric("Rules/glossary", tokens.instruction_glossary_tokens ?? 0)}${metric("Output tokens", tokens.estimated_output_tokens ?? estimate.approx_output_tokens ?? 0)}</div>${coverageNote}${invalidSummary.length ? `<p class="field-error">Invalid selection entries: ${escapeHtml(invalidSummary.join(", "))}</p>` : ""}${largeWarning}${allConfirmation}<p class="muted">${escapeHtml(estimate.pricing_note)} ${estimate.auto_optimize_speed ? "Speed is being optimized automatically within the configured worker bounds." : ""}</p>`;
  document.querySelector("#confirmAllUntranslated")?.addEventListener("change", validateTranslateForm);
  validateTranslateForm();
}

async function createTranslationJob(event) {
  event.preventDefault();
  if (!validateTranslateForm()) return toast("Fix the highlighted fields first.");
  if (!state.lastEstimate) return toast("Run an estimate before creating a job.");
  const created = await api("/api/translation/jobs", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(translatePayload())});
  localStorage.removeItem(translateDraftKey(created.job.novel_id));
  rememberRecent("jobs", {id: created.job.id, label: `Job ${created.job.id.slice(0, 8)}`, href: "#/jobs", at: new Date().toISOString()});
  toast(`Job ${created.job.id.slice(0, 8)} started.`);
  pushNotification("translation", "Translation job started", `${created.job.total_items || 0} chapter items queued.`, `#/jobs/${created.job.id}`);
  window.location.hash = "#/jobs";
}

function renderJobsTable(jobs, focusedJobId = "") {
  return `<table class="responsive-table job-table"><thead><tr><th>Work</th><th>Status</th><th>Progress</th><th>Now</th><th>Throughput</th><th>Budget</th><th>Actions</th></tr></thead><tbody>${jobs.map((job) => {
    const throughput = jobThroughput(job);
    const total = Number(job.total_items || 0);
    const completed = Number(job.completed_items || 0);
    const failed = Number(job.failed_items || 0);
    const remaining = Math.max(0, Number(job.total_items || 0) - Number(job.completed_items || 0) - Number(job.failed_items || 0));
    const skipped = Math.max(0, Number(job.total_items || 0) - Number(job.completed_items || 0) - Number(job.failed_items || 0) - remaining);
    const pct = total ? Math.round(completed / total * 100) : 0;
    const title = jobNovelTitle(job);
    return `<tr class="${focusedJobId === job.id ? "selected-row" : ""}"><td data-label="Work" class="job-work-cell"><a href="#/jobs/${job.id}"><strong title="${escapeAttr(title)}">${escapeHtml(title)}</strong></a><span class="technical-id" title="${escapeAttr(job.id)}">${escapeHtml(truncateMiddle(job.id, 18))}</span><span class="technical-id" title="${escapeAttr(job.model || "")}">${escapeHtml(truncateMiddle(job.model || "model pending", 26))}</span></td><td data-label="Status">${statusBadge(job.status)}<span class="subtle-line">${escapeHtml(job.health?.message || `${job.priority || "normal"} priority`)}</span></td><td data-label="Progress"><div class="mini-progress compact"><span style="width:${pct}%"></span></div><strong>${completed}/${total}</strong><span class="subtle-line">${failed} failed · ${remaining} remaining</span></td><td data-label="Now">${job.activity?.current_chapter ? `Chapter ${job.activity.current_chapter}` : "Idle"}<span class="subtle-line">${job.activity?.active_workers || 0} active workers</span></td><td data-label="Throughput">${escapeHtml(throughput.summary)}<span class="subtle-line">${escapeHtml(throughput.remaining)}</span></td><td data-label="Budget">$${Number(job.actual_cost || 0).toFixed(4)}<span class="subtle-line">est. $${Number(job.estimated_cost || 0).toFixed(4)} · ${timeAgo(job.updated_at)}</span></td><td data-label="Actions" class="row-actions"><div class="action-group">${jobActions(job)}<button type="button" data-copy-link="#/jobs/${job.id}">Copy Link</button></div><details class="job-row-details"><summary>Details</summary><p><strong>Novel ID</strong> ${escapeHtml(job.novel_id || "")}</p><p><strong>Skipped</strong> ${skipped}</p><p><strong>Model</strong> ${escapeHtml(job.model || "")}</p><p><strong>Health</strong> ${escapeHtml(job.health?.state || "unknown")}</p></details></td></tr>`;
  }).join("") || `<tr><td colspan="7">No translation jobs yet.</td></tr>`}</tbody></table>`;
}

function jobActions(job) {
  const actions = [];
  if (["queued", "running"].includes(job.status)) {
    actions.push(["pause", "Pause"], ["stop", "Stop"]);
  } else if (job.status === "paused") {
    actions.push(["resume", "Resume"], ["stop", "Stop"]);
  } else if (job.status === "failed") {
    actions.push(["retry-failed", "Retry Failed"], ["stop", "Stop"]);
  }
  return actions.map(([action, label]) => `<button data-job-action="${action}" data-job="${job.id}">${label}</button>`).join("") || `<span class="muted">No actions</span>`;
}

function jobNovelTitle(job) {
  const novel = state.novels.find((item) => item.id === job.novel_id);
  return novel?.title || job.novel_title || job.novel_id || `Job ${String(job.id || "").slice(0, 8)}`;
}

function truncateMiddle(value, max = 24) {
  const text = String(value || "");
  if (text.length <= max) return text;
  const edge = Math.max(4, Math.floor((max - 3) / 2));
  return `${text.slice(0, edge)}...${text.slice(-edge)}`;
}

function bindJobButtons() {
  document.querySelectorAll("[data-job-action]").forEach((button) => button.addEventListener("click", async () => {
    await api(`/api/translation/jobs/${button.dataset.job}/${button.dataset.jobAction}`, {method: "POST"});
    invalidateCache("/api/translation/jobs");
    route();
  }));
}

async function openJobCenter(focusedJobId = "") {
  if (!canTranslate()) return openSettings("account");
  setLoading("Loading jobs...");
  try {
    const [jobs, imports] = await Promise.all([
      api(`/api/translation/jobs?novel_id=${encodeURIComponent(state.currentNovelId)}`),
      state.admin ? api(`/api/import-jobs?novel_id=${encodeURIComponent(state.currentNovelId)}`) : Promise.resolve({jobs: []}),
    ]);
    const focused = focusedJobId ? await api(`/api/translation/jobs/${focusedJobId}`).catch(() => null) : null;
    const active = (jobs.jobs || []).filter((job) => ["queued", "running", "paused"].includes(job.status)).length;
    app.innerHTML = `${pageHeader("Job Center", "Translation and import operations at a glance.", [["Active", active], ["Translation Jobs", (jobs.jobs || []).length], ["Imports", (imports.jobs || []).length]])}
      <section class="toolbar"><button id="refreshJobs" type="button">Refresh</button><span class="muted">Updated ${timeAgo(new Date().toISOString())}</span></section>
      ${focused?.job ? renderJobDetail(focused.job) : ""}
      <section class="table-card"><h2>Translation Jobs</h2>${renderJobsTable(jobs.jobs || [], focusedJobId)}</section>
      ${state.admin ? `<section class="table-card"><h2>Import Jobs</h2><table><tbody>${(imports.jobs || []).map((job) => `<tr><td>${job.id.slice(0, 8)}</td><td>${escapeHtml(job.target_mode)}</td><td>${escapeHtml(job.status)}</td><td>${escapeHtml(job.updated_at)}</td></tr>`).join("") || `<tr><td>No import jobs.</td></tr>`}</tbody></table></section>` : ""}`;
    bindJobButtons();
    bindCopyLinks(app);
    document.querySelector("#refreshJobs")?.addEventListener("click", () => openJobCenter(focusedJobId));
    restoreScrollPosition();
  } catch (error) {
    setError(error.message);
  }
}

async function openActivityCenter(focusedJobId = "") {
  setLoading("Loading activity...");
  try {
    if (!canTranslate()) {
      const personal = await loadPersonalHome(true);
      app.innerHTML = `${pageHeader("Activity", "Your reading activity.", [["Recent", personal?.history?.length || state.recent.chapters.length || 0]])}
        <section class="dashboard-grid">${renderRecentlyRead((personal?.history?.length ? personal.history : state.recent.chapters || []).slice(0, 8))}<section class="panel"><h2>Needs Attention</h2><p class="empty-state">No account-visible operational items need attention.</p></section><section class="panel"><h2>Recently Completed</h2><p class="empty-state">Completed operational activity is only shown to authorized roles.</p></section></section>`;
      return;
    }
    const [jobs, imports] = await Promise.all([
      api("/api/translation/jobs"),
      state.admin ? api("/api/import-jobs") : Promise.resolve({jobs: []}),
    ]);
    const list = jobs.jobs || [];
    const active = list.filter((job) => ["queued", "running", "paused"].includes(job.status));
    const attention = list.filter((job) => job.status === "failed" || job.error || Number(job.failed_items || 0) > 0);
    const completed = list.filter((job) => ["completed", "cancelled"].includes(job.status)).slice(0, 10);
    app.innerHTML = `${pageHeader("Activity Center", "Operational activity across translation and import work.", [["Active", active.length], ["Needs Attention", attention.length], ["Completed", completed.length]])}
      ${focusedJobId ? "" : ""}
      <section class="table-card"><h2>Active</h2>${renderJobsTable(active, focusedJobId)}</section>
      <section class="table-card"><h2>Needs Attention</h2>${renderJobsTable(attention, focusedJobId)}</section>
      <section class="table-card"><h2>Recently Completed</h2>${renderJobsTable(completed, focusedJobId)}</section>
      ${state.admin ? `<section class="table-card"><h2>Import Activity</h2><table><tbody>${(imports.jobs || []).map((job) => `<tr><td>${job.id.slice(0, 8)}</td><td>${escapeHtml(job.target_mode)}</td><td>${escapeHtml(job.status)}</td><td>${timeAgo(job.updated_at)}</td></tr>`).join("") || `<tr><td>No import activity.</td></tr>`}</tbody></table></section>` : ""}`;
    bindJobButtons();
    bindCopyLinks(app);
  } catch (error) {
    setError(error.message);
  }
}

function openNotifications() {
  updateNav("notifications");
  const items = state.notifications;
  const unread = items.filter((item) => !item.read).length;
  app.innerHTML = `${pageHeader("Notifications", "Reading alerts and saved local updates for this browser.", unread ? [["Unread", unread]] : [])}
    <section class="notification-toolbar">
      <p>${items.length ? `${items.length} saved update${items.length === 1 ? "" : "s"}.` : "No alerts are waiting."}</p>
      <div class="actions"><button id="clearNotifications" type="button" ${items.length ? "" : "disabled"}>Clear</button><a class="button" href="#/settings/notifications">Notification Settings</a></div>
    </section>
    <section class="notification-list"><h2>Recent</h2>${items.length ? items.map(renderNotificationRow).join("") : `<div class="empty-state notification-empty"><h3>All clear</h3><p>Reading and account updates will appear here when the app has something useful to tell you.</p><a class="button" href="#/home">Back Home</a></div>`}</section>`;
  document.querySelector("#clearNotifications")?.addEventListener("click", clearNotifications);
  requestAnimationFrame(markNotificationsRead);
  restoreScrollPosition();
}

function renderNotificationRow(item) {
  const tone = item.type === "backup" || item.type === "recovery" ? "alert" : "info";
  return `<a class="notification-row ${item.read ? "" : "unread"} ${tone}" href="${escapeAttr(item.href || "#/notifications")}"><span class="badge">${escapeHtml(titleCase(item.type || "info"))}</span><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.message || "")}</span><small>${timeAgo(item.created_at)}</small></a>`;
}

async function openCompare(novelId, chapterNumber) {
  if (!canTranslate()) return openSettings("account");
  setLoading("Loading comparison...");
  try {
    const payload = await api(`/api/novels/${encodeURIComponent(novelId)}/compare/${chapterNumber}`);
    app.innerHTML = `${pageHeader("Compare", "Inspect Original, Reference, and English text side by side.", [["Chapter", chapterNumber]])}
      <section class="compare-grid">
        ${renderComparePanel("Original", payload.original)}
        ${renderComparePanel("Reference", payload.reference)}
        ${renderComparePanel("English", payload.english || payload.ai)}
      </section>
      <div class="actions"><a class="button" href="#/reader/${novelId}/${chapterNumber}/english">Open Reader</a><a class="button" href="#/chapters/${novelId}">Back to Chapters</a></div>`;
  } catch (error) {
    setError(error.message);
  }
}

function renderComparePanel(label, payload) {
  return `<article class="panel compare-panel"><h2>${escapeHtml(label)}</h2>${payload?.ok ? paragraphs(payload.text).map((line) => `<p>${escapeHtml(line)}</p>`).join("") : `<p class="empty-state">${escapeHtml(label)} not available.</p>`}</article>`;
}

async function openRecovery(novelId) {
  setLoading("Loading recovery...");
  try {
    await refreshSession();
    if (!state.admin) return renderAdminGate("Recovery");
    const diagnostic = await api(`/api/novels/${encodeURIComponent(novelId)}/recovery/reference`);
    app.innerHTML = `
      ${pageHeader("Recovery", "Preview and import missing Reference chapters without overwriting existing text.", [["Reference", diagnostic.reference_rows_in_range], ["Missing", diagnostic.missing_count], ["Range", `${diagnostic.range.start}-${diagnostic.range.end}`]])}
      <section class="panel"><h2>Missing Reference</h2><p class="chapter-pills">${(diagnostic.missing_reference_chapters || []).map((n) => `<span>${n}</span>`).join("") || "None"}</p><a class="button" href="/api/novels/${novelId}/recovery/request">Download Recovery Request</a></section>
      ${state.admin ? `<form class="panel" id="recoveryForm"><h2>Upload Reader Pack or TXT/ZIP</h2><input id="recoveryFiles" type="file" multiple accept=".zip,.txt"><button class="primary">Preview Upload</button></form>` : adminNotice()}
      <section id="recoveryPreview"></section>`;
    document.querySelector("#recoveryForm")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = new FormData();
      Array.from(document.querySelector("#recoveryFiles").files).forEach((file) => form.append("files", file));
      const preview = await api(`/api/novels/${novelId}/recovery/preview`, {method: "POST", body: form, headers: {}});
      document.querySelector("#recoveryPreview").innerHTML = renderRecoveryPreview(preview, novelId);
      document.querySelector("#applyImport")?.addEventListener("click", async () => {
        const result = await api(`/api/novels/${novelId}/recovery/import/${preview.job_id}`, {method: "POST"});
        toast(`Imported ${result.imported_count} Reference chapters.`);
        pushNotification("recovery", "Recovery import completed", `${result.imported_count || 0} Reference chapters imported.`, "#/admin/recovery");
        openRecovery(novelId);
      });
    });
  } catch (error) {
    setError(error.message);
  }
}

function renderRecoveryPreview(preview, novelId) {
  const canImport = preview.would_import_count > 0;
  return `<section class="panel"><h2>Import Preview</h2><div class="metric-grid">${metric("Files", preview.files_found)}${metric("Recognized", preview.recognized_count)}${metric("Would import", preview.would_import_count)}${metric("Already present", preview.already_present_count)}${metric("Still missing", preview.still_missing_count)}</div>${recoveryList("Would import", preview.chapters_that_would_be_imported)}${recoveryList("Still missing", preview.still_missing_after_import)}${objectDetails("Invalid files", preview.invalid_files)}${objectDetails("Ambiguous", preview.ambiguous_filenames)}${objectDetails("Duplicates", preview.duplicate_chapter_numbers)}<button id="applyImport" class="primary" ${canImport ? "" : "disabled"}>Import Missing References</button></section>`;
}

async function openAdmin(tab = "overview") {
  setLoading(tab === "backups" ? "Loading backup manifest..." : "Loading admin...");
  await refreshSession();
  if (!state.admin) return renderAdminGate("Admin");
  try {
    await loadNovels(true);
    rememberRecent("admin", {label: titleCase(tab), href: `#/admin/${tab}`, at: new Date().toISOString()});
    localStorage.setItem("gt-last-admin-tab", tab);
    const adminData = await loadAdminTabData(tab);
    const {overview, dbHealth, missing, imports, jobs, backupManifest, backupJobs, users, performance, audit} = adminData;
    const tabs = [["overview", "Overview"], ["content", "Content"], ["imports", "Imports"], ["editions", "Editions"], ["novels", "Novels"], ["translation", "Translation"], ["performance", "Performance"], ["jobs", "Jobs"], ["backups", "Backups"], ["recovery", "Recovery"], ["database", "Database"], ["users", "Users"], ["roles", "Roles"], ["diagnostics", "Diagnostics"], ["audit", "Audit Log"], ["system", "System Health"]];
    app.innerHTML = `
      ${pageHeader("Admin", "Operational workspace for content, translation, backups, recovery, users, and diagnostics.", [["Version", APP_VERSION], ["Schema", overview.overview.schema], ["Chapters", overview.overview.chapters], ["Missing English", overview.overview.needs_translation]])}
      <section class="admin-workspace">
        <nav class="admin-tabs">${tabs.map(([key, label]) => `<a class="${tab === key ? "active" : ""}" href="#/admin/${key}">${label}</a>`).join("")}</nav>
        <div class="admin-content">${renderAdminTab(tab, overview, dbHealth, missing, imports, jobs, backupManifest, backupJobs, users, performance, audit)}</div>
      </section>
      <div class="actions"><button id="logoutBtn">Exit Admin Mode</button></div>`;
    bindJobButtons();
    bindCopyLinks(app);
    bindAdminWorkspace();
    document.querySelector("#logoutBtn").addEventListener("click", exitAdminMode);
    restoreScrollPosition();
  } catch (error) {
    setError(error.message);
  }
}

async function loadAdminTabData(tab) {
  const data = {
    overview: await api("/api/admin/overview"),
    dbHealth: {health: {}},
    missing: {missing: {}},
    imports: {jobs: []},
    jobs: {jobs: []},
    backupManifest: {manifest: null, error: null},
    backupJobs: {jobs: []},
    users: {users: []},
    performance: null,
    audit: {events: []},
  };
  if (tab === "database" || tab === "diagnostics" || tab === "system") {
    data.dbHealth = await api("/api/admin/db-health");
  }
  if (tab === "recovery") {
    data.missing = await api(`/api/admin/missing/${state.currentNovelId}`);
  }
  if (tab === "jobs") {
    const [jobs, imports] = await Promise.all([
      api(`/api/translation/jobs?novel_id=${state.currentNovelId}`),
      api(`/api/import-jobs?novel_id=${state.currentNovelId}`),
    ]);
    data.jobs = jobs;
    data.imports = imports;
  }
  if (tab === "translation") {
    data.jobs = await api(`/api/translation/jobs?novel_id=${state.currentNovelId}`);
  }
  if (tab === "performance") {
    data.performance = await api(`/api/admin/translation/performance?novel_id=${encodeURIComponent(state.currentNovelId)}`);
  }
  if (tab === "backups" || tab === "system") {
    const [manifest, jobs] = await Promise.all([
      api("/api/admin/backups/manifest").catch((error) => backupManifestError(error)),
      api("/api/admin/backups/jobs").catch(() => ({jobs: []})),
    ]);
    data.backupManifest = manifest;
    data.backupJobs = jobs;
  }
  if (tab === "users" || tab === "roles") {
    data.users = await api("/api/admin/users");
  }
  if (tab === "audit") {
    data.audit = await api("/api/admin/audit-events").catch(() => ({events: []}));
  }
  return data;
}

function renderAdminTab(tab, overview, dbHealth, missing, imports, jobs, backupManifest, backupJobs, users, performance, audit) {
  const data = overview.overview || {};
  if (tab === "content") return renderContentAdmin(data);
  if (tab === "imports") return renderContentImportCenter();
  if (tab === "editions") return renderEditionManager();
  if (tab === "novels") return renderNovelManagement(state.novels, "");
  if (tab === "translation") return `<section class="dashboard-grid"><div class="panel"><h2>Translation Workspace</h2><p class="muted">Configure jobs in the dedicated workspace while Admin keeps operational context here.</p><div class="actions"><a class="button primary" href="#/translate/${state.currentNovelId}">Open Translate</a><a class="button" href="#/admin/jobs">Open Jobs</a></div></div><div class="panel">${metric("Missing English", data.needs_translation)}${metric("English Editions", data.english ?? data.ai)}${metric("Active Jobs", (jobs.jobs || []).filter((job) => ["queued", "running", "paused"].includes(job.status)).length)}</div></section>`;
  if (tab === "performance") return renderTranslationPerformance(performance);
  if (tab === "database") {
    return `<section class="dashboard-grid"><div class="panel">${metric("Database", dbHealth.health?.reachable ? "Healthy" : "Needs Attention")}${metric("Schema", data.schema)}${metric("Expected Tables", dbHealth.health?.v10_chapters_table_exists ? "Healthy" : "Needs Attention")}${metric("Chapters", data.chapters)}</div><div class="panel"><h2>Technical Details</h2><details><summary>Show details</summary><pre>${escapeHtml(JSON.stringify(dbHealth.health, null, 2))}</pre></details></div></section>`;
  }
  if (tab === "jobs") return `<section class="table-card"><h2>Job Center</h2>${renderJobsTable(jobs.jobs || [])}</section><section class="table-card"><h2>Import Jobs</h2><table><thead><tr><th>Job</th><th>Mode</th><th>Status</th><th>Updated</th></tr></thead><tbody>${(imports.jobs || []).map((job) => `<tr><td>${job.id.slice(0, 8)}</td><td>${escapeHtml(job.target_mode)}</td><td>${escapeHtml(job.status)}</td><td>${escapeHtml(job.updated_at)}</td></tr>`).join("") || `<tr><td colspan="4">No import jobs.</td></tr>`}</tbody></table></section>`;
  if (tab === "backups") return renderBackupsRecovery(backupManifest?.manifest, backupManifest?.error, backupJobs?.jobs || []);
  if (tab === "recovery") return renderNovelRecoveryAdmin(missing.missing);
  if (tab === "users") return renderUsersTable(users.users || []);
  if (tab === "roles") return renderRolesOverview(users.users || []);
  if (tab === "diagnostics") return `<section class="dashboard-grid"><div class="panel">${metric("Version", APP_VERSION)}${metric("DB", dbHealth.health?.ok === false ? "Unhealthy" : "Healthy")}${metric("Schema", data.schema)}${metric("Auth", state.authConfig?.configured ? "Configured" : "Missing")}${metric("OpenAI", "Configured/Missing hidden")}</div><div class="panel"><h2>Details</h2><details><summary>Show sanitized JSON</summary><pre>${escapeHtml(JSON.stringify({overview: data, db: dbHealth.health}, null, 2))}</pre></details></div></section>`;
  if (tab === "audit") return renderAuditLog(audit?.events || []);
  if (tab === "system") return renderSystemHealth(data, dbHealth, backupManifest?.manifest, backupJobs?.jobs || []);
  return renderAdminOverview(data, dbHealth, jobs, imports, backupManifest?.manifest, backupManifest?.error);
}

function backupManifestError(error) {
  return {
    ok: false,
    manifest: null,
    error: {
      status: error.status || 0,
      stage: error.stage || "",
      code: error.code || "",
      message: error.message || "Backup manifest could not be loaded.",
      non_json: Boolean(error.nonJson),
    },
  };
}

function renderUsersTable(users) {
  return `<section class="table-card"><h2>Users</h2><table class="responsive-table"><thead><tr><th>User</th><th>Role</th><th>Updated</th></tr></thead><tbody>${users.map((user) => `<tr><td data-label="User"><strong>${escapeHtml(user.display_name || user.email || user.user_id)}</strong><br><span>${escapeHtml(user.email || user.user_id)}</span></td><td data-label="Role">${escapeHtml(user.role || "user")}</td><td data-label="Updated">${timeAgo(user.updated_at)}</td></tr>`).join("") || `<tr><td colspan="3">No application profiles yet.</td></tr>`}</tbody></table></section>`;
}

function renderRolesOverview(users) {
  const counts = users.reduce((acc, user) => {
    const role = user.role || "user";
    acc[role] = (acc[role] || 0) + 1;
    return acc;
  }, {});
  return `<section class="dashboard-grid">
    <div class="panel"><h2>Roles</h2><p class="muted">Role changes must remain explicit and audit logged. This view summarizes current profiles without exposing credentials.</p><div class="metric-grid">${metric("Admins", counts.admin || 0)}${metric("Translators", counts.translator || 0)}${metric("Users", counts.user || 0)}</div></div>
    <div class="panel"><h2>Policy</h2><p class="muted">Admin, translator, and user permissions are enforced server-side. Role-change APIs should record audit event type role_change before they are expanded.</p></div>
  </section>${renderUsersTable(users)}`;
}

function renderAuditLog(events) {
  return `<section class="table-card"><h2>Audit Log</h2><p class="muted">Audit events store action summaries and sanitized metadata only. Secrets, prompts, headers, provider bodies, cookies, tokens, and chapter text are redacted.</p><table class="responsive-table"><thead><tr><th>Time</th><th>Event</th><th>Target</th><th>Summary</th></tr></thead><tbody>${events.map((event) => `<tr><td data-label="Time">${timeAgo(event.created_at)}</td><td data-label="Event">${escapeHtml(event.event_type)}</td><td data-label="Target">${escapeHtml([event.target_type, event.target_id].filter(Boolean).join(": "))}</td><td data-label="Summary">${escapeHtml(event.summary || "")}</td></tr>`).join("") || `<tr><td colspan="4">No audit events yet.</td></tr>`}</tbody></table></section>`;
}

function renderSystemHealth(data, dbHealth, manifest, backupJobs) {
  const runningBackups = backupJobs.filter((job) => ["queued", "running"].includes(job.status)).length;
  return `<section class="dashboard-grid">
    <div class="panel"><h2>System Health</h2><div class="metric-grid">${metric("Database", dbHealth.health?.reachable ? "Healthy" : "Needs Attention")}${metric("Schema", data.schema)}${metric("Backup safe mode", manifest?.kind === "lightweight_manifest" ? "Enabled" : "Needs Check")}${metric("Running backups", runningBackups)}${metric("Manifest response", manifest?.kind || "Unavailable")}${metric("OpenAI", "Configured/Missing hidden")}</div></div>
    <div class="panel"><h2>Operational Guardrails</h2><p class="muted">Admin page load reads aggregate manifests and job metadata only. Full backups, restores, imports, and translations require explicit actions.</p>${objectDetails("Table Counts", manifest?.table_counts || {})}</div>
  </section>`;
}

function renderContentAdmin(data) {
  return `<section class="dashboard-grid">
    <div class="panel"><h2>Content</h2><p class="muted">Official onboarding starts with Content Import Center: create or select a novel, import content, validate, preview, execute, then read or translate only if needed.</p><div class="actions"><a class="button primary" href="#/admin/imports">Open Import Center</a><a class="button" href="#/admin/editions">Edition Manager</a><a class="button" href="#/admin/recovery">Recovery</a></div></div>
    <div class="panel">${metric("Original", data.original)}${metric("English", data.english ?? data.ai)}${metric("Reference", data.reference)}${metric("Missing English", data.needs_translation)}</div>
    <div class="panel"><h2>Sections</h2><div class="stack-list"><a class="list-row" href="#/admin/imports"><strong>Imports</strong><span>Original, English, Reference, metadata, cover, glossary</span></a><a class="list-row" href="#/admin/editions"><strong>Edition Manager</strong><span>Default English editions</span></a><a class="list-row" href="#/admin/recovery"><strong>Recovery</strong><span>Fill missing data only</span></a></div></div>
  </section>`;
}

function renderContentImportCenter() {
  const selectedNovel = state.novels.find((novel) => novel.id === state.currentNovelId);
  return `<section class="studio-panel content-import-center">
    <div class="studio-heading"><h2>Content Import Center</h2><span>Create Novel -> Import Content -> Validate -> Preview -> Import -> Read -> Translate Optional</span></div>
    <div id="importNovelState">${renderImportNovelState(selectedNovel)}</div>
    <div class="form-grid">
      <label>1. Select Novel<select id="importNovel"><option value="">Create New Novel</option>${state.novels.map((novel) => `<option value="${escapeAttr(novel.id)}" ${novel.id === state.currentNovelId ? "selected" : ""}>${escapeHtml(novel.title || novel.id)}</option>`).join("")}</select></label>
      <label>New Novel Title<input id="importNovelTitle" placeholder="Required when creating a new novel"></label>
      <label>Author<input id="importAuthor" placeholder="Optional"></label>
      <label>Source URL<input id="importSourceUrl" placeholder="Optional"></label>
      <label class="wide">Summary<textarea id="importSummary" rows="2" placeholder="Optional public summary"></textarea></label>
      <label>Cover URL<input id="importCoverUrl" placeholder="Optional cover image URL"></label>
      <label class="wide">2. Choose Import Type<div class="choice-grid">${["original", "english", "ai", "reference", "metadata", "cover", "glossary"].map((type) => `<label class="choice-card"><input type="checkbox" name="importType" value="${type}" ${["original", "english"].includes(type) ? "checked" : ""}><strong>${type === "ai" ? "AI" : titleCase(type)}</strong><span>${type === "english" ? "Readable edition" : type === "ai" ? "AI English edition metadata" : "Import content"}</span></label>`).join("")}</div></label>
      <label>3. Choose Source<select id="importSourceType"><option value="simple">Simple Import (.txt / ZIP)</option><option value="godtranslator-pack">Advanced / Pack Import</option><option value="downloader-pack">Downloader Pack</option><option value="desktop-pack">Desktop Companion Pack</option><option value="mixed-pack">Mixed / Multi-edition Pack</option><option value="zip">ZIP / Downloader Pack Preview</option><option value="folder">Folder manifest JSON</option><option value="reference-pack">Reference Pack</option></select></label>
      <label>Simple Import Content<select id="simpleImportContentType"><option value="original">Original</option><option value="english">English</option><option value="ai">AI</option><option value="reference">Reference</option></select></label>
      <label>English Edition Type<select id="importEditionType"><option value="Imported">Imported</option><option value="Official">Official</option><option value="Edited">Edited</option><option value="Human">Human</option><option value="AI">AI</option><option value="Machine">Machine</option><option value="Community">Community</option></select></label>
      <label>Text files, ZIP, or JSON<input id="importPackFile" type="file" accept=".txt,.zip,.json,text/plain,application/json" multiple></label>
      <label class="wide">Content Items JSON<textarea id="importItemsJson" rows="8" placeholder='[{"chapter_number":1,"content_type":"original","title":"Chapter 1","text":"..."},{"chapter_number":1,"content_type":"english","edition_type":"Official","text":"..."}]'></textarea></label>
      <label class="wide">Metadata JSON<textarea id="importMetadataJson" rows="3" placeholder='{"tags":["xianxia"],"genre":"Fantasy"}'></textarea></label>
      <label class="wide">Glossary<textarea id="importGlossary" rows="3" placeholder="Optional glossary terms for this novel"></textarea></label>
      <label class="inline-check"><input id="importSkipExisting" type="checkbox" checked> Skip existing text</label>
      <label class="inline-check"><input id="importOverwrite" type="checkbox"> Overwrite existing text</label>
      <label class="inline-check"><input id="importAddMissing" type="checkbox" checked> Add only missing</label>
      <label class="inline-check"><input id="importMergeMetadata" type="checkbox" checked> Merge metadata</label>
      <label class="inline-check"><input id="importTitles" type="checkbox" checked> Import titles</label>
      <label class="inline-check"><input id="importDryRun" type="checkbox"> Dry run</label>
    </div>
    <div class="actions"><button id="previewContentImport" class="primary" type="button">Preview</button><button id="executeContentImport" type="button" disabled>Execute Import</button><a class="button" href="#/admin/editions">Edition Manager</a></div>
    <section id="contentImportPreview"></section>
  </section>`;
}

function renderNovelInventoryNotice(novel) {
  if (Number(novel?.chapter_count || 0) !== 0) return "";
  const expected = novel.expected_range_configured ? `Expected range ${escapeHtml(novel.expected_range_label || "")}` : "No expected range configured";
  return `<section class="state-card">
    <h2>No chapters imported yet</h2>
    <p class="muted">Import chapter files or a reader pack to create the first chapter rows.</p>
    <div class="metric-grid">${metric("Chapter Inventory", "Empty")}${metric("Expected Range", expected)}${metric("Missing Counts", novel.missing_counts_known === false ? "Unknown" : "Calculated")}</div>
    ${novel.missing_counts_known === false ? `<p class="muted">Unknown until chapters are imported or a range is configured.</p>` : ""}
    ${state.admin ? `<div class="actions"><a class="button primary" href="#/admin/imports">Import First Chapters</a></div>` : ""}
  </section>`;
}

function renderImportNovelState(novel) {
  if (!novel) {
    return `<section class="state-card"><h2>Create a new novel</h2><p class="muted">Preview will show new chapters detected and rows to create before import executes.</p></section>`;
  }
  if (Number(novel.chapter_count || 0) === 0) {
    return `<section class="state-card">
      <h2>No chapters imported yet</h2>
      <p class="muted">Import chapter files or a reader pack to create the first chapter rows.</p>
      <div class="metric-grid">${metric("Existing Chapters", 0)}${metric("Expected Range", novel.expected_range_configured ? novel.expected_range_label : "Expected range not set")}${metric("Missing Counts", novel.missing_counts_known === false ? "Unknown" : "Calculated")}</div>
      <p class="muted">${novel.expected_range_configured ? "Expected range is set; missing counts are based on that range." : "No expected range configured. Unknown until chapters are imported or a range is configured."}</p>
      <div class="actions"><button id="importFirstChaptersBtn" class="primary" type="button">Import First Chapters</button></div>
    </section>`;
  }
  return `<section class="panel"><h2>Selected Novel Inventory</h2><div class="metric-grid">${metric("Chapters", novel.chapter_count)}${metric("Original", novel.original_count)}${metric("English", novel.english_count ?? novel.ai_count)}${state.admin ? metric("Reference", novel.reference_count) : ""}${metric("Expected Range", novel.expected_range_configured ? novel.expected_range_label : "Expected range not set")}</div></section>`;
}

function updateImportNovelState() {
  const target = document.querySelector("#importNovelState");
  if (!target) return;
  const selectedId = document.querySelector("#importNovel")?.value || "";
  const novel = state.novels.find((item) => item.id === selectedId);
  target.innerHTML = renderImportNovelState(novel);
  document.querySelector("#importFirstChaptersBtn")?.addEventListener("click", () => document.querySelector("#importPackFile")?.click());
}

function renderEditionManager() {
  const novel = state.novels.find((item) => item.id === state.currentNovelId) || state.novels[0] || {};
  return `<section class="studio-panel"><div class="studio-heading"><h2>Edition Manager</h2><span>Choose default English editions without exposing implementation details to readers.</span></div>
    <label>Novel<select id="editionNovel">${state.novels.map((item) => `<option value="${escapeAttr(item.id)}" ${item.id === (novel.id || state.currentNovelId) ? "selected" : ""}>${escapeHtml(item.title || item.id)}</option>`).join("")}</select></label>
    <div class="actions"><button id="loadEditions" class="primary" type="button">Load Editions</button><a class="button" href="#/admin/imports">Import Content</a></div>
    <section id="editionManagerResult"><p class="muted">Load editions to review default English choices.</p></section>
  </section>`;
}

function contentImportPayloadFromForm() {
  let items = [];
  const rawItems = document.querySelector("#importItemsJson")?.value.trim();
  if (rawItems) {
    const parsed = JSON.parse(rawItems);
    items = Array.isArray(parsed) ? parsed : parsed.items || [];
  }
  const metadataRaw = document.querySelector("#importMetadataJson")?.value.trim();
  const metadata = metadataRaw ? JSON.parse(metadataRaw) : null;
  const glossary = document.querySelector("#importGlossary")?.value.trim();
  const simpleContentType = document.querySelector("#simpleImportContentType")?.value || "english";
  const editionType = simpleContentType === "ai" ? "AI" : (document.querySelector("#importEditionType")?.value || "Imported");
  const selectedNovel = document.querySelector("#importNovel")?.value || "";
  const title = document.querySelector("#importNovelTitle")?.value.trim();
  const importTypes = [...document.querySelectorAll("input[name='importType']:checked")].map((item) => item.value);
  return {
    novel_id: selectedNovel,
    novel: {
      id: selectedNovel || title,
      title: title || state.novels.find((novel) => novel.id === selectedNovel)?.title || selectedNovel,
      summary: document.querySelector("#importSummary")?.value.trim(),
      author: document.querySelector("#importAuthor")?.value.trim(),
      cover_url: document.querySelector("#importCoverUrl")?.value.trim(),
      source_url: document.querySelector("#importSourceUrl")?.value.trim(),
      metadata: metadata || undefined,
    },
    metadata: metadata || undefined,
    glossary: glossary || undefined,
    content_type: simpleContentType,
    edition_type: editionType,
    import_types: importTypes,
    source_type: document.querySelector("#importSourceType")?.value,
    items,
    options: {
      skip_existing: document.querySelector("#importSkipExisting")?.checked,
      overwrite_existing: document.querySelector("#importOverwrite")?.checked,
      add_missing: document.querySelector("#importAddMissing")?.checked,
      merge_metadata: document.querySelector("#importMergeMetadata")?.checked,
      import_titles: document.querySelector("#importTitles")?.checked,
      dry_run: document.querySelector("#importDryRun")?.checked,
    },
  };
}

async function previewContentImport() {
  const target = document.querySelector("#contentImportPreview");
  try {
    const files = [...(document.querySelector("#importPackFile")?.files || [])];
    let preview;
    if (files.length) {
      const form = new FormData();
      files.forEach((file) => form.append("files", file));
      preview = await api(`/api/admin/content/import/preview-pack?${contentImportUploadParams().toString()}`, {method: "POST", body: form, headers: {}});
    } else {
      preview = await api("/api/admin/content/import/preview", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(contentImportPayloadFromForm())});
    }
    target.innerHTML = renderContentImportPreview(preview);
    document.querySelector("#executeContentImport").disabled = !preview.can_execute;
  } catch (error) {
    target.innerHTML = `<section class="state-card error"><p>${escapeHtml(error.message)}</p></section>`;
  }
}

async function executeContentImport() {
  const target = document.querySelector("#contentImportPreview");
  try {
    const files = [...(document.querySelector("#importPackFile")?.files || [])];
    let result;
    if (files.length) {
      const form = new FormData();
      files.forEach((file) => form.append("files", file));
      const params = contentImportUploadParams();
      params.set("overwrite_existing", document.querySelector("#importOverwrite")?.checked ? "true" : "false");
      params.set("dry_run", document.querySelector("#importDryRun")?.checked ? "true" : "false");
      result = await api(`/api/admin/content/import/execute-pack?${params.toString()}`, {method: "POST", body: form, headers: {}});
    } else {
      result = await api("/api/admin/content/import/execute", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(contentImportPayloadFromForm())});
    }
    invalidateCache("/api/novels");
    await loadNovels(true);
    target.innerHTML = `<section class="panel"><h2>Import Summary</h2><div class="metric-grid">${metric("Imported", result.summary?.imported || 0)}${metric("Updated", result.summary?.updated || 0)}${metric("Overwritten", result.summary?.overwritten || 0)}${metric("Skipped", result.summary?.skipped || 0)}${metric("Warnings", result.summary?.warnings || 0)}${metric("Errors", result.summary?.errors || 0)}</div><div class="actions"><a class="button primary" href="#/novel/${encodeURIComponent(result.novel_id)}">Open Novel</a><a class="button" href="#/reader/${encodeURIComponent(result.novel_id)}/1/english">Open Reader</a><a class="button" href="#/translate/${encodeURIComponent(result.novel_id)}">Open Translate</a></div>${objectDetails("Warnings", result.pack_warnings || [])}${objectDetails("Errors", result.errors || [])}</section>`;
    pushNotification("import", "Import completed", `${result.summary?.imported || 0} imported, ${result.summary?.updated || 0} updated.`, `#/novel/${encodeURIComponent(result.novel_id)}`);
  } catch (error) {
    target.innerHTML = `<section class="state-card error"><p>${escapeHtml(error.message)}</p></section>`;
  }
}

function renderContentImportPreview(preview) {
  const contentToAdd = preview.content_to_add || {};
  const expectedRange = preview.expected_range_configured ? `${preview.expected_chapter_range?.start}-${preview.expected_chapter_range?.end}` : "Expected range not set";
  return `<section class="panel"><h2>Import Preview</h2>
    ${preview.new_chapters_detected ? `<p class="muted">New chapters detected. Content Import will create chapter rows before adding content.</p>` : ""}
    <div class="metric-grid">
      ${metric("Novel", preview.novel_title || (preview.create_new_novel ? "Create New" : "Existing"))}
      ${metric("Existing Chapters", preview.existing_chapter_count || 0)}
      ${metric("New Chapters", preview.new_chapter_count || 0)}
      ${metric("Chapter Rows to Create", preview.rows_to_create_count || 0)}
      ${metric("Original Content to Add", contentToAdd.original || 0)}
      ${metric("English Content to Add", contentToAdd.english || 0)}
      ${metric("Reference Content to Add", contentToAdd.reference || 0)}
      ${metric("AI Edition Imports", preview.edition_type_counts?.AI || 0)}
      ${metric("Expected Range", expectedRange)}
      ${metric("Would Update", preview.estimated_import?.would_update || 0)}
      ${metric("Would Skip", preview.estimated_import?.would_skip || 0)}
      ${metric("Duplicates", preview.duplicate_count || 0)}
      ${metric("Invalid Files", preview.invalid_files?.length || 0)}
    </div>
    ${objectDetails("Rows to Create", preview.rows_to_create || [])}
    ${objectDetails("Content Types", preview.content_type_counts || {})}
    ${objectDetails("Edition Types", preview.edition_type_counts || {})}
    ${objectDetails("Missing", preview.missing_chapters || {})}
    ${objectDetails("Duplicates", preview.duplicates || [])}
    ${objectDetails("Invalid Files", preview.invalid_files || [])}
    ${objectDetails("Warnings", [...(preview.warnings || []), ...(preview.pack_warnings || [])])}
    ${objectDetails("Preview Items", preview.items || [])}
    <details><summary>Rollback Planning</summary><p class="muted">Import history records preview and item actions. Automatic rollback is intentionally deferred until it can be executed transactionally; use Backups & Recovery restore preview before destructive correction.</p></details>
  </section>`;
}

function contentImportUploadParams() {
  const selectedNovel = document.querySelector("#importNovel")?.value || "";
  const title = document.querySelector("#importNovelTitle")?.value.trim() || "";
  const params = new URLSearchParams({
    novel_id: selectedNovel,
    content_type: document.querySelector("#simpleImportContentType")?.value || "english",
    edition_type: document.querySelector("#simpleImportContentType")?.value === "ai" ? "AI" : (document.querySelector("#importEditionType")?.value || "Imported"),
    novel_title: title,
    author: document.querySelector("#importAuthor")?.value.trim() || "",
    source_url: document.querySelector("#importSourceUrl")?.value.trim() || "",
  });
  return params;
}

async function loadEditionManager() {
  const novelId = document.querySelector("#editionNovel")?.value || state.currentNovelId;
  const target = document.querySelector("#editionManagerResult");
  if (!novelId || !target) return;
  try {
    const payload = await api(`/api/admin/content/editions/${encodeURIComponent(novelId)}`);
    const rows = payload.editions || [];
    target.innerHTML = `<section class="table-card"><h2>English Editions</h2><table class="responsive-table"><thead><tr><th>Chapter</th><th>Edition</th><th>Default</th><th>Characters</th><th></th></tr></thead><tbody>${rows.map((edition) => `<tr><td data-label="Chapter">${edition.chapter_number}</td><td data-label="Edition"><strong>${escapeHtml(edition.edition_type)}</strong><br><span>${escapeHtml(edition.source_label || edition.edition_key)}</span></td><td data-label="Default">${edition.is_default ? "Yes" : "No"}</td><td data-label="Characters">${edition.character_count || 0}</td><td data-label="Actions" class="row-actions">${edition.is_default ? `<span class="badge ok">Default</span>` : `<button type="button" data-default-edition="${escapeAttr(edition.edition_key)}" data-chapter="${edition.chapter_number}">Make Default</button>`}</td></tr>`).join("") || `<tr><td colspan="5">No English editions found.</td></tr>`}</tbody></table></section>`;
    target.querySelectorAll("[data-default-edition]").forEach((button) => button.addEventListener("click", setDefaultEnglishEdition));
  } catch (error) {
    target.innerHTML = `<section class="state-card error"><p>${escapeHtml(error.message)}</p></section>`;
  }
}

async function setDefaultEnglishEdition(event) {
  const button = event.currentTarget;
  const novelId = document.querySelector("#editionNovel")?.value || state.currentNovelId;
  const chapterNumber = button.dataset.chapter;
  const editionKey = button.dataset.defaultEdition;
  await api(`/api/admin/content/editions/${encodeURIComponent(novelId)}/${chapterNumber}/default`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({edition_key: editionKey}),
  });
  invalidateCache("/api/novels");
  toast("Default English edition updated.");
  loadEditionManager();
}

function renderTranslationPerformance(performance) {
  const simple = performance?.simple || {};
  const advanced = performance?.advanced || {};
  const runtime = performance?.runtime || {};
  const settings = advanced.effective_settings || {};
  return `<section class="dashboard-grid">
    <div class="panel">
      <h2>Translation Performance</h2>
      <div class="metric-grid">${metric("Current speed", simple.current_speed ? `${simple.current_speed}/min` : "Measuring")}${metric("Active workers", simple.active_workers ?? 0)}${metric("Peak workers", simple.peak_active_workers ?? 0)}${metric("Avg chapter", simple.average_chapter_time_seconds ? formatDuration(simple.average_chapter_time_seconds) : "Measuring")}${metric("ETA", simple.estimated_remaining_seconds ? formatDuration(simple.estimated_remaining_seconds) : "Unknown")}${metric("Recent failures", simple.recent_failures ?? 0)}</div>
    </div>
    <div class="panel">
      <h2>Advanced Diagnostics</h2>
      <div class="metric-grid">${metric("Queue wait", secondsMetric(advanced.average_queue_wait_seconds))}${metric("Claim", secondsMetric(advanced.average_claim_seconds))}${metric("Chapter load", secondsMetric(advanced.average_chapter_load_seconds))}${metric("Prompt build", secondsMetric(advanced.average_prompt_build_seconds))}${metric("Provider", secondsMetric(advanced.average_provider_wait_seconds))}${metric("Save", secondsMetric(advanced.average_save_seconds))}${metric("Retries", advanced.retry_count ?? 0)}${metric("429", advanced.rate_limited_count ?? 0)}${metric("Timeouts", advanced.timeout_count ?? 0)}${metric("Input tokens", numberMetric(advanced.average_input_tokens))}${metric("Output tokens", numberMetric(advanced.average_output_tokens))}${metric("Reference use", advanced.reference_usage_percent == null ? "Measuring" : `${advanced.reference_usage_percent}%`)}</div>
    </div>
    <div class="panel">
      <h2>Effective Settings</h2>
      <div class="metric-grid">${metric("Preset", titleCase(settings.speed_preset || "unknown"))}${metric("Starting workers", settings.starting_worker_count ?? "Auto")}${metric("Max workers", settings.maximum_worker_count ?? "Auto")}${metric("Global cap", runtime.global_worker_cap ?? settings.global_worker_cap ?? "Unknown")}${metric("Retry limit", settings.retry_limit ?? "Unknown")}${metric("Timeout", secondsMetric(settings.provider_timeout_seconds))}${metric("Benchmark", runtime.benchmark_enabled ? "Enabled" : "Disabled")}</div>
    </div>
  </section>`;
}

function renderAdminOverview(data, dbHealth, jobs, imports, manifest, manifestError = null) {
  return `<section class="overview-panel admin-overview">
    <div class="overview-copy">
      <p class="eyebrow">Admin Overview</p>
      <h2>Production workspace status</h2>
      <p class="muted">Application ${APP_VERSION} is using schema ${escapeHtml(data.schema || "unknown")}. Detailed diagnostics, jobs, recovery, and backup metadata load only when their sections are opened.</p>
      <div class="status-list">
        <span>${statusBadge("healthy")} Application healthy</span>
        <span>${statusBadge("healthy")} Database summary loaded</span>
        <span>${statusBadge("queued")} Backups load on demand</span>
      </div>
    </div>
    <div class="overview-metrics">
      ${metric("Novels", data.novels)}
      ${metric("Chapters", data.chapters)}
      ${metric("English", data.english ?? data.ai)}
      ${metric("Needs Translation", data.needs_translation)}
      ${metric("Original", data.original)}
      ${metric("Reference", data.reference)}
      ${metric("Version", APP_VERSION)}
    </div>
  </section>
  <section class="quick-actions-panel">
    <div><h2>Quick Actions</h2><p class="muted">Common admin paths without crowding the overview.</p></div>
    <div class="actions"><a class="button primary" href="#/admin/backups">Backups & Recovery</a><a class="button" href="#/translate/${state.currentNovelId}">Translate</a><a class="button" href="#/admin/novels">Add Novel</a><a class="button" href="#/admin/recovery">Missing Data</a><a class="button" href="#/admin/jobs">Job Center</a><a class="button" href="#/admin/database">Database</a></div>
  </section>`;
}

function renderBackupsRecovery(manifest, manifestError = null, backupJobs = []) {
  const protectedState = manifestError ? "Needs Attention" : (manifest?.checksum_available ? "Protected" : "Manifest Ready");
  const created = manifest?.created_at ? timeAgo(manifest.created_at) : "No manifest loaded";
  const latest = manifest?.latest_full_backup || {};
  const activeJob = backupJobs.find((job) => ["queued", "running"].includes(job.status)) || manifest?.active_backup_job || null;
  const historyCreated = latest.available ? latest.completed_at || latest.created_at : "No completed full backup recorded.";
  const downloadControl = latest.available && latest.download_url ? `<a class="button" href="${escapeAttr(latest.download_url)}">Download Latest Backup</a>` : `<button type="button" disabled>Download available after backup completes</button>`;
  const activeJobPanel = activeJob ? `<article class="backup-section"><h2>Active Backup Job</h2><div class="metric-grid">${metric("Status", activeJob.status)}${metric("Progress", `${activeJob.progress_percent ?? 0}%`)}${metric("Tables", `${activeJob.completed_tables || 0}/${activeJob.total_tables || 0}`)}${metric("Current Table", activeJob.current_table || "Starting")}${metric("Rows Written", `${activeJob.processed_rows || 0}/${activeJob.total_rows || 0}`)}</div><p class="muted">Full backup generation runs in the background with bounded table batches.</p></article>` : "";
  const manifestErrorPanel = manifestError ? `<section class="state-card error"><h2>Backup manifest could not be loaded.</h2><p>${escapeHtml(manifestError.message || "Manifest request failed.")}</p>${manifestError.status ? `<p class="muted">HTTP ${escapeHtml(manifestError.status)}</p>` : ""}${manifestError.stage ? `<p class="muted">Stage: ${escapeHtml(manifestError.stage)}</p>` : ""}</section>` : "";
  const storage = manifest?.backup_storage || {};
  return `<section class="backup-workspace">
    ${manifestErrorPanel}
    <section class="overview-panel">
      <div class="overview-copy"><p class="eyebrow">Backups & Recovery</p><h2>Protected recovery workflow</h2><p class="muted">Backups include v10 application tables and exclude secrets, API keys, tokens, cookies, and auth password material.</p></div>
      <div class="overview-metrics">${metric("Last Backup", created)}${metric("Protected State", protectedState)}${metric("Version", manifest?.app_version || APP_VERSION)}${metric("Schema", manifest?.schema || "")}</div>
    </section>
    <section class="backup-grid">
      <article class="backup-section"><h2>Manifest</h2><p class="muted">Format ${escapeHtml(manifest?.format_version || "unknown")} · ${manifest?.table_counts?.novels ?? 0} novels · ${manifest?.chapter_source_counts?.chapters ?? 0} chapters.</p><p class="muted">This view uses aggregate SQL only and never creates a full backup on page load.</p>${objectDetails("Unavailable Tables", manifest?.table_errors || {})}</article>
      <article class="backup-section"><h2>Create Backup</h2><p class="muted">Queue a background full backup. The worker streams bounded row batches, tracks checksum after creation, and navigation will not cancel the job.</p><div class="metric-grid">${metric("Storage", storage.configured ? "Configured" : "Not configured")}${metric("Bucket", storage.bucket || "godtranslator-backups")}${metric("Job Count", manifest?.backup_job_count || backupJobs.length)}</div><div class="actions"><button id="createBackupBtn" class="primary" type="button" ${activeJob ? "disabled" : ""}>${activeJob ? "Backup Running" : "Queue Backup Job"}</button>${downloadControl}</div></article>
      ${activeJobPanel}
      <article class="backup-section"><h2>Backup Jobs</h2>${renderBackupJobs(backupJobs)}</article>
      <article class="backup-section"><h2>Backup History</h2><table class="responsive-table"><tbody><tr><td data-label="Created">${escapeHtml(historyCreated)}</td><td data-label="Format">${escapeHtml(manifest?.format_version || "")}</td><td data-label="Contents">${manifest?.table_counts?.novels ?? 0} novels / ${manifest?.chapter_source_counts?.chapters ?? 0} chapters</td><td data-label="Size">${latest.size_bytes ? formatBytes(latest.size_bytes) : "Known after full backup"}</td><td data-label="Storage">${escapeHtml(latest.storage?.status || (storage.configured ? "Configured" : "Manifest only"))}</td></tr></tbody></table></article>
      <article class="backup-section"><h2>Restore</h2><p class="muted">Default restore mode adds missing data only. Restore preview reports add, skip, overwrite, and invalid counts before any apply step.</p><label>Safe restore mode<select id="restoreMode"><option value="add-missing">Add missing data only</option><option value="skip-existing">Skip existing data</option><option value="overwrite">Overwrite existing data</option></select></label><label>Backup JSON<input id="restoreFile" type="file" accept=".json,application/json"></label><div class="actions"><button id="restorePreviewBtn" type="button" disabled>Restore Preview</button></div></article>
      <article class="backup-section"><h2>Novel Recovery</h2><p class="muted">Recover missing Reference chapters for a selected novel without overwriting readable chapter text.</p><div class="actions"><a class="button" href="#/admin/recovery">Open Novel Recovery</a><a class="button" href="/api/novels/${state.currentNovelId}/recovery/request">Download Recovery Request</a></div></article>
    </section>
  </section><section id="backupActionResult"></section><section id="restorePreviewResult"></section>`;
}

function renderBackupJobs(jobs) {
  if (!jobs.length) return `<p class="muted">No backup jobs yet.</p>`;
  return `<table class="responsive-table"><thead><tr><th>Status</th><th>Progress</th><th>Table</th><th>Checksum</th><th></th></tr></thead><tbody>${jobs.map((job) => `<tr><td data-label="Status">${escapeHtml(job.status)}</td><td data-label="Progress">${job.progress_percent ?? 0}% · ${job.processed_rows || 0}/${job.total_rows || 0} rows</td><td data-label="Table">${escapeHtml(job.current_table || "-")}</td><td data-label="Checksum">${escapeHtml(String(job.sha256 || "").slice(0, 12) || "after completion")}</td><td data-label="Action">${["queued", "running"].includes(job.status) ? `<button type="button" data-cancel-backup="${escapeAttr(job.id)}">Cancel</button>` : `<span class="muted">${escapeHtml(job.storage?.status || "")}</span>`}</td></tr>`).join("")}</tbody></table>`;
}

function renderNovelRecoveryAdmin(missing) {
  return `<section class="dashboard-grid">
    <div class="panel"><h2>Novel Recovery</h2><label>Novel<select id="adminRecoveryNovel">${state.novels.map((novel) => `<option value="${novel.id}" ${novel.id === state.currentNovelId ? "selected" : ""}>${escapeHtml(novel.title || novel.id)}</option>`).join("")}</select></label><div class="metric-grid">${metric("Original Missing", missing.missing_original?.length || 0)}${metric("Reference Missing", missing.missing_reference?.length || 0)}${metric("Reference Range", `${missing.reference_target_range?.start ?? "all"}-${missing.reference_target_range?.end ?? "all"}`)}</div></div>
    <div class="panel"><h2>Exact Missing Chapters</h2>${recoveryList("Missing Original", missing.missing_original)}${recoveryList("Missing Reference", missing.missing_reference)}<div class="actions"><a class="button" href="/api/novels/${state.currentNovelId}/recovery/request">Download Recovery Request</a><a class="button" href="#/recovery/${state.currentNovelId}">Upload Recovery Pack</a></div></div>
  </section>`;
}

function bindAdminWorkspace() {
  document.querySelector("#adminRecoveryNovel")?.addEventListener("change", (event) => {
    state.currentNovelId = event.target.value;
    localStorage.setItem("gt-current-novel", state.currentNovelId);
    openAdmin("recovery");
  });
  document.querySelectorAll("#createBackupBtn").forEach((button) => button.addEventListener("click", createBackupFromAdmin));
  document.querySelectorAll("[data-cancel-backup]").forEach((button) => button.addEventListener("click", cancelBackupJob));
  document.querySelector("#restorePreviewBtn")?.addEventListener("click", restorePreviewFromFile);
  document.querySelector("#restoreFile")?.addEventListener("change", (event) => {
    const button = document.querySelector("#restorePreviewBtn");
    if (button) button.disabled = !event.target.files?.[0];
  });
  document.querySelector("#previewContentImport")?.addEventListener("click", previewContentImport);
  document.querySelector("#executeContentImport")?.addEventListener("click", executeContentImport);
  document.querySelector("#importNovel")?.addEventListener("change", (event) => {
    state.currentNovelId = event.target.value || state.currentNovelId;
    if (event.target.value) localStorage.setItem("gt-current-novel", event.target.value);
    updateImportNovelState();
  });
  document.querySelector("#importFirstChaptersBtn")?.addEventListener("click", () => document.querySelector("#importPackFile")?.click());
  document.querySelector("#loadEditions")?.addEventListener("click", loadEditionManager);
  document.querySelector("#editionNovel")?.addEventListener("change", (event) => {
    state.currentNovelId = event.target.value;
    localStorage.setItem("gt-current-novel", state.currentNovelId);
    loadEditionManager();
  });
}

async function createBackupFromAdmin() {
  const target = document.querySelector("#backupActionResult");
  document.querySelectorAll("#createBackupBtn").forEach((button) => {
    button.disabled = true;
    button.textContent = "Queueing Backup...";
  });
  if (target) target.innerHTML = `<section class="state-card"><div class="spinner"></div><p>Queueing background backup job...</p></section>`;
  try {
    const payload = await api("/api/admin/backups/jobs", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({store: true, safe_mode: true})});
    if (target) target.innerHTML = renderBackupJobStatus(payload.job, "Backup Job Queued");
    if (payload.job?.id) pollBackupJob(payload.job.id);
  } catch (error) {
    if (target) target.innerHTML = `<section class="state-card error"><p>${escapeHtml(error.message)}</p></section>`;
    document.querySelectorAll("#createBackupBtn").forEach((button) => {
      button.disabled = false;
      button.textContent = "Queue Backup Job";
    });
  }
}

function renderBackupJobStatus(job, title = "Backup Job") {
  const complete = job?.status === "completed";
  const failed = job?.status === "failed";
  const errorMessage = typeof job?.error === "string" ? job.error : job?.error?.message;
  const download = complete && job?.id ? `<a class="button primary" href="/api/admin/backups/download?job_id=${encodeURIComponent(job.id)}">Download Backup</a>` : "";
  return `<section class="${failed ? "state-card error" : "panel"}"><h2>${escapeHtml(title)}</h2><div class="metric-grid">${metric("Status", job?.status || "unknown")}${metric("Progress", `${job?.progress_percent ?? 0}%`)}${metric("Current Table", job?.current_table || (complete ? "Complete" : "Queued"))}${metric("Tables", `${job?.completed_tables || 0}/${job?.total_tables || 0}`)}${metric("Rows", `${job?.processed_rows || 0}/${job?.total_rows || 0}`)}${metric("Size", job?.size_bytes ? formatBytes(job.size_bytes) : "Pending")}${metric("Checksum", job?.sha256 ? String(job.sha256).slice(0, 12) : "Pending")}${metric("Destination", job?.destination || "local")}</div>${errorMessage ? `<p class="muted">${escapeHtml(errorMessage)}</p>` : ""}${download}</section>`;
}

async function pollBackupJob(jobId) {
  const target = document.querySelector("#backupActionResult");
  if (!jobId || !target) return;
  for (let attempt = 0; attempt < 120; attempt += 1) {
    await delay(1500);
    if (!document.querySelector("#backupActionResult")) return;
    try {
      const payload = await api(`/api/admin/backups/jobs/${encodeURIComponent(jobId)}`);
      const job = payload.job || {};
      target.innerHTML = renderBackupJobStatus(job, job.status === "completed" ? "Backup Completed" : "Backup Job Running");
      if (["completed", "failed", "cancelled"].includes(job.status)) {
        document.querySelectorAll("#createBackupBtn").forEach((button) => {
          button.disabled = false;
          button.textContent = "Queue Backup Job";
        });
        if (job.status === "completed" && !sessionStorage.getItem(`gt-backup-notified:${jobId}`)) {
          sessionStorage.setItem(`gt-backup-notified:${jobId}`, "1");
          pushNotification("backup", "Backup completed", `${formatBytes(job.size_bytes || 0)} written with checksum ${String(job.sha256 || "").slice(0, 12)}.`, "#/admin/backups");
        }
        if (job.status === "failed" && !sessionStorage.getItem(`gt-backup-notified:${jobId}`)) {
          sessionStorage.setItem(`gt-backup-notified:${jobId}`, "1");
          pushNotification("backup", "Backup failed", typeof job.error === "string" ? job.error : "Open Backups for details.", "#/admin/backups");
        }
        return;
      }
    } catch (error) {
      target.innerHTML = `<section class="state-card error"><p>${escapeHtml(error.message)}</p></section>`;
      return;
    }
  }
}

async function cancelBackupJob(event) {
  const jobId = event.currentTarget.dataset.cancelBackup;
  if (!jobId) return;
  await api(`/api/admin/backups/jobs/${encodeURIComponent(jobId)}/cancel`, {method: "POST"});
  toast("Backup cancellation requested.");
  openAdmin("backups");
}

async function restorePreviewFromFile() {
  const file = document.querySelector("#restoreFile")?.files?.[0];
  const target = document.querySelector("#restorePreviewResult");
  if (!file || !target) return toast("Choose a backup JSON file first.");
  try {
    const backup = JSON.parse(await file.text());
    const mode = document.querySelector("#restoreMode")?.value || "add-missing";
    const preview = await api("/api/admin/backups/restore-preview", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({backup, mode})});
    target.innerHTML = `<section class="panel"><h2>Restore Preview</h2><div class="metric-grid">${metric("Compatible", preview.compatible ? "Healthy" : "Needs Attention")}${metric("Mode", preview.mode)}${metric("Will overwrite chapter text", preview.will_overwrite_chapter_text ? "Yes" : "No")}</div>${Object.entries(preview.changes || {}).map(([table, change]) => `<details><summary>${escapeHtml(table)}: add ${change.add}, skip ${change.skip_existing}, overwrite ${change.overwrite}, invalid ${change.invalid}</summary><pre>${escapeHtml(JSON.stringify(change.examples || [], null, 2))}</pre></details>`).join("")}</section>`;
  } catch (error) {
    target.innerHTML = `<section class="state-card error"><p>${escapeHtml(error.message)}</p></section>`;
  }
}

function formatBytes(bytes) {
  const value = Number(bytes || 0);
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function openSettings(section = "", intent = "") {
  clearToasts();
  const pref = state.preferences;
  const sections = [
    ["appearance", "Appearance"],
    ["reader", "Reading"],
    ["accessibility", "Accessibility"],
    ["notifications", "Notifications"],
    ["account", "Account"],
    ["privacy", "Privacy"],
    ...(state.admin || canTranslate() ? [["advanced", "Advanced"]] : []),
  ];
  const activeSection = sections.some(([key]) => key === section) ? section : "";
  if (!activeSection) {
    updateNav("settings");
    app.innerHTML = `
      <section class="settings-root">
        <div><p class="eyebrow">Settings</p><h1>Reading preferences</h1><p class="muted">Adjust the interface without leaving reader-first defaults behind.</p></div>
        <nav class="settings-root-list" aria-label="Settings categories">
          ${sections.map(([key, label]) => `<a href="#/settings/${key}"><strong>${escapeHtml(label)}</strong><span>${settingsSummary(key, pref)}</span></a>`).join("")}
        </nav>
      </section>`;
    restoreScrollPosition();
    return;
  }
  app.innerHTML = `
    <section class="settings-subpage">
      <a class="settings-back" href="#/settings">Back to Settings</a>
      <div class="settings-subpage-heading"><p class="eyebrow">Settings</p><h1>${escapeHtml(sections.find(([key]) => key === activeSection)?.[1] || "Settings")}</h1></div>
      <nav class="settings-nav">
        ${sections.map(([key, label]) => `<a class="${activeSection === key ? "active" : ""}" href="#/settings/${key}">${label}</a>`).join("")}
      </nav>
      ${renderSettingsSection(activeSection, pref, intent)}
    </section>`;
  document.querySelectorAll("[data-pref]").forEach((field) => field.addEventListener("input", savePreferenceFromField));
  document.querySelectorAll(".pref-switch").forEach((field) => field.addEventListener("keydown", handleSwitchKeydown));
  if (activeSection === "account") bindAccountControls();
  if (activeSection === "account" && !state.account) requestAnimationFrame(() => document.querySelector("#authEmail")?.focus());
  document.querySelector("#resetPrefs")?.addEventListener("click", () => {
    state.preferences = defaultPreferences();
    localStorage.setItem("gt-preferences", JSON.stringify(state.preferences));
    applyPreferences();
    openSettings(activeSection);
    toast("Preferences reset.");
  });
}

function renderSettingsSection(section, pref, intent = "") {
  if (section === "reader") return renderReaderSettings(pref);
  if (section === "library") return renderLibrarySettings(pref);
  if (section === "notifications") return renderNotificationSettings(pref);
  if (section === "keyboard") return renderKeyboardSettings(pref);
  if (section === "account") return renderAccountSettings(intent);
  if (section === "accessibility") return renderAccessibilitySettings(pref);
  if (section === "privacy") return renderPrivacySettings(pref);
  if (section === "desktop") return renderDesktopSettings(pref);
  if (section === "advanced") return renderAdvancedSettings(pref);
  return renderAppearanceSettings(pref);
}

function renderAppearanceSettings(pref) {
  return `<section class="studio-panel">
    <div class="studio-heading"><h2>Appearance</h2><span>${state.account ? "Saved to account when possible" : "Saved locally"}</span></div>
    <h3>Basic</h3>
    <div class="choice-grid">${["obsidian", "forest", "midnight", "warm-dark", "light"].map((item) => radioCard("theme", item, pref.theme, titleCase(item), "visual theme")).join("")}</div>
    <h3>Accent</h3>
    <div class="swatch-row">${["green", "teal", "blue", "purple", "amber"].map((item) => `<label class="swatch ${pref.accent === item ? "active" : ""}" data-accent-swatch="${item}"><input data-pref="accent" type="radio" name="accent" value="${item}" ${pref.accent === item ? "checked" : ""}><span></span>${titleCase(item)}</label>`).join("")}</div>
    <details open><summary>Advanced</summary><div class="preview-grid">${["compact", "comfortable", "spacious"].map((item) => radioCard("density", item, pref.density, `${titleCase(item)} density`, "spacing preview")).join("")}${radioToggle("interfaceBlur", pref.interfaceBlur, "Interface blur", "Soft translucent surfaces")}${radioToggle("reduceMotion", pref.reduceMotion, "Reduce motion", "Disable interface animation")}${radioToggle("contrastFocus", pref.contrastFocus, "High contrast focus", "Stronger keyboard focus")}</div></details>
    <div class="actions"><button id="resetPrefs" type="button">Reset to defaults</button></div>
  </section>`;
}

function renderNotificationSettings(pref) {
  const readerOptions = [
    radioToggle("notifyReading", pref.notifyReading, "Reading reminders", "Show helpful resume prompts"),
    radioToggle("notifyNewChapters", pref.notifyNewChapters, "New chapter alerts", "Show alerts only when a real detector reports updates"),
    ...(canTranslate() ? [radioToggle("notifyTranslation", pref.notifyTranslation, "Translation completed", "Show completed translation jobs and jobs needing attention")] : []),
  ];
  const adminOptions = state.admin ? [
    radioToggle("notifyRecovery", pref.notifyRecovery, "Recovery updates", "Show recovery import and request status"),
    radioToggle("notifyBackups", pref.notifyBackups, "Backup updates", "Show backup completion or failure messages"),
    radioToggle("notifyDesktop", pref.notifyDesktop, "Desktop sync", "Show Desktop Companion sync results"),
    radioToggle("notifyImports", pref.notifyImports, "Import updates", "Show content import summaries"),
  ] : [];
  return `<section class="studio-panel">
    <div class="studio-heading"><h2>Notifications</h2><span>Saved ${state.account ? "to your account" : "locally"} when possible</span></div>
    <p class="muted">Only real reading or workflow updates appear. Technical logs and diagnostics stay out of the normal notification list.</p>
    <div class="preview-grid">${readerOptions.join("")}</div>
    ${adminOptions.length ? `<details><summary>Operational updates</summary><div class="preview-grid">${adminOptions.join("")}</div></details>` : ""}
    <div class="preview-grid">${radioToggle("quietNotifications", pref.quietNotifications, "Quiet mode", "Reduce non-critical notification noise")}</div>
    <div class="actions"><a class="button" href="#/notifications">Open Notifications</a></div>
  </section>`;
}

function settingsSummary(key, pref) {
  if (key === "appearance") return `${titleCase(pref.theme)} theme`;
  if (key === "reader") return `${pref.readerFontSize}px text`;
  if (key === "accessibility") return pref.reduceMotion ? "Reduced motion on" : "Motion and focus";
  if (key === "notifications") return pref.quietNotifications ? "Quiet mode" : "Reading alerts";
  if (key === "account") return state.account ? "Signed in" : "Guest reading";
  if (key === "privacy") return pref.saveLocalHistory ? "Local history on" : "Local history off";
  return "Advanced controls";
}

function renderKeyboardSettings(pref) {
  return `<section class="studio-panel">
    <div class="studio-heading"><h2>Keyboard</h2><span>Shortcut behavior</span></div>
    <h3>Basic</h3>
    <div class="preview-grid">${radioToggle("keyboardShortcuts", pref.keyboardShortcuts, "Keyboard shortcuts", "Enable Ctrl/Cmd+K, reader navigation, and help")}${radioToggle("readerArrowKeys", pref.readerArrowKeys, "Reader arrow keys", "Use Left and Right for chapters")}</div>
    <details open><summary>Advanced</summary><div class="shortcut-grid"><span>Ctrl/Cmd + K</span><strong>Global search and commands</strong><span>?</span><strong>Shortcut help</strong><span>Left / Right</span><strong>Previous / next chapter</strong><span>B</span><strong>Bookmark chapter</strong><span>F</span><strong>Focus mode</strong></div></details>
  </section>`;
}

function renderPrivacySettings(pref) {
  return `<section class="studio-panel">
    <div class="studio-heading"><h2>Privacy</h2><span>Reading data and local state</span></div>
    <h3>Basic</h3>
    <div class="preview-grid">${radioToggle("saveLocalHistory", pref.saveLocalHistory, "Local recent history", "Remember recent novels and chapters on this device")}${radioToggle("syncAccountProgress", pref.syncAccountProgress, "Sync account progress", "Save reading position when signed in")}</div>
    <details><summary>Advanced</summary><p class="muted">Reference text remains protected by role server-side. Secrets, tokens, provider bodies, and chapter text are not stored in settings preferences.</p></details>
  </section>`;
}

function renderDesktopSettings(pref) {
  return `<section class="studio-panel">
    <div class="studio-heading"><h2>Desktop</h2><span>Companion sync preferences</span></div>
    <h3>Basic</h3>
    <div class="preview-grid">${radioToggle("desktopSyncPrompts", pref.desktopSyncPrompts, "Desktop sync prompts", "Show Desktop Companion next actions")}${radioToggle("desktopImportSummary", pref.desktopImportSummary, "Import summaries", "Show pack upload and import summaries")}</div>
    <details open><summary>Advanced</summary><p class="muted">Secure desktop device authorization is planned for a later v11 phase. This page does not store passwords or raw tokens.</p><div class="actions"><a class="button" href="#/admin/imports">Open Import Center</a>${state.admin ? `<a class="button" href="#/admin/diagnostics">Diagnostics</a>` : ""}</div></details>
  </section>`;
}

function renderAdvancedSettings(pref) {
  return `<section class="studio-panel">
    <div class="studio-heading"><h2>Advanced</h2><span>Progressive disclosure</span></div>
    <h3>Basic</h3>
    <div class="choice-grid">${["basic", "advanced", "expert"].map((item) => radioCard("settingsDepth", item, pref.settingsDepth || "basic", titleCase(item), item === "expert" ? "Show low-level operational controls when available" : `${titleCase(item)} controls`)).join("")}</div>
    <details open><summary>Advanced</summary><div class="preview-grid">${radioToggle("showTechnicalIds", pref.showTechnicalIds, "Technical IDs", "Show compact IDs in operational pages")}${radioToggle("developerHints", pref.developerHints, "Developer hints", "Show additional diagnostic copy where safe")}</div></details>
    <details><summary>Expert</summary><p class="muted">Expert controls never bypass permissions, budget limits, backup safety, or production data protections.</p></details>
    <div class="actions"><button id="resetPrefs" type="button">Reset to defaults</button></div>
  </section>`;
}

function renderLibrarySettings(pref) {
  return `<section class="studio-panel">
    <div class="studio-heading"><h2>Library</h2><span>Catalog density and metadata</span></div>
    <h3>Basic</h3>
    <div class="choice-grid">${["compact", "standard", "large"].map((item) => radioCard("cardSize", item, pref.cardSize, `${titleCase(item)} cards`, "card size")).join("")}</div>
    <details open><summary>Advanced</summary><div class="preview-grid">
      ${["small", "medium", "large"].map((item) => radioCard("coverSize", item, pref.coverSize, `${titleCase(item)} covers`, "cover treatment")).join("")}
      ${["dense", "balanced", "airy"].map((item) => radioCard("gridDensity", item, pref.gridDensity, `${titleCase(item)} grid`, "grid density")).join("")}
      ${["minimal", "balanced", "full"].map((item) => radioCard("metadataAmount", item, pref.metadataAmount, `${titleCase(item)} metadata`, "metadata amount")).join("")}
    </div></details>
  </section>`;
}

function renderReaderSettings(pref) {
  return `<section class="studio-panel">
    <div class="studio-heading"><h2>Reader</h2><span>Live reading preview</span></div>
    <article class="reader-preview"><p>Chapter text appears here with your current font, spacing, width, and theme.</p><p>Use the controls below to shape long reading sessions without crowding the Reader itself.</p></article>
    <h3>Basic</h3>
    <div class="choice-grid">${["paper", "sepia", "dark", "oled", "green-night", "midnight"].map((item) => radioCard("readerTone", item, pref.readerTone, titleCase(item), "reader theme")).join("")}</div>
    <div class="form-grid">${rangeControl("readerFontSize", "Font size", pref.readerFontSize, 16, 25, 1, "px")}${rangeControl("readingWidth", "Reading width", pref.readingWidth, 620, 940, 20, "px")}</div>
    <details open><summary>Advanced</summary><div class="form-grid">
      <label>Font family<select data-pref="readerFont">${["serif", "sans", "system"].map((item) => `<option value="${item}" ${pref.readerFont === item ? "selected" : ""}>${titleCase(item)}</option>`).join("")}</select></label>
      ${rangeControl("readerLineHeight", "Line height", pref.readerLineHeight, 1.55, 2.1, 0.05, "")}
      ${rangeControl("paragraphSpacing", "Paragraph spacing", pref.paragraphSpacing, 0.85, 1.6, 0.05, "em")}
      <label>Alignment<select data-pref="textAlign">${["left", "justify"].map((item) => `<option value="${item}" ${pref.textAlign === item ? "selected" : ""}>${titleCase(item)}</option>`).join("")}</select></label>
      ${radioToggle("reduceMotion", pref.reduceMotion, "Reduce motion", "Calmer reader transitions")}
      ${radioToggle("contrastFocus", pref.contrastFocus, "High contrast focus", "Stronger keyboard focus in Reader")}
      ${radioToggle("accessibilityComfort", pref.accessibilityComfort, "Comfort reading", "Favor stable spacing and calmer reader chrome")}
    </div></details>
    <div class="actions"><button id="resetPrefs" type="button">Reset to defaults</button></div>
  </section>`;
}

function renderAccessibilitySettings(pref) {
  return `<section class="studio-panel">
    <div class="studio-heading"><h2>Accessibility</h2><span>Motion, focus, and contrast</span></div>
    <p class="muted">These controls affect the visible interface immediately and are saved with the existing preferences system.</p>
    <h3>Reading comfort</h3>
    <div class="form-grid">${rangeControl("readerFontSize", "Reader font size", pref.readerFontSize, 16, 25, 1, "px")}${rangeControl("readerLineHeight", "Line height", pref.readerLineHeight, 1.55, 2.1, 0.05, "")}</div>
    <h3>Interface comfort</h3>
    <div class="preview-grid">${radioToggle("reduceMotion", pref.reduceMotion, "Reduce motion", "Disable interface animation")}${radioToggle("contrastFocus", pref.contrastFocus, "High contrast focus", "Stronger keyboard focus")}${radioToggle("accessibilityComfort", pref.accessibilityComfort, "Comfort reading", "Favor stable spacing and calmer transitions")}</div>
    <div class="actions"><button id="resetPrefs" type="button">Reset to defaults</button></div>
  </section>`;
}

function rangeControl(name, label, value, min, max, step, unit) {
  const display = `${escapeHtml(value)}${unit}`;
  return `<label class="range-field"><span>${escapeHtml(label)}<strong data-range-value="${escapeAttr(name)}">${display}</strong></span><input data-pref="${escapeAttr(name)}" type="range" min="${min}" max="${max}" step="${step}" value="${escapeAttr(value)}"></label>`;
}

function radioCard(name, value, current, title, subtitle) {
  return `<label class="choice-card ${current === value ? "active" : ""}"><input data-pref="${name}" type="radio" name="${name}" value="${value}" ${current === value ? "checked" : ""}><strong>${escapeHtml(title)}</strong><span>${escapeHtml(subtitle)}</span></label>`;
}

function radioToggle(name, checked, title, subtitle) {
  const on = Boolean(checked);
  return `<label class="choice-card toggle-card ${on ? "active" : ""}" data-toggle-card="${escapeAttr(name)}"><span class="toggle-copy"><strong>${escapeHtml(title)}</strong><span>${escapeHtml(subtitle)}</span></span><input class="pref-switch" data-pref="${escapeAttr(name)}" type="checkbox" role="switch" aria-label="${escapeAttr(title)}" aria-checked="${on ? "true" : "false"}" ${on ? "checked" : ""}><span class="switch-state" aria-hidden="true">${on ? "On" : "Off"}</span></label>`;
}

function renderAccountSettings(intent = "") {
  if (state.account) {
    return `<section class="panel account-panel">
      <h2>Account</h2>
      <div class="account-card">
        <div class="avatar">${escapeHtml(initials(state.account.display_name || state.account.email || "U"))}</div>
        <div><strong>${escapeHtml(state.account.display_name || state.account.email || "Signed in")}</strong><p class="muted">${escapeHtml(state.account.email || "")}</p><span class="badge ok">${escapeHtml(state.account.role || "user")}</span></div>
      </div>
      <div class="account-links">
        <a class="button" href="#/continue">Continue Reading</a>
        <a class="button" href="#/bookmarks">Bookmarks</a>
        <a class="button" href="#/history">History</a>
        <a class="button" href="#/settings/appearance">Personalization</a>
      </div>
      ${renderRecentAccountLinks()}
      <div class="actions"><button id="signOutBtn" type="button">Sign Out</button>${state.admin ? `<button id="exitAdminBtn" type="button">Exit Admin Mode</button>` : `<a class="button" href="#/admin">Admin Login</a>`}</div>
    </section>`;
  }
  const configured = Boolean(state.authConfig?.configured && state.supabaseClient);
  const title = intent === "signup" ? "Create Account" : intent === "forgot-password" || intent === "reset-password" ? "Reset Password" : "Sign In";
  if (!configured) {
    return `<section class="account-landing auth-unavailable">
      <div class="account-copy">
        <p class="eyebrow">${escapeHtml(APP_BRAND.shortName)} Account</p>
        <h2>Guest reading is available</h2>
        <p>Account sign-in is not configured on this deployment. You can still read locally as a guest; saved local history, bookmarks, and preferences stay on this device.</p>
      </div>
      <div class="auth-card auth-unavailable-card">
        <h2>Account sign-in unavailable</h2>
        <p class="muted">Unavailable account actions are hidden because they cannot work here.</p>
        <div class="actions account-footer"><a class="button primary" href="#/continue">Continue as Guest</a><a class="button" href="#/home">Back</a></div>
      </div>
    </section>`;
  }
  return `<section class="account-landing">
    <div class="account-copy">
      <p class="eyebrow">${escapeHtml(APP_BRAND.shortName)} Account</p>
      <h2>${title}</h2>
      <p>Keep your reading place, bookmarks, and preferences with you. Guest reading still works on this device.</p>
    </div>
    <div class="auth-card">
      <form id="authForm" class="auth-form">
        <label>Email<input id="authEmail" type="email" autocomplete="email" placeholder="reader@example.com"></label>
        <label>Password<span class="password-field"><input id="authPassword" type="password" autocomplete="current-password" placeholder="Password"><button id="toggleAuthPassword" type="button" aria-label="Show password">Show</button></span></label>
        <p id="authStatus" class="field-error" role="status" aria-live="polite"></p>
        <div class="auth-actions">
          <button class="primary" id="signInBtn" type="submit">Sign In</button>
          <button id="googleBtn" type="button">Continue with Google</button>
        </div>
        <div class="auth-secondary">
          <button id="signUpBtn" type="button">Create Account</button>
          <button id="forgotBtn" type="button">Forgot Password</button>
        </div>
      </form>
      <div class="actions account-footer"><a class="button" href="#/home">Back</a></div>
    </div>
  </section>`;
}

function renderRecentAccountLinks() {
  const items = [
    ...(state.recent.novels || []).slice(0, 2),
    ...(state.recent.chapters || []).slice(0, 2),
    ...(canTranslate() ? (state.recent.jobs || []).slice(0, 2) : []),
  ].filter(Boolean);
  if (!items.length) return "";
  return `<section class="recent-strip">${items.map((item) => `<a href="${escapeAttr(item.href)}">${escapeHtml(item.label)}</a>`).join("")}</section>`;
}

function renderAdminGate(title) {
  app.innerHTML = `<section class="login-panel"><h1>${escapeHtml(title)} Login</h1><p class="muted">Admin actions require a secure server-side session.</p><form id="loginForm"><label>Password<input id="adminPassword" type="password" autocomplete="current-password"></label><button class="primary">Login</button></form></section>`;
  document.querySelector("#loginForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await api("/api/admin/login", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({password: document.querySelector("#adminPassword").value})});
      state.admin = true;
      route();
    } catch (error) {
      toast(error.message || "Admin login failed.");
    }
  });
}

function adminNotice() {
  return `<section class="panel"><h2>Admin required</h2><p class="muted">Log in to manage data or run protected operations.</p><a class="button" href="#/admin">Admin Login</a></section>`;
}

function pageHeader(title, subtitle, stats = []) {
  return `${renderBreadcrumbs()}<section class="page-header"><div><p class="eyebrow">${escapeHtml(APP_BRAND.shortName)}</p><h1>${escapeHtml(title)}</h1><p>${escapeHtml(subtitle)}</p></div>${stats.length ? `<div class="stats">${stats.map(([label, value]) => metric(label, value)).join("")}</div>` : ""}</section>`;
}

function metric(label, value) {
  return `<div class="metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value ?? 0)}</strong></div>`;
}

function badge(label, ok) {
  return `<span class="badge ${ok ? "ok" : "missing"}">${escapeHtml(label)} ${ok ? "yes" : "missing"}</span>`;
}

function recoveryList(label, values) {
  const items = values || [];
  return `<details ${items.length ? "open" : ""}><summary>${escapeHtml(label)} (${items.length})</summary><p class="chapter-pills">${items.map((item) => `<span>${escapeHtml(item)}</span>`).join("") || "None"}</p></details>`;
}

function objectDetails(label, value) {
  if (!value || (Array.isArray(value) && !value.length) || (!Array.isArray(value) && !Object.keys(value).length)) return "";
  return `<details><summary>${escapeHtml(label)}</summary><pre>${escapeHtml(JSON.stringify(value, null, 2))}</pre></details>`;
}

function renderBreadcrumbs() {
  const crumbs = breadcrumbsForHash(window.location.hash || "#/home");
  if (crumbs.length < 2) return "";
  return `<nav class="breadcrumbs" aria-label="Breadcrumbs">${crumbs.map((item, index) => index === crumbs.length - 1 ? `<span>${escapeHtml(item.label)}</span>` : `<a href="${escapeAttr(item.href)}">${escapeHtml(item.label)}</a>`).join("<span>/</span>")}</nav>`;
}

function breadcrumbsForHash(hash) {
  const [path] = String(hash || "#/home").replace(/^#\/?/, "").split("?");
  const parts = path.split("/").filter(Boolean);
  const novelId = parts[1] || state.currentNovelId;
  const novel = state.novels.find((item) => item.id === novelId);
  const novelLabel = novel ? displayNovelTitle(novel) : humanizeId(novelId || "Novel");
  const root = [{label: "Home", href: "#/home"}];
  if (!parts.length || parts[0] === "home") return root;
  if (parts[0] === "library") return [...root, {label: "Library", href: "#/library"}];
  if (parts[0] === "novel") return [...root, {label: novelLabel, href: hash}];
  if (parts[0] === "chapters") return [...root, {label: "Library", href: "#/library"}, {label: novelLabel, href: hash}];
  if (parts[0] === "reader") return [...root, {label: novelLabel, href: `#/chapters/${novelId}`}, {label: `Chapter ${parts[2] || ""}`, href: hash}];
  if (parts[0] === "translate") return [...root, {label: novelLabel, href: `#/chapters/${novelId}`}, {label: "Translate", href: hash}];
  if (parts[0] === "compare") return [...root, {label: novelLabel, href: `#/chapters/${novelId}`}, {label: `Compare ${parts[2] || ""}`, href: hash}];
  if (parts[0] === "jobs") return [...root, {label: "Jobs", href: "#/jobs"}, ...(parts[1] ? [{label: parts[1].slice(0, 8), href: hash}] : [])];
  if (parts[0] === "admin") return [...root, {label: "Admin", href: "#/admin"}, ...(parts[1] ? [{label: titleCase(parts[1]), href: hash}] : [])];
  return [...root, {label: titleCase(parts[0]), href: hash}];
}

function statusBadge(status) {
  const ok = ["completed", "running", "queued", "healthy", "protected"].includes(String(status || "").toLowerCase());
  const missing = ["failed", "needs attention", "unhealthy"].includes(String(status || "").toLowerCase());
  return `<span class="badge ${ok ? "ok" : missing ? "missing" : ""}" aria-label="Status: ${escapeAttr(status || "unknown")}">${escapeHtml(status || "unknown")}</span>`;
}

function jobActivityText(job) {
  const activity = job.activity || {};
  const workers = activity.active_workers || 0;
  const stalled = activity.stalled_items || 0;
  const throughput = jobThroughput(job);
  const heartbeat = activity.last_heartbeat_at ? `Heartbeat ${timeAgo(activity.last_heartbeat_at)}` : "No heartbeat yet";
  return `Running in parallel: ${workers} active<br><span>${throughput.summary}${stalled ? ` / ${stalled} stalled` : ""} / ${escapeHtml(heartbeat)}</span>`;
}

function renderJobDetail(job) {
  const items = job.items || [];
  const visible = items.slice(0, 12);
  const throughput = jobThroughput(job);
  return `<section class="panel job-detail"><div class="actions"><h2>Job ${job.id.slice(0, 8)}</h2><button type="button" data-copy-link="#/jobs/${job.id}">Copy Link</button></div><div class="metric-grid">${metric("Status", job.status)}${metric("Completed", `${job.completed_items || 0}/${job.total_items || 0}`)}${metric("Active workers", job.activity?.active_workers || 0)}${metric("Speed", throughput.summary)}${metric("Remaining", throughput.remaining)}${metric("Updated", timeAgo(job.updated_at))}</div><details open><summary>Advanced worker details</summary><div class="job-items">${visible.map((item) => `<span class="job-item">${item.chapter_number} ${escapeHtml(item.status || "")}${item.worker_id ? ` - ${escapeHtml(item.worker_id.slice(0, 8))}` : ""}${item.failure_category ? ` - ${escapeHtml(item.failure_category)}` : ""}</span>`).join("") || `<p class="muted">No items.</p>`}</div></details></section>`;
}

async function fetchReaderChapter(novelId, chapterNumber, source) {
  const path = chapterTextPath(novelId, chapterNumber, source);
  const cached = state.cache.get(path);
  if (cached && Date.now() - cached.time < 120_000) return cached.payload;
  const key = `${novelId}:${chapterNumber}:${source}`;
  if (readerRequestMap.has(key)) return readerRequestMap.get(key);
  if (readerAbortController) readerAbortController.abort();
  readerAbortController = new AbortController();
  const request = api(path, {signal: readerAbortController.signal})
    .then((payload) => {
      rememberCachePayload(path, payload);
      return payload;
    })
    .finally(() => readerRequestMap.delete(key));
  readerRequestMap.set(key, request);
  return request;
}

function chapterTextPath(novelId, chapterNumber, source) {
  return `/api/novels/${encodeURIComponent(novelId)}/chapters/${chapterNumber}/${source}`;
}

function prefetchNeighborChapters(novelId, chapterNumber, source) {
  if (source === "reference" && !canViewReference()) return;
  [neighborChapter(chapterNumber, -1), neighborChapter(chapterNumber, 1)]
    .filter(Boolean)
    .forEach((chapter) => cachedApi(chapterTextPath(novelId, chapter, source), 120_000).catch(() => {}));
}

function bindReaderProgress(novelId, chapterNumber, source) {
  if (readerScrollHandler) window.removeEventListener("scroll", readerScrollHandler);
  readerScrollHandler = debounce(() => {
    const percent = readerScrollPercent();
    localStorage.setItem(readerScrollKey(novelId, chapterNumber, source), String(percent));
    rememberRecent("chapters", {novel_id: novelId, chapter_number: chapterNumber, source, label: `Chapter ${chapterNumber}`, href: `#/reader/${encodeURIComponent(novelId)}/${chapterNumber}/${source}`, scroll_percent: percent, at: new Date().toISOString()});
    saveProgressDebounced(novelId, chapterNumber, source, percent);
    updateBackToTop();
    updateReaderProgressUi(percent);
  }, 700);
  window.addEventListener("scroll", readerScrollHandler, {passive: true});
}

function bindReaderChrome() {
  if (readerChromeHandler) window.removeEventListener("scroll", readerChromeHandler);
  lastReaderScrollY = window.scrollY;
  document.body.dataset.readerChrome = "visible";
  readerChromeHandler = () => {
    closeParagraphMenu(false);
    if (state.preferences.reduceMotion || !window.location.hash.startsWith("#/reader/")) return;
    const current = window.scrollY;
    const movingDown = current > lastReaderScrollY + 18;
    const movingUp = current < lastReaderScrollY - 8;
    if (movingDown && current > 180) document.body.dataset.readerChrome = "quiet";
    if (movingUp || current < 120) document.body.dataset.readerChrome = "visible";
    lastReaderScrollY = current;
  };
  window.addEventListener("scroll", readerChromeHandler, {passive: true});
  document.querySelector(".reader-panel")?.addEventListener("pointerdown", (event) => {
    if (event.target.closest("button, a, input, textarea, select")) return;
    document.body.dataset.readerChrome = "visible";
  });
}

function updateReaderProgressUi(percent = readerScrollPercent()) {
  const rounded = Math.round(percent);
  const text = document.querySelector("#readerProgressText");
  const bar = document.querySelector("#readerScrollProgress");
  if (text) text.textContent = `${rounded}%`;
  if (bar) bar.style.width = `${rounded}%`;
}

function updateBackToTop() {
  const button = document.querySelector("#backToTop");
  if (button) button.hidden = window.scrollY < 500;
}

function readerScrollKey(novelId, chapterNumber, source) {
  return `gt-reader-scroll:${novelId}:${chapterNumber}:${source}`;
}

function restoreReaderScroll(novelId, chapterNumber, source) {
  const saved = Number(localStorage.getItem(readerScrollKey(novelId, chapterNumber, source)) || 0);
  if (!Number.isFinite(saved) || saved <= 0) return;
  requestAnimationFrame(() => {
    const total = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
    window.scrollTo({top: total * saved / 100, behavior: state.preferences.reduceMotion ? "auto" : "smooth"});
  });
}

function chapterStateKey(novelId) {
  return `gt-chapter-state:${novelId}`;
}

function persistChapterState(novelId) {
  writeStored(chapterStateKey(novelId), {view: state.chapterView, search: state.chapterSearch, offset: state.chapterOffset});
}

function restoreChapterState(novelId) {
  const saved = readStored(chapterStateKey(novelId), {});
  state.chapterView = saved.view || "all";
  state.chapterSearch = saved.search || "";
  state.chapterOffset = Number(saved.offset || 0);
}

function translateDraftKey(novelId) {
  return `gt-translate-draft:${novelId}`;
}

function translateDraft(novelId) {
  return readStored(translateDraftKey(novelId), {});
}

function saveTranslateDraft() {
  const novelId = document.querySelector("#translateNovel")?.value || state.currentNovelId;
  const payload = {...translatePayload(), saved_at: new Date().toISOString()};
  writeStored(translateDraftKey(novelId), payload);
  const label = document.querySelector("#draftStatus");
  if (label) label.textContent = "Draft saved just now";
}

function validateTranslateForm() {
  const selectionMode = document.querySelector("#selectionMode")?.value || "next-untranslated";
  const chaptersInput = document.querySelector("#translateChapters");
  const chapterError = document.querySelector("#chapterError");
  const customCountError = document.querySelector("#customCountError");
  const budgetError = document.querySelector("#budgetError");
  const estimateButton = document.querySelector("#estimateBtn");
  const createButton = document.querySelector("#createJobBtn");
  const launchReason = document.querySelector("#launchReason");
  if (!chaptersInput || !chapterError || !budgetError) return true;
  const raw = chaptersInput.value.trim();
  const parsed = parseChapterInputDetailed(raw);
  const invalidChapter = selectionMode === "specific" && (!raw || parsed.chapters.length === 0 || parsed.invalidTokens.length > 0);
  const nextCountMode = document.querySelector("#nextCount")?.value || "25";
  const customCount = numberOrNull("#customNextCount");
  const maxEligible = currentNovelEligibleMax();
  const invalidCustomCount = selectionMode === "next-untranslated" && nextCountMode === "custom" && (!customCount || customCount < 1 || customCount > maxEligible);
  const total = numberOrNull("#maxTotalBudget");
  const per = numberOrNull("#maxPerChapterBudget");
  const invalidBudget = total !== null && per !== null && per > total;
  const overBudget = estimateExceedsBudget(state.lastEstimate);
  const noEligible = state.lastEstimate && Number(state.lastEstimate.eligible_count || 0) <= 0;
  const needsAllConfirmation = state.lastEstimate && isAllTranslationSelection() && !document.querySelector("#confirmAllUntranslated")?.checked;
  chapterError.textContent = invalidChapter ? "Enter chapters like 26,53,60-70 or choose all untranslated." : "";
  if (customCountError) {
    customCountError.textContent = invalidCustomCount
      ? `Enter a count from 1${maxEligible > 0 ? ` to ${maxEligible}` : ""}.`
      : "";
  }
  budgetError.textContent = invalidBudget ? "Per-chapter budget cannot exceed total budget." : (overBudget ? "Estimated cost exceeds the configured budget." : "");
  const valid = !invalidChapter && !invalidCustomCount && !invalidBudget;
  if (estimateButton) estimateButton.disabled = !valid;
  if (createButton) createButton.disabled = !valid || !state.lastEstimate || overBudget || noEligible || needsAllConfirmation;
  if (launchReason) {
    if (!valid) {
      launchReason.textContent = "Fix the highlighted fields before estimating or launching.";
    } else if (!state.lastEstimate) {
      launchReason.textContent = "Run an estimate before Launch Job is available.";
    } else if (overBudget) {
      launchReason.textContent = "Launch Job is disabled because the estimate exceeds the configured budget.";
    } else if (noEligible) {
      launchReason.textContent = "Launch Job is disabled because no eligible chapters were found.";
    } else if (needsAllConfirmation) {
      launchReason.textContent = "Confirm the all-chapters launch before creating the job.";
    } else {
      launchReason.textContent = "Estimate is current. Launch Job will create persistent queued chapter items for this novel.";
    }
  }
  return valid && !overBudget && !noEligible && !needsAllConfirmation;
}

function preferredSource(chapter) {
  if (chapter?.has_english || chapter?.has_ai) return "english";
  if (state.admin && chapter?.has_reference) return "reference";
  return "original";
}

function neighborChapter(chapterNumber, direction) {
  const index = state.chapters.findIndex((item) => item.chapter_number === Number(chapterNumber));
  const target = state.chapters[index + direction];
  return target ? target.chapter_number : null;
}

function paragraphs(text) {
  return String(text || "").replace(/\r\n/g, "\n").split(/\n{2,}|\n/).map((part) => part.trim()).filter(Boolean);
}

function progress(novel) {
  if (novel.translation_coverage !== undefined && novel.translation_coverage !== null) {
    return Math.max(0, Math.min(100, Math.round(Number(novel.translation_coverage) || 0)));
  }
  const denominator = coverageDenominator(novel);
  const computed = denominator ? Math.round(Number(novel.english_count ?? novel.ai_count ?? 0) / denominator * 100) : 0;
  return Math.max(0, Math.min(100, computed));
}

function coverageDenominator(novel) {
  const english = Number(novel.english_count ?? novel.ai_count ?? 0);
  const chapterCount = Number(novel.chapter_count || 0);
  const original = Number(novel.original_count || 0);
  const expected = Number(novel.expected_chapter_count || 0);
  const explicit = Number(novel.coverage_chapter_basis || 0);
  if (explicit > 0) return explicit;
  if (expected > 0) return expected;
  return Math.max(chapterCount, original, english, 0);
}

function coverageBasisLabel(novel) {
  if (novel.coverage_basis_label) return novel.coverage_basis_label;
  return novel.expected_range_configured ? "expected chapters" : "chapter inventory";
}

function sum(rows, key) {
  return rows.reduce((total, row) => total + Number(row[key] || 0), 0);
}

function timeAgo(value) {
  const date = value instanceof Date ? value : new Date(value || Date.now());
  const seconds = Math.max(0, Math.round((Date.now() - date.getTime()) / 1000));
  if (!Number.isFinite(seconds)) return "just now";
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds} seconds ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

function durationEstimateText(estimate) {
  if (!estimate || !estimate.has_history) return "Improves after first chapters";
  return `${formatDuration(estimate.low_seconds)}-${formatDuration(estimate.high_seconds)}`;
}

function budgetMarginText(estimate) {
  const limit = numberOrNull("#maxTotalBudget");
  if (!limit) return "No cap";
  const remaining = limit - Number(estimate.estimated_cost || 0);
  return remaining >= 0 ? `$${remaining.toFixed(4)} left` : `$${Math.abs(remaining).toFixed(4)} over`;
}

function estimateExceedsBudget(estimate) {
  if (!estimate) return false;
  const total = numberOrNull("#maxTotalBudget");
  const per = numberOrNull("#maxPerChapterBudget");
  const eligible = Math.max(1, Number(estimate.eligible_count || 0));
  const cost = Number(estimate.estimated_cost || 0);
  return (total !== null && cost > total) || (per !== null && cost / eligible > per);
}

function isAllTranslationSelection() {
  const selectionMode = document.querySelector("#selectionMode")?.value || "next-untranslated";
  return selectionMode === "all-untranslated" || (selectionMode === "next-untranslated" && document.querySelector("#nextCount")?.value === "all");
}

function currentNovelEligibleMax() {
  const novelId = document.querySelector("#translateNovel")?.value || state.currentNovelId;
  const novel = state.novels.find((item) => item.id === novelId) || {};
  if (document.querySelector("#onlyUntranslated")?.checked === false) {
    return Number(novel.original_count || novel.chapter_count || 0);
  }
  return Number(novel.missing_english_count ?? novel.remaining_count ?? 0);
}

function formatDuration(seconds) {
  const value = Number(seconds || 0);
  if (!value) return "unknown";
  if (value < 60) return `${Math.round(value)} sec`;
  if (value < 3600) return `${Math.round(value / 60)} min`;
  return `${Math.round(value / 3600)} hr`;
}

function secondsMetric(value) {
  if (value === null || value === undefined || value === "") return "Measuring";
  const number = Number(value);
  if (!Number.isFinite(number)) return "Measuring";
  return number < 1 ? `${number.toFixed(3)} sec` : formatDuration(number);
}

function numberMetric(value) {
  if (value === null || value === undefined || value === "") return "Measuring";
  const number = Number(value);
  if (!Number.isFinite(number)) return "Measuring";
  return number >= 100 ? Math.round(number) : number.toFixed(1);
}

function jobThroughput(job) {
  const completed = Number(job.completed_items || 0);
  const total = Number(job.total_items || 0);
  const started = job.started_at ? new Date(job.started_at).getTime() : 0;
  const finished = job.finished_at ? new Date(job.finished_at).getTime() : Date.now();
  const elapsedMinutes = started ? Math.max(0.016, (finished - started) / 60000) : 0;
  const perMinute = elapsedMinutes ? completed / elapsedMinutes : 0;
  const remainingItems = Math.max(0, total - completed - Number(job.failed_items || 0));
  const remainingMinutes = perMinute > 0 ? remainingItems / perMinute : 0;
  return {
    summary: perMinute ? `${perMinute.toFixed(1)} chapters/min` : "warming up",
    remaining: remainingMinutes ? `about ${formatDuration(remainingMinutes * 60)}` : "estimating",
  };
}

function initials(value) {
  return String(value || "GT").split(/\s+/).map((word) => word[0]).join("").slice(0, 2).toUpperCase();
}

function humanizeId(value) {
  return String(value || "Novel")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function displayNovelTitle(novel) {
  const title = String(novel?.title || "").trim();
  if (title && !/^[a-z0-9]+(?:[-_][a-z0-9]+){2,}$/i.test(title)) return title;
  return humanizeId(title || novel?.id);
}

function numberOrNull(selector) {
  const field = document.querySelector(selector);
  const value = field?.value;
  if (value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function readStored(key, fallback) {
  try {
    const parsed = JSON.parse(localStorage.getItem(key) || (Array.isArray(fallback) ? "[]" : "{}"));
    if (Array.isArray(fallback)) return Array.isArray(parsed) ? parsed : fallback;
    return {...fallback, ...(parsed && typeof parsed === "object" ? parsed : {})};
  } catch {
    return fallback;
  }
}

function writeStored(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}

function rememberRecent(type, item) {
  const list = state.recent[type] || [];
  const key = recentItemKey(item);
  state.recent[type] = [item, ...list.filter((existing) => recentItemKey(existing) !== key)].slice(0, 8);
  writeStored("gt-recent", state.recent);
}

function recentItemKey(item) {
  if (item?.novel_id && item?.chapter_number) return `${item.novel_id}:${item.chapter_number}:${item.source || ""}`;
  return item?.id || item?.href || item?.label || "";
}

function dedupeRecentReading(items = []) {
  const seen = new Set();
  return (items || []).filter((item) => {
    const normalized = normalizedContinueReading(item);
    if (!normalized) return false;
    const key = recentItemKey(normalized);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function bindCopyLinks(root = document) {
  root.querySelectorAll("[data-copy-link]").forEach((button) => {
    if (button.dataset.copyBound) return;
    button.dataset.copyBound = "1";
    button.addEventListener("click", () => copyLink(button.dataset.copyLink));
  });
}

async function copyLink(hash) {
  const url = new URL(hash || window.location.hash || "#/home", window.location.href).toString();
  try {
    await navigator.clipboard.writeText(url);
    toast("Link copied.");
  } catch {
    fallbackCopyText(url);
  }
}

function fallbackCopyText(value) {
  const area = document.createElement("textarea");
  area.value = value;
  area.setAttribute("readonly", "readonly");
  area.className = "sr-only";
  document.body.appendChild(area);
  area.select();
  try {
    document.execCommand("copy");
    toast("Link copied.");
  } catch {
    toast("Clipboard is unavailable.");
  } finally {
    area.remove();
  }
}

function saveScrollPosition() {
  if (!activeRouteKey) return;
  sessionStorage.setItem(`gt-scroll:${activeRouteKey}`, String(window.scrollY || 0));
}

function restoreScrollPosition(key = window.location.hash || "#/home") {
  const saved = Number(sessionStorage.getItem(`gt-scroll:${key}`) || 0);
  if (saved > 0) requestAnimationFrame(() => window.scrollTo({top: saved, behavior: "auto"}));
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function debounce(fn, wait) {
  let id;
  return (...args) => { clearTimeout(id); id = setTimeout(() => fn(...args), wait); };
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#039;"}[char]));
}

function escapeAttr(value) {
  return escapeHtml(value).replace(/`/g, "&#096;");
}

function defaultPreferences() {
  return {
    theme: "obsidian",
    accent: "green",
    density: "comfortable",
    cardSize: "standard",
    coverSize: "medium",
    gridDensity: "balanced",
    metadataAmount: "balanced",
    reduceMotion: false,
    contrastFocus: false,
    accessibilityComfort: false,
    interfaceBlur: true,
    readerFont: "serif",
    readerFontSize: Number(localStorage.getItem("gt-reader-font") || 20),
    readerLineHeight: 1.72,
    paragraphSpacing: 0.95,
    readingWidth: 760,
    readerTone: "dark",
    textAlign: "left",
    settingsDepth: "basic",
    notifyReading: true,
    notifyJobs: true,
    notifyTranslation: true,
    notifyImports: true,
    notifyRecovery: true,
    notifyBackups: true,
    notifyDesktop: true,
    notifyNewChapters: true,
    quietNotifications: false,
    keyboardShortcuts: true,
    readerArrowKeys: true,
    saveLocalHistory: true,
    syncAccountProgress: true,
    desktopSyncPrompts: true,
    desktopImportSummary: true,
    pinnedNovels: [],
    readingStatuses: {},
    collections: [],
    showTechnicalIds: false,
    developerHints: false,
  };
}

function loadPreferences() {
  try {
    return {...defaultPreferences(), ...JSON.parse(localStorage.getItem("gt-preferences") || "{}")};
  } catch {
    return defaultPreferences();
  }
}

function savePreferenceFromField(event) {
  const key = event.currentTarget.dataset.pref;
  let value = event.currentTarget.type === "checkbox" ? event.currentTarget.checked : event.currentTarget.value;
  if (["readerLineHeight", "paragraphSpacing", "readingWidth", "readerFontSize"].includes(key)) value = Number(value);
  state.preferences[key] = value;
  if (key === "readerFontSize") {
    state.fontSize = value;
    localStorage.setItem("gt-reader-font", String(value));
  }
  const valueLabel = document.querySelector(`[data-range-value="${CSS.escape(key)}"]`);
  if (valueLabel) valueLabel.textContent = `${value}${key === "readerFontSize" || key === "readingWidth" ? "px" : key === "paragraphSpacing" ? "em" : ""}`;
  syncPreferenceSwitchUi(event.currentTarget, value);
  localStorage.setItem("gt-preferences", JSON.stringify(state.preferences));
  applyPreferences();
  saveRemotePreferences();
  toast("Preferences saved.");
}

async function saveRemotePreferences() {
  if (!state.account) return;
  try {
    await api("/api/account/preferences", {method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify({preferences: state.preferences})});
  } catch {
    // Local preferences remain valid if the account write fails.
  }
}

const saveRemotePreferencesQuiet = debounce(() => saveRemotePreferences(), 1200);

function saveReaderPreferenceFromField(event) {
  const key = event.currentTarget.dataset.pref;
  let value = event.currentTarget.type === "checkbox" ? event.currentTarget.checked : event.currentTarget.value;
  if (["readerLineHeight", "paragraphSpacing", "readingWidth", "readerFontSize"].includes(key)) value = Number(value);
  state.preferences[key] = value;
  if (key === "readerFontSize") {
    state.fontSize = value;
    localStorage.setItem("gt-reader-font", String(value));
    const slider = document.querySelector("#readerMenuFontSize");
    if (slider) slider.value = String(value);
  }
  syncPreferenceSwitchUi(event.currentTarget, value);
  localStorage.setItem("gt-preferences", JSON.stringify(state.preferences));
  applyPreferences();
  saveRemotePreferencesQuiet();
}

function syncPreferenceSwitchUi(field, value = field?.checked) {
  if (!field || field.type !== "checkbox") return;
  const on = Boolean(value);
  field.checked = on;
  field.setAttribute("aria-checked", on ? "true" : "false");
  const card = field.closest(".toggle-card");
  card?.classList.toggle("active", on);
  const stateLabel = card?.querySelector(".switch-state");
  if (stateLabel) stateLabel.textContent = on ? "On" : "Off";
}

function handleSwitchKeydown(event) {
  if (event.key !== "Enter") return;
  event.preventDefault();
  event.currentTarget.click();
}

function bindAccountControls() {
  document.querySelector("#authForm")?.addEventListener("submit", (event) => {
    event.preventDefault();
    authEmailPassword("signIn");
  });
  document.querySelector("#signUpBtn")?.addEventListener("click", () => authEmailPassword("signUp"));
  document.querySelector("#forgotBtn")?.addEventListener("click", resetPassword);
  document.querySelector("#googleBtn")?.addEventListener("click", signInWithGoogle);
  document.querySelector("#toggleAuthPassword")?.addEventListener("click", togglePasswordVisibility);
  document.querySelector("#signOutBtn")?.addEventListener("click", signOut);
  document.querySelector("#exitAdminBtn")?.addEventListener("click", exitAdminMode);
}

async function authEmailPassword(mode) {
  if (!state.supabaseClient) return toast("Account features are not configured.");
  const email = document.querySelector("#authEmail")?.value;
  const password = document.querySelector("#authPassword")?.value;
  if (!email || !password) return setAuthStatus("Enter your email and password.");
  setAuthLoading(true, mode === "signUp" ? "Creating account..." : "Signing in...");
  try {
    const result = mode === "signUp"
      ? await state.supabaseClient.auth.signUp({email, password})
      : await state.supabaseClient.auth.signInWithPassword({email, password});
    if (result.error) {
      setAuthStatus(result.error.message);
      return;
    }
    await refreshAccount();
    await refreshSession();
    openSettings("account");
    toast(mode === "signUp" ? "Check your email to confirm your account." : "Signed in.");
  } finally {
    setAuthLoading(false);
  }
}

function setAuthLoading(active, message = "") {
  document.querySelectorAll("#authForm button, #authForm input").forEach((field) => { field.disabled = active || (state.authConfig?.configured === false); });
  const signIn = document.querySelector("#signInBtn");
  if (signIn) signIn.textContent = active ? "Please wait..." : "Sign In";
  setAuthStatus(message);
}

function setAuthStatus(message) {
  const status = document.querySelector("#authStatus");
  if (status) status.textContent = message || "";
  if (message) toast(message);
}

function togglePasswordVisibility() {
  const field = document.querySelector("#authPassword");
  const button = document.querySelector("#toggleAuthPassword");
  if (!field || !button) return;
  const showing = field.type === "text";
  field.type = showing ? "password" : "text";
  button.textContent = showing ? "Show" : "Hide";
  button.setAttribute("aria-label", showing ? "Show password" : "Hide password");
  field.focus();
}

async function resetPassword() {
  if (!state.supabaseClient) return toast("Account features are not configured.");
  const email = document.querySelector("#authEmail")?.value;
  if (!email) return toast("Enter your email first.");
  const redirectTo = new URL("#/settings/account", window.location.href).toString();
  const result = await state.supabaseClient.auth.resetPasswordForEmail(email, {redirectTo});
  toast(result.error ? result.error.message : "Password reset email sent.");
}

async function signInWithGoogle() {
  if (!state.supabaseClient) return toast("Google login is not configured yet.");
  const redirectTo = state.authConfig?.redirect_url?.startsWith("http") ? state.authConfig.redirect_url : new URL("/auth/callback", window.location.origin).toString();
  const result = await state.supabaseClient.auth.signInWithOAuth({provider: "google", options: {redirectTo}});
  if (result.error) toast(result.error.message);
}

async function signOut() {
  if (state.supabaseClient) await state.supabaseClient.auth.signOut();
  state.account = null;
  state.personal = null;
  await refreshSession();
  renderNav();
  openSettings("account");
  toast("Signed out.");
}

async function exitAdminMode() {
  await api("/api/admin/logout", {method: "POST"});
  state.admin = false;
  await refreshSession();
  renderNav();
  route();
  toast("Exited Admin Mode.");
}

function applyPreferences() {
  const pref = state.preferences;
  document.body.dataset.theme = pref.theme;
  document.body.dataset.accent = pref.accent;
  document.body.dataset.density = pref.density;
  document.body.dataset.cardSize = pref.cardSize;
  document.body.dataset.coverSize = pref.coverSize;
  document.body.dataset.gridDensity = pref.gridDensity;
  document.body.dataset.metadata = pref.metadataAmount;
  document.body.dataset.motion = pref.reduceMotion ? "reduced" : "standard";
  document.body.dataset.focus = pref.contrastFocus ? "strong" : "standard";
  document.body.dataset.comfort = pref.accessibilityComfort ? "on" : "off";
  document.body.dataset.blur = pref.interfaceBlur ? "on" : "off";
  document.documentElement.style.setProperty("--reader-font", `${pref.readerFontSize || state.fontSize}px`);
  document.documentElement.style.setProperty("--reader-line-height", String(pref.readerLineHeight));
  document.documentElement.style.setProperty("--reader-paragraph-spacing", `${pref.paragraphSpacing}em`);
  document.documentElement.style.setProperty("--reader-width", `${pref.readingWidth}px`);
  document.documentElement.style.setProperty("--reader-align", pref.textAlign);
  document.body.dataset.readerFont = pref.readerFont;
  document.body.dataset.readerTone = pref.readerTone;
}

function bindShellControls() {
  document.querySelector("#globalSearchBtn")?.addEventListener("click", openCommandPalette);
  document.querySelector("#jobCenterBtn")?.addEventListener("click", () => { window.location.hash = canTranslate() ? "#/activity" : "#/settings/account"; });
  document.addEventListener("click", (event) => {
    if (profileMenu?.open && !profileMenu.contains(event.target)) profileMenu.open = false;
  });
  profileMenu?.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    event.preventDefault();
    profileMenu.open = false;
  });
  commandInput?.addEventListener("input", renderCommandResults);
  commandInput?.addEventListener("keydown", closeCommandPaletteOnEscape);
  document.querySelector("#commandClose")?.addEventListener("click", () => closeCommandPalette());
  commandDialog?.addEventListener("keydown", closeCommandPaletteOnEscape, {capture: true});
  commandDialog?.addEventListener("cancel", (event) => {
    event.preventDefault();
    closeCommandPalette();
  });
  commandDialog?.addEventListener("click", (event) => {
    if (event.target === commandDialog) closeCommandPalette();
  });
  commandDialog?.addEventListener("touchstart", (event) => {
    commandTouchStartY = event.changedTouches?.[0]?.clientY || 0;
  }, {passive: true});
  commandDialog?.addEventListener("touchend", (event) => {
    const y = event.changedTouches?.[0]?.clientY || 0;
    if (commandTouchStartY && y - commandTouchStartY > 64) closeCommandPalette();
    commandTouchStartY = 0;
  }, {passive: true});
  commandDialog?.addEventListener("close", () => {
    if (commandInput) commandInput.value = "";
    renderMobileBottomNav(activeRouteName());
    if (commandPaletteClosingFromPop) return;
    if (commandPaletteOpenFromHistory) {
      commandPaletteOpenFromHistory = false;
      history.back();
    }
  });
  document.addEventListener("keydown", (event) => {
    const target = event.target;
    const typing = target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
    if (event.key === "Escape" && !document.querySelector("#paragraphActionMenu")?.hidden) {
      event.preventDefault();
      closeParagraphMenu();
      return;
    }
    if (event.key === "Escape" && commandDialog?.open) {
      event.preventDefault();
      closeCommandPalette();
      return;
    }
    if (event.key === "Escape" && profileMenu?.open) {
      event.preventDefault();
      profileMenu.open = false;
      return;
    }
    if (state.preferences.keyboardShortcuts && (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      openCommandPalette();
    }
    if (state.preferences.keyboardShortcuts && !typing && event.key === "?") {
      event.preventDefault();
      showShortcutHelp();
    }
    if (state.preferences.keyboardShortcuts && !typing && window.location.hash.startsWith("#/reader/")) {
      const parts = window.location.hash.replace(/^#\/?/, "").split("/");
      const novelId = parts[1];
      const chapter = Number(parts[2]);
      if (event.key === "+") adjustReaderFont(1);
      if (event.key === "-") adjustReaderFont(-1);
      if (state.preferences.readerArrowKeys && event.key === "ArrowLeft") {
        const previous = neighborChapter(chapter, -1);
        if (previous) {
          event.preventDefault();
          window.location.hash = `#/reader/${novelId}/${previous}/${state.source}`;
        }
      }
      if (state.preferences.readerArrowKeys && event.key === "ArrowRight") {
        const next = neighborChapter(chapter, 1);
        if (next) {
          event.preventDefault();
          window.location.hash = `#/reader/${novelId}/${next}/${state.source}`;
        }
      }
      if (event.key.toLowerCase() === "f") {
        state.zen = !state.zen;
        document.body.dataset.zen = state.zen ? "on" : "off";
        document.querySelector(".reader-panel")?.classList.toggle("zen", state.zen);
        const focusExit = document.querySelector("#readerFocusExit");
        if (focusExit) focusExit.hidden = !state.zen;
        if (state.zen) revealFocusExit();
      }
      if (event.key.toLowerCase() === "t") {
        event.preventDefault();
        openChapterDrawer();
      }
      if (event.key.toLowerCase() === "s") {
        event.preventDefault();
        openReaderMenu();
      }
      if (event.key.toLowerCase() === "b") saveBookmark(novelId, chapter);
    }
    if (state.preferences.keyboardShortcuts && window.location.hash.startsWith("#/reader/") && event.key === "Escape") {
      const drawer = document.querySelector("#chapterDrawer");
      const menu = document.querySelector("#readerMenuPanel");
      if (drawer && !drawer.hidden) {
        event.preventDefault();
        closeChapterDrawer();
      } else if (menu && !menu.hidden) {
        event.preventDefault();
        closeReaderMenu();
      } else if (state.zen) {
        event.preventDefault();
        state.zen = false;
        document.body.dataset.zen = "off";
        document.querySelector(".reader-panel")?.classList.remove("zen");
        const focusExit = document.querySelector("#readerFocusExit");
        if (focusExit) {
          focusExit.classList.remove("visible");
          focusExit.hidden = true;
        }
      }
    }
  });
  document.addEventListener("pointerdown", (event) => {
    if (event.target.closest("#paragraphActionMenu") || event.target.closest("[data-reader-paragraph]")) return;
    closeParagraphMenu(false);
  }, {capture: true});
}

function closeCommandPaletteOnEscape(event) {
  if (event.key !== "Escape" || !commandDialog?.open) return;
  event.preventDefault();
  event.stopPropagation();
  closeCommandPalette();
}

function openCommandPalette() {
  if (!commandDialog || !commandInput) return;
  if (profileMenu) profileMenu.open = false;
  renderCommandResults();
  if (!commandDialog.open) {
    commandPaletteOpenFromHistory = true;
    history.pushState({commandPalette: true}, "", window.location.href);
    commandDialog.showModal();
  }
  commandInput.focus();
  renderMobileBottomNav("search");
}

function closeCommandPalette() {
  if (!commandDialog) return;
  const restoreHistory = commandPaletteOpenFromHistory;
  commandPaletteOpenFromHistory = false;
  commandPaletteClosingFromPop = restoreHistory;
  if (commandDialog.open) commandDialog.close();
  if (restoreHistory) {
    history.back();
    setTimeout(() => { commandPaletteClosingFromPop = false; }, 0);
  }
}

function closeCommandPaletteFromHistory() {
  if (!commandDialog?.open) return;
  commandPaletteClosingFromPop = true;
  commandPaletteOpenFromHistory = false;
  commandDialog.close();
  setTimeout(() => { commandPaletteClosingFromPop = false; }, 0);
}

function navigateFromCommandPalette(href) {
  if (!href) return;
  commandPaletteClosingFromPop = true;
  commandPaletteOpenFromHistory = false;
  if (commandDialog?.open) commandDialog.close();
  history.replaceState(null, "", href);
  activeRouteKey = window.location.hash || "#/home";
  route();
  setTimeout(() => { commandPaletteClosingFromPop = false; }, 0);
}

function showShortcutHelp() {
  const existing = document.querySelector("#shortcutDialog");
  if (existing) existing.remove();
  const dialog = document.createElement("dialog");
  dialog.id = "shortcutDialog";
  dialog.className = "command-dialog shortcut-dialog";
  dialog.innerHTML = `<form method="dialog"><section class="panel"><h2>Keyboard Shortcuts</h2><div class="shortcut-grid"><span>Ctrl/Cmd + K</span><strong>Search and commands</strong><span>?</span><strong>Shortcut help</strong><span>Left / Right</span><strong>Previous / next chapter</strong><span>T</span><strong>Table of contents</strong><span>S</span><strong>Reader menu</strong><span>B</span><strong>Bookmark chapter</strong><span>F</span><strong>Reader focus mode</strong><span>Esc</span><strong>Close reader panels</strong></div><div class="actions"><button class="primary">Close</button></div></section></form>`;
  document.body.appendChild(dialog);
  dialog.addEventListener("close", () => dialog.remove());
  dialog.showModal();
}

function renderCommandResults() {
  if (!commandResults) return;
  const query = (commandInput?.value || "").trim().toLowerCase();
  const primaryCommands = [
    ["Go Home", "#/home", true],
    ["Go to Library", "#/library", true],
    ["Continue Reading", continueReadingHref(), continueReadingHref() !== "#/library"],
    ["Open Translate", `#/translate/${state.currentNovelId}`, canTranslate()],
    ["Open Activity", "#/activity", canTranslate()],
    ["Show Shortcuts", "#shortcuts", true],
  ];
  const settingsCommands = [
    ["Settings", "#/settings", true],
    ["Settings: Appearance", "#/settings/appearance", true],
    ["Settings: Reading", "#/settings/reader", true],
    ["Settings: Accessibility", "#/settings/accessibility", true],
    ["Settings: Notifications", "#/settings/notifications", true],
    ["Settings: Account", "#/settings/account", true],
    ["Settings: Privacy", "#/settings/privacy", true],
    ["Settings: Advanced", "#/settings/advanced", state.admin || canTranslate()],
  ];
  const adminCommands = [
    ["Manage Novels", "#/admin/novels", state.admin],
    ["Add Novel", "#/novels/add", state.admin],
    ["Open Novel Recovery", "#/admin/recovery", state.admin],
    ["Open Admin", "#/admin", state.admin],
  ];
  const novelMatches = state.novels.map((novel) => [`Novel: ${displayNovelTitle(novel)}${novel.author ? ` by ${novel.author}` : ""}`, `#/novel/${novel.id}`, true]);
  const chapterMatches = state.chapters.slice(0, 500).map((chapter) => [`Chapter ${chapter.chapter_number}: ${chapter.title}`, `#/reader/${state.currentNovelId}/${chapter.chapter_number}/${safeReaderSource()}`, true]);
  const recentMatches = [
    ...(state.recent.novels || []).map((item) => [`Recent Novel: ${item.label}`, item.href, true]),
    ...(state.recent.chapters || []).map((item) => [`Recent Chapter: ${item.label}`, item.href, true]),
    ...(state.recent.jobs || []).map((item) => [`Recent Job: ${item.label}`, item.href, canTranslate()]),
    ...(state.recent.admin || []).map((item) => [`Recent Admin: ${item.label}`, item.href, state.admin]),
  ];
  const filterRows = (rows, limit = 8) => rows
    .filter(([, , allowed]) => allowed)
    .filter(([label]) => !query || label.toLowerCase().includes(query))
    .slice(0, limit);
  const sections = [
    ["Commands", filterRows([...primaryCommands, ...adminCommands], 8)],
    ["Settings Commands", filterRows(settingsCommands, 10)],
    ["Novels", filterRows(novelMatches, 8)],
    ["Chapters", filterRows(chapterMatches, 8)],
    ["Recent", filterRows(recentMatches, 8)],
  ].filter(([, rows]) => rows.length);
  commandResults.innerHTML = sections.map(([title, rows]) => `<section class="command-section"><h2>${escapeHtml(title)}</h2>${rows.map(([label, href]) => `<a href="${href}" data-command-result>${escapeHtml(label)}</a>`).join("")}</section>`).join("") || `<p class="muted">No matches.</p>`;
  commandResults.querySelectorAll("[data-command-result]").forEach((link) => link.addEventListener("click", (event) => {
    event.preventDefault();
    if (link.getAttribute("href") === "#shortcuts") {
      commandPaletteClosingFromPop = true;
      commandPaletteOpenFromHistory = false;
      if (commandDialog?.open) commandDialog.close();
      setTimeout(() => { commandPaletteClosingFromPop = false; }, 0);
      showShortcutHelp();
      return;
    }
    if (query) rememberRecent("searches", {label: query, href: link.getAttribute("href"), at: new Date().toISOString()});
    navigateFromCommandPalette(link.getAttribute("href"));
  }));
}

function adjustReaderFont(delta) {
  state.fontSize = Math.max(16, Math.min(25, state.fontSize + delta));
  localStorage.setItem("gt-reader-font", String(state.fontSize));
  document.documentElement.style.setProperty("--reader-font", `${state.fontSize}px`);
}

function toast(message, actionLabel = "", action = null) {
  const item = document.createElement("div");
  item.className = "toast";
  item.dataset.toastMessage = message;
  item.setAttribute("role", "status");
  item.setAttribute("aria-live", "polite");
  item.innerHTML = `<span>${escapeHtml(message)}</span>${actionLabel ? `<button type="button">${escapeHtml(actionLabel)}</button>` : ""}`;
  item.querySelector("button")?.addEventListener("click", async () => {
    item.remove();
    if (action) await action();
  });
  document.body.appendChild(item);
  requestAnimationFrame(() => item.classList.add("show"));
  setTimeout(() => {
    item.classList.remove("show");
    setTimeout(() => item.remove(), 240);
  }, 1800);
}

function clearToasts() {
  document.querySelectorAll(".toast").forEach((item) => item.remove());
}

function titleCase(value) {
  return String(value || "").replace(/-/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

window.addEventListener("hashchange", () => {
  saveScrollPosition();
  closeParagraphMenu(false);
  activeRouteKey = window.location.hash || "#/home";
  if (!activeRouteKey.startsWith("#/reader/") && readerScrollHandler) {
    window.removeEventListener("scroll", readerScrollHandler);
    readerScrollHandler = null;
  }
  if (!activeRouteKey.startsWith("#/reader/") && readerChromeHandler) {
    window.removeEventListener("scroll", readerChromeHandler);
    readerChromeHandler = null;
    document.body.dataset.readerChrome = "visible";
  }
  if (!activeRouteKey.startsWith("#/reader/") && readerAbortController) {
    readerAbortController.abort();
    readerAbortController = null;
    readerRequestMap.clear();
  }
  route();
});
window.addEventListener("popstate", () => {
  if (commandDialog?.open) closeCommandPaletteFromHistory();
});
window.addEventListener("DOMContentLoaded", async () => {
  applyBranding();
  applyPreferences();
  bindShellControls();
  await loadAuth();
  await refreshSession();
  await loadNovels().catch(() => {});
  activeRouteKey = window.location.hash || "#/home";
  route();
});
