const app = document.querySelector("#app");

app.innerHTML = `
<div class="app-shell">
  <header class="topbar">
    <button class="brand" id="homeButton" type="button">
      <span class="brand-mark" id="brandMark">IG</span>
      <span><strong>IAmGodTranslator</strong><small>Novel library</small></span>
    </button>
    <nav class="header-links">
      <button class="link-button" id="supportButton" type="button">Thanks</button>
      <span class="status-chip" id="apiStatus">Checking</span>
      <button class="secondary-button" id="adminButton" type="button">Admin</button>
      <button class="icon-button" id="themeToggle" type="button">T</button>
    </nav>
  </header>
  <nav class="workspace-tabs" id="workspaceTabs" aria-label="Open workspaces"></nav>
  <main>
    <section class="view active" id="libraryView">
      <div class="library-hero">
        <div class="library-title">
          <div class="library-icon" id="libraryIcon">IG</div>
          <div><p class="eyebrow">Library Home</p><h1>Your Translation Library</h1><p class="hero-copy">Read original chapters, reference translations, and AI translations in one quiet library.</p></div>
        </div>
        <button class="primary-button admin-only" id="addNovelButton" type="button">Add New Novel</button>
      </div>
      <div class="support-panel" id="supportPanel" hidden>
        <h2>Thanks</h2>
        <p>Thank you to everyone reading, testing, and helping this library get steadier chapter by chapter.</p>
      </div>
      <div class="toolbar"><label><span>Search</span><input id="novelSearch" type="search" placeholder="Search novels by title"></label><label><span>Sort</span><select id="novelSort"><option value="updated">Last updated</option><option value="name">Name</option><option value="translated">AI Translation count</option></select></label></div>
      <div class="novel-grid" id="novelGrid"><div class="empty-state">Loading library...</div></div>
    </section>

    <section class="view" id="detailView">
      <div class="novel-hero">
        <button class="secondary-button" id="backToLibrary" type="button">Library</button>
        <div class="dashboard-cover" id="dashboardCover">IG</div>
        <div class="novel-summary-block">
          <p class="eyebrow">Novel Detail</p>
          <h1 id="novelTitle">Novel</h1>
          <p id="novelSummary" class="novel-summary">No summary yet.</p>
          <div class="tag-row" id="novelTags"></div>
        </div>
      </div>
      <div class="metrics-grid"><div><span>Original Story</span><strong id="metricOriginal">0</strong></div><div><span>Reference Translation</span><strong id="metricReference">0</strong></div><div><span>AI Translation</span><strong id="metricTranslated">0</strong></div><div><span>Remaining</span><strong id="metricRemaining">0</strong></div><div><span>Last backup</span><strong id="metricBackup">Never</strong></div><div><span>Model</span><strong id="metricModel">gpt-4o-mini</strong></div><div><span>Status</span><strong id="metricStatus">Ready</strong></div><div><span>Storage</span><strong id="metricStorage">-</strong></div></div>
      <nav class="tabs"><button class="tab active" data-tab="chapters" type="button">Chapters</button><button class="tab" data-tab="reader" type="button">Reader</button><button class="tab admin-only" data-tab="translate" type="button">Translate</button><button class="tab admin-only" data-tab="backups" type="button">Backups</button><button class="tab admin-only" data-tab="settings" type="button">Settings</button></nav>

      <section class="tab-panel active" id="chaptersPanel">
        <div class="toolbar chapter-toolbar"><label><span>Search chapters</span><input id="chapterSearch" type="search" placeholder="Chapter number or title"></label><label><span>Filter</span><select id="chapterFilter"><option value="all">All</option><option value="has-original">Has Original Story</option><option value="has-reference">Has Reference Translation</option><option value="has-ai">Has AI Translation</option><option value="missing-ai">Missing AI Translation</option><option value="missing-reference">Missing Reference Translation</option></select></label><label><span>Jump to chapter</span><input id="chapterJump" type="number" min="1" placeholder="26"></label></div>
        <div class="pager"><button class="secondary-button" id="prevPage" type="button">Previous page</button><span id="pageInfo">Page 1</span><button class="secondary-button" id="nextPage" type="button">Next page</button></div>
        <div class="chapter-list" id="chapterList"></div>
      </section>

      <section class="tab-panel" id="readerPanel">
        <div class="reader-shell" id="readerShell">
          <div class="reader-toolbar"><button class="secondary-button" id="readerBack" type="button">Back to Novel</button><button class="secondary-button" id="readerLibrary" type="button">Back to Library</button><div class="reader-controls"><button class="secondary-button" id="chapterPickerButton" type="button">Chapters</button><button class="icon-button" id="fontDown" type="button">A-</button><button class="icon-button" id="fontUp" type="button">A+</button><button class="icon-button" id="widthToggle" type="button">W</button><select id="readerTheme"><option value="paper">Paper</option><option value="dark">Dark</option><option value="sepia">Sepia</option></select><button class="icon-button" id="fullscreenReader" type="button">F</button></div></div>
          <div class="reader-nav"><button class="secondary-button" id="prevChapter" type="button">Previous</button><div><p class="eyebrow" id="readerChapterNumber">Chapter</p><h2 id="readerChapterTitle">Open a chapter</h2></div><button class="secondary-button" id="nextChapter" type="button">Next</button></div>
          <div class="reader-tabs"><button class="reader-tab active" data-reader-tab="original" type="button">Original Story</button><button class="reader-tab" data-reader-tab="reference" type="button">Reference Translation</button><button class="reader-tab" data-reader-tab="ai" type="button">AI Translation</button></div>
          <aside class="chapter-picker" id="chapterPickerPanel" hidden></aside>
          <article class="reader-content" id="readerContent">Select a chapter from the chapter library.</article>
          <div class="reader-bottom-nav"><button class="secondary-button" id="prevChapterBottom" type="button">Previous Chapter</button><button class="secondary-button" id="nextChapterBottom" type="button">Next Chapter</button></div>
        </div>
      </section>

      <section class="tab-panel admin-only" id="translatePanel">
        <div class="translate-grid">
          <form class="panel" id="originalUploadForm"><h2>Original Story Upload</h2><p class="helper">Original Story is the source of truth for translation.</p><input id="originalFiles" name="original" type="file" accept=".txt,.zip,text/plain,application/zip" multiple required><button class="primary-button" type="submit">Upload Original Story</button></form>
          <form class="panel" id="referenceUploadForm"><h2>Reference Translation Upload</h2><p class="helper">Reference Translation is optional support text.</p><input id="referenceFiles" name="reference" type="file" accept=".txt,.zip,text/plain,application/zip" multiple><button class="secondary-button" type="submit">Upload Reference Translation</button></form>
        </div>
        <div class="translate-grid">
          <form class="panel settings-grid" id="batchForm"><h2>Batch Settings</h2><label><span>Model</span><select id="model"><option value="gpt-4o-mini">gpt-4o-mini</option></select></label><label><span>Max total budget</span><input id="maxTotalBudget" type="number" step="0.01" min="0" value="15.00"></label><label><span>Max per-chapter budget</span><input id="maxCostPerChapter" type="number" step="0.001" min="0" value="0.017"></label><label><span>Retry limit</span><input id="retryFailedChapters" type="number" min="0" max="1" value="1"></label><label><span>Batch size</span><input id="batchSize" type="number" min="1" max="200" value="25"></label><label class="check"><input id="stopWhenBudgetReached" type="checkbox" checked> Stop when budget reached</label></form>
          <section class="panel"><h2>Batch Actions</h2><div class="warning">Paid translation warning: starting a batch calls the OpenAI API and may spend money. This will only translate chapters missing AI Translation.</div><div class="actions"><button class="secondary-button" id="estimateBatch" type="button">Show Cost Estimate</button><button class="primary-button" id="startBatch" type="button" disabled>Start Batch</button></div></section>
        </div>
        <section class="panel"><h2>Cost Estimate & Queue Preview</h2><div class="estimate-box" id="estimateBox">No batch estimate yet.</div><div class="progress-track"><div id="jobProgress" class="progress-fill"></div></div><div class="chapter-list compact" id="queueList"></div></section>
      </section>

      <section class="tab-panel admin-only" id="backupsPanel"><div class="warning storage-warning">Render free storage may reset. Download Full Novel Backup ZIP after every upload or translation batch.</div><div class="backup-grid"><form class="panel" id="importOriginalForm"><h2>Import Original Story ZIP</h2><input id="importOriginalFile" name="original_zip" type="file" accept=".zip,application/zip" required><button class="primary-button" type="submit">Import Original Story ZIP</button></form><form class="panel" id="importReferenceForm"><h2>Import Reference Translation ZIP</h2><input id="importReferenceFile" name="reference_zip" type="file" accept=".zip,application/zip" required><button class="secondary-button" type="submit">Import Reference Translation ZIP</button></form><form class="panel" id="importAiForm"><h2>Import AI Translated Chapters ZIP</h2><input id="importAiFile" name="translated_zip" type="file" accept=".zip,application/zip" required><button class="primary-button" type="submit">Import AI Translated Chapters ZIP</button></form><form class="panel" id="coverUploadForm"><h2>Novel Cover</h2><input id="coverFile" name="cover" type="file" accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp" required><button class="secondary-button" type="submit">Upload Cover</button></form><a class="panel link-card" id="downloadOriginal" href="#">Download Original Story ZIP</a><a class="panel link-card" id="downloadReference" href="#">Download Reference Translation ZIP</a><a class="panel link-card" id="downloadEnglish" href="#">Download AI Translations ZIP</a><a class="panel link-card" id="downloadPrompts" href="#">Download all prompts as ZIP</a><a class="panel link-card" id="downloadBackup" href="#">Download Full Novel Backup ZIP</a><form class="panel" id="restoreNovelForm"><h2>Restore Full Novel Backup ZIP</h2><input id="restoreFile" name="backup" type="file" accept=".zip,application/zip" required><button class="secondary-button" type="submit">Restore Full Novel Backup ZIP</button></form></div></section>

      <section class="tab-panel admin-only" id="settingsPanel">
        <form class="panel settings-grid" id="novelSettingsForm"><h2>Novel Metadata</h2><label><span>Novel title</span><input id="settingsTitle" type="text"></label><label><span>Source language</span><input id="sourceLanguage" type="text" value="Chinese"></label><label><span>Target language</span><input id="targetLanguage" type="text" value="English"></label><label><span>Default model</span><input id="defaultModel" type="text" value="gpt-4o-mini"></label><label><span>Tags, comma separated</span><input id="settingsTags" type="text"></label><label class="wide-field"><span>Summary</span><textarea id="settingsSummary" rows="4"></textarea></label><label><span>App version</span><input value="3.1 public reader admin UI" disabled></label><label><span>Storage mode</span><input id="storageModeDisplay" type="text" disabled></label><label><span>DATA_DIR</span><input id="dataDirDisplay" type="text" disabled></label><button class="primary-button" type="submit">Save Settings</button></form>
        <form class="panel settings-grid" id="appIconForm"><h2>Upload App / Library Icon</h2><input id="appIconFile" name="icon" type="file" accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp" required><button class="secondary-button" type="submit">Upload App / Library Icon</button></form>
      </section>
    </section>
  </main>
  <div class="toast" id="toast" role="status" aria-live="polite"></div>
</div>
<dialog id="addNovelDialog"><form id="addNovelForm"><h2>Add New Novel</h2><label><span>Title</span><input id="newNovelTitle" type="text" required></label><div class="actions"><button class="secondary-button" id="cancelAddNovel" type="button">Cancel</button><button class="primary-button" type="submit">Create</button></div></form></dialog>
<dialog id="adminDialog"><form method="dialog" id="adminForm"><h2>Admin Login</h2><p class="helper" id="adminHelp">Admin tools are private.</p><label><span>Password</span><input id="adminPassword" type="password" autocomplete="current-password"></label><div class="actions"><button class="secondary-button" value="cancel">Cancel</button><button class="primary-button" value="default">Login</button></div></form></dialog>`;

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));
const state = { novels: [], appInfo: {}, admin: { enabled: false, authenticated: false }, workspaces: [{ id: "library", type: "library", title: "Library" }], activeWorkspaceId: "library", currentNovel: null, chapters: [], filteredChapters: [], readerChapter: null, readerTab: "original", currentJob: null, pollTimer: null, readerSize: 18, readerWide: false, chapterPage: 1, pageSize: 50, searchTimer: null };

