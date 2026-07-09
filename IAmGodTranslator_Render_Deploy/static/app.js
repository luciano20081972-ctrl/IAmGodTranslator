const app = document.querySelector("#app");
const nav = document.querySelector("#primaryNav");

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
  admin: false,
  lastEstimate: null,
};

const sourceLabels = {ai: "AI", reference: "Reference", original: "Original"};
const chapterViews = [
  ["all", "All"],
  ["translated", "Translated"],
  ["needs", "Needs Translation"],
  ["missing-original", "Missing Original"],
  ["missing-reference", "Missing Reference"],
  ["errors", "Has Errors"],
];

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: {"Accept": "application/json", ...(options.headers || {})},
    ...options,
  });
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
  return payload;
}

function route() {
  const [path, query = ""] = (window.location.hash || "#/library").replace(/^#\/?/, "").split("?");
  const parts = path.split("/").filter(Boolean);
  const params = new URLSearchParams(query);
  updateNav(parts[0] || "library");
  if (parts[0] === "reader" && parts[1] && parts[2]) return openReader(parts[1], Number(parts[2]), parts[3] || state.source);
  if (parts[0] === "chapters" && parts[1]) return openChapters(parts[1]);
  if (parts[0] === "translate") return openTranslate(parts[1] || state.currentNovelId, params);
  if (parts[0] === "recovery") return openRecovery(parts[1] || state.currentNovelId);
  if (parts[0] === "novels") return openNovels();
  if (parts[0] === "admin") return openAdmin();
  return openLibrary();
}

function updateNav(active) {
  if (!nav) return;
  nav.querySelectorAll("a").forEach((link) => {
    const target = link.getAttribute("href").replace("#/", "").split("/")[0];
    link.classList.toggle("active", target === active || (active === "reader" && target === "chapters"));
  });
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
  } catch {
    state.admin = false;
  }
}

async function loadNovels(force = false) {
  if (!force && state.novels.length) return state.novels;
  const payload = await api("/api/novels");
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
    app.innerHTML = `
      ${pageHeader("Library", "A calm command center for reading and translation progress.", [
        ["Novels", novels.length],
        ["Chapters", sum(novels, "chapter_count")],
        ["Original", sum(novels, "original_count")],
        ["Reference", sum(novels, "reference_count")],
        ["AI", sum(novels, "ai_count")],
      ])}
      <section class="toolbar">
        <input class="search" id="librarySearch" type="search" placeholder="Search novels">
        <select id="libraryFilter"><option value="active">Active</option><option value="all">All</option><option value="archived">Archived</option></select>
        <select id="librarySort"><option value="updated">Recently updated</option><option value="title">Title</option><option value="progress">Translation progress</option></select>
      </section>
      <section class="novel-grid" id="novelGrid"></section>
    `;
    ["librarySearch", "libraryFilter", "librarySort"].forEach((id) => document.querySelector(`#${id}`).addEventListener("input", renderLibraryCards));
    renderLibraryCards();
  } catch (error) {
    setError(error.message);
  }
}

function renderLibraryCards() {
  const grid = document.querySelector("#novelGrid");
  if (!grid) return;
  const query = document.querySelector("#librarySearch").value.trim().toLowerCase();
  const filter = document.querySelector("#libraryFilter").value;
  const sort = document.querySelector("#librarySort").value;
  let novels = state.novels.filter((novel) => {
    if (filter === "active" && novel.is_archived) return false;
    if (filter === "archived" && !novel.is_archived) return false;
    if (!query) return true;
    return `${novel.title} ${novel.author || ""}`.toLowerCase().includes(query);
  });
  novels = novels.sort((a, b) => {
    if (sort === "title") return String(a.title).localeCompare(String(b.title));
    if (sort === "progress") return progress(b) - progress(a);
    return String(b.updated_at || "").localeCompare(String(a.updated_at || ""));
  });
  grid.innerHTML = novels.map(renderNovelCard).join("") || `<div class="empty-state">No novels match this view.</div>`;
}

