const app = document.querySelector("#app");
const nav = document.querySelector("#primaryNav");
const commandDialog = document.querySelector("#commandDialog");
const commandInput = document.querySelector("#commandInput");
const commandResults = document.querySelector("#commandResults");
const accountBtn = document.querySelector("#accountBtn");

const CACHE_TTL_MS = 45_000;
let activeRouteKey = window.location.hash || "#/library";
let connectionInterrupted = false;
let readerScrollHandler = null;

const state = {
  novels: [],
  currentNovelId: localStorage.getItem("gt-current-novel") || "i-am-god",
  chapters: [],
  chapterTotal: 0,
  chapterView: "all",
  chapterSearch: "",
  chapterOffset: 0,
  pageSize: 50,
  source: ["ai", "reference", "original"].includes(localStorage.getItem("gt-reader-source")) ? localStorage.getItem("gt-reader-source") : "ai",
  fontSize: Number(localStorage.getItem("gt-reader-font") || 19),
  zen: false,
  admin: false,
  role: "guest",
  authConfig: null,
  account: null,
  personal: null,
  supabaseClient: null,
  lastEstimate: null,
  preferences: loadPreferences(),
  libraryView: readStored("gt-library-view", {search: "", filter: "active", sort: "updated"}),
  recent: readStored("gt-recent", {novels: [], chapters: [], jobs: [], searches: [], admin: []}),
  cache: new Map(),
};

const sourceLabels = {ai: "AI", reference: "Reference", original: "Original"};
const APP_VERSION = "10.2.0";
const chapterViews = [
  ["all", "All"],
  ["translated", "Translated"],
  ["needs", "Needs Translation"],
  ["missing-original", "Missing Original"],
  ["missing-reference", "Missing Reference"],
  ["errors", "Has Errors"],
];

async function api(path, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      return await apiOnce(path, options);
    } catch (error) {
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
    error.network = true;
    throw error;
  }
  const text = await response.text();
  let payload = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    throw new Error(`The server returned a non-JSON response for ${path}.`);
  }
  if (!response.ok) {
    const detail = payload?.detail || payload?.message || `Request failed: ${response.status}`;
    const error = new Error(detail);
    error.status = response.status;
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
  state.cache.set(path, {time: Date.now(), payload});
  return payload;
}

function invalidateCache(prefix = "") {
  for (const key of [...state.cache.keys()]) {
    if (!prefix || key.startsWith(prefix)) state.cache.delete(key);
  }
}

function route() {
  const [path, query = ""] = (window.location.hash || "#/library").replace(/^#\/?/, "").split("?");
  const parts = path.split("/").filter(Boolean);
  const params = new URLSearchParams(query);
  updateNav(parts[0] || "library");
  if (parts[0] === "reader" && parts[1] && parts[2]) return openReader(parts[1], Number(parts[2]), parts[3] || state.source);
  if (parts[0] === "novel" && parts[1]) return openNovelDetail(parts[1]);
  if (parts[0] === "compare" && parts[1] && parts[2]) return openCompare(parts[1], Number(parts[2]));
  if (parts[0] === "jobs") return openJobCenter(parts[1] || "");
  if (parts[0] === "chapters" && parts[1]) return openChapters(parts[1]);
  if (parts[0] === "translate") return openTranslate(parts[1] || state.currentNovelId, params);
  if (parts[0] === "recovery") return openRecovery(parts[1] || state.currentNovelId);
  if (parts[0] === "novels") return openNovels();
  if (parts[0] === "history") return openHistory();
  if (parts[0] === "bookmarks") return openBookmarks();
  if (parts[0] === "settings") return openSettings(parts[1] || "appearance");
  if (["account", "login", "signup", "forgot-password", "reset-password"].includes(parts[0])) return openSettings("account", parts[0]);
  if (parts[0] === "admin") return openAdmin(parts[1] || localStorage.getItem("gt-last-admin-tab") || "overview");
  return openLibrary();
}

function updateNav(active) {
  if (!nav) return;
  renderNav();
  nav.querySelectorAll("a").forEach((link) => {
    const target = link.getAttribute("href").replace("#/", "").split("/")[0];
    link.classList.toggle("active", target === active || (active === "reader" && target === "chapters"));
  });
}

function renderNav() {
  if (!nav) return;
  const links = [
    ["library", "Library", "#/library", true],
    ["chapters", "Chapters", `#/chapters/${state.currentNovelId}`, true],
    ["history", "History", "#/history", Boolean(state.account)],
    ["bookmarks", "Bookmarks", "#/bookmarks", Boolean(state.account)],
    ["translate", "Translate", `#/translate/${state.currentNovelId}`, canTranslate()],
    ["novels", "Novels", "#/novels", state.admin],
    ["recovery", "Recovery", `#/recovery/${state.currentNovelId}`, state.admin],
    ["admin", "Admin", "#/admin", state.admin],
  ];
  nav.innerHTML = links.filter(([, , , allowed]) => allowed).map(([key, label, href]) => `<a data-nav="${key}" href="${href}">${label}</a>`).join("");
  if (accountBtn) {
    accountBtn.textContent = state.account?.display_name || state.account?.email || (state.admin ? "Admin" : "Guest");
    accountBtn.href = "#/account";
  }
}

function canTranslate() {
  return state.admin || state.role === "translator";
}

function setLoading(label = "Loading...") {
  app.innerHTML = `<section class="state-card"><div class="spinner"></div><p>${escapeHtml(label)}</p></section>`;
}

function setError(message, action = `<a class="button" href="#/library">Back to Library</a>`) {
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
  }
  return state.novels;
}