const els = {
  apiStatus: $("#apiStatus"), homeButton: $("#homeButton"), themeToggle: $("#themeToggle"), brandMark: $("#brandMark"), libraryIcon: $("#libraryIcon"), workspaceTabs: $("#workspaceTabs"), adminButton: $("#adminButton"), adminDialog: $("#adminDialog"), adminForm: $("#adminForm"), adminPassword: $("#adminPassword"), adminHelp: $("#adminHelp"), supportButton: $("#supportButton"), supportPanel: $("#supportPanel"),
  libraryView: $("#libraryView"), detailView: $("#detailView"), novelGrid: $("#novelGrid"), novelSearch: $("#novelSearch"), novelSort: $("#novelSort"), addNovelButton: $("#addNovelButton"), addNovelDialog: $("#addNovelDialog"), addNovelForm: $("#addNovelForm"), cancelAddNovel: $("#cancelAddNovel"), newNovelTitle: $("#newNovelTitle"),
  backToLibrary: $("#backToLibrary"), dashboardCover: $("#dashboardCover"), novelTitle: $("#novelTitle"), novelSummary: $("#novelSummary"), novelTags: $("#novelTags"), metricStorage: $("#metricStorage"), metricOriginal: $("#metricOriginal"), metricReference: $("#metricReference"), metricTranslated: $("#metricTranslated"), metricRemaining: $("#metricRemaining"), metricBackup: $("#metricBackup"), metricModel: $("#metricModel"), metricStatus: $("#metricStatus"),
  chapterSearch: $("#chapterSearch"), chapterFilter: $("#chapterFilter"), chapterJump: $("#chapterJump"), chapterList: $("#chapterList"), prevPage: $("#prevPage"), nextPage: $("#nextPage"), pageInfo: $("#pageInfo"),
  readerBack: $("#readerBack"), readerLibrary: $("#readerLibrary"), readerShell: $("#readerShell"), prevChapter: $("#prevChapter"), nextChapter: $("#nextChapter"), prevChapterBottom: $("#prevChapterBottom"), nextChapterBottom: $("#nextChapterBottom"), chapterPickerButton: $("#chapterPickerButton"), chapterPickerPanel: $("#chapterPickerPanel"), fullscreenReader: $("#fullscreenReader"), readerChapterNumber: $("#readerChapterNumber"), readerChapterTitle: $("#readerChapterTitle"), readerContent: $("#readerContent"), readerTheme: $("#readerTheme"), fontDown: $("#fontDown"), fontUp: $("#fontUp"), widthToggle: $("#widthToggle"),
  originalUploadForm: $("#originalUploadForm"), referenceUploadForm: $("#referenceUploadForm"), originalFiles: $("#originalFiles"), referenceFiles: $("#referenceFiles"), model: $("#model"), maxTotalBudget: $("#maxTotalBudget"), maxCostPerChapter: $("#maxCostPerChapter"), retryFailedChapters: $("#retryFailedChapters"), batchSize: $("#batchSize"), stopWhenBudgetReached: $("#stopWhenBudgetReached"), estimateBatch: $("#estimateBatch"), startBatch: $("#startBatch"), estimateBox: $("#estimateBox"), jobProgress: $("#jobProgress"), queueList: $("#queueList"),
  importOriginalForm: $("#importOriginalForm"), importOriginalFile: $("#importOriginalFile"), importReferenceForm: $("#importReferenceForm"), importReferenceFile: $("#importReferenceFile"), importAiForm: $("#importAiForm"), importAiFile: $("#importAiFile"), coverUploadForm: $("#coverUploadForm"), coverFile: $("#coverFile"), downloadOriginal: $("#downloadOriginal"), downloadReference: $("#downloadReference"), downloadEnglish: $("#downloadEnglish"), downloadPrompts: $("#downloadPrompts"), downloadBackup: $("#downloadBackup"), restoreNovelForm: $("#restoreNovelForm"), restoreFile: $("#restoreFile"),
  novelSettingsForm: $("#novelSettingsForm"), settingsTitle: $("#settingsTitle"), settingsSummary: $("#settingsSummary"), settingsTags: $("#settingsTags"), sourceLanguage: $("#sourceLanguage"), targetLanguage: $("#targetLanguage"), defaultModel: $("#defaultModel"), storageModeDisplay: $("#storageModeDisplay"), dataDirDisplay: $("#dataDirDisplay"), appIconForm: $("#appIconForm"), appIconFile: $("#appIconFile"), toast: $("#toast")
};