function renderNovelCard(novel) {
  const pct = progress(novel);
  return `
    <article class="novel-card">
      <a class="cover" href="#/chapters/${encodeURIComponent(novel.id)}">
        ${novel.cover_url ? `<img src="${escapeAttr(novel.cover_url)}" alt="">` : `<span>${escapeHtml(initials(novel.title || novel.id))}</span>`}
      </a>
      <div class="novel-card-body">
        <div class="status-row"><span class="badge ok">${novel.is_archived ? "Archived" : "Active"}</span><span>${pct}% AI</span></div>
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
          <a class="button primary" href="#/chapters/${encodeURIComponent(novel.id)}">Open</a>
          <a class="button" href="#/reader/${encodeURIComponent(novel.id)}/1/${state.source}">Read</a>
          <a class="button" href="#/translate/${encodeURIComponent(novel.id)}">Translate</a>
        </div>
      </div>
    </article>`;
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
    document.querySelectorAll("[data-archive]").forEach((button) => button.addEventListener("click", archiveNovel));
  } catch (error) {
    setError(error.message);
  }
}

function renderNovelForm() {
  return `<form class="panel form-grid" id="novelForm">
    <h2>Create or Update Novel</h2>
    <label>ID / slug<input name="id" required placeholder="my-novel"></label>
    <label>Title<input name="title" required></label>
    <label>Author<input name="author"></label>
    <label>Status<input name="status" value="active"></label>
    <label>Cover URL<input name="cover_url"></label>
    <label>Source URL<input name="source_url"></label>
    <label>Reference Source URL<input name="reference_source_url"></label>
    <label>Default model<input name="model" value="gpt-4o-mini"></label>
    <label class="wide">Summary<textarea name="summary" rows="3"></textarea></label>
    <button class="primary" type="submit">Save Novel</button>
  </form>`;
}

async function saveNovelForm(event) {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.currentTarget).entries());
  try {
    await api("/api/novels", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data)});
    state.novels = [];
    openNovels();
  } catch (error) {
    alert(error.message);
  }
}

async function archiveNovel(event) {
  const button = event.currentTarget;
  await api(`/api/novels/${button.dataset.archive}/archive`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({archived: button.dataset.value === "true"})});
  state.novels = [];
  openNovels();
}

async function openChapters(novelId) {
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
  const payload = await api(path);
  state.chapters = payload.chapters || [];
  state.chapterTotal = payload.total || 0;
  return payload;
}

function renderChapters(payload) {
  const novel = payload.novel;
  const counts = payload.counts || {};
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
      <a class="button" href="#/translate/${novel.id}">Translate</a>
      <a class="button" href="#/recovery/${novel.id}">Recovery</a>
    </section>
    <section class="table-card">
      <div class="table-meta">Showing ${state.chapterTotal ? state.chapterOffset + 1 : 0}-${Math.min(state.chapterOffset + state.pageSize, state.chapterTotal)} of ${state.chapterTotal} chapters</div>
      <table><thead><tr><th>Chapter</th><th>Original</th><th>Reference</th><th>AI</th><th>Status</th><th></th></tr></thead><tbody>
        ${state.chapters.map((chapter) => `<tr><td><strong>Chapter ${chapter.chapter_number}</strong><br><span>${escapeHtml(chapter.title)}</span></td><td>${badge("Original", chapter.has_original)}</td><td>${badge("Reference", chapter.has_reference)}</td><td>${badge("AI", chapter.has_ai)}</td><td>${escapeHtml(chapter.translation_status || "")}</td><td class="row-actions"><a class="button" href="#/reader/${novel.id}/${chapter.chapter_number}/${state.source}">Read</a><a class="button" href="#/translate/${novel.id}?chapter=${chapter.chapter_number}">Translate</a></td></tr>`).join("") || `<tr><td colspan="6">No chapters match this view.</td></tr>`}
      </tbody></table>
      <div class="pager"><button id="prevPage" ${state.chapterOffset <= 0 ? "disabled" : ""}>Previous</button><button id="nextPage" ${state.chapterOffset + state.pageSize >= state.chapterTotal ? "disabled" : ""}>Next</button></div>
    </section>`;
  document.querySelector("#chapterNovel").addEventListener("change", (e) => { window.location.hash = `#/chapters/${e.target.value}`; });
  document.querySelector("#chapterSearch").addEventListener("input", debounce((e) => { state.chapterSearch = e.target.value; state.chapterOffset = 0; openChapters(novel.id); }, 250));
  document.querySelector("#chapterView").addEventListener("change", (e) => { state.chapterView = e.target.value; state.chapterOffset = 0; openChapters(novel.id); });
  document.querySelector("#prevPage").addEventListener("click", () => { state.chapterOffset = Math.max(0, state.chapterOffset - state.pageSize); openChapters(novel.id); });
  document.querySelector("#nextPage").addEventListener("click", () => { state.chapterOffset += state.pageSize; openChapters(novel.id); });
}

