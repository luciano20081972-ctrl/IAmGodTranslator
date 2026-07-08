const app = document.querySelector("#app");

const state = {
  novels: [],
  currentNovel: null,
  library: null,
  chapters: [],
  source: localStorage.getItem("gt-v10-source") || "auto",
  fontSize: Number(localStorage.getItem("gt-v10-font-size") || 19),
};

const sourceLabels = {
  original: "Original",
  reference: "Reference",
  ai: "AI",
};

function route() {
  const hash = window.location.hash || "#/library";
  const parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  if (parts[0] === "reader" && parts.length >= 3) {
    const novelId = parts[1];
    const chapter = Number(parts[2]);
    const source = parts[3] || "auto";
    openReader(novelId, chapter, source);
    return;
  }
  if (parts[0] === "recovery" && parts[1]) {
    openRecovery(parts[1]);
    return;
  }
  if (parts[0] === "novel" && parts[1]) {
    openNovel(parts[1]);
    return;
  }
  openLibrary();
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {"Accept": "application/json", ...(options.headers || {})},
    ...options,
  });
  const text = await response.text();
  let payload = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    throw new Error(`Non-JSON response from ${path}`);
  }
  if (!response.ok) {
    throw new Error(payload?.detail || payload?.message || `Request failed: ${response.status}`);
  }
  return payload;
}

function setLoading(message = "Loading...") {
  app.innerHTML = `<section class="loading-card">${escapeHtml(message)}</section>`;
}

function setError(message) {
  app.innerHTML = `
    <section class="error-state">
      <h2>Reader could not load.</h2>
      <p>${escapeHtml(message)}</p>
      <p><a class="button" href="#/library">Back to Library</a></p>
    </section>
  `;
}

async function ensureNovels() {
  if (state.novels.length) return state.novels;
  const payload = await api("/api/novels");
  state.novels = payload.novels || [];
  return state.novels;
}

async function ensureLibrary(novelId) {
  if (state.library?.novel?.id === novelId) return state.library;
  const payload = await api(`/api/novels/${encodeURIComponent(novelId)}/library?limit=5000`);
  state.library = payload;
  state.currentNovel = payload.novel;
  state.chapters = payload.chapters || [];
  return payload;
}

async function openLibrary() {
  setLoading("Loading library...");
  try {
    const novels = await ensureNovels();
    app.innerHTML = `
      <section class="hero">
        <div>
          <div class="eyebrow">Library</div>
          <h1>GodTranslator</h1>
          <p class="muted">Clean v10 reader powered directly by the database.</p>
        </div>
      </section>
      <section class="chapter-list" style="margin-top: 1rem;">
        ${novels.map(renderNovelCard).join("") || `<div class="empty-state">No novels found in the v10 database.</div>`}
      </section>
    `;
  } catch (error) {
    setError(error.message);
  }
}

function renderNovelCard(novel) {
  const remaining = Math.max(0, Number(novel.original_count || 0) - Number(novel.ai_count || 0));
  return `
    <a class="hero" href="#/novel/${encodeURIComponent(novel.id)}">
      <div>
        <div class="eyebrow">Novel</div>
        <h2>${escapeHtml(novel.title || novel.id)}</h2>
        <p class="muted">Open the chapter library and database-backed reader.</p>
      </div>
      <div class="stats" aria-label="Novel counts">
        ${stat("Chapters", novel.chapter_count)}
        ${stat("Original", novel.original_count)}
        ${stat("Reference", novel.reference_count)}
        ${stat("AI", novel.ai_count)}
        ${stat("Needs Translation", remaining)}
      </div>
    </a>
  `;
}

async function openNovel(novelId) {
  setLoading("Loading chapters...");
  try {
    const payload = await ensureLibrary(novelId);
    renderNovel(payload);
  } catch (error) {
    setError(error.message);
  }
}

function renderNovel(payload) {
  const novel = payload.novel;
  const counts = payload.counts || {};
  const total = counts.total_chapter_rows ?? payload.total ?? 0;
  const original = counts.original_readable ?? 0;
  const reference = counts.reference_readable ?? 0;
  const ai = counts.ai_readable ?? 0;
  const needs = counts.needs_translation ?? Math.max(0, original - ai);
  app.innerHTML = `
    <section class="hero">
      <div>
        <div class="eyebrow">Chapter Library</div>
        <h1>${escapeHtml(novel.title || novel.id)}</h1>
        <p class="muted">All rows come from the v10 database API.</p>
      </div>
      <div class="stats">
        ${stat("Chapters", total)}
        ${stat("Original", original)}
        ${stat("Reference", reference)}
        ${stat("AI", ai)}
        ${stat("Needs Translation", needs)}
      </div>
    </section>
    <section class="toolbar">
      <input class="search" id="chapterSearch" type="search" placeholder="Search chapters">
      <span class="muted" id="chapterCount"></span>
      <a class="button" href="#/recovery/${encodeURIComponent(novel.id)}">Recovery & Import</a>
    </section>
    <section class="chapter-list" id="chapterList"></section>
  `;
  document.querySelector("#chapterSearch").addEventListener("input", renderChapterList);
  renderChapterList();
}