const tabs = $$(".tab");
const panels = $$(".tab-panel");
const readerTabs = $$(".reader-tab");

function toast(message, error = false) { els.toast.textContent = message; els.toast.style.background = error ? "var(--danger)" : "var(--text)"; els.toast.classList.add("show"); clearTimeout(toast.timer); toast.timer = setTimeout(() => els.toast.classList.remove("show"), 3400); }
async function api(path, options = {}) { const res = await fetch(path, options); const text = await res.text(); let data = {}; try { data = text ? JSON.parse(text) : {}; } catch (_error) { if (!res.ok) throw new Error("Server returned a non-JSON error. Check server logs or uploaded chapters."); throw new Error("Server returned an unexpected response."); } if (!res.ok) throw new Error(data.detail || `Request failed: ${res.status}`); return data; }
function esc(value) { return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char])); }
function date(value) { if (!value) return "Never"; try { return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(value)); } catch { return value; } }
function status(value) { return ({ completed: "translated", estimated: "queued", running: "translating", test_completed: "translated" }[value] || value || "unknown"); }
function money(value) { return `$${Number(value || 0).toFixed(4)}`; }

function setTheme(theme) { const dark = theme === "dark"; document.body.classList.toggle("dark", dark); localStorage.setItem("igt-theme", dark ? "dark" : "light"); }
function showView(name) { els.libraryView.classList.toggle("active", name === "library"); els.detailView.classList.toggle("active", name === "detail"); }
function switchTab(tab) { if (!state.admin.authenticated && ["translate", "backups", "settings"].includes(tab)) { toast("Admin login required.", true); return; } tabs.forEach((button) => button.classList.toggle("active", button.dataset.tab === tab)); panels.forEach((panel) => panel.classList.toggle("active", panel.id === `${tab}Panel`)); }
function coverMarkup(novel, className = "cover") { return novel.cover_url ? `<img class="${className}" src="${esc(novel.cover_url)}" alt="">` : `<div class="${className} placeholder-cover"><span>${esc(novel.title.slice(0, 2).toUpperCase() || "IG")}</span></div>`; }
function renderIcon(container, url) { container.innerHTML = url ? `<img src="${esc(url)}" alt="">` : "<span>IG</span>"; }
function activePanelName() { const panel = panels.find((item) => item.classList.contains("active")); return panel ? panel.id.replace("Panel", "") : "chapters"; }
function currentWorkspace() { return state.workspaces.find((workspace) => workspace.id === state.activeWorkspaceId); }
function workspaceFor(id) { return state.workspaces.find((workspace) => workspace.id === id); }
function upsertWorkspace(workspace) { const existing = workspaceFor(workspace.id); if (existing) Object.assign(existing, workspace); else state.workspaces.push(workspace); }
function saveCurrentWorkspace() {
  const workspace = currentWorkspace();
  if (!workspace || workspace.type === "library") return;
  workspace.novelId = state.currentNovel?.novel_id || workspace.novelId;
  workspace.novelTitle = state.currentNovel?.title || workspace.novelTitle;
  workspace.detailTab = activePanelName();
  workspace.chapterPage = state.chapterPage;
  workspace.readerChapter = state.readerChapter;
  workspace.readerTab = state.readerTab;
  workspace.title = workspace.type === "reader" && state.readerChapter ? `Chapter ${state.readerChapter}` : (state.currentNovel?.title || workspace.title);
}
function renderWorkspaces() {
  els.workspaceTabs.innerHTML = "";
  for (const workspace of state.workspaces) {
    const tab = document.createElement("button");
    tab.className = `workspace-tab ${workspace.id === state.activeWorkspaceId ? "active" : ""}`;
    tab.type = "button";
    tab.innerHTML = `<span>${esc(workspace.title)}</span>`;
    tab.addEventListener("click", () => activateWorkspace(workspace.id));
    if (workspace.type !== "library") {
      const close = document.createElement("span");
      close.className = "workspace-close";
      close.textContent = "x";
      close.addEventListener("click", (event) => { event.stopPropagation(); closeWorkspace(workspace.id); });
      tab.appendChild(close);
    }
    els.workspaceTabs.appendChild(tab);
  }
}
async function activateWorkspace(id) {
  if (id === state.activeWorkspaceId) return;
  saveCurrentWorkspace();
  const workspace = workspaceFor(id);
  if (!workspace) return;
  state.activeWorkspaceId = id;
  if (workspace.type === "library") {
    showView("library");
    renderWorkspaces();
    return;
  }
  await loadNovelWorkspace(workspace);
}
async function loadNovelWorkspace(workspace) {
  const data = await api(`/api/novels/${workspace.novelId}/library`);
  state.currentNovel = data.novel;
  state.chapters = data.chapters || [];
  state.chapterPage = workspace.chapterPage || 1;
  state.readerChapter = workspace.readerChapter || null;
  state.readerTab = workspace.readerTab || state.readerTab || "original";
  state.currentJob = null;
  showView("detail");
  renderDetail();
  renderChapters();
  renderQueue();
  switchTab(workspace.type === "reader" ? "reader" : (workspace.detailTab || "chapters"));
  if (workspace.type === "reader" && state.readerChapter) await openReader(state.readerChapter, state.readerTab, { keepWorkspace: true });
  renderWorkspaces();
}
function closeWorkspace(id) {
  const index = state.workspaces.findIndex((workspace) => workspace.id === id);
  if (index <= 0) return;
  state.workspaces.splice(index, 1);
  if (state.activeWorkspaceId === id) {
    const next = state.workspaces[Math.max(0, index - 1)] || state.workspaces[0];
    state.activeWorkspaceId = "";
    activateWorkspace(next.id);
  } else {
    renderWorkspaces();
  }
}
function showLibrary() { saveCurrentWorkspace(); state.activeWorkspaceId = "library"; showView("library"); renderWorkspaces(); }
async function backToNovelWorkspace() {
  if (!state.currentNovel) return showLibrary();
  saveCurrentWorkspace();
  const id = `novel:${state.currentNovel.novel_id}`;
  upsertWorkspace({ id, type: "novel", novelId: state.currentNovel.novel_id, novelTitle: state.currentNovel.title, title: state.currentNovel.title, detailTab: "chapters", chapterPage: state.chapterPage, readerChapter: state.readerChapter, readerTab: state.readerTab });
  state.activeWorkspaceId = "";
  await activateWorkspace(id);
}
function closeAddNovelDialog() {
  els.addNovelForm.reset();
  if (els.addNovelDialog.open) els.addNovelDialog.close();
}