async function openReader(novelId, chapterNumber, requestedSource) {
  setLoading("Opening reader...");
  try {
    if (!state.chapters.length || state.currentNovelId !== novelId) {
      state.currentNovelId = novelId;
      state.chapterOffset = Math.max(0, chapterNumber - 25);
      await loadChapters(novelId);
      state.chapterOffset = 0;
      await api(`/api/novels/${novelId}/library?limit=5000`).then((payload) => { state.chapters = payload.chapters || []; });
    }
    const chapter = state.chapters.find((item) => item.chapter_number === chapterNumber);
    const source = ["ai", "reference", "original"].includes(requestedSource) ? requestedSource : preferredSource(chapter);
    state.source = source;
    localStorage.setItem("gt-reader-source", source);
    const payload = await api(`/api/novels/${encodeURIComponent(novelId)}/chapters/${chapterNumber}/${source}`);
    renderReader(novelId, chapterNumber, source, payload);
  } catch (error) {
    setError(error.message);
  }
}

function renderReader(novelId, chapterNumber, source, payload) {
  const previous = neighborChapter(chapterNumber, -1);
  const next = neighborChapter(chapterNumber, 1);
  document.documentElement.style.setProperty("--reader-font", `${state.fontSize}px`);
  app.innerHTML = `
    <section class="reader-panel">
      <div class="reader-nav"><a class="button" href="#/chapters/${novelId}">Back to Chapters</a><a class="button" href="#/library">Library</a><div class="spacer"></div><button data-go="${previous || ""}" ${previous ? "" : "disabled"}>Previous</button><select id="chapterPicker">${state.chapters.map((c) => `<option value="${c.chapter_number}" ${c.chapter_number === chapterNumber ? "selected" : ""}>Chapter ${c.chapter_number}</option>`).join("")}</select><button data-go="${next || ""}" ${next ? "" : "disabled"}>Next</button></div>
      <div class="reader-tabs">${["ai", "reference", "original"].map((item) => `<button data-source="${item}" class="${item === source ? "active" : ""}">${sourceLabels[item]}</button>`).join("")}<label>Font <input id="fontSize" type="range" min="16" max="25" value="${state.fontSize}"></label></div>
      <header class="reader-heading"><span>${sourceLabels[source]}</span><h1>Chapter ${chapterNumber}</h1><p>${escapeHtml(payload.title || `Chapter ${chapterNumber}`)}</p></header>
      <article class="reader-text">${renderReaderText(payload, source)}</article>
      <div class="reader-bottom"><button data-go="${previous || ""}" ${previous ? "" : "disabled"}>Previous Chapter</button><button data-go="${next || ""}" ${next ? "" : "disabled"}>Next Chapter</button></div>
    </section>`;
  document.querySelectorAll("[data-go]").forEach((button) => button.addEventListener("click", () => { if (button.dataset.go) window.location.hash = `#/reader/${novelId}/${button.dataset.go}/${state.source}`; }));
  document.querySelector("#chapterPicker").addEventListener("change", (event) => { window.location.hash = `#/reader/${novelId}/${event.target.value}/${state.source}`; });
  document.querySelectorAll("[data-source]").forEach((button) => button.addEventListener("click", () => { window.location.hash = `#/reader/${novelId}/${chapterNumber}/${button.dataset.source}`; }));
  document.querySelector("#fontSize").addEventListener("input", (event) => { state.fontSize = Number(event.target.value); localStorage.setItem("gt-reader-font", String(state.fontSize)); document.documentElement.style.setProperty("--reader-font", `${state.fontSize}px`); });
}

function renderReaderText(payload, source) {
  if (!payload.ok) return `<div class="empty-state">${escapeHtml(sourceLabels[source])} is not available for this chapter.</div>`;
  return paragraphs(payload.text).map((line) => `<p>${escapeHtml(line)}</p>`).join("");
}