function renderChapterList() {
  const list = document.querySelector("#chapterList");
  const count = document.querySelector("#chapterCount");
  const query = (document.querySelector("#chapterSearch")?.value || "").trim().toLowerCase();
  const rows = state.chapters.filter((chapter) => {
    if (!query) return true;
    return `${chapter.chapter_number} ${chapter.title || ""}`.toLowerCase().includes(query);
  });
  count.textContent = `Showing ${rows.length} of ${state.chapters.length} chapters`;
  list.innerHTML = rows.map(renderChapterRow).join("") || `<div class="empty-state">No chapters match this search.</div>`;
}

function renderChapterRow(chapter) {
  const title = chapter.title || `Chapter ${chapter.chapter_number}`;
  return `
    <a class="chapter-row" href="#/reader/${encodeURIComponent(state.currentNovel.id)}/${chapter.chapter_number}/${preferredSource(chapter)}">
      <span>
        <span class="chapter-title">Chapter ${chapter.chapter_number}</span>
        <span class="muted">${escapeHtml(title)}</span>
      </span>
      <span class="badges">
        ${badge("Original", chapter.has_original)}
        ${badge("Reference", chapter.has_reference)}
        ${badge("AI", chapter.has_ai)}
      </span>
    </a>
  `;
}

async function openRecovery(novelId) {
  setLoading("Loading recovery tools...");
  try {
    await ensureLibrary(novelId);
    const diagnostic = await api(`/api/novels/${encodeURIComponent(novelId)}/recovery/reference`);
    renderRecovery(novelId, diagnostic);
  } catch (error) {
    setError(error.message);
  }
}

function renderRecovery(novelId, diagnostic, preview = null, importResult = null) {
  const missing = diagnostic.missing_reference_chapters || [];
  app.innerHTML = `
    <section class="hero">
      <div>
        <div class="eyebrow">Recovery & Import</div>
        <h1>Reference Recovery</h1>
        <p class="muted">Preview Reference files before writing missing Reference text. Existing Reference chapters are never overwritten.</p>
      </div>
      <div class="stats">
        ${stat("Range Rows", diagnostic.rows_in_range)}
        ${stat("Reference", diagnostic.reference_rows_in_range)}
        ${stat("Missing", diagnostic.missing_count)}
      </div>
    </section>

    <section class="recovery-grid">
      <div class="panel recovery-card">
        <h2>Missing Reference Chapters</h2>
        <p class="muted">Range ${diagnostic.range.start}-${diagnostic.range.end}</p>
        <p class="chapter-pills">${missing.map((chapter) => `<span>${chapter}</span>`).join("") || "None"}</p>
        <a class="button" href="/api/novels/${encodeURIComponent(novelId)}/recovery/request">Download Recovery Request JSON</a>
      </div>

      <form class="panel recovery-card" id="recoveryUploadForm">
        <h2>Upload Reference Files</h2>
        <p class="muted">Accepts a ZIP or multiple UTF-8 .txt files. Preview is required before import.</p>
        <input id="recoveryFiles" type="file" multiple accept=".zip,.txt">
        <button type="submit">Preview Upload</button>
      </form>
    </section>

    <section id="recoveryPreview">${preview ? renderRecoveryPreview(preview) : ""}</section>
    <section id="importResult">${importResult ? renderImportResult(importResult) : ""}</section>
  `;
  document.querySelector("#recoveryUploadForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const files = document.querySelector("#recoveryFiles").files;
    if (!files.length) return;
    const form = new FormData();
    Array.from(files).forEach((file) => form.append("files", file));
    const button = event.submitter;
    button.disabled = true;
    button.textContent = "Previewing...";
    try {
      const nextPreview = await api(`/api/novels/${encodeURIComponent(novelId)}/recovery/preview`, {
        method: "POST",
        body: form,
        headers: {},
      });
      renderRecovery(novelId, diagnostic, nextPreview, null);
    } catch (error) {
      document.querySelector("#recoveryPreview").innerHTML = `<div class="error-state">${escapeHtml(error.message)}</div>`;
      button.disabled = false;
      button.textContent = "Preview Upload";
    }
  });
  document.querySelector("#applyImport")?.addEventListener("click", async (event) => {
    const jobId = event.currentTarget.dataset.jobId;
    event.currentTarget.disabled = true;
    event.currentTarget.textContent = "Importing...";
    try {
      const result = await api(`/api/novels/${encodeURIComponent(novelId)}/recovery/import/${encodeURIComponent(jobId)}`, {method: "POST"});
      state.library = null;
      const refreshed = await api(`/api/novels/${encodeURIComponent(novelId)}/recovery/reference`);
      renderRecovery(novelId, refreshed, preview, result);
    } catch (error) {
      document.querySelector("#importResult").innerHTML = `<div class="error-state">${escapeHtml(error.message)}</div>`;
      event.currentTarget.disabled = false;
      event.currentTarget.textContent = "Import Missing References";
    }
  });
}

