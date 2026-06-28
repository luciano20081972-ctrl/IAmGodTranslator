const state = {
  currentJobId: null,
  pollTimer: null,
};

const els = {
  apiStatus: document.querySelector("#apiStatus"),
  uploadForm: document.querySelector("#uploadForm"),
  chineseFiles: document.querySelector("#chineseFiles"),
  referenceFiles: document.querySelector("#referenceFiles"),
  chineseList: document.querySelector("#chineseList"),
  referenceList: document.querySelector("#referenceList"),
  maxTotalBudget: document.querySelector("#maxTotalBudget"),
  maxCostPerChapter: document.querySelector("#maxCostPerChapter"),
  stopWhenBudgetReached: document.querySelector("#stopWhenBudgetReached"),
  testChapterOnly: document.querySelector("#testChapterOnly"),
  showEstimateBeforeStarting: document.querySelector("#showEstimateBeforeStarting"),
  retryFailedChapters: document.querySelector("#retryFailedChapters"),
  submitButton: document.querySelector("#submitButton"),
  startTranslation: document.querySelector("#startTranslation"),
  estimatePanel: document.querySelector("#estimatePanel"),
  estimateSummary: document.querySelector("#estimateSummary"),
  estimateReportLink: document.querySelector("#estimateReportLink"),
  formMessage: document.querySelector("#formMessage"),
  refreshJobs: document.querySelector("#refreshJobs"),
  jobStatus: document.querySelector("#jobStatus"),
  jobCounts: document.querySelector("#jobCounts"),
  progressFill: document.querySelector("#progressFill"),
  chapterList: document.querySelector("#chapterList"),
  jobStrip: document.querySelector("#jobStrip"),
  downloadAll: document.querySelector("#downloadAll"),
};

function setMessage(text, isError = false) {
  els.formMessage.textContent = text;
  els.formMessage.classList.toggle("error", isError);
}

function renderFileList(input, list) {
  list.innerHTML = "";

  for (const file of input.files) {
    const li = document.createElement("li");
    li.textContent = file.name;
    list.appendChild(li);
  }
}

function statusLabel(status) {
  const labels = {
    queued: "Queued",
    running: "Running",
    completed: "Completed",
    failed: "Failed",
    estimated: "Estimated",
    test_completed: "Test Complete",
    budget_reached: "Budget Reached",
    skipped: "Skipped",
    pending: "Pending",
    translating: "Translating",
  };

  return labels[status] || status || "Unknown";
}