async function loadAdminStatus() { state.admin = await api("/api/admin/status").catch(() => ({ enabled: false, authenticated: false })); renderAdminState(); }
async function loadAppInfo() { state.appInfo = await api("/api/app").catch(() => ({})); renderIcon(els.brandMark, state.appInfo.icon_url); renderIcon(els.libraryIcon, state.appInfo.icon_url); }
async function loadNovels() { els.novelGrid.innerHTML = '<div class="empty-state">Loading library...</div>'; state.novels = (await api("/api/novels")).novels || []; renderNovels(); }
function renderAdminState() { document.body.classList.toggle("is-admin", state.admin.authenticated); els.adminButton.textContent = state.admin.authenticated ? "Logout" : "Admin"; els.adminHelp.textContent = state.admin.enabled ? "Enter the admin password to unlock private controls." : "Admin login is disabled because ADMIN_PASSWORD is not set. Private tools are hidden."; if (!state.admin.authenticated && ["translatePanel", "backupsPanel", "settingsPanel"].some((id) => document.getElementById(id).classList.contains("active"))) switchTab("chapters"); }

function renderNovels() {
  const q = els.novelSearch.value.toLowerCase();
  const sort = els.novelSort.value;
  let novels = state.novels.filter((novel) => novel.title.toLowerCase().includes(q));
  novels.sort((a, b) => sort === "name" ? a.title.localeCompare(b.title) : sort === "translated" ? b.counts.translated_chapters - a.counts.translated_chapters : String(b.updated_at).localeCompare(String(a.updated_at)));
  els.novelGrid.innerHTML = novels.length ? "" : '<div class="empty-state">No novels found. Add a novel to begin.</div>';
  for (const novel of novels) {
    const card = document.createElement("article");
    card.className = "novel-card";
    card.innerHTML = `${coverMarkup(novel, "library-cover")}<div class="novel-card-body"><h2>${esc(novel.title)}</h2><p class="card-meta">${esc(novel.summary || "Novel ready for reading.")}</p><div class="tag-row">${(novel.tags || []).slice(0, 3).map((tag) => `<span>${esc(tag)}</span>`).join("")}</div><div class="card-stats"><div><span>Original</span><strong>${novel.counts.original_files}</strong></div><div><span>Reference</span><strong>${novel.counts.reference_files}</strong></div><div><span>AI</span><strong>${novel.counts.translated_chapters}</strong></div><div><span>Remaining</span><strong>${novel.counts.remaining_chapters}</strong></div></div><button class="primary-button" type="button">Open Novel</button></div>`;
    card.querySelector("button").addEventListener("click", () => openNovel(novel.novel_id));
    els.novelGrid.appendChild(card);
  }
}