function renderRecoveryPreview(preview) {
  const canImport = Number(preview.would_import_count || 0) > 0;
  return `
    <div class="panel recovery-card">
      <h2>Preview Result</h2>
      <div class="stats compact">
        ${stat("Files Found", preview.files_found)}
        ${stat("Recognized", preview.recognized_count)}
        ${stat("Would Import", preview.would_import_count)}
        ${stat("Already Present", preview.already_present_count)}
        ${stat("Still Missing", preview.still_missing_count)}
      </div>
      ${recoveryList("Would insert", preview.chapters_that_would_be_imported)}
      ${recoveryList("Already present", preview.already_present_reference_chapters)}
      ${recoveryList("Still missing", preview.still_missing_after_import)}
      ${recoveryObjectList("Duplicates", preview.duplicate_chapter_numbers)}
      ${recoveryList("Empty files", preview.empty_files)}
      ${recoveryList("Unexpected chapters", preview.unexpected_chapters)}
      ${recoveryObjectList("Invalid files", preview.invalid_files)}
      ${recoveryObjectList("Ambiguous filenames", preview.ambiguous_filenames)}
      <button id="applyImport" data-job-id="${escapeHtml(preview.job_id)}" ${canImport ? "" : "disabled"}>Import Missing References</button>
    </div>
  `;
}

function renderImportResult(result) {
  return `
    <div class="panel recovery-card">
      <h2>Import Complete</h2>
      <p class="muted">Imported ${Number(result.imported_count || 0)} Reference chapters. Existing Reference chapters skipped: ${Number(result.skipped_existing_count || 0)}.</p>
      ${recoveryList("Imported", result.imported_chapters)}
      ${recoveryList("Skipped existing", result.skipped_existing_chapters)}
    </div>
  `;
}

function recoveryList(label, values) {
  const items = values || [];
  if (!items.length) return "";
  return `<details><summary>${escapeHtml(label)} (${items.length})</summary><p class="chapter-pills">${items.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</p></details>`;
}

function recoveryObjectList(label, values) {
  if (!values || (Array.isArray(values) && !values.length) || (!Array.isArray(values) && !Object.keys(values).length)) return "";
  return `<details><summary>${escapeHtml(label)}</summary><pre>${escapeHtml(JSON.stringify(values, null, 2))}</pre></details>`;
}

async function openReader(novelId, chapterNumber, requestedSource) {
  try {
    await ensureLibrary(novelId);
    const chapter = findChapter(chapterNumber);
    const source = requestedSource === "auto" ? preferredSource(chapter) : requestedSource;
    state.source = source;
    localStorage.setItem("gt-v10-source", source);
    history.replaceState(null, "", `#/reader/${encodeURIComponent(novelId)}/${chapterNumber}/${source}`);
    setLoading("Loading chapter...");
    const payload = await api(`/api/novels/${encodeURIComponent(novelId)}/chapters/${chapterNumber}/${source}`);
    renderReader(novelId, chapterNumber, source, payload);
  } catch (error) {
    setError(error.message);
  }
}