function formatDate(value) {
  if (!value) {
    return "";
  }

  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function completionPercent(job) {
  const total = job.counts?.total || 0;
  const completed = job.counts?.completed || 0;

  if (!total) {
    return 0;
  }

  return Math.round((completed / total) * 100);
}

function renderJob(job) {
  state.currentJobId = job.job_id;

  const total = job.counts.total;
  const completed = job.counts.completed;
  const failed = job.counts.failed;
  const percent = completionPercent(job);

  els.jobStatus.textContent = failed ? `${statusLabel(job.status)} - ${failed} failed` : statusLabel(job.status);
  els.jobCounts.textContent = `${completed} / ${total}`;
  els.progressFill.style.width = `${percent}%`;
  renderEstimate(job);

  if (completed > 0) {
    els.downloadAll.classList.remove("disabled");
    els.downloadAll.removeAttribute("aria-disabled");
    els.downloadAll.href = `/api/jobs/${job.job_id}/download`;
  } else {
    els.downloadAll.classList.add("disabled");
    els.downloadAll.setAttribute("aria-disabled", "true");
    els.downloadAll.href = "#";
  }

  els.chapterList.innerHTML = "";

  if (!job.chapters.length) {
    els.chapterList.innerHTML = '<div class="empty-state">No chapters in this job.</div>';
    return;
  }

  for (const chapter of job.chapters) {
    const row = document.createElement("article");
    row.className = "chapter-row";

    const main = document.createElement("div");
    main.className = "chapter-main";

    const title = document.createElement("div");
    title.className = "chapter-title";
    title.textContent = `${String(chapter.chapter).padStart(4, "0")} · ${chapter.title}`;

    const sub = document.createElement("div");
    sub.className = "chapter-sub";
    sub.textContent = chapter.error || (chapter.reference_file ? `Reference: ${chapter.reference_file}` : chapter.source_file);

    main.append(title, sub);

    const actions = document.createElement("div");
    actions.className = "chapter-actions";

    const pill = document.createElement("span");
    pill.className = `pill ${chapter.status}`;
    pill.textContent = statusLabel(chapter.status);

    actions.appendChild(pill);

    if (chapter.status === "completed") {
      const link = document.createElement("a");
      link.href = `/api/jobs/${job.job_id}/chapters/${chapter.chapter}/download`;
      link.title = "Download chapter";
      link.setAttribute("aria-label", `Download chapter ${chapter.chapter}`);
      link.textContent = "D";
      actions.appendChild(link);
    }

    row.append(main, actions);
    els.chapterList.appendChild(row);
  }
}

function renderHistory(jobs) {
  els.jobStrip.innerHTML = "";

  if (!jobs.length) {
    els.jobStrip.innerHTML = '<div class="empty-state">No recent jobs.</div>';
    return;
  }

  for (const job of jobs) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "job-card";
    card.classList.toggle("active", job.job_id === state.currentJobId);

    const main = document.createElement("div");
    const title = document.createElement("div");
    title.className = "job-card-title";
    title.textContent = statusLabel(job.status);

    const meta = document.createElement("div");
    meta.className = "job-card-meta";
    meta.textContent = `${job.counts.completed}/${job.counts.total} - ${formatDate(job.created_at)}`;

    const percent = document.createElement("strong");
    percent.textContent = `${completionPercent(job)}%`;

    main.append(title, meta);
    card.append(main, percent);

    card.addEventListener("click", () => {
      state.currentJobId = job.job_id;
      fetchJob(job.job_id);
    });

    els.jobStrip.appendChild(card);
  }
}

function formatCurrency(value) {
  return `$${Number(value || 0).toFixed(6)}`;
}

function renderEstimate(job) {
  if (!job.estimate) {
    els.estimatePanel.hidden = true;
    return;
  }

  const totals = job.estimate.totals;
  els.estimatePanel.hidden = false;
  els.estimateSummary.innerHTML = "";

  const metrics = [
    ["Chapters", totals.chapter_count],
    ["Input tokens", totals.input_tokens.toLocaleString()],
    ["Output tokens", totals.output_tokens.toLocaleString()],
    ["Cheapest total", formatCurrency(totals.cheapest_model_cost)],
    ["Recommended total", formatCurrency(totals.recommended_model_cost)],
    ["Cheapest with retries", formatCurrency(totals.cheapest_model_cost_with_retries)],
    ["Cheapest model", job.estimate.cheapest_model],
    ["Recommended", job.estimate.recommended_model],
  ];

  for (const [label, value] of metrics) {
    const item = document.createElement("div");
    item.className = "estimate-metric";
    item.innerHTML = `<span>${label}</span><strong>${value}</strong>`;
    els.estimateSummary.appendChild(item);
  }

  els.estimateReportLink.href = `/api/jobs/${job.job_id}/estimate-report`;
  const canStart = ["estimated", "queued", "test_completed", "budget_reached"].includes(job.status);
  els.startTranslation.disabled = !canStart;
}

async function checkHealth() {
  try {
    const response = await fetch("/api/health");

    if (!response.ok) {
      throw new Error("Server unavailable");
    }

    els.apiStatus.textContent = "Server online";
    els.apiStatus.classList.add("online");
  } catch (error) {
    els.apiStatus.textContent = "Server offline";
    els.apiStatus.classList.remove("online");
  }
}