async function openNovel(id) {
  saveCurrentWorkspace();
  const data = await api(`/api/novels/${id}/library`);
  state.currentNovel = data.novel;
  state.chapters = data.chapters || [];
  state.chapterPage = 1;
  state.currentJob = null;
  state.activeWorkspaceId = `novel:${id}`;
  upsertWorkspace({ id: state.activeWorkspaceId, type: "novel", novelId: id, novelTitle: data.novel.title, title: data.novel.title, detailTab: "chapters", chapterPage: 1, readerTab: state.readerTab });
  showView("detail");
  renderDetail();
  renderChapters();
  renderQueue();
  switchTab("chapters");
  renderWorkspaces();
}

function renderDetail() {
  const n = state.currentNovel, c = n.counts;
  els.novelTitle.textContent = n.title;
  els.novelSummary.textContent = n.summary || "No summary yet.";
  els.novelTags.innerHTML = (n.tags || []).length ? n.tags.map((tag) => `<span>${esc(tag)}</span>`).join("") : "<span>Novel</span>";
  els.metricStorage.textContent = n.storage_mode;
  els.metricOriginal.textContent = c.original_files;
  els.metricReference.textContent = c.reference_files;
  els.metricTranslated.textContent = c.translated_chapters;
  els.metricRemaining.textContent = c.remaining_chapters;
  els.metricBackup.textContent = date(n.last_backup_at);
  els.metricModel.textContent = n.current_model;
  els.metricStatus.textContent = status(n.status);
  els.dashboardCover.innerHTML = n.cover_url ? `<img src="${esc(n.cover_url)}" alt="">` : `<span>${esc(n.title.slice(0, 2).toUpperCase() || "IG")}</span>`;
  els.downloadOriginal.href = `/api/novels/${n.novel_id}/download/original`;
  els.downloadReference.href = `/api/novels/${n.novel_id}/download/reference`;
  els.downloadEnglish.href = `/api/novels/${n.novel_id}/download/ai`;
  els.downloadPrompts.href = `/api/novels/${n.novel_id}/download/prompts`;
  els.downloadBackup.href = `/api/novels/${n.novel_id}/backup`;
  els.settingsTitle.value = n.title;
  els.settingsSummary.value = n.summary || "";
  els.settingsTags.value = (n.tags || []).join(", ");
  els.sourceLanguage.value = n.source_language || "Chinese";
  els.targetLanguage.value = n.target_language || "English";
  els.defaultModel.value = n.current_model || "gpt-4o-mini";
  els.storageModeDisplay.value = n.storage_mode || "";
  els.dataDirDisplay.value = n.data_dir || "";
}

function modeBadge(label, available) { return `<span class="badge ${available ? "translated" : "missing"}">${label}: ${available ? "available" : "missing"}</span>`; }
function chapterMatchesFilter(chapter, filter) { if (filter === "has-original") return chapter.has_original; if (filter === "has-reference") return chapter.has_reference; if (filter === "has-ai") return chapter.has_translation; if (filter === "missing-ai") return !chapter.has_translation; if (filter === "missing-reference") return !chapter.has_reference; return true; }
function filteredChapters() { const q = els.chapterSearch.value.toLowerCase(); const f = els.chapterFilter.value; return state.chapters.filter((c) => chapterMatchesFilter(c, f) && `${c.chapter} ${c.title}`.toLowerCase().includes(q)).sort((a, b) => a.chapter - b.chapter); }