async function openTranslate(novelId, params = new URLSearchParams()) {
  setLoading("Loading translation workspace...");
  try {
    state.currentNovelId = novelId;
    localStorage.setItem("gt-current-novel", novelId);
    await refreshSession();
    await loadNovels();
    if (!state.admin) return renderAdminGate("Translate");
    const jobs = await api(`/api/translation/jobs?novel_id=${encodeURIComponent(novelId)}`);
    const novel = state.novels.find((item) => item.id === novelId) || {};
    app.innerHTML = `
      ${pageHeader("Translate", "Plan controlled translation jobs from Original text, with Reference as optional guidance.", [["Novel", novel.title || novelId], ["Default model", novel.model || "gpt-4o-mini"]])}
      <section class="panel form-grid" id="translateForm">
        <label>Novel<select id="translateNovel">${state.novels.map((n) => `<option value="${n.id}" ${n.id === novelId ? "selected" : ""}>${escapeHtml(n.title)}</option>`).join("")}</select></label>
        <label>Chapters<input id="translateChapters" value="${escapeAttr(params.get("chapter") || "")}" placeholder="26,53,60-70"></label>
        <label><input id="allUntranslated" type="checkbox"> All untranslated</label>
        <label>Model<input id="model" value="${escapeAttr(novel.model || "gpt-4o-mini")}"></label>
        <label>Max total budget<input id="maxTotalBudget" type="number" step="0.01"></label>
        <label>Max cost per chapter<input id="maxPerChapterBudget" type="number" step="0.001"></label>
        <label>Retry count<input id="retryCount" type="number" value="1"></label>
        <label>Batch size<input id="batchSize" type="number" value="25"></label>
        <label><input id="stopOnBudget" type="checkbox" checked> Stop on budget</label>
        <label><input id="useReference" type="checkbox" checked> Use Reference when available</label>
        <label><input id="onlyUntranslated" type="checkbox" checked> Only untranslated</label>
        <label class="wide">Style guide<textarea id="styleGuide" rows="3"></textarea></label>
        <div class="actions"><button id="estimateBtn" class="primary">Estimate</button><button id="createJobBtn">Create Job</button></div>
      </section>
      <section id="estimateResult"></section>
      <section class="table-card"><h2>Recent Jobs</h2>${renderJobsTable(jobs.jobs || [])}</section>`;
    document.querySelector("#translateNovel").addEventListener("change", (e) => { window.location.hash = `#/translate/${e.target.value}`; });
    document.querySelector("#estimateBtn").addEventListener("click", estimateTranslation);
    document.querySelector("#createJobBtn").addEventListener("click", createTranslationJob);
    bindJobButtons();
  } catch (error) {
    setError(error.message);
  }
}

function translatePayload() {
  return {
    novel_id: document.querySelector("#translateNovel").value,
    chapters: document.querySelector("#translateChapters").value,
    all_untranslated: document.querySelector("#allUntranslated").checked,
    model: document.querySelector("#model").value || "gpt-4o-mini",
    max_total_budget: numberOrNull("#maxTotalBudget"),
    max_per_chapter_budget: numberOrNull("#maxPerChapterBudget"),
    retry_count: numberOrNull("#retryCount"),
    batch_size: numberOrNull("#batchSize"),
    stop_on_budget: document.querySelector("#stopOnBudget").checked,
    use_reference: document.querySelector("#useReference").checked,
    only_untranslated: document.querySelector("#onlyUntranslated").checked,
    style_guide: document.querySelector("#styleGuide").value,
  };
}

async function estimateTranslation(event) {
  event.preventDefault();
  const estimate = await api("/api/translation/estimate", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(translatePayload())});
  state.lastEstimate = estimate;
  document.querySelector("#estimateResult").innerHTML = `<section class="panel"><h2>Estimate</h2><div class="metric-grid">${metric("Selected", estimate.selected_count)}${metric("Eligible", estimate.eligible_count)}${metric("Skipped", estimate.skipped_count)}${metric("Input tokens", estimate.approx_input_tokens)}${metric("Output tokens", estimate.approx_output_tokens)}${metric("Approx cost", `$${Number(estimate.estimated_cost || 0).toFixed(4)}`)}</div><p class="muted">${escapeHtml(estimate.pricing_note)}</p></section>`;
}

async function createTranslationJob(event) {
  event.preventDefault();
  const created = await api("/api/translation/jobs", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(translatePayload())});
  alert(`Created job ${created.job.id.slice(0, 8)}`);
  openTranslate(created.job.novel_id);
}