function renderReader(novelId, chapterNumber, source, payload) {
  const chapter = findChapter(chapterNumber);
  const previous = previousChapter(chapterNumber);
  const next = nextChapter(chapterNumber);
  const title = payload.title || chapter?.title || `Chapter ${chapterNumber}`;
  document.documentElement.style.setProperty("--reader-font", `${state.fontSize}px`);
  app.innerHTML = `
    <section class="reader-panel">
      <div class="reader-bar">
        <div class="reader-controls">
          <a class="button" href="#/novel/${encodeURIComponent(novelId)}">Back to Chapters</a>
          <a class="button" href="#/library">Library</a>
        </div>
        <div class="reader-controls">
          <button data-go="${previous || ""}" ${previous ? "" : "disabled"}>Previous</button>
          <select class="chapter-select" id="chapterPicker" aria-label="Choose chapter">
            ${state.chapters.map((item) => `<option value="${item.chapter_number}" ${item.chapter_number === chapterNumber ? "selected" : ""}>Chapter ${item.chapter_number}</option>`).join("")}
          </select>
          <button data-go="${next || ""}" ${next ? "" : "disabled"}>Next</button>
        </div>
      </div>

      <div class="source-tabs" role="tablist" aria-label="Text source">
        ${sourceButton("original", source)}
        ${sourceButton("reference", source)}
        ${sourceButton("ai", source)}
        <label class="muted">Font <input class="font-range" id="fontSize" type="range" min="16" max="24" value="${state.fontSize}"></label>
      </div>

      <div class="reader-heading">
        <div class="eyebrow">${escapeHtml(sourceLabels[source])}</div>
        <h1>Chapter ${chapterNumber}</h1>
        <div class="reader-meta">${escapeHtml(title)}</div>
      </div>

      <article class="reader-text">
        ${renderReaderText(payload, source)}
      </article>

      <div class="reader-bottom">
        <button data-go="${previous || ""}" ${previous ? "" : "disabled"}>Previous Chapter</button>
        <button data-go="${next || ""}" ${next ? "" : "disabled"}>Next Chapter</button>
      </div>
    </section>
  `;
  document.querySelectorAll("[data-go]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = Number(button.dataset.go);
      if (target) window.location.hash = `#/reader/${encodeURIComponent(novelId)}/${target}/${state.source}`;
    });
  });
  document.querySelector("#chapterPicker").addEventListener("change", (event) => {
    window.location.hash = `#/reader/${encodeURIComponent(novelId)}/${event.target.value}/${state.source}`;
  });
  document.querySelectorAll("[data-source]").forEach((button) => {
    button.addEventListener("click", () => {
      window.location.hash = `#/reader/${encodeURIComponent(novelId)}/${chapterNumber}/${button.dataset.source}`;
    });
  });
  document.querySelector("#fontSize").addEventListener("input", (event) => {
    state.fontSize = Number(event.target.value);
    localStorage.setItem("gt-v10-font-size", String(state.fontSize));
    document.documentElement.style.setProperty("--reader-font", `${state.fontSize}px`);
  });
}

function renderReaderText(payload, source) {
  if (!payload.ok) {
    const message = payload.status === `${source}_missing`
      ? `${sourceLabels[source]} is not available for this chapter.`
      : (payload.message || "This chapter source is not available.");
    return `<div class="missing-state">${escapeHtml(message)}</div>`;
  }
  return paragraphs(payload.text).map((part) => `<p>${escapeHtml(part)}</p>`).join("");
}

function preferredSource(chapter) {
  if (chapter?.has_ai) return "ai";
  if (chapter?.has_reference) return "reference";
  return "original";
}

function findChapter(chapterNumber) {
  return state.chapters.find((chapter) => chapter.chapter_number === Number(chapterNumber));
}

function previousChapter(chapterNumber) {
  const index = state.chapters.findIndex((chapter) => chapter.chapter_number === Number(chapterNumber));
  return index > 0 ? state.chapters[index - 1].chapter_number : null;
}

function nextChapter(chapterNumber) {
  const index = state.chapters.findIndex((chapter) => chapter.chapter_number === Number(chapterNumber));
  return index >= 0 && index < state.chapters.length - 1 ? state.chapters[index + 1].chapter_number : null;
}

function sourceButton(source, active) {
  return `<button data-source="${source}" class="${source === active ? "active" : ""}" type="button">${sourceLabels[source]}</button>`;
}

function stat(label, value) {
  return `<div class="stat"><span>${escapeHtml(label)}</span><strong>${Number(value || 0).toLocaleString()}</strong></div>`;
}

function badge(label, ok) {
  return `<span class="badge ${ok ? "ok" : "missing"}">${escapeHtml(label)} ${ok ? "✓" : "missing"}</span>`;
}

function paragraphs(text) {
  return String(text || "").replace(/\r\n/g, "\n").split(/\n{2,}|\n/).map((part) => part.trim()).filter(Boolean);
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#039;",
  }[char]));
}

window.addEventListener("hashchange", route);
window.addEventListener("DOMContentLoaded", route);