function renderChapters() {
  state.filteredChapters = filteredChapters();
  const totalPages = Math.max(1, Math.ceil(state.filteredChapters.length / state.pageSize));
  state.chapterPage = Math.min(Math.max(1, state.chapterPage), totalPages);
  const start = (state.chapterPage - 1) * state.pageSize;
  const chapters = state.filteredChapters.slice(start, start + state.pageSize);
  els.pageInfo.textContent = `Page ${state.chapterPage} of ${totalPages} (${state.filteredChapters.length} chapters)`;
  els.prevPage.disabled = state.chapterPage <= 1;
  els.nextPage.disabled = state.chapterPage >= totalPages;
  els.chapterList.innerHTML = chapters.length ? "" : '<div class="empty-state">No chapters match this view.</div>';
  for (const c of chapters) {
    const row = document.createElement("article");
    row.className = "chapter-row";
    row.innerHTML = `<div><div class="chapter-title">${String(c.chapter).padStart(4, "0")} - ${esc(c.title || "Untitled")}</div><div class="chapter-meta mode-badges">${modeBadge("Original", c.has_original)} ${modeBadge("Reference", c.has_reference)} ${modeBadge("AI", c.has_translation)}</div></div><div class="chapter-actions"></div>`;
    const read = document.createElement("button");
    read.className = "primary-button";
    read.textContent = "Read";
    read.addEventListener("click", () => openReader(c.chapter, state.readerTab));
    row.addEventListener("dblclick", () => openReader(c.chapter, state.readerTab));
    row.querySelector(".chapter-actions").appendChild(read);
    els.chapterList.appendChild(row);
  }
  renderChapterPicker();
}

async function openReader(chapter, tab = state.readerTab, options = {}) {
  const c = state.chapters.find((item) => Number(item.chapter) === Number(chapter));
  if (!c) return;
  if (!options.keepWorkspace) saveCurrentWorkspace();
  state.readerChapter = Number(chapter);
  state.readerTab = tab || "original";
  if (!options.keepWorkspace && state.currentNovel) {
    state.activeWorkspaceId = `reader:${state.currentNovel.novel_id}`;
    upsertWorkspace({ id: state.activeWorkspaceId, type: "reader", novelId: state.currentNovel.novel_id, novelTitle: state.currentNovel.title, title: `Chapter ${c.chapter}`, detailTab: "reader", chapterPage: state.chapterPage, readerChapter: state.readerChapter, readerTab: state.readerTab });
  }
  switchTab("reader");
  els.readerChapterNumber.textContent = `Chapter ${c.chapter}`;
  els.readerChapterTitle.textContent = c.title || "Untitled";
  readerTabs.forEach((button) => button.classList.toggle("active", button.dataset.readerTab === state.readerTab));
  renderChapterPicker();
  await loadReaderText();
  const workspace = currentWorkspace();
  if (workspace && workspace.type === "reader") {
    workspace.title = `Chapter ${c.chapter}`;
    workspace.readerChapter = state.readerChapter;
    workspace.readerTab = state.readerTab;
    renderWorkspaces();
  }
  api("/api/reader/last", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ novel_id: state.currentNovel.novel_id, chapter: state.readerChapter }) }).catch(() => {});
}

async function loadReaderText() {
  const endpoint = state.readerTab === "ai" ? "english" : state.readerTab;
  const missing = { original: "Original Story not available.", reference: "Reference Translation not available.", ai: "AI Translation not available yet." };
  els.readerContent.textContent = "Loading...";
  try {
    const data = await api(`/api/novels/${state.currentNovel.novel_id}/chapters/${state.readerChapter}/${endpoint}`);
    els.readerContent.textContent = data.text && data.text.trim() ? data.text : missing[state.readerTab];
  } catch (_error) {
    els.readerContent.textContent = missing[state.readerTab] || "Chapter text not available.";
  }
}

function adjacent(offset) { const chapters = state.chapters.slice().sort((a, b) => a.chapter - b.chapter); const i = chapters.findIndex((c) => c.chapter === state.readerChapter); if (chapters[i + offset]) openReader(chapters[i + offset].chapter, state.readerTab); }
function renderChapterPicker() { if (!els.chapterPickerPanel) return; const chapters = state.chapters.slice().sort((a, b) => a.chapter - b.chapter); els.chapterPickerPanel.innerHTML = chapters.map((c) => `<button class="chapter-picker-item ${c.chapter === state.readerChapter ? "active" : ""}" type="button" data-chapter="${c.chapter}">${String(c.chapter).padStart(4, "0")} ${esc(c.title || "")}</button>`).join(""); els.chapterPickerPanel.querySelectorAll("button").forEach((button) => button.addEventListener("click", () => { els.chapterPickerPanel.hidden = true; openReader(Number(button.dataset.chapter), state.readerTab); })); }