function renderJobsTable(jobs) {
  return `<table><thead><tr><th>Job</th><th>Status</th><th>Progress</th><th>Budget</th><th>Actions</th></tr></thead><tbody>${jobs.map((job) => `<tr><td>${job.id.slice(0, 8)}<br><span>${escapeHtml(job.model || "")}</span></td><td>${escapeHtml(job.status)}</td><td>${job.completed_items || 0}/${job.total_items || 0} failed ${job.failed_items || 0}</td><td>$${Number(job.actual_cost || 0).toFixed(4)} / $${Number(job.estimated_cost || 0).toFixed(4)}</td><td class="row-actions">${jobActions(job)}</td></tr>`).join("") || `<tr><td colspan="5">No translation jobs yet.</td></tr>`}</tbody></table>`;
}

function jobActions(job) {
  const actions = [];
  if (["queued", "running"].includes(job.status)) {
    actions.push(["run-next", "Run Next Item"], ["pause", "Pause"], ["stop", "Stop"]);
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
    openTranslate(state.currentNovelId);
  }));
}

async function openRecovery(novelId) {
  setLoading("Loading recovery...");
  try {
    await refreshSession();
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

async function openAdmin() {
  setLoading("Loading admin...");
  await refreshSession();
  if (!state.admin) return renderAdminGate("Admin");
  try {
    const [overview, dbHealth, missing, imports, jobs] = await Promise.all([
      api("/api/admin/overview"),
      api("/api/admin/db-health"),
      api(`/api/admin/missing/${state.currentNovelId}`),
      api(`/api/import-jobs?novel_id=${state.currentNovelId}`),
      api(`/api/translation/jobs?novel_id=${state.currentNovelId}`),
    ]);
    app.innerHTML = `
      ${pageHeader("Admin", "Operational view for database health, jobs, imports, missing data, and exports.", [["Version", "10.1.0"], ["Schema", overview.overview.schema], ["Chapters", overview.overview.chapters], ["Needs Translation", overview.overview.needs_translation]])}
      <section class="dashboard-grid">
        <div class="panel"><h2>Database Health</h2><pre>${escapeHtml(JSON.stringify(dbHealth.health, null, 2))}</pre></div>
        <div class="panel"><h2>Missing Data</h2>${recoveryList("Missing Original", missing.missing.missing_original)}${recoveryList("Missing Reference", missing.missing.missing_reference)}${objectDetails("Translation errors", missing.missing.translation_errors)}</div>
        <div class="panel"><h2>Backup & Export</h2><p class="muted">Exports a versioned ZIP from PostgreSQL. No automatic restore or startup scanning.</p><a class="button primary" href="/api/novels/${state.currentNovelId}/backup">Export Novel Backup</a></div>
      </section>
      <section class="table-card"><h2>Translation Jobs</h2>${renderJobsTable(jobs.jobs || [])}</section>
      <section class="table-card"><h2>Import Jobs</h2><table><tbody>${(imports.jobs || []).map((job) => `<tr><td>${job.id.slice(0, 8)}</td><td>${job.target_mode}</td><td>${job.status}</td><td>${job.updated_at}</td></tr>`).join("") || `<tr><td>No import jobs.</td></tr>`}</tbody></table></section>
      <div class="actions"><button id="logoutBtn">Logout</button><a class="button" href="#/recovery/${state.currentNovelId}">Open Recovery</a></div>`;
    bindJobButtons();
    document.querySelector("#logoutBtn").addEventListener("click", async () => { await api("/api/admin/logout", {method: "POST"}); state.admin = false; openAdmin(); });
  } catch (error) {
    setError(error.message);
  }
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
  return `<section class="page-header"><div><p class="eyebrow">GodTranslator</p><h1>${escapeHtml(title)}</h1><p>${escapeHtml(subtitle)}</p></div>${stats.length ? `<div class="stats">${stats.map(([label, value]) => metric(label, value)).join("")}</div>` : ""}</section>`;
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

function initials(value) {
  return String(value || "GT").split(/\s+/).map((word) => word[0]).join("").slice(0, 2).toUpperCase();
}

function numberOrNull(selector) {
  const value = document.querySelector(selector).value;
  return value === "" ? null : Number(value);
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

window.addEventListener("hashchange", route);
window.addEventListener("DOMContentLoaded", async () => {
  await refreshSession();
  await loadNovels().catch(() => {});
  route();
});