async function openLibrary() {
  setLoading("Opening library...");
  try {
    const novels = await loadNovels(true);
    const personal = await loadPersonalHome(true);
    app.innerHTML = `
      ${pageHeader("Library", "A calm command center for reading and translation progress.", [
        ["Novels", novels.length],
        ["Chapters", sum(novels, "chapter_count")],
        ["Original", sum(novels, "original_count")],
        ["Reference", sum(novels, "reference_count")],
        ["AI", sum(novels, "ai_count")],
      ])}
      ${renderContinueReading(personal?.continue_reading)}
      <section class="toolbar">
        <input class="search" id="librarySearch" type="search" value="${escapeAttr(state.libraryView.search)}" placeholder="Search novels">
        <select id="libraryFilter"><option value="active" ${state.libraryView.filter === "active" ? "selected" : ""}>Active</option><option value="all" ${state.libraryView.filter === "all" ? "selected" : ""}>All</option><option value="favorites" ${state.libraryView.filter === "favorites" ? "selected" : ""}>Favorites</option><option value="archived" ${state.libraryView.filter === "archived" ? "selected" : ""}>Archived</option></select>
        <select id="librarySort"><option value="updated" ${state.libraryView.sort === "updated" ? "selected" : ""}>Recently updated</option><option value="title" ${state.libraryView.sort === "title" ? "selected" : ""}>Title</option><option value="progress" ${state.libraryView.sort === "progress" ? "selected" : ""}>Translation progress</option></select>
        <button id="resetLibraryFilters" type="button">Reset Filters</button>
      </section>
      <section class="novel-grid" id="novelGrid"></section>
    `;
    ["librarySearch", "libraryFilter", "librarySort"].forEach((id) => document.querySelector(`#${id}`).addEventListener("input", renderLibraryCards));
    document.querySelector("#resetLibraryFilters").addEventListener("click", () => {
      state.libraryView = {search: "", filter: "active", sort: "updated"};
      writeStored("gt-library-view", state.libraryView);
      openLibrary();
    });
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
  state.libraryView = {search: rawQuery, filter, sort};
  writeStored("gt-library-view", state.libraryView);
  if (query) rememberRecent("searches", {label: query, href: "#/library", at: new Date().toISOString()});
  let novels = state.novels.filter((novel) => {
    if (filter === "active" && novel.is_archived) return false;
    if (filter === "archived" && !novel.is_archived) return false;
    if (filter === "favorites" && !favoriteIds().has(novel.id)) return false;
    if (!query) return true;
    return `${novel.title} ${novel.author || ""}`.toLowerCase().includes(query);
  });
  novels = novels.sort((a, b) => {
    if (sort === "title") return String(a.title).localeCompare(String(b.title));
    if (sort === "progress") return progress(b) - progress(a);
    return String(b.updated_at || "").localeCompare(String(a.updated_at || ""));
  });
  grid.innerHTML = novels.map(renderNovelCard).join("") || `<div class="empty-state">No novels match this view.</div>`;
  grid.querySelectorAll("[data-favorite]").forEach((button) => button.addEventListener("click", toggleFavorite));
  bindCopyLinks(grid);
}

function renderContinueReading(progress) {
  if (!progress) {
    return state.account ? `<section class="continue-card"><div><p class="eyebrow">Continue Reading</p><h2>No saved progress yet</h2><p class="muted">Open a chapter and GodTranslator will remember your place.</p></div></section>` : "";
  }
  return `<section class="continue-card">
    <div><p class="eyebrow">Continue Reading</p><h2>${escapeHtml(progress.novel_title)}</h2><p>Chapter ${progress.chapter_number}: ${escapeHtml(progress.chapter_title)}</p><p class="muted">${sourceLabels[progress.source] || progress.source} · ${Math.round(progress.scroll_percent || 0)}%</p></div>
    <a class="button primary" href="#/reader/${encodeURIComponent(progress.novel_id)}/${progress.chapter_number}/${progress.source}">Continue</a>
  </section>`;
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

function renderNovelCard(novel) {
  const pct = progress(novel);
  const favorite = favoriteIds().has(novel.id);
  return `
    <article class="novel-card">
      <a class="cover" href="#/novel/${encodeURIComponent(novel.id)}">
        ${novel.cover_url ? `<img src="${escapeAttr(novel.cover_url)}" alt="">` : `<span>${escapeHtml(initials(novel.title || novel.id))}</span>`}
      </a>
      <div class="novel-card-body">
        <div class="status-row"><span class="badge ok">${novel.is_archived ? "Archived" : "Active"}</span>${state.account ? `<button class="ghost-btn" data-favorite="${escapeAttr(novel.id)}">${favorite ? "Favorited" : "Favorite"}</button>` : ""}<span>${pct}% AI</span></div>
        <h2>${escapeHtml(novel.title || novel.id)}</h2>
        <p class="muted">${escapeHtml(novel.author || "Unknown author")}</p>
        <div class="mini-progress"><span style="width:${pct}%"></span></div>
        <div class="metric-grid">
          ${metric("Chapters", novel.chapter_count)}
          ${metric("Original", novel.original_count)}
          ${metric("Reference", novel.reference_count)}
          ${metric("AI", novel.ai_count)}
          ${metric("Remaining", novel.remaining_count)}
        </div>
        <div class="actions">
          <a class="button primary" href="#/novel/${encodeURIComponent(novel.id)}">Open</a>
          <a class="button" href="#/reader/${encodeURIComponent(novel.id)}/1/${state.source}">Read</a>
          ${canTranslate() ? `<a class="button" href="#/translate/${encodeURIComponent(novel.id)}">Translate</a>` : ""}
          <details class="more-menu"><summary>More</summary><button type="button" data-copy-link="#/novel/${encodeURIComponent(novel.id)}">Copy Link</button>${state.admin ? `<a class="button" href="#/novels">Admin Edit</a>` : ""}</details>
        </div>
      </div>
    </article>`;
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
    const baseNovel = detail.novel || state.novels.find((item) => item.id === novelId) || {};
    const detailCounts = detail.counts || {};
    const novel = {
      ...baseNovel,
      chapter_count: detailCounts.total ?? baseNovel.chapter_count,
      original_count: detailCounts.original ?? baseNovel.original_count,
      reference_count: detailCounts.reference ?? baseNovel.reference_count,
      ai_count: detailCounts.ai ?? baseNovel.ai_count,
      remaining_count: detailCounts.needs_translation ?? baseNovel.remaining_count,
    };
    const pct = progress(novel);
    const personal = await loadPersonalHome(true);
    const current = personal?.continue_reading?.novel_id === novelId ? personal.continue_reading : null;
    rememberRecent("novels", {id: novelId, label: novel.title || novelId, href: `#/novel/${encodeURIComponent(novelId)}`, at: new Date().toISOString()});
    app.innerHTML = `
      <section class="novel-hero">
        <div class="hero-cover">${novel.cover_url ? `<img src="${escapeAttr(novel.cover_url)}" alt="">` : `<span>${escapeHtml(initials(novel.title || novel.id))}</span>`}</div>
        <div class="hero-copy">
          <p class="eyebrow">${escapeHtml(novel.status || "Active")}</p>
          <h1>${escapeHtml(novel.title || novel.id)}</h1>
          <p>${escapeHtml(novel.summary || "A database-first GodTranslator novel workspace.")}</p>
          <div class="mini-progress"><span style="width:${pct}%"></span></div>
          <div class="metric-grid">${metric("Chapters", novel.chapter_count)}${metric("Original", novel.original_count)}${metric("Reference", novel.reference_count)}${metric("AI", novel.ai_count)}${metric("Remaining", novel.remaining_count)}</div>
          <div class="actions">
            <a class="button primary" href="${current ? `#/reader/${current.novel_id}/${current.chapter_number}/${current.source}` : `#/reader/${novel.id}/1/${state.source}`}">Continue Reading</a>
            <a class="button" href="#/chapters/${novel.id}">Chapters</a>
            <button type="button" data-copy-link="#/novel/${encodeURIComponent(novel.id)}">Copy Link</button>
            ${canTranslate() ? `<a class="button" href="#/translate/${novel.id}">Translate</a>` : ""}${state.admin ? `<a class="button" href="#/novels">Edit</a>` : ""}
          </div>
        </div>
      </section>
      <section class="split-panels">
        <div class="panel"><h2>Overview</h2><p class="muted">${escapeHtml(novel.author || "Unknown author")}</p><p>AI progress is ${pct}% based on readable Original and AI chapter text.</p></div>
        <div class="panel"><h2>Recent Chapters</h2>${(library.chapters || []).map((chapter) => `<a class="chapter-link" href="#/reader/${novel.id}/${chapter.chapter_number}/${state.source}"><strong>Chapter ${chapter.chapter_number}</strong><span>${escapeHtml(chapter.title)}</span></a>`).join("") || `<p class="empty-state">No chapters found.</p>`}</div>
      </section>`;
    bindCopyLinks(app);
    restoreScrollPosition();
  } catch (error) {
    setError(error.message);
  }
}

async function openNovels() {
  setLoading("Loading novels...");
  try {
    await refreshSession();
    const novels = await loadNovels(true);
    app.innerHTML = `
      ${pageHeader("Novels", "Manage titles, metadata, covers, and archive status.", [["Total", novels.length], ["Active", novels.filter((n) => !n.is_archived).length], ["Archived", novels.filter((n) => n.is_archived).length]])}
      ${state.admin ? renderNovelForm() : adminNotice()}
      <section class="table-card">
        <table><thead><tr><th>Novel</th><th>Status</th><th>Counts</th><th>Actions</th></tr></thead><tbody>
          ${novels.map((novel) => `<tr><td><strong>${escapeHtml(novel.title)}</strong><br><span>${escapeHtml(novel.id)}</span></td><td>${novel.is_archived ? "Archived" : "Active"}</td><td>${novel.chapter_count || 0} chapters / ${novel.ai_count || 0} AI</td><td class="row-actions"><a class="button" href="#/chapters/${novel.id}">Chapters</a>${state.admin ? `<button data-archive="${novel.id}" data-value="${novel.is_archived ? "false" : "true"}">${novel.is_archived ? "Unarchive" : "Archive"}</button>` : ""}</td></tr>`).join("")}
        </tbody></table>
      </section>`;
    document.querySelector("#novelForm")?.addEventListener("submit", saveNovelForm);
    document.querySelector("#novelForm")?.addEventListener("input", () => {
      writeStored("gt-novel-form-draft", Object.fromEntries(new FormData(document.querySelector("#novelForm")).entries()));
      document.querySelector("#novelDraftStatus").textContent = "Draft saved just now";
    });
    document.querySelector("#discardNovelDraft")?.addEventListener("click", () => { localStorage.removeItem("gt-novel-form-draft"); openNovels(); });
    document.querySelectorAll("[data-archive]").forEach((button) => button.addEventListener("click", archiveNovel));
    restoreScrollPosition();
  } catch (error) {
    setError(error.message);
  }
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
    <label>Reference target end<input name="reference_target_end" type="number" min="1" placeholder="434" value="${escapeAttr(draft.reference_target_end || "")}"></label>
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
    alert(error.message);
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
  const counts = payload.counts || {};
  rememberRecent("novels", {id: novel.id, label: novel.title || novel.id, href: `#/chapters/${encodeURIComponent(novel.id)}`, at: new Date().toISOString()});
  app.innerHTML = `
    ${pageHeader(novel.title || novel.id, "Browse chapter availability, translation state, and reader entry points.", [
      ["Chapters", counts.total_chapter_rows],
      ["Original", counts.original_readable],
      ["Reference", counts.reference_readable],
      ["AI", counts.ai_readable],
      ["Needs Translation", counts.needs_translation],
    ])}
    <section class="toolbar">
      <select id="chapterNovel">${state.novels.map((n) => `<option value="${n.id}" ${n.id === novel.id ? "selected" : ""}>${escapeHtml(n.title)}</option>`).join("")}</select>
      <input class="search" id="chapterSearch" type="search" value="${escapeAttr(state.chapterSearch)}" placeholder="Search chapter number or title">
      <select id="chapterView">${chapterViews.map(([value, label]) => `<option value="${value}" ${value === state.chapterView ? "selected" : ""}>${label}</option>`).join("")}</select>
      ${canTranslate() ? `<a class="button" href="#/translate/${novel.id}">Translate</a>` : ""}${state.admin ? `<a class="button" href="#/recovery/${novel.id}">Recovery</a>` : ""}
    </section>
    <section class="table-card">
      <div class="table-meta">Showing ${state.chapterTotal ? state.chapterOffset + 1 : 0}-${Math.min(state.chapterOffset + state.pageSize, state.chapterTotal)} of ${state.chapterTotal} chapters</div>
      <table class="responsive-table"><thead><tr><th>Chapter</th><th>Original</th><th>Reference</th><th>AI</th><th>Status</th><th></th></tr></thead><tbody>
        ${state.chapters.map((chapter) => `<tr><td data-label="Chapter"><strong>Chapter ${chapter.chapter_number}</strong><br><span>${escapeHtml(chapter.title)}</span></td><td data-label="Original">${badge("Original", chapter.has_original)}</td><td data-label="Reference">${badge("Reference", chapter.has_reference)}</td><td data-label="AI">${badge("AI", chapter.has_ai)}</td><td data-label="Status">${escapeHtml(chapter.translation_status || "")}</td><td data-label="Actions" class="row-actions"><a class="button" href="#/reader/${novel.id}/${chapter.chapter_number}/${state.source}">Read</a><button type="button" data-copy-link="#/reader/${novel.id}/${chapter.chapter_number}/${state.source}">Copy Link</button>${canTranslate() ? `<a class="button" href="#/translate/${novel.id}?chapter=${chapter.chapter_number}">Translate</a><a class="button" href="#/compare/${novel.id}/${chapter.chapter_number}">Compare</a>` : ""}</td></tr>`).join("") || `<tr><td colspan="6">No chapters match this view.</td></tr>`}
      </tbody></table>
      <div class="pager"><button id="prevPage" ${state.chapterOffset <= 0 ? "disabled" : ""}>Previous</button><button id="nextPage" ${state.chapterOffset + state.pageSize >= state.chapterTotal ? "disabled" : ""}>Next</button></div>
    </section>`;
  document.querySelector("#chapterNovel").addEventListener("change", (e) => { window.location.hash = `#/chapters/${e.target.value}`; });
  document.querySelector("#chapterSearch").addEventListener("input", debounce((e) => { state.chapterSearch = e.target.value; state.chapterOffset = 0; persistChapterState(novel.id); openChapters(novel.id); }, 250));
  document.querySelector("#chapterView").addEventListener("change", (e) => { state.chapterView = e.target.value; state.chapterOffset = 0; persistChapterState(novel.id); openChapters(novel.id); });
  document.querySelector("#prevPage").addEventListener("click", () => { state.chapterOffset = Math.max(0, state.chapterOffset - state.pageSize); persistChapterState(novel.id); openChapters(novel.id); });
  document.querySelector("#nextPage").addEventListener("click", () => { state.chapterOffset += state.pageSize; persistChapterState(novel.id); openChapters(novel.id); });
  bindCopyLinks(app);
  restoreScrollPosition();
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
    const source = ["ai", "reference", "original"].includes(requestedSource) ? requestedSource : preferredSource(chapter);
    state.source = source;
    localStorage.setItem("gt-reader-source", source);
    const payload = await cachedApi(chapterTextPath(novelId, chapterNumber, source), 120_000);
    renderReader(novelId, chapterNumber, source, payload);
    prefetchNeighborChapters(novelId, chapterNumber, source);
  } catch (error) {
    setError(error.message);
  }
}

function renderReader(novelId, chapterNumber, source, payload) {
  const previous = neighborChapter(chapterNumber, -1);
  const next = neighborChapter(chapterNumber, 1);
  rememberRecent("chapters", {novel_id: novelId, chapter_number: chapterNumber, source, label: `Chapter ${chapterNumber}`, href: `#/reader/${encodeURIComponent(novelId)}/${chapterNumber}/${source}`, at: new Date().toISOString()});
  document.documentElement.style.setProperty("--reader-font", `${state.fontSize}px`);
  document.body.dataset.zen = state.zen ? "on" : "off";
  app.innerHTML = `
    <section class="reader-panel ${state.zen ? "zen" : ""}">
      <div class="reader-nav"><a class="button" href="#/chapters/${novelId}">Back to Chapters</a><a class="button" href="#/novel/${novelId}">Novel</a><a class="button" href="#/library">Library</a><div class="spacer"></div><button data-go="${previous || ""}" ${previous ? "" : "disabled"}>Previous</button><select id="chapterPicker">${state.chapters.map((c) => `<option value="${c.chapter_number}" ${c.chapter_number === chapterNumber ? "selected" : ""}>Chapter ${c.chapter_number}</option>`).join("")}</select><button data-go="${next || ""}" ${next ? "" : "disabled"}>Next</button></div>
      <div class="reader-tabs">${["ai", "reference", "original"].map((item) => `<button data-source="${item}" class="${item === source ? "active" : ""}">${sourceLabels[item]}</button>`).join("")}<button id="bookmarkChapter" type="button">Bookmark</button><button type="button" data-copy-link="#/reader/${encodeURIComponent(novelId)}/${chapterNumber}/${source}">Copy Link</button><button id="zenToggle" type="button">${state.zen ? "Exit Zen" : "Zen"}</button><a class="button" href="#/settings/reader">Reader Settings</a><label>Font <input id="fontSize" type="range" min="16" max="25" value="${state.fontSize}"></label></div>
      <header class="reader-heading"><span>${sourceLabels[source]}</span><h1>Chapter ${chapterNumber}</h1><p>${escapeHtml(payload.title || `Chapter ${chapterNumber}`)}</p></header>
      <article class="reader-text">${renderReaderText(payload, source)}</article>
      <div class="reader-bottom"><button data-go="${previous || ""}" ${previous ? "" : "disabled"}>Previous Chapter</button><button data-go="${next || ""}" ${next ? "" : "disabled"}>Next Chapter</button></div>
    </section>`;
  document.querySelectorAll("[data-go]").forEach((button) => button.addEventListener("click", () => { if (button.dataset.go) window.location.hash = `#/reader/${novelId}/${button.dataset.go}/${state.source}`; }));
  document.querySelector("#chapterPicker").addEventListener("change", (event) => { window.location.hash = `#/reader/${novelId}/${event.target.value}/${state.source}`; });
  document.querySelectorAll("[data-source]").forEach((button) => button.addEventListener("click", () => { window.location.hash = `#/reader/${novelId}/${chapterNumber}/${button.dataset.source}`; }));
  document.querySelector("#fontSize").addEventListener("input", (event) => { state.fontSize = Number(event.target.value); localStorage.setItem("gt-reader-font", String(state.fontSize)); document.documentElement.style.setProperty("--reader-font", `${state.fontSize}px`); });
  document.querySelector("#bookmarkChapter").addEventListener("click", () => saveBookmark(novelId, chapterNumber));
  document.querySelector("#zenToggle").addEventListener("click", () => { state.zen = !state.zen; renderReader(novelId, chapterNumber, source, payload); });
  bindCopyLinks(app);
  bindReaderProgress(novelId, chapterNumber, source);
  restoreReaderScroll(novelId, chapterNumber, source);
}

function renderReaderText(payload, source) {
  if (!payload.ok) return `<div class="empty-state">${escapeHtml(sourceLabels[source])} is not available for this chapter.</div>`;
  return paragraphs(payload.text).map((line) => `<p>${escapeHtml(line)}</p>`).join("");
}

async function saveBookmark(novelId, chapterNumber) {
  if (!state.account) return toast("Sign in to save bookmarks.");
  const note = prompt("Bookmark note (optional)") || "";
  await api("/api/account/bookmarks", {method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify({novel_id: novelId, chapter_number: chapterNumber, note})});
  await loadPersonalHome(true);
  toast("Bookmark saved.");
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
    app.innerHTML = `${pageHeader("Reading History", "Your recent GodTranslator reading sessions.", [["Items", payload.history.length]])}
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
    const [jobs, modelRegistry] = await Promise.all([
      api(`/api/translation/jobs?novel_id=${encodeURIComponent(novelId)}`),
      api("/api/models"),
    ]);
    const novel = state.novels.find((item) => item.id === novelId) || {};
    const models = modelRegistry.models || [];
    const draft = translateDraft(novelId);
    const form = params.get("chapter") ? {...draft, selection_mode: "specific", chapters: params.get("chapter"), all_untranslated: false} : draft;
    const mode = form.translation_mode || "simple";
    const selectionMode = form.selection_mode || (form.all_untranslated ? "all-untranslated" : "next-untranslated");
    const speedPreset = form.speed_preset || (mode === "economy" ? "careful" : "balanced");
    app.innerHTML = `
      ${pageHeader("Translate", "Plan controlled translation jobs from Original text, with Reference as optional guidance.", [["Novel", novel.title || novelId], ["Default model", novel.model || "gpt-4o-mini"]])}
      <section class="draft-bar"><span id="draftStatus">${draft.saved_at ? `Draft saved ${timeAgo(draft.saved_at)}` : "No saved draft"}</span><div class="actions"><button id="restoreTranslateDraft" type="button" ${draft.saved_at ? "" : "disabled"}>Restore Draft</button><button id="discardTranslateDraft" type="button" ${draft.saved_at ? "" : "disabled"}>Discard Draft</button></div></section>
      <section class="translate-workspace">
        <div class="translate-steps" id="translateForm">
          <section class="panel form-grid"><h2>1. Mode & Chapters</h2><label>Mode<select id="translationMode"><option value="simple" ${mode === "simple" ? "selected" : ""}>Simple</option><option value="fast" ${mode === "fast" ? "selected" : ""}>Fast</option><option value="advanced" ${mode === "advanced" ? "selected" : ""}>Advanced</option><option value="economy" ${mode === "economy" ? "selected" : ""}>Economy / Overnight</option></select></label><label>Novel<select id="translateNovel">${state.novels.map((n) => `<option value="${n.id}" ${n.id === novelId ? "selected" : ""}>${escapeHtml(n.title)}</option>`).join("")}</select></label><label>What to translate<select id="selectionMode"><option value="next-untranslated" ${selectionMode === "next-untranslated" ? "selected" : ""}>Next untranslated chapters</option><option value="specific" ${selectionMode === "specific" ? "selected" : ""}>Specific chapters</option><option value="all-untranslated" ${selectionMode === "all-untranslated" ? "selected" : ""}>All untranslated</option></select></label><label id="nextCountLabel">Next count<select id="nextCount"><option value="25" ${Number(form.next_count || 25) === 25 ? "selected" : ""}>Next 25</option><option value="50" ${Number(form.next_count) === 50 ? "selected" : ""}>Next 50</option><option value="100" ${Number(form.next_count) === 100 ? "selected" : ""}>Next 100</option></select></label><label id="chapterInputLabel">Chapters<input id="translateChapters" value="${escapeAttr(form.chapters || "")}" placeholder="26,53,60-70"><span class="field-error" id="chapterError"></span></label><p class="muted wide" id="chapterPreview">Choose what to translate.</p></section>
          <section class="panel form-grid"><h2>2. Translation Profile</h2><label>Profile<select id="profile"><option ${form.profile === "Default literary translation" ? "selected" : ""}>Default literary translation</option><option ${form.profile === "Reference-guided polish" ? "selected" : ""}>Reference-guided polish</option></select></label><label class="wide">Style guide<textarea id="styleGuide" rows="3">${escapeHtml(form.style_guide || "")}</textarea></label><label class="wide">Glossary notes<textarea id="glossary" rows="3">${escapeHtml(form.glossary || "")}</textarea></label></section>
          <section class="panel form-grid"><h2>3. Speed & Model</h2><label>Speed preset<select id="speedPreset"><option value="careful" ${speedPreset === "careful" ? "selected" : ""}>Careful - lowest pressure</option><option value="balanced" ${speedPreset === "balanced" ? "selected" : ""}>Balanced - recommended</option><option value="fast" ${speedPreset === "fast" ? "selected" : ""}>Fast - higher parallel processing</option><option value="maximum-safe" ${speedPreset === "maximum-safe" ? "selected" : ""}>Maximum Safe - highest safe throughput</option></select></label><label>Model<select id="model">${models.map((model) => `<option value="${escapeAttr(model.id)}" ${model.id === (form.model || novel.model || "gpt-4o-mini") ? "selected" : ""}>${escapeHtml(model.display_name)} · ${escapeHtml(model.pricing?.note || "Pricing not configured")}</option>`).join("")}</select></label><label><input id="autoOptimizeSpeed" type="checkbox" ${form.auto_optimize_speed === false ? "" : "checked"}> Auto Optimize Speed</label><p class="muted wide" id="speedDescription">Speed is being optimized automatically.</p></section>
          <section class="panel form-grid"><h2>4. Budget & Safety</h2><label>Max total budget<input id="maxTotalBudget" type="number" step="0.01" value="${escapeAttr(form.max_total_budget ?? "")}"><span class="field-error" id="budgetError"></span></label><label>Max cost per chapter<input id="maxPerChapterBudget" type="number" step="0.001" value="${escapeAttr(form.max_per_chapter_budget ?? "")}"></label><label><input id="useReference" type="checkbox" ${form.use_reference === false ? "" : "checked"}> Use Reference when available</label><label><input id="onlyUntranslated" type="checkbox" ${form.only_untranslated === false ? "" : "checked"}> Only untranslated</label><div class="advanced-settings wide"><h3>Advanced Performance</h3><div class="form-grid"><label>Retry limit<input id="retryCount" type="number" min="0" max="5" value="${escapeAttr(form.retry_count ?? 2)}"></label><label>Queue depth<input id="batchSize" type="number" min="1" max="5000" value="${escapeAttr(form.batch_size ?? 25)}"></label><label>Maximum workers<select id="translationConcurrency"><option value="" ${form.concurrency ? "" : "selected"}>Auto</option><option value="1" ${Number(form.concurrency) === 1 ? "selected" : ""}>1 worker</option><option value="2" ${Number(form.concurrency) === 2 ? "selected" : ""}>2 workers</option><option value="3" ${Number(form.concurrency) === 3 ? "selected" : ""}>3 workers</option><option value="4" ${Number(form.concurrency) === 4 ? "selected" : ""}>4 workers</option><option value="6" ${Number(form.concurrency) === 6 ? "selected" : ""}>6 workers</option><option value="8" ${Number(form.concurrency) === 8 ? "selected" : ""}>8 workers</option></select></label><label>Priority<select id="jobPriority"><option value="normal" ${form.priority === "high" ? "" : "selected"}>Normal</option><option value="high" ${form.priority === "high" ? "selected" : ""}>High</option></select></label><label><input id="stopOnBudget" type="checkbox" ${form.stop_on_budget === false ? "" : "checked"}> Stop on budget</label></div></div></section>
        </div>
        <aside class="estimate-panel"><h2>5. Estimate</h2><section id="estimateResult"><p class="muted">Run an estimate before creating a job. Estimates are approximate.</p></section><div class="actions"><button id="estimateBtn" class="primary">Estimate</button><button id="createJobBtn">Launch Job</button></div></aside>
      </section>
      <section class="table-card"><h2>Recent Jobs</h2>${renderJobsTable(jobs.jobs || [])}</section>`;
    document.querySelector("#translateNovel").addEventListener("change", (e) => { window.location.hash = `#/translate/${e.target.value}`; });
    document.querySelector("#translateChapters").addEventListener("input", renderChapterPreview);
    document.querySelector("#selectionMode").addEventListener("change", renderChapterPreview);
    document.querySelector("#nextCount").addEventListener("change", renderChapterPreview);
    document.querySelector("#translationMode").addEventListener("change", toggleTranslationMode);
    document.querySelector("#speedPreset").addEventListener("change", updateSpeedDescription);
    document.querySelector("#autoOptimizeSpeed").addEventListener("change", updateSpeedDescription);
    document.querySelector("#estimateBtn").addEventListener("click", estimateTranslation);
    document.querySelector("#createJobBtn").addEventListener("click", createTranslationJob);
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

function translatePayload() {
  const selectionMode = document.querySelector("#selectionMode").value;
  return {
    novel_id: document.querySelector("#translateNovel").value,
    translation_mode: document.querySelector("#translationMode").value,
    speed_preset: document.querySelector("#speedPreset").value,
    auto_optimize_speed: document.querySelector("#autoOptimizeSpeed").checked,
    selection_mode: selectionMode,
    next_count: numberOrNull("#nextCount"),
    chapters: document.querySelector("#translateChapters").value,
    all_untranslated: selectionMode === "all-untranslated",
    model: document.querySelector("#model").value || "gpt-4o-mini",
    max_total_budget: numberOrNull("#maxTotalBudget"),
    max_per_chapter_budget: numberOrNull("#maxPerChapterBudget"),
    retry_count: numberOrNull("#retryCount"),
    batch_size: numberOrNull("#batchSize"),
    concurrency: numberOrNull("#translationConcurrency"),
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
  if (chapterLabel) chapterLabel.hidden = mode !== "specific";
  if (nextLabel) nextLabel.hidden = mode !== "next-untranslated";
  if (mode === "all-untranslated") {
    target.textContent = "Preview: all chapters with readable Original text and missing AI translation.";
    return;
  }
  if (mode === "next-untranslated") {
    target.textContent = `Preview: next ${document.querySelector("#nextCount")?.value || 25} untranslated chapters will be selected from the database when the job is created.`;
    validateTranslateForm();
    return;
  }
  const parsed = parseChapterInput(document.querySelector("#translateChapters")?.value || "");
  validateTranslateForm();
  target.textContent = parsed.length
    ? `Preview: ${parsed.length} chapter${parsed.length === 1 ? "" : "s"} selected (${parsed.slice(0, 12).join(", ")}${parsed.length > 12 ? ", ..." : ""}).`
    : "Enter chapters like 26,53,60-70.";
}

function parseChapterInput(value) {
  const chapters = new Set();
  String(value || "").split(",").map((item) => item.trim()).filter(Boolean).forEach((part) => {
    if (/^\d+\s*-\s*\d+$/.test(part)) {
      const [a, b] = part.split("-").map((item) => Number(item.trim()));
      for (let i = Math.min(a, b); i <= Math.max(a, b); i += 1) chapters.add(i);
    } else if (/^\d+$/.test(part)) {
      chapters.add(Number(part));
    }
  });
  return [...chapters].sort((a, b) => a - b);
}

function toggleTranslationMode() {
  const mode = document.querySelector("#translationMode")?.value || "simple";
  const advanced = document.querySelector(".advanced-settings");
  const speedPreset = document.querySelector("#speedPreset");
  if (advanced) advanced.hidden = mode !== "advanced";
  if (speedPreset && mode === "economy") speedPreset.value = "careful";
  if (speedPreset && mode === "fast" && speedPreset.value === "careful") speedPreset.value = "fast";
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
  };
  const suffix = auto ? " Speed is being optimized automatically." : " Auto optimization is off for this job.";
  const economy = mode === "economy" ? " Economy / Overnight prioritizes low pressure and is not intended for immediate completion. " : "";
  const target = document.querySelector("#speedDescription");
  if (target) target.textContent = `${economy}${descriptions[preset] || descriptions.balanced}${suffix}`;
}

async function estimateTranslation(event) {
  event.preventDefault();
  if (!validateTranslateForm()) return toast("Fix the highlighted fields first.");
  const estimate = await api("/api/translation/estimate", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(translatePayload())});
  state.lastEstimate = estimate;
  document.querySelector("#estimateResult").innerHTML = `<div class="metric-grid">${metric("Selected", estimate.selected_count)}${metric("Eligible", estimate.eligible_count)}${metric("Speed mode", titleCase(estimate.speed_preset || "balanced"))}${metric("Expected workers", estimate.expected_workers || 1)}${metric("Approx duration", durationEstimateText(estimate.duration_estimate))}${metric("Approx cost", `$${Number(estimate.estimated_cost || 0).toFixed(4)}`)}</div><p class="muted">${escapeHtml(estimate.pricing_note)} ${estimate.auto_optimize_speed ? "Speed is being optimized automatically." : ""}</p>`;
}

async function createTranslationJob(event) {
  event.preventDefault();
  if (!validateTranslateForm()) return toast("Fix the highlighted fields first.");
  if (!state.lastEstimate) return toast("Run an estimate before creating a job.");
  const created = await api("/api/translation/jobs", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(translatePayload())});
  localStorage.removeItem(translateDraftKey(created.job.novel_id));
  rememberRecent("jobs", {id: created.job.id, label: `Job ${created.job.id.slice(0, 8)}`, href: "#/jobs", at: new Date().toISOString()});
  toast(`Job ${created.job.id.slice(0, 8)} started.`);
  window.location.hash = "#/jobs";
}