async function upload(kind) { const input = kind === "original" ? els.originalFiles : els.referenceFiles; if (!input.files.length) return toast("Choose files first.", true); const form = new FormData(); for (const file of input.files) form.append(kind, file); await api(`/api/novels/${state.currentNovel.novel_id}/upload/${kind}`, { method: "POST", body: form }); input.value = ""; await openNovel(state.currentNovel.novel_id); switchTab("translate"); toast(kind === "original" ? "Original Story uploaded." : "Reference Translation uploaded."); }
function settings(startNow = false) { return { model: els.model.value, max_total_budget: els.maxTotalBudget.value, max_cost_per_chapter: els.maxCostPerChapter.value, retry_failed_chapters: Number(els.retryFailedChapters.value || 0), batch_size: Number(els.batchSize.value || 25), stop_when_budget_reached: els.stopWhenBudgetReached.checked, show_estimate_before_starting: true, test_chapter_only: false, start_now: startNow }; }
async function buildEstimate() { try { state.currentJob = await api(`/api/novels/${state.currentNovel.novel_id}/translate/batch`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(settings(false)) }); els.startBatch.disabled = false; renderQueue(); toast("Cost estimate ready. Translation has not started."); } catch (_error) { els.startBatch.disabled = true; throw new Error("Cost estimate failed. Check server logs or uploaded chapters."); } }
async function startBatch() { if (!state.currentJob) await buildEstimate(); if (!window.confirm("Start paid translation for this estimated batch?")) return; await api(`/api/novels/${state.currentNovel.novel_id}/jobs/${state.currentJob.job_id}/start`, { method: "POST" }); toast("Batch started."); pollJob(); }
async function pollJob() { if (!state.currentJob) return; clearTimeout(state.pollTimer); state.currentJob = await api(`/api/novels/${state.currentNovel.novel_id}/jobs/${state.currentJob.job_id}`); renderQueue(); if (["queued", "running"].includes(state.currentJob.status)) state.pollTimer = setTimeout(pollJob, 3000); }
function renderQueue() { const job = state.currentJob; if (!job) { els.estimateBox.textContent = "No batch estimate yet."; els.jobProgress.style.width = "0%"; els.queueList.innerHTML = '<div class="empty-state">Build a cost estimate to preview the next batch queue.</div>'; return; } const total = job.counts?.total || 0, done = job.counts?.completed || 0; els.jobProgress.style.width = `${total ? Math.round((done / total) * 100) : 0}%`; els.estimateBox.innerHTML = `<strong>${status(job.status)}</strong><br>Chapters: ${total}. Cheapest estimate: ${money(job.estimate?.cheapest_total_cost)}. Recommended estimate: ${money(job.estimate?.recommended_total_cost)}.`; els.queueList.innerHTML = ""; for (const c of job.chapters || []) { const row = document.createElement("article"); row.className = "chapter-row"; row.innerHTML = `<div><div class="chapter-title">${String(c.chapter).padStart(4, "0")} - ${esc(c.title || "")}</div><div class="chapter-meta">${esc(c.error || "Ready")}</div></div><span class="badge ${c.status}">${status(c.status)}</span>`; els.queueList.appendChild(row); } }