async function fetchJobs() {
  const response = await fetch("/api/jobs");

  if (!response.ok) {
    throw new Error("Could not load jobs");
  }

  const data = await response.json();
  renderHistory(data.jobs);

  if (!state.currentJobId && data.jobs.length) {
    renderJob(data.jobs[0]);
  }
}

async function fetchJob(jobId) {
  const response = await fetch(`/api/jobs/${jobId}`);

  if (!response.ok) {
    throw new Error("Could not load job");
  }

  const job = await response.json();
  renderJob(job);
  await fetchJobs();

  if (["completed", "failed", "test_completed", "budget_reached"].includes(job.status)) {
    stopPolling();
  }
}

function startPolling(jobId) {
  stopPolling();
  state.pollTimer = window.setInterval(() => fetchJob(jobId).catch(() => {}), 1800);
}

function stopPolling() {
  if (state.pollTimer) {
    window.clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
}

async function submitJob(event) {
  event.preventDefault();
  setMessage("");

  if (!els.chineseFiles.files.length) {
    setMessage("Add at least one Chinese TXT or ZIP file.", true);
    return;
  }

  const body = new FormData();

  for (const file of els.chineseFiles.files) {
    body.append("chinese", file);
  }

  for (const file of els.referenceFiles.files) {
    body.append("references", file);
  }

  body.append("max_total_budget", els.maxTotalBudget.value);
  body.append("max_cost_per_chapter", els.maxCostPerChapter.value);
  body.append("stop_when_budget_reached", els.stopWhenBudgetReached.checked ? "true" : "false");
  body.append("test_chapter_only", els.testChapterOnly.checked ? "true" : "false");
  body.append("show_estimate_before_starting", els.showEstimateBeforeStarting.checked ? "true" : "false");
  body.append("retry_failed_chapters", els.retryFailedChapters.value || "1");

  els.submitButton.disabled = true;
  setMessage("Scanning chapters and estimating cost...");

  try {
    const response = await fetch("/api/jobs", {
      method: "POST",
      body,
    });

    const payload = await response.json();

    if (!response.ok) {
      throw new Error(payload.detail || "Upload failed");
    }

    renderJob(payload);
    await fetchJobs();
    setMessage("Cost estimate ready. Review it before starting translation.");
    els.uploadForm.reset();
    els.stopWhenBudgetReached.checked = true;
    els.testChapterOnly.checked = true;
    els.showEstimateBeforeStarting.checked = true;
    els.retryFailedChapters.value = "1";
    renderFileList(els.chineseFiles, els.chineseList);
    renderFileList(els.referenceFiles, els.referenceList);
  } catch (error) {
    setMessage(error.message, true);
  } finally {
    els.submitButton.disabled = false;
  }
}

async function startCurrentJob() {
  if (!state.currentJobId) {
    return;
  }

  els.startTranslation.disabled = true;
  setMessage("Starting translation...");

  try {
    const response = await fetch(`/api/jobs/${state.currentJobId}/start`, {
      method: "POST",
    });
    const payload = await response.json();

    if (!response.ok) {
      throw new Error(payload.detail || "Could not start translation");
    }

    startPolling(state.currentJobId);
    setMessage("Translation started.");
  } catch (error) {
    setMessage(error.message, true);
    els.startTranslation.disabled = false;
  }
}

els.chineseFiles.addEventListener("change", () => renderFileList(els.chineseFiles, els.chineseList));
els.referenceFiles.addEventListener("change", () => renderFileList(els.referenceFiles, els.referenceList));
els.uploadForm.addEventListener("submit", submitJob);
els.startTranslation.addEventListener("click", startCurrentJob);
els.refreshJobs.addEventListener("click", () => fetchJobs().catch(() => setMessage("Could not refresh jobs.", true)));

checkHealth();
fetchJobs().catch(() => {});

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/service-worker.js").catch(() => {});
  });
}