function renderJobsTable(jobs, focusedJobId = "") {
  return `<table class="responsive-table"><thead><tr><th>Job</th><th>Status</th><th>Progress</th><th>Activity</th><th>Budget</th><th>Actions</th></tr></thead><tbody>${jobs.map((job) => `<tr class="${focusedJobId === job.id ? "selected-row" : ""}"><td data-label="Job"><a href="#/jobs/${job.id}">${job.id.slice(0, 8)}</a><br><span>${escapeHtml(job.model || "")}</span></td><td data-label="Status">${statusBadge(job.status)}<br><span>${timeAgo(job.updated_at)}</span></td><td data-label="Progress">${job.completed_items || 0}/${job.total_items || 0}<br><span>failed ${job.failed_items || 0}</span></td><td data-label="Activity">${jobActivityText(job)}</td><td data-label="Budget">$${Number(job.actual_cost || 0).toFixed(4)} / $${Number(job.estimated_cost || 0).toFixed(4)}</td><td data-label="Actions" class="row-actions">${jobActions(job)}<button type="button" data-copy-link="#/jobs/${job.id}">Copy Link</button></td></tr>`).join("") || `<tr><td colspan="6">No translation jobs yet.</td></tr>`}</tbody></table>`;
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

async function openCompare(novelId, chapterNumber) {
  if (!canTranslate()) return openSettings("account");
  setLoading("Loading comparison...");
  try {
    const payload = await api(`/api/novels/${encodeURIComponent(novelId)}/compare/${chapterNumber}`);
    app.innerHTML = `${pageHeader("Compare", "Inspect Original, Reference, and AI text side by side.", [["Chapter", chapterNumber]])}
      <section class="compare-grid">
        ${renderComparePanel("Original", payload.original)}
        ${renderComparePanel("Reference", payload.reference)}
        ${renderComparePanel("AI Translation", payload.ai)}
      </section>
      <div class="actions"><a class="button" href="#/reader/${novelId}/${chapterNumber}/ai">Open Reader</a><a class="button" href="#/chapters/${novelId}">Back to Chapters</a></div>`;
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
      ${state.admin ? `<form class="panel" id="recoveryForm"><h2>Upload GodTranslator Pack or TXT/ZIP</h2><input id="recoveryFiles" type="file" multiple accept=".zip,.txt"><button class="primary">Preview Upload</button></form>` : adminNotice()}
      <section id="recoveryPreview"></section>`;
    document.querySelector("#recoveryForm")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = new FormData();
      Array.from(document.querySelector("#recoveryFiles").files).forEach((file) => form.append("files", file));
      const preview = await api(`/api/novels/${novelId}/recovery/preview`, {method: "POST", body: form, headers: {}});
      document.querySelector("#recoveryPreview").innerHTML = renderRecoveryPreview(preview, novelId);
      document.querySelector("#applyImport")?.addEventListener("click", async () => {
        const result = await api(`/api/novels/${novelId}/recovery/import/${preview.job_id}`, {method: "POST"});
        alert(`Imported ${result.imported_count} Reference chapters.`);
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
  setLoading("Loading admin...");
  await refreshSession();
  if (!state.admin) return renderAdminGate("Admin");
  try {
    rememberRecent("admin", {label: titleCase(tab), href: `#/admin/${tab}`, at: new Date().toISOString()});
    localStorage.setItem("gt-last-admin-tab", tab);
    const [overview, dbHealth, missing, imports, jobs] = await Promise.all([
      api("/api/admin/overview"),
      api("/api/admin/db-health"),
      api(`/api/admin/missing/${state.currentNovelId}`),
      api(`/api/import-jobs?novel_id=${state.currentNovelId}`),
      api(`/api/translation/jobs?novel_id=${state.currentNovelId}`),
    ]);
    const tabs = [["overview", "Overview"], ["database", "Database"], ["jobs", "Translation Jobs"], ["imports", "Import Jobs"], ["missing", "Missing Data"], ["backups", "Backups"], ["diagnostics", "Diagnostics"]];
    app.innerHTML = `
      ${pageHeader("Admin", "Operational view for database health, jobs, imports, missing data, and exports.", [["Version", APP_VERSION], ["Schema", overview.overview.schema], ["Chapters", overview.overview.chapters], ["Needs Translation", overview.overview.needs_translation]])}
      <nav class="admin-tabs">${tabs.map(([key, label]) => `<a class="${tab === key ? "active" : ""}" href="#/admin/${key}">${label}</a>`).join("")}</nav>
      ${renderAdminTab(tab, overview, dbHealth, missing, imports, jobs)}
      <div class="actions"><button id="logoutBtn">Logout</button><a class="button" href="#/recovery/${state.currentNovelId}">Open Recovery</a></div>`;
    bindJobButtons();
    bindCopyLinks(app);
    document.querySelector("#logoutBtn").addEventListener("click", async () => { await api("/api/admin/logout", {method: "POST"}); state.admin = false; openAdmin(); });
    restoreScrollPosition();
  } catch (error) {
    setError(error.message);
  }
}

function renderAdminTab(tab, overview, dbHealth, missing, imports, jobs) {
  const data = overview.overview || {};
  if (tab === "database") {
    return `<section class="dashboard-grid"><div class="panel">${metric("Database", dbHealth.health?.ok === false ? "Unhealthy" : "Connected")}${metric("Schema", data.schema)}${metric("Expected Tables", "Healthy")}${metric("Chapters", data.chapters)}</div><div class="panel"><h2>Technical Details</h2><details><summary>Show details</summary><pre>${escapeHtml(JSON.stringify(dbHealth.health, null, 2))}</pre></details></div></section>`;
  }
  if (tab === "jobs") return `<section class="table-card"><h2>Translation Jobs</h2>${renderJobsTable(jobs.jobs || [])}</section>`;
  if (tab === "imports") return `<section class="table-card"><h2>Import Jobs</h2><table><thead><tr><th>Job</th><th>Mode</th><th>Status</th><th>Updated</th></tr></thead><tbody>${(imports.jobs || []).map((job) => `<tr><td>${job.id.slice(0, 8)}</td><td>${escapeHtml(job.target_mode)}</td><td>${escapeHtml(job.status)}</td><td>${escapeHtml(job.updated_at)}</td></tr>`).join("") || `<tr><td colspan="4">No import jobs.</td></tr>`}</tbody></table></section>`;
  if (tab === "missing") return `<section class="dashboard-grid"><div class="panel"><h2>Missing Data</h2><p class="muted">Reference range: ${escapeHtml(missing.missing.reference_target_range?.start ?? "all")} - ${escapeHtml(missing.missing.reference_target_range?.end ?? "all")}</p>${recoveryList("Missing Original", missing.missing.missing_original)}${recoveryList("Missing Reference", missing.missing.missing_reference)}</div><div class="panel"><h2>Recovery</h2><p>Expected I Am God missing Reference is Chapter 362 only after the target range fix.</p><a class="button" href="#/recovery/${state.currentNovelId}">Open Recovery</a></div></section>`;
  if (tab === "backups") return `<section class="dashboard-grid"><div class="panel"><h2>Backup & Export</h2><p class="muted">Exports a versioned ZIP from PostgreSQL. Secrets, database URLs, passwords, and Auth tokens are never included.</p><a class="button primary" href="/api/novels/${state.currentNovelId}/backup">Export Novel Backup</a></div><div class="panel"><h2>Contents</h2><p>Novel metadata, chapters, translation jobs, and import metadata from the v10 database source of truth.</p></div></section>`;
  if (tab === "diagnostics") return `<section class="dashboard-grid"><div class="panel">${metric("Version", APP_VERSION)}${metric("DB", dbHealth.health?.ok === false ? "Unhealthy" : "Healthy")}${metric("Schema", data.schema)}${metric("Auth", state.authConfig?.configured ? "Configured" : "Missing")}${metric("OpenAI", "Configured/Missing hidden")}</div><div class="panel"><h2>Details</h2><details><summary>Show sanitized JSON</summary><pre>${escapeHtml(JSON.stringify({overview: data, db: dbHealth.health}, null, 2))}</pre></details></div></section>`;
  return `<section class="dashboard-grid"><div class="panel">${metric("Application", "GodTranslator")}${metric("Database", dbHealth.health?.ok === false ? "Unhealthy" : "Connected")}${metric("Novels", data.novels)}${metric("Chapters", data.chapters)}</div><div class="panel">${metric("Original", data.original)}${metric("Reference", data.reference)}${metric("AI", data.ai)}${metric("Needs Translation", data.needs_translation)}</div><div class="panel">${metric("Active Jobs", (jobs.jobs || []).filter((job) => ["queued", "running", "paused"].includes(job.status)).length)}${metric("Recent Errors", (jobs.jobs || []).filter((job) => job.error).length)}<a class="button" href="#/admin/jobs">Open Jobs</a></div></section>`;
}

function openSettings(section = "appearance", intent = "") {
  const pref = state.preferences;
  app.innerHTML = `
    ${pageHeader("Settings", "Personalize GodTranslator for reading, focus, and everyday use.", [["Theme", pref.theme], ["Density", pref.density], ["Motion", pref.reduceMotion ? "Reduced" : "Standard"]])}
    <section class="settings-layout">
      <nav class="settings-nav">
        <a class="${section === "appearance" ? "active" : ""}" href="#/settings/appearance">Appearance</a>
        <a class="${section === "reader" ? "active" : ""}" href="#/settings/reader">Reader</a>
        <a class="${section === "account" ? "active" : ""}" href="#/settings/account">Account</a>
      </nav>
      ${section === "reader" ? renderReaderSettings(pref) : section === "account" ? renderAccountSettings(intent) : renderAppearanceSettings(pref)}
    </section>`;
  document.querySelectorAll("[data-pref]").forEach((field) => field.addEventListener("input", savePreferenceFromField));
  if (section === "account") bindAccountControls();
  document.querySelector("#resetPrefs")?.addEventListener("click", () => {
    state.preferences = defaultPreferences();
    localStorage.setItem("gt-preferences", JSON.stringify(state.preferences));
    applyPreferences();
    openSettings(section);
    toast("Preferences reset.");
  });
}

function renderAppearanceSettings(pref) {
  return `<section class="panel form-grid">
    <h2>Appearance</h2>
    <label>Theme<select data-pref="theme">${["obsidian", "forest", "midnight", "warm-dark", "light"].map((item) => `<option value="${item}" ${pref.theme === item ? "selected" : ""}>${titleCase(item)}</option>`).join("")}</select></label>
    <label>Accent<select data-pref="accent">${["green", "teal", "blue", "purple", "amber"].map((item) => `<option value="${item}" ${pref.accent === item ? "selected" : ""}>${titleCase(item)}</option>`).join("")}</select></label>
    <label>Density<select data-pref="density">${["compact", "comfortable", "spacious"].map((item) => `<option value="${item}" ${pref.density === item ? "selected" : ""}>${titleCase(item)}</option>`).join("")}</select></label>
    <label>Card size<select data-pref="cardSize">${["compact", "standard", "large"].map((item) => `<option value="${item}" ${pref.cardSize === item ? "selected" : ""}>${titleCase(item)}</option>`).join("")}</select></label>
    <label><input data-pref="reduceMotion" type="checkbox" ${pref.reduceMotion ? "checked" : ""}> Reduce motion</label>
    <label><input data-pref="interfaceBlur" type="checkbox" ${pref.interfaceBlur ? "checked" : ""}> Interface blur</label>
    <div class="actions wide"><button id="resetPrefs" type="button">Reset to defaults</button></div>
  </section>`;
}

function renderReaderSettings(pref) {
  return `<section class="panel form-grid">
    <h2>Reader</h2>
    <label>Font family<select data-pref="readerFont">${["serif", "sans", "system"].map((item) => `<option value="${item}" ${pref.readerFont === item ? "selected" : ""}>${titleCase(item)}</option>`).join("")}</select></label>
    <label>Line height<input data-pref="readerLineHeight" type="range" min="1.55" max="2.15" step="0.05" value="${pref.readerLineHeight}"></label>
    <label>Paragraph spacing<input data-pref="paragraphSpacing" type="range" min="0.7" max="1.8" step="0.1" value="${pref.paragraphSpacing}"></label>
    <label>Reading width<input data-pref="readingWidth" type="range" min="680" max="1080" step="20" value="${pref.readingWidth}"></label>
    <label>Reader tone<select data-pref="readerTone">${["obsidian", "paper", "sepia", "midnight", "forest"].map((item) => `<option value="${item}" ${pref.readerTone === item ? "selected" : ""}>${titleCase(item)}</option>`).join("")}</select></label>
    <label>Text align<select data-pref="textAlign">${["left", "justify"].map((item) => `<option value="${item}" ${pref.textAlign === item ? "selected" : ""}>${titleCase(item)}</option>`).join("")}</select></label>
    <div class="actions wide"><button id="resetPrefs" type="button">Reset to defaults</button></div>
  </section>`;
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
        <a class="button" href="#/library">Continue Reading</a>
        <a class="button" href="#/bookmarks">Bookmarks</a>
        <a class="button" href="#/history">History</a>
        <a class="button" href="#/settings/appearance">Personalization</a>
      </div>
      ${renderRecentAccountLinks()}
      <div class="actions"><button id="signOutBtn" type="button">Sign Out</button><a class="button" href="#/admin">Admin Login</a></div>
    </section>`;
  }
  const configured = Boolean(state.authConfig?.configured && state.supabaseClient);
  const title = intent === "signup" ? "Create Account" : intent === "forgot-password" || intent === "reset-password" ? "Reset Password" : "Sign In";
  return `<section class="panel account-panel">
    <h2>${title}</h2>
    ${configured ? "" : `<p class="empty-state">Account features are not configured. Public reading and local personalization still work.</p>`}
    <form id="authForm" class="form-grid">
      <label>Email<input id="authEmail" type="email" autocomplete="email" ${configured ? "" : "disabled"}></label>
      <label>Password<input id="authPassword" type="password" autocomplete="current-password" ${configured ? "" : "disabled"}></label>
      <div class="actions wide">
        <button class="primary" id="signInBtn" type="button" ${configured ? "" : "disabled"}>Sign In</button>
        <button id="signUpBtn" type="button" ${configured ? "" : "disabled"}>Create Account</button>
        <button id="forgotBtn" type="button" ${configured ? "" : "disabled"}>Forgot Password</button>
        <button id="googleBtn" type="button" ${configured ? "" : "disabled"}>Continue with Google</button>
      </div>
    </form>
    <div class="actions"><a class="button" href="#/admin">Emergency Admin Login</a><a class="button" href="#/library">Back to Library</a></div>
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
      alert(error.message);
    }
  });
}