async function restore(event) { event.preventDefault(); if (!els.restoreFile.files.length) return; const form = new FormData(); form.append("backup", els.restoreFile.files[0]); await api(`/api/novels/${state.currentNovel.novel_id}/restore`, { method: "POST", body: form }); await openNovel(state.currentNovel.novel_id); switchTab("backups"); toast("Novel backup restored."); }
async function importOriginalZip(event) { event.preventDefault(); if (!els.importOriginalFile.files.length) return toast("Choose an Original Story ZIP first.", true); const form = new FormData(); form.append("original_zip", els.importOriginalFile.files[0]); const result = await api(`/api/novels/${state.currentNovel.novel_id}/import/original`, { method: "POST", body: form }); els.importOriginalFile.value = ""; await openNovel(state.currentNovel.novel_id); switchTab("backups"); toast(`Imported ${result.imported} valid original chapters, ignored ${result.duplicates} duplicates.`); }
async function importReferenceZip(event) { event.preventDefault(); if (!els.importReferenceFile.files.length) return toast("Choose a Reference Translation ZIP first.", true); const form = new FormData(); form.append("reference_zip", els.importReferenceFile.files[0]); const result = await api(`/api/novels/${state.currentNovel.novel_id}/import/reference`, { method: "POST", body: form }); els.importReferenceFile.value = ""; await openNovel(state.currentNovel.novel_id); switchTab("backups"); toast(`Imported ${result.imported} valid reference chapters.`); }
async function importAiTranslations(event) { event.preventDefault(); if (!els.importAiFile.files.length) return toast("Choose an AI translated chapters ZIP first.", true); const form = new FormData(); form.append("translated_zip", els.importAiFile.files[0]); const result = await api(`/api/novels/${state.currentNovel.novel_id}/import/ai-translations`, { method: "POST", body: form }); els.importAiFile.value = ""; await openNovel(state.currentNovel.novel_id); switchTab("backups"); toast(`Imported ${result.imported} AI translated chapters.`); }
async function uploadCover(event) { event.preventDefault(); if (!els.coverFile.files.length) return toast("Choose a cover image first.", true); const form = new FormData(); form.append("cover", els.coverFile.files[0]); const result = await api(`/api/novels/${state.currentNovel.novel_id}/cover`, { method: "POST", body: form }); els.coverFile.value = ""; state.currentNovel = result.novel; state.chapters = result.chapters || state.chapters; await loadNovels(); renderDetail(); toast("Cover uploaded."); }
async function uploadAppIcon(event) { event.preventDefault(); if (!els.appIconFile.files.length) return toast("Choose an app icon first.", true); const form = new FormData(); form.append("icon", els.appIconFile.files[0]); state.appInfo = await api("/api/admin/app-icon", { method: "POST", body: form }); els.appIconFile.value = ""; renderIcon(els.brandMark, state.appInfo.icon_url); renderIcon(els.libraryIcon, state.appInfo.icon_url); toast("App icon uploaded."); }
async function saveSettings(event) { event.preventDefault(); state.currentNovel = await api(`/api/novels/${state.currentNovel.novel_id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title: els.settingsTitle.value, summary: els.settingsSummary.value, tags: els.settingsTags.value, source_language: els.sourceLanguage.value, target_language: els.targetLanguage.value, settings: { model: els.defaultModel.value } }) }); await loadNovels(); renderDetail(); toast("Settings saved."); }

async function login(event) { event.preventDefault(); await api("/api/admin/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password: els.adminPassword.value }) }); els.adminPassword.value = ""; els.adminDialog.close(); await loadAdminStatus(); toast("Admin unlocked."); }
async function logout() { await api("/api/admin/logout", { method: "POST" }); await loadAdminStatus(); toast("Admin locked."); }

function debounceChapters() { clearTimeout(state.searchTimer); state.searchTimer = setTimeout(() => { state.chapterPage = 1; renderChapters(); }, 180); }
function bind() {
  els.homeButton.onclick = () => showLibrary();
  els.backToLibrary.onclick = () => showLibrary();
  els.supportButton.onclick = () => { els.supportPanel.hidden = !els.supportPanel.hidden; };
  els.novelSearch.oninput = renderNovels;
  els.novelSort.onchange = renderNovels;
  els.chapterSearch.oninput = debounceChapters;
  els.chapterFilter.onchange = () => { state.chapterPage = 1; renderChapters(); };
  els.chapterJump.onchange = () => { const chapter = Number(els.chapterJump.value); const index = filteredChapters().findIndex((c) => c.chapter === chapter); if (index >= 0) { state.chapterPage = Math.floor(index / state.pageSize) + 1; renderChapters(); } };
  els.prevPage.onclick = () => { state.chapterPage -= 1; renderChapters(); };
  els.nextPage.onclick = () => { state.chapterPage += 1; renderChapters(); };
  els.themeToggle.onclick = () => setTheme(document.body.classList.contains("dark") ? "light" : "dark");
  tabs.forEach((button) => button.onclick = () => switchTab(button.dataset.tab));
  readerTabs.forEach((button) => button.onclick = () => openReader(state.readerChapter, button.dataset.readerTab));
  els.readerBack.onclick = () => backToNovelWorkspace().catch((err) => toast(err.message, true));
  els.readerLibrary.onclick = () => showLibrary();
  els.prevChapter.onclick = () => adjacent(-1);
  els.nextChapter.onclick = () => adjacent(1);
  els.prevChapterBottom.onclick = () => adjacent(-1);
  els.nextChapterBottom.onclick = () => adjacent(1);
  els.chapterPickerButton.onclick = () => { renderChapterPicker(); els.chapterPickerPanel.hidden = !els.chapterPickerPanel.hidden; };
  els.fullscreenReader.onclick = () => { if (document.fullscreenElement) document.exitFullscreen(); else if (els.readerShell.requestFullscreen) els.readerShell.requestFullscreen(); };
  els.fontDown.onclick = () => { state.readerSize = Math.max(15, state.readerSize - 1); document.documentElement.style.setProperty("--reader-size", `${state.readerSize}px`); };
  els.fontUp.onclick = () => { state.readerSize = Math.min(24, state.readerSize + 1); document.documentElement.style.setProperty("--reader-size", `${state.readerSize}px`); };
  els.widthToggle.onclick = () => { state.readerWide = !state.readerWide; els.readerContent.classList.toggle("wide", state.readerWide); };
  els.readerTheme.onchange = () => els.readerShell.dataset.theme = els.readerTheme.value;
  els.adminButton.onclick = () => state.admin.authenticated ? logout().catch((err) => toast(err.message, true)) : (els.adminDialog.showModal ? els.adminDialog.showModal() : els.adminPassword.focus());
  els.adminForm.onsubmit = (event) => login(event).catch((err) => toast(err.message, true));
  els.originalUploadForm.onsubmit = (event) => { event.preventDefault(); upload("original").catch((err) => toast(err.message, true)); };
  els.referenceUploadForm.onsubmit = (event) => { event.preventDefault(); upload("reference").catch((err) => toast(err.message, true)); };
  els.estimateBatch.onclick = () => buildEstimate().catch((err) => toast(err.message, true));
  els.startBatch.onclick = () => startBatch().catch((err) => toast(err.message, true));
  els.importOriginalForm.onsubmit = (event) => importOriginalZip(event).catch((err) => toast(err.message, true));
  els.importReferenceForm.onsubmit = (event) => importReferenceZip(event).catch((err) => toast(err.message, true));
  els.importAiForm.onsubmit = (event) => importAiTranslations(event).catch((err) => toast(err.message, true));
  els.coverUploadForm.onsubmit = (event) => uploadCover(event).catch((err) => toast(err.message, true));
  els.appIconForm.onsubmit = (event) => uploadAppIcon(event).catch((err) => toast(err.message, true));
  els.restoreNovelForm.onsubmit = (event) => restore(event).catch((err) => toast(err.message, true));
  els.novelSettingsForm.onsubmit = (event) => saveSettings(event).catch((err) => toast(err.message, true));
  els.addNovelButton.onclick = () => els.addNovelDialog.showModal ? els.addNovelDialog.showModal() : els.newNovelTitle.focus();
  els.cancelAddNovel.onclick = () => closeAddNovelDialog();
  els.addNovelDialog.addEventListener("click", (event) => { if (event.target === els.addNovelDialog) closeAddNovelDialog(); });
  els.addNovelDialog.addEventListener("close", () => els.addNovelForm.reset());
  els.addNovelForm.onsubmit = async (event) => { event.preventDefault(); if (!els.addNovelForm.reportValidity()) return; const title = els.newNovelTitle.value.trim(); const novel = await api("/api/novels", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title }) }); closeAddNovelDialog(); await loadNovels(); openNovel(novel.novel_id); };
}

function registerServiceWorker() { if (!("serviceWorker" in navigator)) return; navigator.serviceWorker.register("/service-worker.js?v=5").then((registration) => registration.update()).catch(() => {}); }
async function init() { registerServiceWorker(); setTheme(localStorage.getItem("igt-theme") || "dark"); bind(); renderWorkspaces(); await loadAppInfo(); await loadAdminStatus(); try { await api("/api/health"); els.apiStatus.textContent = "Online"; els.apiStatus.classList.add("ok"); } catch { els.apiStatus.textContent = "Offline"; } await loadNovels(); }
init().catch((error) => toast(error.message, true));