function adminNotice() {
  return `<section class="panel"><h2>Admin required</h2><p class="muted">Log in to manage data or run protected operations.</p><a class="button" href="#/admin">Admin Login</a></section>`;
}

function pageHeader(title, subtitle, stats = []) {
  return `${renderBreadcrumbs()}<section class="page-header"><div><p class="eyebrow">GodTranslator</p><h1>${escapeHtml(title)}</h1><p>${escapeHtml(subtitle)}</p></div>${stats.length ? `<div class="stats">${stats.map(([label, value]) => metric(label, value)).join("")}</div>` : ""}</section>`;
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
  const crumbs = breadcrumbsForHash(window.location.hash || "#/library");
  if (crumbs.length < 2) return "";
  return `<nav class="breadcrumbs" aria-label="Breadcrumbs">${crumbs.map((item, index) => index === crumbs.length - 1 ? `<span>${escapeHtml(item.label)}</span>` : `<a href="${escapeAttr(item.href)}">${escapeHtml(item.label)}</a>`).join("<span>/</span>")}</nav>`;
}

function breadcrumbsForHash(hash) {
  const [path] = String(hash || "#/library").replace(/^#\/?/, "").split("?");
  const parts = path.split("/").filter(Boolean);
  const novelId = parts[1] || state.currentNovelId;
  const novel = state.novels.find((item) => item.id === novelId);
  const novelLabel = novel?.title || novelId || "Novel";
  const root = [{label: "Home", href: "#/library"}];
  if (!parts.length || parts[0] === "library") return root;
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
  const ok = ["completed", "running", "queued"].includes(status);
  return `<span class="badge ${ok ? "ok" : status === "failed" ? "missing" : ""}">${escapeHtml(status || "unknown")}</span>`;
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

function chapterTextPath(novelId, chapterNumber, source) {
  return `/api/novels/${encodeURIComponent(novelId)}/chapters/${chapterNumber}/${source}`;
}

function prefetchNeighborChapters(novelId, chapterNumber, source) {
  [neighborChapter(chapterNumber, -1), neighborChapter(chapterNumber, 1)]
    .filter(Boolean)
    .forEach((chapter) => cachedApi(chapterTextPath(novelId, chapter, source), 120_000).catch(() => {}));
}

function bindReaderProgress(novelId, chapterNumber, source) {
  if (readerScrollHandler) window.removeEventListener("scroll", readerScrollHandler);
  readerScrollHandler = debounce(() => {
    const percent = readerScrollPercent();
    localStorage.setItem(readerScrollKey(novelId, chapterNumber, source), String(percent));
    saveProgressDebounced(novelId, chapterNumber, source, percent);
  }, 700);
  window.addEventListener("scroll", readerScrollHandler, {passive: true});
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
  const budgetError = document.querySelector("#budgetError");
  const estimateButton = document.querySelector("#estimateBtn");
  const createButton = document.querySelector("#createJobBtn");
  if (!chaptersInput || !chapterError || !budgetError) return true;
  const raw = chaptersInput.value.trim();
  const parsed = parseChapterInput(raw);
  const invalidChapter = selectionMode === "specific" && (!raw || parsed.length === 0 || /[^\d,\-\s]/.test(raw));
  const total = numberOrNull("#maxTotalBudget");
  const per = numberOrNull("#maxPerChapterBudget");
  const invalidBudget = total !== null && per !== null && per > total;
  chapterError.textContent = invalidChapter ? "Enter chapters like 26,53,60-70 or choose all untranslated." : "";
  budgetError.textContent = invalidBudget ? "Per-chapter budget cannot exceed total budget." : "";
  const valid = !invalidChapter && !invalidBudget;
  if (estimateButton) estimateButton.disabled = !valid;
  if (createButton) createButton.disabled = !valid;
  return valid;
}

function preferredSource(chapter) {
  if (chapter?.has_ai) return "ai";
  if (chapter?.has_reference) return "reference";
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
  const original = Number(novel.original_count || 0);
  return original ? Math.round(Number(novel.ai_count || 0) / original * 100) : 0;
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

function formatDuration(seconds) {
  const value = Number(seconds || 0);
  if (!value) return "unknown";
  if (value < 60) return `${Math.round(value)} sec`;
  if (value < 3600) return `${Math.round(value / 60)} min`;
  return `${Math.round(value / 3600)} hr`;
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

function numberOrNull(selector) {
  const field = document.querySelector(selector);
  const value = field?.value;
  if (value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function readStored(key, fallback) {
  try {
    return {...fallback, ...JSON.parse(localStorage.getItem(key) || "{}")};
  } catch {
    return fallback;
  }
}

function writeStored(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}

function rememberRecent(type, item) {
  const list = state.recent[type] || [];
  const key = item.id || item.href || item.label;
  state.recent[type] = [item, ...list.filter((existing) => (existing.id || existing.href || existing.label) !== key)].slice(0, 8);
  writeStored("gt-recent", state.recent);
}

function bindCopyLinks(root = document) {
  root.querySelectorAll("[data-copy-link]").forEach((button) => {
    if (button.dataset.copyBound) return;
    button.dataset.copyBound = "1";
    button.addEventListener("click", () => copyLink(button.dataset.copyLink));
  });
}

async function copyLink(hash) {
  const url = new URL(hash || window.location.hash || "#/library", window.location.href).toString();
  try {
    await navigator.clipboard.writeText(url);
    toast("Link copied.");
  } catch {
    window.prompt("Copy link", url);
  }
}

function saveScrollPosition() {
  if (!activeRouteKey) return;
  sessionStorage.setItem(`gt-scroll:${activeRouteKey}`, String(window.scrollY || 0));
}

function restoreScrollPosition(key = window.location.hash || "#/library") {
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
    reduceMotion: false,
    interfaceBlur: true,
    readerFont: "serif",
    readerLineHeight: 1.8,
    paragraphSpacing: 1.2,
    readingWidth: 900,
    readerTone: "obsidian",
    textAlign: "left",
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
  if (["readerLineHeight", "paragraphSpacing", "readingWidth"].includes(key)) value = Number(value);
  state.preferences[key] = value;
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

function bindAccountControls() {
  document.querySelector("#signInBtn")?.addEventListener("click", () => authEmailPassword("signIn"));
  document.querySelector("#signUpBtn")?.addEventListener("click", () => authEmailPassword("signUp"));
  document.querySelector("#forgotBtn")?.addEventListener("click", resetPassword);
  document.querySelector("#googleBtn")?.addEventListener("click", signInWithGoogle);
  document.querySelector("#signOutBtn")?.addEventListener("click", signOut);
}

async function authEmailPassword(mode) {
  if (!state.supabaseClient) return toast("Account features are not configured.");
  const email = document.querySelector("#authEmail")?.value;
  const password = document.querySelector("#authPassword")?.value;
  if (!email || !password) return toast("Enter email and password.");
  const result = mode === "signUp"
    ? await state.supabaseClient.auth.signUp({email, password})
    : await state.supabaseClient.auth.signInWithPassword({email, password});
  if (result.error) return toast(result.error.message);
  await refreshAccount();
  await refreshSession();
  openSettings("account");
  toast(mode === "signUp" ? "Check your email to confirm your account." : "Signed in.");
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
  state.admin = false;
  state.role = "guest";
  renderNav();
  openSettings("account");
  toast("Signed out.");
}

function applyPreferences() {
  const pref = state.preferences;
  document.body.dataset.theme = pref.theme;
  document.body.dataset.accent = pref.accent;
  document.body.dataset.density = pref.density;
  document.body.dataset.cardSize = pref.cardSize;
  document.body.dataset.motion = pref.reduceMotion ? "reduced" : "standard";
  document.body.dataset.blur = pref.interfaceBlur ? "on" : "off";
  document.documentElement.style.setProperty("--reader-line-height", String(pref.readerLineHeight));
  document.documentElement.style.setProperty("--reader-paragraph-spacing", `${pref.paragraphSpacing}em`);
  document.documentElement.style.setProperty("--reader-width", `${pref.readingWidth}px`);
  document.documentElement.style.setProperty("--reader-align", pref.textAlign);
  document.body.dataset.readerFont = pref.readerFont;
  document.body.dataset.readerTone = pref.readerTone;
}

function bindShellControls() {
  document.querySelector("#globalSearchBtn")?.addEventListener("click", openCommandPalette);
  document.querySelector("#personalizeBtn")?.addEventListener("click", () => { window.location.hash = "#/settings/appearance"; });
  document.querySelector("#jobCenterBtn")?.addEventListener("click", () => { window.location.hash = canTranslate() ? "#/jobs" : "#/settings/account"; });
  commandInput?.addEventListener("input", renderCommandResults);
  commandDialog?.addEventListener("close", () => { if (commandInput) commandInput.value = ""; });
  document.addEventListener("keydown", (event) => {
    const target = event.target;
    const typing = target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      openCommandPalette();
    }
    if (!typing && event.key === "?") {
      event.preventDefault();
      showShortcutHelp();
    }
    if (!typing && window.location.hash.startsWith("#/reader/")) {
      const parts = window.location.hash.replace(/^#\/?/, "").split("/");
      const novelId = parts[1];
      const chapter = Number(parts[2]);
      if (event.key === "+") adjustReaderFont(1);
      if (event.key === "-") adjustReaderFont(-1);
      if (event.key === "ArrowLeft") {
        const previous = neighborChapter(chapter, -1);
        if (previous) window.location.hash = `#/reader/${novelId}/${previous}/${state.source}`;
      }
      if (event.key === "ArrowRight") {
        const next = neighborChapter(chapter, 1);
        if (next) window.location.hash = `#/reader/${novelId}/${next}/${state.source}`;
      }
      if (event.key.toLowerCase() === "f") {
        state.zen = !state.zen;
        document.body.dataset.zen = state.zen ? "on" : "off";
        document.querySelector(".reader-panel")?.classList.toggle("zen", state.zen);
      }
      if (event.key.toLowerCase() === "b") saveBookmark(novelId, chapter);
    }
  });
}

function openCommandPalette() {
  if (!commandDialog || !commandInput) return;
  renderCommandResults();
  commandDialog.showModal();
  commandInput.focus();
}

function showShortcutHelp() {
  const existing = document.querySelector("#shortcutDialog");
  if (existing) existing.remove();
  const dialog = document.createElement("dialog");
  dialog.id = "shortcutDialog";
  dialog.className = "command-dialog shortcut-dialog";
  dialog.innerHTML = `<form method="dialog"><section class="panel"><h2>Keyboard Shortcuts</h2><div class="shortcut-grid"><span>Ctrl/Cmd + K</span><strong>Search and commands</strong><span>?</span><strong>Shortcut help</strong><span>Left / Right</span><strong>Previous / next chapter</strong><span>B</span><strong>Bookmark chapter</strong><span>F</span><strong>Reader focus mode</strong><span>Esc</span><strong>Close dialogs</strong></div><div class="actions"><button class="primary">Close</button></div></section></form>`;
  document.body.appendChild(dialog);
  dialog.addEventListener("close", () => dialog.remove());
  dialog.showModal();
}

function renderCommandResults() {
  if (!commandResults) return;
  const query = (commandInput?.value || "").trim().toLowerCase();
  const commands = [
    ["Go to Library", "#/library", true],
    ["Continue Reading", state.personal?.continue_reading ? `#/reader/${state.personal.continue_reading.novel_id}/${state.personal.continue_reading.chapter_number}/${state.personal.continue_reading.source}` : "#/library", Boolean(state.personal?.continue_reading)],
    ["Open Chapters", `#/chapters/${state.currentNovelId}`, true],
    ["Open Settings", "#/settings/appearance", true],
    ["Open Translate", `#/translate/${state.currentNovelId}`, canTranslate()],
    ["Open Job Center", "#/jobs", canTranslate()],
    ["Manage Novels", "#/novels", state.admin],
    ["Add Novel", "#/novels", state.admin],
    ["Open Recovery", `#/recovery/${state.currentNovelId}`, state.admin],
    ["Open Admin", "#/admin", state.admin],
    ["Show Shortcuts", "#shortcuts", true],
  ];
  const novelMatches = state.novels.map((novel) => [`Novel: ${novel.title}`, `#/chapters/${novel.id}`, true]);
  const chapterMatches = state.chapters.slice(0, 500).map((chapter) => [`Chapter ${chapter.chapter_number}: ${chapter.title}`, `#/reader/${state.currentNovelId}/${chapter.chapter_number}/${state.source}`, true]);
  const recentMatches = [
    ...(state.recent.novels || []).map((item) => [`Recent Novel: ${item.label}`, item.href, true]),
    ...(state.recent.chapters || []).map((item) => [`Recent Chapter: ${item.label}`, item.href, true]),
    ...(state.recent.jobs || []).map((item) => [`Recent Job: ${item.label}`, item.href, canTranslate()]),
    ...(state.recent.admin || []).map((item) => [`Recent Admin: ${item.label}`, item.href, state.admin]),
  ];
  const rows = [...commands, ...recentMatches, ...novelMatches, ...chapterMatches]
    .filter(([, , allowed]) => allowed)
    .filter(([label]) => !query || label.toLowerCase().includes(query))
    .slice(0, 20);
  commandResults.innerHTML = rows.map(([label, href]) => `<a href="${href}" data-command-result>${escapeHtml(label)}</a>`).join("") || `<p class="muted">No matches.</p>`;
  commandResults.querySelectorAll("[data-command-result]").forEach((link) => link.addEventListener("click", (event) => {
    if (link.getAttribute("href") === "#shortcuts") {
      event.preventDefault();
      commandDialog?.close();
      showShortcutHelp();
      return;
    }
    if (query) rememberRecent("searches", {label: query, href: link.getAttribute("href"), at: new Date().toISOString()});
    commandDialog?.close();
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

function titleCase(value) {
  return String(value || "").replace(/-/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

window.addEventListener("hashchange", () => {
  saveScrollPosition();
  activeRouteKey = window.location.hash || "#/library";
  if (!activeRouteKey.startsWith("#/reader/") && readerScrollHandler) {
    window.removeEventListener("scroll", readerScrollHandler);
    readerScrollHandler = null;
  }
  route();
});
window.addEventListener("DOMContentLoaded", async () => {
  applyPreferences();
  bindShellControls();
  await loadAuth();
  await refreshSession();
  await loadNovels().catch(() => {});
  activeRouteKey = window.location.hash || "#/library";
  route();
});
