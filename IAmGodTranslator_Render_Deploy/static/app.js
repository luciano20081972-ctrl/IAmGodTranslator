const app = document.querySelector("#app");

app.innerHTML = `
<div class="app-shell">
  <header class="topbar">
    <button class="brand" id="homeButton" type="button">
      <span class="brand-mark" id="brandMark">IG</span>
      <span><strong id="brandName">GodTranslator</strong><small id="brandSubtitle">Novel Library</small></span>
    </button>
    <nav class="main-nav" aria-label="Primary">
      <button class="nav-button active" data-main-nav="home" type="button"><span>&#8962;</span> Home</button>
      <button class="nav-button" data-main-nav="library" type="button"><span>&#9635;</span> Library</button>
      <button class="nav-button" data-main-nav="browse" type="button"><span>&#9638;</span> Browse</button>
      <button class="nav-button" data-main-nav="rankings" type="button"><span>&#9734;</span> Rankings</button>
      <button class="nav-button" data-main-nav="updates" type="button"><span>&#9687;</span> Updates</button>
      <button class="nav-button" data-main-nav="reader" type="button"><span>&#9636;</span> Reader</button>
      <button class="nav-button admin-only" data-main-nav="translate" type="button"><span>&#9889;</span> Translate</button>
      <button class="nav-button admin-only" data-main-nav="backups" type="button"><span>&#8681;</span> Backups</button>
      <button class="nav-button admin-only" data-main-nav="settings" type="button"><span>&#9881;</span> Admin</button>
    </nav>
    <nav class="header-links">
      <label class="global-search"><span>Search</span><input id="globalSearch" type="search" placeholder="Search novels or chapters"></label>
      <span class="current-novel-pill" id="currentNovelPill" hidden>Library</span>
      <button class="secondary-button contextual-action" id="quickReaderButton" type="button">Open Reader</button>
      <button class="secondary-button admin-only" id="quickTranslateButton" type="button">Continue Translating</button>
      <a class="secondary-button admin-only" id="quickBackupButton" href="#">Download Backup</a>
      <button class="link-button" id="supportButton" type="button">Thanks</button>
      <span class="status-chip" id="apiStatus">Checking</span>
      <button class="secondary-button" id="accountButton" type="button">Login</button>
      <button class="primary-button" id="registerButton" type="button">Register</button>
      <button class="secondary-button" id="adminButton" type="button">Admin</button>
      <button class="icon-button" id="themeToggle" type="button" aria-label="Toggle theme">&#9790;</button>
    </nav>
  </header>
  <nav class="workspace-tabs" id="workspaceTabs" aria-label="Open workspaces"></nav>
  <nav class="breadcrumb" id="breadcrumb">Home</nav>
  <nav class="admin-bar admin-only" id="adminBar" aria-label="Admin tools"><span>Admin Control Panel</span><button type="button" data-admin-tab="translate">Translate</button><button type="button" data-admin-tab="backups">Backups</button><button type="button" data-admin-tab="settings">Settings</button><button type="button" data-admin-tab="chapters">Novel Management</button></nav>
  <main>
    <section class="view active" id="libraryView">
      <div class="library-hero">
        <div class="library-title">
          <div class="library-icon" id="libraryIcon">IG</div>
          <div><p class="eyebrow">Home</p><h1>GodTranslator</h1><p class="hero-copy">Read translated novels, AI-assisted translations, and curated web novels in a polished private library.</p><div class="hero-actions"><button class="primary-button" data-home-browse type="button">Browse Novels</button><button class="secondary-button" data-home-continue type="button">Continue Reading</button><button class="secondary-button" data-home-login type="button">Login</button></div></div>
        </div>
        <button class="primary-button admin-only" id="addNovelButton" type="button">Add New Novel</button>
      </div>
      <div class="support-panel" id="supportPanel" hidden>
        <h2>Thanks</h2>
        <p>Thank you to everyone reading, testing, and helping this library get steadier chapter by chapter.</p>
      </div>
      <div class="library-sections" id="librarySections"></div>
      <div class="toolbar" id="libraryToolbar"><label><span>Search</span><input id="novelSearch" type="search" placeholder="Search novels by title"></label><label><span>Filter</span><select id="browseFilter"><option value="all">All</option><option value="in-progress">In Progress</option><option value="completed">Completed</option><option value="has-reference">Has Reference Translation</option><option value="missing-reference">Missing Reference Translation</option><option value="has-ai">Has AI Translation</option><option value="needs-translation">Needs Translation</option><option value="bookmarked">My Library / Bookmarked</option><option value="recently-read">Recently Read</option></select></label><label><span>Sort</span><select id="novelSort"><option value="updated">Last updated</option><option value="name">Name</option><option value="progress">Progress</option><option value="rating">Rating</option><option value="translated">AI Translation count</option><option value="remaining">Remaining count</option></select></label></div>
      <div class="novel-grid" id="novelGrid"><div class="empty-state">Loading library...</div></div>
      <footer class="site-footer"><div><strong>GodTranslator</strong><p>Novel reading and private translation platform.</p></div><nav><button class="link-button" data-footer-nav="library" type="button">Library</button><button class="link-button" data-footer-nav="rankings" type="button">Rankings</button><button class="link-button" data-footer-nav="updates" type="button">Updates</button><button class="link-button" data-footer-nav="reader" type="button">Reader</button><button class="link-button admin-only" data-footer-nav="backups" type="button">Backups</button><button class="link-button admin-only" data-footer-nav="settings" type="button">Admin</button></nav><div class="footer-tags"><button type="button" data-category="Fantasy">Fantasy</button><button type="button" data-category="Sci-fi">Sci-fi</button><button type="button" data-category="Mystery">Mystery</button><button type="button" data-category="Romance">Romance</button><button type="button" data-category="Martial Arts">Martial Arts</button><button type="button" data-category="Supernatural">Supernatural</button><button type="button" data-category="Slice of Life">Slice of Life</button><button type="button" data-category="Completed">Completed</button></div></footer>
    </section>

    <section class="view" id="detailView">
      <div class="novel-hero">
        <button class="secondary-button" id="backToLibrary" type="button">Library</button>
        <div class="dashboard-cover" id="dashboardCover">IG</div>
        <div class="novel-summary-block">
          <p class="eyebrow">Novel Detail</p>
          <h1 id="novelTitle">Novel</h1>
          <p id="novelSummary" class="novel-summary">No summary yet.</p>
          <div class="rating-row"><button class="bookmark-button" id="novelBookmarkButton" type="button">Bookmark</button><div class="star-rating" id="novelRating" aria-label="Novel rating"></div></div>
          <div class="tag-row" id="novelTags"></div>
          <div class="hero-actions">
            <button class="primary-button" id="continueReadingButton" type="button">Continue Reading</button>
            <button class="secondary-button" id="openChaptersButton" type="button">Open Chapters</button>
            <button class="secondary-button admin-only" id="refreshNovelButton" type="button">Refresh Novel Data</button>
          </div>
          <div class="progress-track hero-progress"><div id="novelProgress" class="progress-fill"></div></div>
        </div>
      </div>
      <div class="metrics-grid"><div><span>Chapters</span><strong id="metricOriginal">0</strong></div><div><span>Reference</span><strong id="metricReference">0</strong></div><div><span>Translated</span><strong id="metricTranslated">0</strong></div><div><span>Remaining</span><strong id="metricRemaining">0</strong></div><div><span>Progress</span><strong id="metricPercent">0%</strong></div><div><span>Last updated</span><strong id="metricUpdated">Never</strong></div><div class="admin-only"><span>Last backup</span><strong id="metricBackup">Never</strong></div><div class="admin-only"><span>Model</span><strong id="metricModel">gpt-4o-mini</strong></div><div><span>Status</span><strong id="metricStatus">Ready</strong></div><div class="admin-only"><span>Storage</span><strong id="metricStorage">-</strong></div></div>
      <nav class="tabs"><button class="tab active" data-tab="overview" type="button">Overview</button><button class="tab" data-tab="chapters" type="button">Chapters</button><button class="tab" data-tab="reader" type="button">Reader</button><button class="tab admin-only" data-tab="translate" type="button">Translate</button><button class="tab admin-only" data-tab="backups" type="button">Backups</button><button class="tab admin-only" data-tab="settings" type="button">Admin Settings</button></nav>

      <section class="tab-panel active" id="overviewPanel">
        <div class="overview-grid">
          <section class="panel feature-panel"><p class="eyebrow">Reading</p><h2>Continue your novel</h2><p class="helper">Choose Original Story, Reference Translation, or AI Translation manually in Reader. The app will not switch modes for you.</p><button class="primary-button" id="overviewReaderButton" type="button">Open Reader</button></section>
          <section class="panel feature-panel admin-only"><p class="eyebrow">Translation workflow</p><h2>Safe batch flow</h2><ol class="workflow-list"><li>Upload Original Story.</li><li>Upload Reference Translation if available.</li><li>Show cost estimate.</li><li>Translate a safe batch.</li><li>Check Reader.</li><li>Download AI ZIP and Full Backup ZIP.</li></ol><button class="secondary-button" id="overviewTranslateButton" type="button">Open Translate</button></section>
          <section class="panel feature-panel admin-only"><p class="eyebrow">Protection</p><h2>Backup after every batch</h2><p class="helper">Render free storage may reset after redeploy or restart. Download a full backup whenever chapters change.</p><button class="secondary-button" id="overviewBackupButton" type="button">Open Backups</button></section>
        </div>
      </section>

      <section class="tab-panel" id="chaptersPanel">
        <div class="toolbar chapter-toolbar"><label><span>Search chapters</span><input id="chapterSearch" type="search" placeholder="Chapter number or title"></label><label><span>Filter</span><select id="chapterFilter"><option value="all">All</option><option value="has-original">Has Original Story</option><option value="has-reference">Has Reference Translation</option><option value="has-ai">Has AI Translation</option><option value="missing-ai">Missing AI Translation</option><option value="missing-reference">Missing Reference Translation</option><option value="bookmarked">Bookmarked</option><option value="recently-read">Recently Read</option><option value="ready">Ready to Translate</option><option value="failed">Failed</option></select></label><label><span>Sort</span><select id="chapterSort"><option value="asc">Oldest first</option><option value="desc">Newest first</option><option value="missing-ai">Missing AI first</option><option value="translated">Translated first</option><option value="title">Title</option></select></label><label><span>Page size</span><select id="chapterPageSize"><option value="25">25</option><option value="50" selected>50</option><option value="100">100</option><option value="200">200</option></select></label><label><span>Jump to chapter</span><input id="chapterJump" type="number" min="1" placeholder="26"></label></div>
        <div class="bulk-actions"><button class="secondary-button" id="selectMissingAi" type="button">Select missing AI</button><button class="secondary-button" id="selectCurrentPage" type="button">Select current page</button><button class="secondary-button" id="clearSelectedChapters" type="button">Clear selection</button><span id="selectedChapterCount">0 selected</span></div>
        <div class="pager"><button class="secondary-button" id="prevPage" type="button">Previous page</button><span id="pageInfo">Page 1</span><button class="secondary-button" id="nextPage" type="button">Next page</button></div>
        <div class="chapter-list" id="chapterList"></div>
      </section>

      <section class="tab-panel" id="readerPanel">
        <div class="reader-shell" id="readerShell">
          <div class="reader-toolbar"><button class="secondary-button" id="readerBack" type="button">Back to Novel</button><button class="secondary-button" id="readerLibrary" type="button">Back to Library</button><div class="reader-controls"><button class="secondary-button" id="chapterPickerButton" type="button">Chapters</button><button class="secondary-button" id="readerBookmarkButton" type="button">Bookmark</button><button class="secondary-button compact-control" id="fontDown" type="button" title="Decrease font">A-</button><button class="secondary-button compact-control" id="fontUp" type="button" title="Increase font">A+</button><button class="secondary-button compact-control" id="widthToggle" type="button" title="Toggle page width">Width</button><select id="readerTheme" title="Reader theme"><option value="paper">Paper</option><option value="dark">Dark</option><option value="sepia">Sepia</option><option value="oled">OLED Black</option><option value="green">Green Night</option><option value="gold">Golden Dark</option></select><button class="secondary-button compact-control" id="readerSettingsButton" type="button" title="Reader settings">Settings</button><button class="secondary-button compact-control" id="fullscreenReader" type="button" title="Focus mode">Focus</button></div></div>
          <div class="reader-nav"><button class="secondary-button" id="prevChapter" type="button">Previous</button><button class="chapter-select-button" id="centerChapterPicker" type="button"><p class="eyebrow" id="readerChapterNumber">Chapter</p><h2 id="readerChapterTitle">Open a chapter</h2><p class="reader-progress" id="readerProgress">Choose a chapter to begin.</p></button><button class="secondary-button" id="nextChapter" type="button">Next</button></div>
          <div class="reader-tabs"><button class="reader-tab active" data-reader-tab="original" type="button">Original Story</button><button class="reader-tab" data-reader-tab="reference" type="button">Reference Translation</button><button class="reader-tab" data-reader-tab="ai" type="button">AI Translation</button></div>
          <aside class="chapter-picker" id="chapterPickerPanel" hidden></aside>
          <aside class="reader-settings-drawer" id="readerSettingsDrawer" hidden><div class="drawer-head"><h2>Reader Settings</h2><button class="icon-button" id="closeReaderSettings" type="button">x</button></div><label><span>Font family</span><select id="readerFontFamily"><option value="default">Default</option><option value="dyslexic">Dyslexic fallback</option><option value="system">Roboto/system</option><option value="serif">Lora/serif</option></select></label><label><span>Font size</span><input id="readerFontSize" type="range" min="14" max="34" value="19"></label><label><span>Line height</span><input id="readerLineHeight" type="range" min="1.2" max="2" step="0.05" value="1.9"></label><label><span>Paragraph spacing</span><input id="readerParagraphSpacing" type="range" min="0" max="32" value="14"></label><label><span>Page width</span><select id="readerPageWidth"><option value="680px">Narrow</option><option value="820px">Normal</option><option value="1040px">Wide</option></select></label><label><span>Text alignment</span><select id="readerTextAlign"><option value="left">Left</option><option value="center">Center</option><option value="justify">Justify</option></select></label><label><span>Reader background</span><select id="readerBackground"><option value="#0f1513">Dark</option><option value="#202426">Soft gray</option><option value="#211b13">Sepia brown</option><option value="#111d14">Dark olive</option><option value="#0d1728">Dark navy</option></select></label><label><span>Highlight color</span><input id="readerAccent" type="color" value="#68d1b4"></label><label class="check"><input id="readerAllowCopy" type="checkbox" checked> Allow copy/text selection</label></aside>
          <article class="reader-content" id="readerContent">Select a chapter from the chapter library.</article>
          <div class="reader-bottom-nav"><button class="secondary-button" id="prevChapterBottom" type="button">Previous Chapter</button><button class="secondary-button" id="chapterPickerBottom" type="button">Chapter Selector</button><button class="secondary-button" id="nextChapterBottom" type="button">Next Chapter</button><button class="secondary-button" id="backToTopButton" type="button">Back to top</button></div>
        </div>
      </section>

      <section class="tab-panel admin-only" id="translatePanel">
        <div class="workflow-card"><strong>Recommended workflow:</strong> Upload Original Story, add Reference Translation if available, show the cost estimate, translate a safe batch, verify in Reader, then download AI ZIP and Full Backup ZIP.</div>
        <div class="translate-grid">
          <form class="panel" id="originalUploadForm"><h2>Original Story Upload</h2><p class="helper">Original Story is the source of truth for translation.</p><input id="originalFiles" name="original" type="file" accept=".txt,.zip,text/plain,application/zip" multiple required><button class="primary-button" type="submit">Upload Original Story</button></form>
          <form class="panel" id="referenceUploadForm"><h2>Reference Translation Upload</h2><p class="helper">Reference Translation is optional support text.</p><input id="referenceFiles" name="reference" type="file" accept=".txt,.zip,text/plain,application/zip" multiple><button class="secondary-button" type="submit">Upload Reference Translation</button></form>
        </div>
        <div class="translate-grid">
          <form class="panel settings-grid" id="batchForm"><h2>Batch Settings</h2><label><span>Model</span><select id="model"><option value="gpt-4o-mini">gpt-4o-mini</option></select></label><label><span>Max total budget</span><input id="maxTotalBudget" type="number" step="0.01" min="0" value="15.00"></label><label><span>Max per-chapter budget</span><input id="maxCostPerChapter" type="number" step="0.001" min="0" value="0.017"></label><label><span>Retry limit</span><input id="retryFailedChapters" type="number" min="0" max="1" value="1"></label><label><span>Batch size</span><input id="batchSize" type="number" min="1" max="200" value="25"></label><label class="check"><input id="stopWhenBudgetReached" type="checkbox" checked> Stop when budget reached</label></form>
          <section class="panel"><h2>Batch Actions</h2><div class="warning">Paid translation warning: starting a batch calls the OpenAI API and may spend money. This will only translate chapters missing AI Translation.</div><p class="helper">Recommended safe batch: 50 chapters. Bigger batches cost more and take longer.</p><div class="actions"><button class="secondary-button" id="estimateBatch" type="button">Show Cost Estimate</button><button class="primary-button" id="startBatch" type="button" disabled>Start Batch</button></div></section>
        </div>
        <section class="panel"><h2>Cost Estimate & Queue Preview</h2><div class="estimate-box" id="estimateBox">No batch estimate yet.</div><div class="progress-track"><div id="jobProgress" class="progress-fill"></div></div><div class="chapter-list compact" id="queueList"></div></section>
      </section>

      <section class="tab-panel admin-only" id="backupsPanel"><div class="warning storage-warning">Backup and restore run as background jobs. Do not refresh during backup/restore.</div><div class="backup-summary" id="backupSummary">Current counts will appear after a novel loads.</div><section class="panel backup-job-panel"><h2>Full Backup Job</h2><p class="helper">Creates a manifest-based ZIP without blocking the web request.</p><div class="actions"><button class="primary-button" id="startFullBackupButton" type="button">Create Full Backup</button><button class="secondary-button" id="cancelFullBackupButton" type="button" disabled>Cancel Backup</button><button class="secondary-button" id="refreshBackupJobsButton" type="button">Refresh Jobs</button></div><div class="progress-track"><div class="progress-fill" id="backupJobProgress"></div></div><div class="estimate-box" id="backupJobStatus">No backup job running.</div></section><div class="backup-grid"><a class="panel link-card" id="downloadEnglish" href="#">Export AI ZIP</a><a class="panel link-card" id="downloadOriginal" href="#">Export Original ZIP</a><a class="panel link-card" id="downloadReference" href="#">Export Reference ZIP</a><a class="panel link-card" id="downloadPrompts" href="#">Export Prompts ZIP</a><form class="panel" id="restoreNovelForm"><h2>Restore Full Backup ZIP</h2><p class="helper">Run dry-run first. Real restore never deletes files and only overwrites when selected.</p><input id="restoreFile" name="backup" type="file" accept=".zip,application/zip" required><label><span>Conflict mode</span><select id="restoreConflictMode"><option value="write_missing_only">Write missing only</option><option value="skip_existing">Skip existing</option><option value="overwrite_existing">Overwrite existing</option></select></label><div class="actions"><button class="secondary-button" id="restoreDryRunButton" type="submit">Dry Run Restore</button><button class="danger-button" id="restoreConfirmButton" type="button" disabled>Confirm Restore</button></div><div class="progress-track"><div class="progress-fill" id="restoreJobProgress"></div></div><div class="estimate-box" id="restoreJobStatus">No restore job running.</div></form><section class="panel"><h2>Recent Backup/Restore Jobs</h2><div class="job-history-list" id="backupJobList">No recent jobs loaded.</div></section><form class="panel" id="importAiForm"><h2>Import AI Translation ZIP</h2><p class="helper">Do not refresh during imports. This writes AI translations only.</p><input id="importAiFile" name="translated_zip" type="file" accept=".zip,application/zip" required><button class="primary-button" id="importAiButton" type="submit">Import AI Translation ZIP</button></form><form class="panel" id="importOriginalForm"><h2>Import Original Chinese ZIP</h2><p class="helper">Do not refresh during imports. This writes original source chapters only.</p><input id="importOriginalFile" name="original_zip" type="file" accept=".zip,application/zip" required><button class="primary-button" id="importOriginalButton" type="submit">Import Original Chinese ZIP</button></form><form class="panel" id="importReferenceForm"><h2>Import Reference Translation ZIP</h2><p class="helper">Do not refresh during imports. This writes reference translations only.</p><input id="importReferenceFile" name="reference_zip" type="file" accept=".zip,application/zip" required><button class="secondary-button" id="importReferenceButton" type="submit">Import Reference Translation ZIP</button></form><form class="panel" id="coverUploadForm"><h2>Novel Cover</h2><input id="coverFile" name="cover" type="file" accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp" required><button class="secondary-button" type="submit">Upload Cover</button></form></div></section>

      <section class="tab-panel admin-only" id="settingsPanel">
        <section class="admin-dashboard" id="adminDashboard"><div class="admin-dashboard-head"><div><p class="eyebrow">Private control room</p><h2>Admin Dashboard</h2><p class="helper">Manage storage, imports, backups, repair tools, users, and novel settings without crowding the reader experience.</p></div><div class="admin-metrics" id="adminMetrics">Open Storage Health to refresh platform status.</div></div><div class="admin-card-grid"><section class="panel admin-card"><p class="eyebrow">Quick Actions</p><h3>Workspace shortcuts</h3><div class="action-stack"><button class="secondary-button" type="button" data-admin-tab="chapters">Novel Management</button><button class="secondary-button" type="button" data-admin-tab="translate">Translation Tools</button><button class="secondary-button" type="button" data-admin-tab="backups">Backups / Restore</button></div></section><section class="panel admin-card"><p class="eyebrow">Storage Health</p><h3>Persistence check</h3><div class="actions"><button class="secondary-button" id="checkStorageButton" type="button">Check Storage</button><button class="secondary-button" id="migrateStorageButton" type="button">Copy old local data into DATA_DIR</button><button class="primary-button" id="migrateSupabaseButton" type="button">Migrate Local Data to Supabase</button></div><div class="storage-health" id="storageHealth">Storage health has not been checked yet.</div></section><section class="panel admin-card"><p class="eyebrow">Data Repair</p><h3>Audit and safe repair</h3><div class="actions"><button class="secondary-button" id="auditContentButton" type="button">Audit Novel Files</button><button class="secondary-button" id="dryRunRepairButton" type="button">Dry Run Repair</button><button class="danger-button" id="applyRepairButton" type="button">Apply Safe Repair</button></div><div class="estimate-box" id="repairReport">No audit has been run.</div></section><section class="panel admin-card"><p class="eyebrow">Users / Roles</p><h3>Account controls</h3><div class="user-list" id="adminUsersList">User list loads after admin login.</div></section></div></section>
        <form class="panel settings-grid" id="novelSettingsForm"><h2>Novel Management / Settings</h2><label><span>Novel title</span><input id="settingsTitle" type="text"></label><label><span>Source language</span><input id="sourceLanguage" type="text" value="Chinese"></label><label><span>Target language</span><input id="targetLanguage" type="text" value="English"></label><label><span>Default model</span><input id="defaultModel" type="text" value="gpt-4o-mini"></label><label><span>Tags, comma separated</span><input id="settingsTags" type="text"></label><label class="wide-field"><span>Summary</span><textarea id="settingsSummary" rows="4"></textarea></label><label><span>App version</span><input value="7.0 final UI polish" disabled></label><label><span>Storage mode</span><input id="storageModeDisplay" type="text" disabled></label><label><span>DATA_DIR</span><input id="dataDirDisplay" type="text" disabled></label><button class="primary-button" type="submit">Save Settings</button></form>
        <form class="panel settings-grid" id="appIconForm"><h2>Upload App / Library Icon</h2><input id="appIconFile" name="icon" type="file" accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp" required><button class="secondary-button" type="submit">Upload App / Library Icon</button></form>
        <form class="panel settings-grid" id="appAppearanceForm"><h2>App Appearance</h2><label><span>App display name</span><input id="appDisplayName" type="text"></label><label><span>App subtitle</span><input id="appSubtitleInput" type="text"></label><label><span>Main accent</span><input id="themeMainAccent" type="color"></label><label><span>Button/highlight</span><input id="themeHighlight" type="color"></label><label><span>Header/logo accent</span><input id="themeLogoAccent" type="color"></label><label><span>Card background</span><input id="themeCardBackground" type="color"></label><label><span>Page background</span><input id="themePageBackground" type="color"></label><label><span>Reader background default</span><input id="themeReaderBackground" type="color"></label><label><span>Reader text default</span><input id="themeReaderText" type="color"></label><div class="actions"><button class="primary-button" type="submit">Save Appearance</button><button class="secondary-button" id="resetThemeButton" type="button">Reset Theme</button></div></form>
      </section>
    </section>
  </main>
  <section class="app-recovery" id="appRecovery" hidden>
    <div class="recovery-card">
      <p class="eyebrow">Connection Recovery</p>
      <h2>GodTranslator could not finish loading.</h2>
      <p id="recoveryMessage">The server did not respond. Render may still be waking up or restarting. Try again in a moment.</p>
      <div class="actions">
        <button class="primary-button" id="recoveryRetry" type="button">Retry</button>
        <button class="secondary-button" id="recoveryCheckHealth" type="button">Check Health</button>
        <button class="secondary-button" id="recoveryClearCache" type="button">Clear Local Cache</button>
        <a class="secondary-button" id="recoveryHealthLink" href="/api/health" target="_blank" rel="noreferrer">Open /api/health</a>
      </div>
      <details><summary>Technical details</summary><pre id="recoveryDetails"></pre></details>
    </div>
  </section>
  <div class="toast" id="toast" role="status" aria-live="polite"></div>
</div>
<dialog id="addNovelDialog"><form id="addNovelForm"><h2>Add New Novel</h2><label><span>Title</span><input id="newNovelTitle" type="text" required></label><div class="actions"><button class="secondary-button" id="cancelAddNovel" type="button">Cancel</button><button class="primary-button" type="submit">Create</button></div></form></dialog>
<dialog id="accountDialog"><form id="accountForm"><h2 id="accountTitle">Login</h2><p class="helper" id="accountMessage">Use an account to sync bookmarks, ratings, and reading history.</p><label><span>Email</span><input id="accountEmail" type="email" autocomplete="email" required></label><label id="accountUsernameWrap" hidden><span>Username</span><input id="accountUsername" type="text" autocomplete="username"></label><label><span>Password</span><input id="accountPassword" type="password" autocomplete="current-password" required></label><label id="accountConfirmWrap" hidden><span>Confirm password</span><input id="accountConfirm" type="password" autocomplete="new-password"></label><div class="actions"><button class="secondary-button" id="forgotPasswordButton" type="button">Forgot Password</button><button class="secondary-button" id="accountModeButton" type="button">Create account</button><button class="primary-button" id="accountSubmitButton" type="submit">Login</button></div><div class="actions account-user-actions" id="accountUserActions" hidden><button class="secondary-button" id="resendVerificationButton" type="button">Resend Verification</button><button class="secondary-button" id="logoutAccountButton" type="button">Logout</button></div><p class="helper">Google login not configured yet. Production OAuth can be enabled later with Google environment variables.</p></form></dialog>
<dialog id="adminDialog"><form method="dialog" id="adminForm"><h2>Admin Login</h2><p class="helper" id="adminHelp">Admin tools are private.</p><label><span>Password</span><input id="adminPassword" type="password" autocomplete="current-password"></label><div class="actions"><button class="secondary-button" value="cancel">Cancel</button><button class="primary-button" value="default">Login</button></div></form></dialog>`;

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));
const state = { novels: [], appInfo: {}, admin: { enabled: false, authenticated: false }, auth: { authenticated: false, user: null }, accountMode: "login", workspaces: [{ id: "library", type: "library", title: "Library" }], activeWorkspaceId: "library", libraryMode: "home", currentNovel: null, chapters: [], filteredChapters: [], selectedChapters: new Set(), readerChapter: null, readerTab: "original", currentJob: null, pollTimer: null, backupJobId: null, backupPollTimer: null, restoreJobId: null, restorePollTimer: null, restoreDryRunComplete: false, readerSize: 18, readerWide: false, chapterPage: 1, pageSize: 50, pickerPage: 1, pickerPageSize: 50, pickerSearch: "", pickerNewest: false, searchTimer: null, readerPrefs: {}, ratings: {}, bookmarks: { novels: {}, chapters: {} }, history: {} };

const els = {
  apiStatus: $("#apiStatus"), homeButton: $("#homeButton"), themeToggle: $("#themeToggle"), globalSearch: $("#globalSearch"), brandMark: $("#brandMark"), brandName: $("#brandName"), brandSubtitle: $("#brandSubtitle"), libraryIcon: $("#libraryIcon"), workspaceTabs: $("#workspaceTabs"), breadcrumb: $("#breadcrumb"), accountButton: $("#accountButton"), registerButton: $("#registerButton"), accountDialog: $("#accountDialog"), accountForm: $("#accountForm"), accountTitle: $("#accountTitle"), accountMessage: $("#accountMessage"), accountEmail: $("#accountEmail"), accountUsername: $("#accountUsername"), accountUsernameWrap: $("#accountUsernameWrap"), accountPassword: $("#accountPassword"), accountConfirm: $("#accountConfirm"), accountConfirmWrap: $("#accountConfirmWrap"), accountModeButton: $("#accountModeButton"), accountSubmitButton: $("#accountSubmitButton"), forgotPasswordButton: $("#forgotPasswordButton"), accountUserActions: $("#accountUserActions"), resendVerificationButton: $("#resendVerificationButton"), logoutAccountButton: $("#logoutAccountButton"), adminButton: $("#adminButton"), adminDialog: $("#adminDialog"), adminForm: $("#adminForm"), adminPassword: $("#adminPassword"), adminHelp: $("#adminHelp"), supportButton: $("#supportButton"), supportPanel: $("#supportPanel"), mainNav: $$(".nav-button"), currentNovelPill: $("#currentNovelPill"), quickReaderButton: $("#quickReaderButton"), quickTranslateButton: $("#quickTranslateButton"), quickBackupButton: $("#quickBackupButton"),
  libraryView: $("#libraryView"), detailView: $("#detailView"), librarySections: $("#librarySections"), libraryToolbar: $("#libraryToolbar"), novelGrid: $("#novelGrid"), novelSearch: $("#novelSearch"), browseFilter: $("#browseFilter"), novelSort: $("#novelSort"), addNovelButton: $("#addNovelButton"), addNovelDialog: $("#addNovelDialog"), addNovelForm: $("#addNovelForm"), cancelAddNovel: $("#cancelAddNovel"), newNovelTitle: $("#newNovelTitle"),
  backToLibrary: $("#backToLibrary"), dashboardCover: $("#dashboardCover"), novelTitle: $("#novelTitle"), novelSummary: $("#novelSummary"), novelTags: $("#novelTags"), novelBookmarkButton: $("#novelBookmarkButton"), novelRating: $("#novelRating"), continueReadingButton: $("#continueReadingButton"), openChaptersButton: $("#openChaptersButton"), refreshNovelButton: $("#refreshNovelButton"), overviewReaderButton: $("#overviewReaderButton"), overviewTranslateButton: $("#overviewTranslateButton"), overviewBackupButton: $("#overviewBackupButton"), novelProgress: $("#novelProgress"), backupSummary: $("#backupSummary"), metricStorage: $("#metricStorage"), metricOriginal: $("#metricOriginal"), metricReference: $("#metricReference"), metricTranslated: $("#metricTranslated"), metricRemaining: $("#metricRemaining"), metricPercent: $("#metricPercent"), metricUpdated: $("#metricUpdated"), metricBackup: $("#metricBackup"), metricModel: $("#metricModel"), metricStatus: $("#metricStatus"),
  chapterSearch: $("#chapterSearch"), chapterFilter: $("#chapterFilter"), chapterSort: $("#chapterSort"), chapterPageSize: $("#chapterPageSize"), chapterJump: $("#chapterJump"), chapterList: $("#chapterList"), selectMissingAi: $("#selectMissingAi"), selectCurrentPage: $("#selectCurrentPage"), clearSelectedChapters: $("#clearSelectedChapters"), selectedChapterCount: $("#selectedChapterCount"), prevPage: $("#prevPage"), nextPage: $("#nextPage"), pageInfo: $("#pageInfo"),
  readerPanel: $("#readerPanel"), readerBack: $("#readerBack"), readerLibrary: $("#readerLibrary"), readerShell: $("#readerShell"), prevChapter: $("#prevChapter"), nextChapter: $("#nextChapter"), prevChapterBottom: $("#prevChapterBottom"), nextChapterBottom: $("#nextChapterBottom"), chapterPickerBottom: $("#chapterPickerBottom"), backToTopButton: $("#backToTopButton"), centerChapterPicker: $("#centerChapterPicker"), chapterPickerButton: $("#chapterPickerButton"), readerBookmarkButton: $("#readerBookmarkButton"), chapterPickerPanel: $("#chapterPickerPanel"), readerSettingsButton: $("#readerSettingsButton"), readerSettingsDrawer: $("#readerSettingsDrawer"), closeReaderSettings: $("#closeReaderSettings"), fullscreenReader: $("#fullscreenReader"), readerChapterNumber: $("#readerChapterNumber"), readerChapterTitle: $("#readerChapterTitle"), readerProgress: $("#readerProgress"), readerContent: $("#readerContent"), readerTheme: $("#readerTheme"), readerFontFamily: $("#readerFontFamily"), readerFontSize: $("#readerFontSize"), readerLineHeight: $("#readerLineHeight"), readerParagraphSpacing: $("#readerParagraphSpacing"), readerPageWidth: $("#readerPageWidth"), readerTextAlign: $("#readerTextAlign"), readerBackground: $("#readerBackground"), readerAccent: $("#readerAccent"), readerAllowCopy: $("#readerAllowCopy"), fontDown: $("#fontDown"), fontUp: $("#fontUp"), widthToggle: $("#widthToggle"),
  originalUploadForm: $("#originalUploadForm"), referenceUploadForm: $("#referenceUploadForm"), originalFiles: $("#originalFiles"), referenceFiles: $("#referenceFiles"), model: $("#model"), maxTotalBudget: $("#maxTotalBudget"), maxCostPerChapter: $("#maxCostPerChapter"), retryFailedChapters: $("#retryFailedChapters"), batchSize: $("#batchSize"), stopWhenBudgetReached: $("#stopWhenBudgetReached"), estimateBatch: $("#estimateBatch"), startBatch: $("#startBatch"), estimateBox: $("#estimateBox"), jobProgress: $("#jobProgress"), queueList: $("#queueList"),
  importOriginalForm: $("#importOriginalForm"), importOriginalFile: $("#importOriginalFile"), importOriginalButton: $("#importOriginalButton"), importReferenceForm: $("#importReferenceForm"), importReferenceFile: $("#importReferenceFile"), importReferenceButton: $("#importReferenceButton"), importAiForm: $("#importAiForm"), importAiFile: $("#importAiFile"), importAiButton: $("#importAiButton"), coverUploadForm: $("#coverUploadForm"), coverFile: $("#coverFile"), coverUploadButton: $("#coverUploadForm button[type='submit']"), downloadOriginal: $("#downloadOriginal"), downloadReference: $("#downloadReference"), downloadEnglish: $("#downloadEnglish"), downloadPrompts: $("#downloadPrompts"), startFullBackupButton: $("#startFullBackupButton"), cancelFullBackupButton: $("#cancelFullBackupButton"), refreshBackupJobsButton: $("#refreshBackupJobsButton"), backupJobProgress: $("#backupJobProgress"), backupJobStatus: $("#backupJobStatus"), backupJobList: $("#backupJobList"), restoreNovelForm: $("#restoreNovelForm"), restoreFile: $("#restoreFile"), restoreConflictMode: $("#restoreConflictMode"), restoreDryRunButton: $("#restoreDryRunButton"), restoreConfirmButton: $("#restoreConfirmButton"), restoreJobProgress: $("#restoreJobProgress"), restoreJobStatus: $("#restoreJobStatus"),
  adminMetrics: $("#adminMetrics"), storageHealth: $("#storageHealth"), checkStorageButton: $("#checkStorageButton"), migrateStorageButton: $("#migrateStorageButton"), migrateSupabaseButton: $("#migrateSupabaseButton"), rebuildIndexButton: $("#rebuildIndexButton"), auditContentButton: $("#auditContentButton"), dryRunRepairButton: $("#dryRunRepairButton"), applyRepairButton: $("#applyRepairButton"), repairReport: $("#repairReport"), adminUsersList: $("#adminUsersList"), novelSettingsForm: $("#novelSettingsForm"), settingsTitle: $("#settingsTitle"), settingsSummary: $("#settingsSummary"), settingsTags: $("#settingsTags"), sourceLanguage: $("#sourceLanguage"), targetLanguage: $("#targetLanguage"), defaultModel: $("#defaultModel"), storageModeDisplay: $("#storageModeDisplay"), dataDirDisplay: $("#dataDirDisplay"), appIconForm: $("#appIconForm"), appIconFile: $("#appIconFile"), appAppearanceForm: $("#appAppearanceForm"), appDisplayName: $("#appDisplayName"), appSubtitleInput: $("#appSubtitleInput"), themeMainAccent: $("#themeMainAccent"), themeHighlight: $("#themeHighlight"), themeLogoAccent: $("#themeLogoAccent"), themeCardBackground: $("#themeCardBackground"), themePageBackground: $("#themePageBackground"), themeReaderBackground: $("#themeReaderBackground"), themeReaderText: $("#themeReaderText"), resetThemeButton: $("#resetThemeButton"), appRecovery: $("#appRecovery"), recoveryMessage: $("#recoveryMessage"), recoveryDetails: $("#recoveryDetails"), recoveryRetry: $("#recoveryRetry"), recoveryCheckHealth: $("#recoveryCheckHealth"), recoveryClearCache: $("#recoveryClearCache"), toast: $("#toast")
};

const tabs = $$(".tab");
const panels = $$(".tab-panel");
const readerTabs = $$(".reader-tab");

function toast(message, error = false) { els.toast.textContent = message; els.toast.style.background = error ? "var(--danger)" : "var(--text)"; els.toast.classList.add("show"); clearTimeout(toast.timer); toast.timer = setTimeout(() => els.toast.classList.remove("show"), 3400); }
class ApiError extends Error {
  constructor(message, detail = {}) {
    super(message);
    this.name = "ApiError";
    Object.assign(this, detail);
    this.timestamp = detail.timestamp || new Date().toISOString();
  }
}
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
function friendlyApiMessage(status, rawMessage = "") {
  const text = String(rawMessage || "");
  if (status === "timeout" || /failed to fetch|networkerror|abort/i.test(text)) return "The server did not respond. Render may still be waking up or restarting. Try again in a moment.";
  if ([500, 502, 503, 504].includes(Number(status))) return "The server is temporarily unavailable. Render may be restarting or waking up. Try again in a moment.";
  if (status === "non-json") return "The server returned an unexpected response. Try again or check /api/health.";
  return text || `Request failed${status ? ` (${status})` : ""}.`;
}
async function api(path, options = {}) {
  const { timeoutMs = 30000, ...fetchOptions } = options;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const headers = fetchOptions.headers || {};
  try {
    const res = await fetch(path, { cache: fetchOptions.method ? "no-store" : "no-store", ...fetchOptions, headers, signal: controller.signal });
    const text = await res.text();
    let data = {};
    try {
      data = text ? JSON.parse(text) : {};
    } catch (_error) {
      throw new ApiError(friendlyApiMessage("non-json"), { endpoint: path, status: res.status || "non-json", raw: text.slice(0, 500) });
    }
    if (!res.ok) {
      const detail = data.detail || data.message || `Request failed: ${res.status}`;
      throw new ApiError(friendlyApiMessage(res.status, detail), { endpoint: path, status: res.status, data });
    }
    return data;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    const status = error.name === "AbortError" ? "timeout" : "network";
    throw new ApiError(friendlyApiMessage(status, error.message), { endpoint: path, status, technical: error.message || String(error) });
  } finally {
    clearTimeout(timer);
  }
}
async function apiWithRetry(path, options = {}, attempts = 3) {
  let lastError;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try { return await api(path, options); }
    catch (error) {
      lastError = error;
      if (attempt >= attempts || (error.status && !["network", "timeout", 500, 502, 503, 504].includes(error.status))) break;
      await sleep(600 * attempt);
    }
  }
  throw lastError;
}
function setBusy(button, busy) {
  if (!button) return;
  button.disabled = busy;
  button.classList.toggle("is-busy", busy);
}
async function withBusy(button, work) {
  setBusy(button, true);
  try { return await work(); }
  finally { setBusy(button, false); }
}
function showRecovery(error) {
  if (!els.appRecovery) return;
  const detail = {
    endpoint: error?.endpoint || "startup",
    status: error?.status || "unknown",
    message: error?.message || String(error || "Unknown error"),
    timestamp: error?.timestamp || new Date().toISOString(),
  };
  els.recoveryMessage.textContent = detail.message || "The server did not respond. Render may still be waking up or restarting. Try again in a moment.";
  els.recoveryDetails.textContent = JSON.stringify(detail, null, 2);
  els.appRecovery.hidden = false;
  els.apiStatus.textContent = "Offline";
  els.apiStatus.classList.remove("ok");
}
function hideRecovery() { if (els.appRecovery) els.appRecovery.hidden = true; }
async function clearFrontendCache() {
  if ("caches" in window) await caches.keys().then((keys) => Promise.all(keys.map((key) => caches.delete(key))));
  if ("serviceWorker" in navigator) await navigator.serviceWorker.getRegistrations().then((regs) => Promise.all(regs.map((reg) => reg.unregister())));
  toast("Frontend cache cleared. Retry loading the app.");
}
function esc(value) { return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char])); }
function date(value) { if (!value) return "Never"; try { return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(value)); } catch { return value; } }
function status(value) { return ({ completed: "translated", estimated: "queued", running: "translating", test_completed: "translated" }[value] || value || "unknown"); }
function money(value) { return `$${Number(value || 0).toFixed(4)}`; }

function setTheme(theme) { const dark = theme === "dark"; document.body.classList.toggle("dark", dark); document.body.classList.toggle("light", !dark); localStorage.setItem("igt-theme", dark ? "dark" : "light"); if (els.themeToggle) els.themeToggle.innerHTML = dark ? "&#9790;" : "&#9728;"; }
function updateMainNav(active = null) {
  const selected = active || (els.libraryView.classList.contains("active") ? state.libraryMode : activePanelName());
  els.mainNav.forEach((button) => button.classList.toggle("active", button.dataset.mainNav === selected));
  els.currentNovelPill.textContent = state.currentNovel ? state.currentNovel.title : "Library";
  els.quickBackupButton.href = "#";
  els.quickBackupButton.textContent = "Open Backups";
  els.quickReaderButton.hidden = !state.currentNovel;
  els.breadcrumb.innerHTML = state.currentNovel ? `<button type="button" data-crumb-home>Home</button><span>/</span><button type="button" data-crumb-library>Library</button><span>/</span><strong>${esc(state.currentNovel.title)}</strong>` : "<strong>Home</strong>";
  els.breadcrumb.querySelector("[data-crumb-home]")?.addEventListener("click", () => showLibrary());
  els.breadcrumb.querySelector("[data-crumb-library]")?.addEventListener("click", () => setLibraryMode("library", "bookmarked"));
}
function showView(name) { els.libraryView.classList.toggle("active", name === "library"); els.detailView.classList.toggle("active", name === "detail"); updateMainNav(name === "library" ? state.libraryMode : activePanelName()); }
function switchTab(tab) { if (!state.admin.authenticated && ["translate", "backups", "settings"].includes(tab)) { toast("Admin login required.", true); return; } tabs.forEach((button) => button.classList.toggle("active", button.dataset.tab === tab)); panels.forEach((panel) => panel.classList.toggle("active", panel.id === `${tab}Panel`)); updateMainNav(tab); if (tab === "backups" && state.admin.authenticated) refreshBackupJobs().catch((err) => toast(err.message, true)); if (tab === "settings" && state.admin.authenticated) { refreshStorageHealth().catch((err) => toast(err.message, true)); refreshAdminUsers().catch((err) => toast(err.message, true)); } }
function coverMarkup(novel, className = "cover") { return novel.cover_url ? `<img class="${className}" src="${esc(novel.cover_url)}" alt="">` : `<div class="${className} placeholder-cover"><span>${esc(novel.title.slice(0, 2).toUpperCase() || "IG")}</span></div>`; }
function renderIcon(container, url) { container.innerHTML = url ? `<img src="${esc(url)}" alt="">` : "<span>IG</span>"; }
function progressPercent(counts = {}) { const original = Number(counts.original_files || counts.total_chapters || 0); const translated = Number(counts.translated_chapters || 0); return original ? Math.min(100, Math.round((translated / original) * 100)) : 0; }
function loadLocalUiState() {
  try { state.ratings = JSON.parse(localStorage.getItem("igt-ratings") || "{}"); } catch { state.ratings = {}; }
  try { state.bookmarks = { novels: {}, chapters: {}, ...JSON.parse(localStorage.getItem("igt-bookmarks") || "{}") }; } catch { state.bookmarks = { novels: {}, chapters: {} }; }
  try { state.history = JSON.parse(localStorage.getItem("igt-reading-history") || "{}"); } catch { state.history = {}; }
}
function saveLocalUiState() { localStorage.setItem("igt-ratings", JSON.stringify(state.ratings)); localStorage.setItem("igt-bookmarks", JSON.stringify(state.bookmarks)); localStorage.setItem("igt-reading-history", JSON.stringify(state.history)); }
function applyBackendLibrary(data = {}) {
  if (!state.auth.authenticated) return;
  state.bookmarks = { novels: {}, chapters: {} };
  state.ratings = {};
  state.history = {};
  for (const item of data.novel_bookmarks || []) state.bookmarks.novels[item.novel_id] = true;
  for (const item of data.chapter_bookmarks || []) state.bookmarks.chapters[chapterKey(item.novel_id, item.chapter_number)] = true;
  for (const item of data.ratings || []) state.ratings[item.novel_id] = Number(item.rating);
  for (const item of data.reading_history || []) {
    const memory = { novel_id: item.novel_id, chapter: Number(item.chapter_number), mode: item.mode || "ai", updated_at: item.updated_at };
    state.history[chapterKey(item.novel_id, item.chapter_number)] = memory;
    localStorage.setItem(lastReaderKey(item.novel_id), JSON.stringify(memory));
    localStorage.setItem("igt-last-reader", JSON.stringify(memory));
  }
}
async function loadBackendLibrary() {
  if (!state.auth.authenticated) return;
  applyBackendLibrary(await api("/api/me/library"));
  renderNovels();
  if (state.currentNovel) { renderDetail(); renderChapters(); updateReaderBookmarkState(); }
}
function ratingFor(novelId) { return Number(state.ratings[novelId] || 0); }
function isNovelBookmarked(novelId) { return Boolean(state.bookmarks.novels[novelId]); }
function chapterKey(novelId, chapter) { return `${novelId}:${Number(chapter)}`; }
function isChapterBookmarked(novelId, chapter) { return Boolean(state.bookmarks.chapters[chapterKey(novelId, chapter)]); }
function chapterHistory(novelId, chapter) { return state.history[chapterKey(novelId, chapter)] || null; }
async function toggleNovelBookmark(novelId) {
  const next = !state.bookmarks.novels[novelId];
  state.bookmarks.novels[novelId] = next;
  if (!next) delete state.bookmarks.novels[novelId];
  if (!state.auth.authenticated) saveLocalUiState();
  renderNovels();
  if (state.currentNovel?.novel_id === novelId) renderDetail();
  if (!state.auth.authenticated) return;
  try { await api(`/api/novels/${novelId}/bookmark`, { method: next ? "POST" : "DELETE" }); }
  catch (err) { state.bookmarks.novels[novelId] = !next; if (next) delete state.bookmarks.novels[novelId]; renderNovels(); if (state.currentNovel?.novel_id === novelId) renderDetail(); toast(err.message, true); }
}
async function toggleChapterBookmark(novelId, chapter) {
  const key = chapterKey(novelId, chapter);
  const next = !state.bookmarks.chapters[key];
  state.bookmarks.chapters[key] = next;
  if (!next) delete state.bookmarks.chapters[key];
  if (!state.auth.authenticated) saveLocalUiState();
  renderChapters();
  renderChapterPicker();
  if (Number(state.readerChapter) === Number(chapter)) updateReaderBookmarkState();
  if (!state.auth.authenticated) return;
  try { await api(`/api/novels/${novelId}/chapters/${Number(chapter)}/bookmark`, { method: next ? "POST" : "DELETE" }); }
  catch (err) { state.bookmarks.chapters[key] = !next; if (next) delete state.bookmarks.chapters[key]; renderChapters(); renderChapterPicker(); updateReaderBookmarkState(); toast(err.message, true); }
}
async function setRating(novelId, rating) {
  if (!state.auth.authenticated) { openAccountDialog("login"); toast("Login required to rate.", true); return; }
  const previous = state.ratings[novelId] || 0;
  state.ratings[novelId] = rating;
  renderNovels();
  if (state.currentNovel?.novel_id === novelId) renderDetail();
  try { await api(`/api/novels/${novelId}/rating`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ rating }) }); toast(`Rated ${rating} star${rating === 1 ? "" : "s"}.`); }
  catch (err) { state.ratings[novelId] = previous; renderNovels(); if (state.currentNovel?.novel_id === novelId) renderDetail(); toast(err.message, true); }
}
function starMarkup(novelId, interactive = false) { const rating = ratingFor(novelId); return `<span class="stars ${interactive ? "interactive" : ""}">${[1,2,3,4,5].map((value) => `<button type="button" ${interactive ? `data-rating="${value}"` : "disabled"} class="${value <= rating ? "filled" : ""}" aria-label="${value} star">&#9733;</button>`).join("")}</span><span class="rating-value">${rating ? rating.toFixed(1) : "Not rated"}</span>`; }
function readCountFor(novelId) { return Object.keys(state.history).filter((key) => key.startsWith(`${novelId}:`)).length; }
function lastReaderKey(novelId) { return `igt-last-reader:${novelId}`; }
function saveReaderMemory() { if (!state.currentNovel || !state.readerChapter) return; const item = { novel_id: state.currentNovel.novel_id, chapter: state.readerChapter, mode: state.readerTab, updated_at: new Date().toISOString() }; localStorage.setItem("igt-last-reader", JSON.stringify(item)); localStorage.setItem(lastReaderKey(state.currentNovel.novel_id), JSON.stringify(item)); state.history[chapterKey(state.currentNovel.novel_id, state.readerChapter)] = item; if (state.auth.authenticated) api("/api/reading-history", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ novel_id: item.novel_id, chapter_number: item.chapter, mode: item.mode }) }).catch((err) => toast(err.message, true)); else saveLocalUiState(); }
function loadReaderMemory(novelId = state.currentNovel?.novel_id) { try { return JSON.parse(localStorage.getItem(lastReaderKey(novelId)) || localStorage.getItem("igt-last-reader") || "{}"); } catch { return {}; } }
function firstReadableChapter() { return state.chapters[0]?.chapter || null; }
function targetReaderChapter() { const memory = loadReaderMemory(); return state.chapters.some((chapter) => Number(chapter.chapter) === Number(memory.chapter)) ? Number(memory.chapter) : firstReadableChapter(); }
function defaultTags(novel) { return (novel.tags || []).length ? novel.tags : (novel.novel_id === "i-am-god" ? ["Fantasy", "Mythic", "Divine", "Civilization", "Mystery"] : []); }
function novelMatchesBrowse(novel, filter) { const p = progressPercent(novel.counts); if (filter === "in-progress") return p > 0 && p < 100; if (filter === "completed") return p >= 100; if (filter === "has-reference") return novel.counts.reference_files > 0; if (filter === "missing-reference") return novel.counts.reference_files === 0; if (filter === "has-ai") return novel.counts.translated_chapters > 0; if (filter === "needs-translation") return novel.counts.remaining_chapters > 0; if (filter === "bookmarked") return isNovelBookmarked(novel.novel_id); if (filter === "recently-read") return readCountFor(novel.novel_id) > 0; if (filter.startsWith("tag:")) return defaultTags(novel).map((tag) => tag.toLowerCase()).includes(filter.slice(4).toLowerCase()); return true; }
function sortNovels(novels, sort) { return novels.sort((a, b) => sort === "name" ? a.title.localeCompare(b.title) : sort === "progress" ? progressPercent(b.counts) - progressPercent(a.counts) : sort === "rating" ? ratingFor(b.novel_id) - ratingFor(a.novel_id) : sort === "translated" ? b.counts.translated_chapters - a.counts.translated_chapters : sort === "remaining" ? a.counts.remaining_chapters - b.counts.remaining_chapters : String(b.updated_at).localeCompare(String(a.updated_at))); }
function applyAppInfo() {
  const info = state.appInfo || {};
  const theme = info.theme || {};
  document.documentElement.style.setProperty("--accent", theme.main_accent || "#68d1b4");
  document.documentElement.style.setProperty("--accent-2", theme.highlight || "#d6bf7a");
  document.documentElement.style.setProperty("--logo-accent", theme.logo_accent || theme.main_accent || "#68d1b4");
  document.documentElement.style.setProperty("--surface", theme.card_background || "#111816");
  document.documentElement.style.setProperty("--bg", theme.page_background || "#080d0c");
  document.documentElement.style.setProperty("--reader-bg", theme.reader_background || "#0f1513");
  document.documentElement.style.setProperty("--reader-text", theme.reader_text || "#efe8d5");
  const displayName = !info.name || info.name === "IAmGodTranslator" ? "GodTranslator" : info.name;
  els.brandName.textContent = displayName;
  els.brandSubtitle.textContent = info.subtitle || "Novel Library";
  renderIcon(els.brandMark, info.icon_url);
  renderIcon(els.libraryIcon, info.icon_url);
  if (els.appDisplayName) {
    els.appDisplayName.value = displayName;
    els.appSubtitleInput.value = info.subtitle || "Novel Library";
    els.themeMainAccent.value = theme.main_accent || "#68d1b4";
    els.themeHighlight.value = theme.highlight || "#d6bf7a";
    els.themeLogoAccent.value = theme.logo_accent || "#68d1b4";
    els.themeCardBackground.value = theme.card_background || "#111816";
    els.themePageBackground.value = theme.page_background || "#080d0c";
    els.themeReaderBackground.value = theme.reader_background || "#0f1513";
    els.themeReaderText.value = theme.reader_text || "#efe8d5";
  }
}
function defaultReaderPrefs() { return { fontFamily: "default", fontSize: 19, lineHeight: 1.9, paragraphSpacing: 14, pageWidth: "820px", textAlign: "left", theme: "dark", background: getComputedStyle(document.documentElement).getPropertyValue("--reader-bg").trim() || "#0f1513", accent: getComputedStyle(document.documentElement).getPropertyValue("--accent").trim() || "#68d1b4", allowCopy: true }; }
function loadReaderPrefs() { try { state.readerPrefs = { ...defaultReaderPrefs(), ...JSON.parse(localStorage.getItem("igt-reader-prefs") || "{}") }; } catch { state.readerPrefs = defaultReaderPrefs(); } applyReaderPrefs(); }
function saveReaderPrefs() { localStorage.setItem("igt-reader-prefs", JSON.stringify(state.readerPrefs)); applyReaderPrefs(); }
function applyReaderPrefs() {
  const p = { ...defaultReaderPrefs(), ...state.readerPrefs };
  const fonts = { default: 'Georgia,"Times New Roman",serif', dyslexic: '"Comic Sans MS","Trebuchet MS",system-ui,sans-serif', system: 'system-ui,-apple-system,"Segoe UI",sans-serif', serif: 'Georgia,"Times New Roman",serif' };
  document.documentElement.style.setProperty("--reader-size", `${p.fontSize}px`);
  document.documentElement.style.setProperty("--reader-line-height", String(p.lineHeight));
  document.documentElement.style.setProperty("--reader-paragraph-spacing", `${p.paragraphSpacing}px`);
  document.documentElement.style.setProperty("--reader-width", p.pageWidth);
  document.documentElement.style.setProperty("--reader-active", p.accent);
  els.readerContent.style.fontFamily = fonts[p.fontFamily] || fonts.default;
  els.readerContent.style.textAlign = p.textAlign;
  els.readerContent.style.userSelect = p.allowCopy ? "text" : "none";
  els.readerShell.style.background = p.background;
  els.readerShell.dataset.theme = p.theme || "dark";
  els.readerTheme.value = p.theme || "dark";
  els.readerFontFamily.value = p.fontFamily;
  els.readerFontSize.value = p.fontSize;
  els.readerLineHeight.value = p.lineHeight;
  els.readerParagraphSpacing.value = p.paragraphSpacing;
  els.readerPageWidth.value = p.pageWidth;
  els.readerTextAlign.value = p.textAlign;
  els.readerBackground.value = p.background;
  els.readerAccent.value = p.accent;
  els.readerAllowCopy.checked = Boolean(p.allowCopy);
}
function libraryRoute() { return "#/library"; }
function novelRoute(novelId) { return `#/novel/${encodeURIComponent(novelId)}`; }
function readerRoute(novelId, chapter, mode = state.readerTab) { return `#/novel/${encodeURIComponent(novelId)}/chapter/${Number(chapter)}?mode=${encodeURIComponent(mode || "original")}`; }
function pushRoute(hash, replace = false) { if (window.location.hash === hash) return; const method = replace ? "replaceState" : "pushState"; history[method]({}, "", hash); }
function parsedRoute() {
  const hash = window.location.hash || libraryRoute();
  const [path, query = ""] = hash.replace(/^#\/?/, "").split("?");
  const parts = path.split("/").filter(Boolean);
  const params = new URLSearchParams(query);
  if (!parts.length || parts[0] === "library") return { type: "library" };
  if (parts[0] === "novel" && parts[1] && parts[2] === "chapter" && parts[3]) return { type: "reader", novelId: decodeURIComponent(parts[1]), chapter: Number(parts[3]), mode: params.get("mode") || "original" };
  if (parts[0] === "novel" && parts[1]) return { type: "novel", novelId: decodeURIComponent(parts[1]) };
  return { type: "library" };
}
async function applyRouteFromLocation() {
  const route = parsedRoute();
  if (route.type === "library") {
    showLibrary({ skipHistory: true });
    return;
  }
  if (route.type === "novel") {
    await openNovel(route.novelId, { skipHistory: true, skipSave: true });
    return;
  }
  if (route.type === "reader") {
    await openNovel(route.novelId, { skipHistory: true, skipSave: true, initialTab: "reader" });
    await openReader(route.chapter, route.mode, { skipHistory: true });
  }
}
function handleRouteChange() {
  clearTimeout(handleRouteChange.timer);
  handleRouteChange.timer = setTimeout(() => applyRouteFromLocation().catch((err) => toast(err.message, true)), 0);
}
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
async function activateWorkspace(id, options = {}) {
  if (id === state.activeWorkspaceId) return;
  saveCurrentWorkspace();
  const workspace = workspaceFor(id);
  if (!workspace) return;
  state.activeWorkspaceId = id;
  if (workspace.type === "library") {
    showView("library");
    renderWorkspaces();
    if (!options.skipHistory) pushRoute(libraryRoute());
    return;
  }
  await loadNovelWorkspace(workspace);
  if (!options.skipHistory && workspace.type === "novel") pushRoute(novelRoute(workspace.novelId));
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
function showLibrary(options = {}) { if (!options.skipSave) saveCurrentWorkspace(); state.activeWorkspaceId = "library"; showView("library"); renderWorkspaces(); renderNovels(); if (!options.skipHistory) pushRoute(libraryRoute()); }
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
async function loadAuthState() {
  state.auth = await api("/api/auth/me").catch(() => ({ authenticated: false, user: null }));
  renderAuthState();
  if (state.auth.authenticated) await loadBackendLibrary().catch((err) => toast(err.message, true));
}
async function loadAppInfo() { state.appInfo = await api("/api/app").catch(() => ({})); applyAppInfo(); applyReaderPrefs(); }
async function loadNovels() { els.novelGrid.innerHTML = '<div class="empty-state">Loading library...</div>'; state.novels = (await apiWithRetry("/api/novels")).novels || []; renderNovels(); }
function renderAdminState() { document.body.classList.toggle("is-admin", state.admin.authenticated); els.adminButton.textContent = state.admin.authenticated ? "Admin / Lock" : "Admin"; els.adminHelp.textContent = state.admin.enabled ? "Enter your admin password to open the control panel." : "Login is disabled because ADMIN_PASSWORD is not set. Private tools are hidden."; if (!state.admin.authenticated && ["translatePanel", "backupsPanel", "settingsPanel"].some((id) => document.getElementById(id).classList.contains("active"))) switchTab("chapters"); }
function renderAuthState() {
  const user = state.auth.user;
  els.accountButton.textContent = user ? `${user.username || user.email}` : "Login";
  els.registerButton.hidden = Boolean(user);
  els.accountMessage.textContent = user ? `${user.email} · ${user.role}${user.email_verified ? " · verified" : " · email not verified"}` : "Use an account to sync bookmarks, ratings, and reading history.";
  els.accountUserActions.hidden = !user;
}
function readerThemeBackground(theme) {
  return ({ paper: "#f5ecd9", dark: "#111614", sepia: "#ead6b4", oled: "#000000", green: "#0b1d17", gold: "#17130d" }[theme] || "#111614");
}
function openAccountDialog(mode = state.auth.authenticated ? "settings" : "login") {
  state.accountMode = mode;
  const user = state.auth.user;
  const registering = mode === "register";
  const reset = mode === "reset";
  els.accountTitle.textContent = user && mode === "settings" ? "Account Settings" : reset ? "Forgot Password" : registering ? "Register" : "Login";
  els.accountUsernameWrap.hidden = !registering;
  els.accountConfirmWrap.hidden = !registering;
  els.accountPassword.required = !reset;
  els.accountPassword.parentElement.hidden = reset || Boolean(user);
  els.accountSubmitButton.textContent = reset ? "Send Reset Link" : registering ? "Create Account" : "Login";
  els.accountSubmitButton.hidden = Boolean(user);
  els.accountModeButton.textContent = registering ? "Already have an account?" : "Create account";
  els.forgotPasswordButton.hidden = reset || Boolean(user);
  if (user) {
    els.accountEmail.value = user.email || "";
    els.accountUsername.value = user.username || "";
    els.accountPassword.value = "";
    els.accountEmail.required = false;
  } else {
    els.accountEmail.required = true;
  }
  if (els.accountDialog.showModal) els.accountDialog.showModal(); else els.accountEmail.focus();
}
async function submitAccount(event) {
  event.preventDefault();
  if (state.accountMode === "settings") return;
  const email = els.accountEmail.value.trim();
  if (state.accountMode === "reset") {
    const result = await api("/api/auth/request-password-reset", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email }) });
    els.accountMessage.textContent = result.message || "If an account exists for this email, a reset link was sent.";
    toast("Password reset request sent.");
    return;
  }
  if (state.accountMode === "register") {
    if (els.accountPassword.value !== els.accountConfirm.value) return toast("Passwords do not match.", true);
    await api("/api/auth/register", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, username: els.accountUsername.value.trim(), password: els.accountPassword.value }) });
    els.accountMessage.textContent = "Check your email to verify your account. If email is not configured, admin can finish SMTP setup later.";
  } else {
    await api("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password: els.accountPassword.value }) });
  }
  els.accountPassword.value = "";
  els.accountConfirm.value = "";
  await loadAuthState();
  await loadNovels();
  toast(state.accountMode === "register" ? "Account created." : "Logged in.");
  if (els.accountDialog.open) els.accountDialog.close();
}
async function logoutAccount() {
  await api("/api/auth/logout", { method: "POST" });
  state.auth = { authenticated: false, user: null };
  loadLocalUiState();
  renderAuthState();
  renderNovels();
  if (state.currentNovel) { renderDetail(); renderChapters(); }
  toast("Logged out.");
}
async function refreshStorageHealth() {
  const storage = await api("/api/storage");
  const counts = storage.counts || {};
  const folders = storage.folders || {};
  const supabase = storage.supabase || {};
  const warnings = [...(storage.warnings || []), ...(supabase.warnings || [])];
  els.storageHealth.innerHTML = `<div class="warning">Your files are only safe after DATA_DIR points to persistent storage or Supabase is active.</div><div class="storage-grid"><div><span>Storage backend</span><strong>${esc(storage.backend || "local")}</strong></div><div><span>Supabase configured</span><strong>${supabase.configured ? "true" : "false"}</strong></div><div><span>Supabase storage</span><strong>${supabase.reachable ? "reachable" : "not reachable"}</strong></div><div><span>Supabase bucket</span><strong>${esc(supabase.bucket || "novel-files")}</strong></div><div><span>DATA_DIR fallback</span><strong>${esc(storage.configured_data_dir || storage.data_dir)}</strong></div><div><span>Resolved path</span><strong>${esc(storage.resolved_data_dir || storage.data_dir)}</strong></div><div><span>Writable</span><strong>${storage.writable ? "true" : "false"}</strong></div><div><span>Database</span><strong>${esc(storage.database?.backend || "unknown")} ${storage.database_reachable ? "reachable" : "warning"}</strong></div><div><span>Original</span><strong>${counts.originals || storage.saved_chinese_chapters || 0}</strong></div><div><span>Reference</span><strong>${counts.references || storage.saved_novelfire_references || 0}</strong></div><div><span>AI</span><strong>${counts.ai_translations || storage.saved_translations || 0}</strong></div><div><span>Prompts</span><strong>${counts.prompts || 0}</strong></div><div><span>Backups</span><strong>${counts.backups || 0}</strong></div><div><span>Covers/uploads</span><strong>${counts.covers_uploads || 0}</strong></div></div><p class="helper">Local folders: ${Object.entries(folders).map(([name, ok]) => `${esc(name)} ${ok ? "ok" : "missing"}`).join(" · ") || "not reported"}</p><p class="helper">Supabase buckets: ${Object.entries(supabase.buckets || {}).map(([name, ok]) => `${esc(name)} ${ok ? "ok" : "missing"}`).join(" · ") || "not checked"}</p>${warnings.length ? `<div class="warning">${warnings.map(esc).join("<br>")}</div>` : ""}`;
  const totalOriginal = state.novels.reduce((sum, novel) => sum + Number(novel.counts?.original_files || 0), 0);
  const totalReference = state.novels.reduce((sum, novel) => sum + Number(novel.counts?.reference_files || 0), 0);
  const totalAi = state.novels.reduce((sum, novel) => sum + Number(novel.counts?.translated_chapters || 0), 0);
  els.adminMetrics.innerHTML = `<div class="storage-grid"><div><span>Novels</span><strong>${state.novels.length}</strong></div><div><span>Original chapters</span><strong>${totalOriginal}</strong></div><div><span>Reference chapters</span><strong>${totalReference}</strong></div><div><span>AI translations</span><strong>${totalAi}</strong></div></div>`;
}
async function refreshAdminUsers() {
  const data = await api("/api/admin/users");
  const users = data.users || [];
  if (!users.length) { els.adminUsersList.innerHTML = '<div class="empty-state compact-empty">No accounts yet.</div>'; return; }
  els.adminUsersList.innerHTML = users.map((user) => `<article class="user-row" data-user="${esc(user.id)}"><div><strong>${esc(user.username || user.email)}</strong><span>${esc(user.email)} · ${user.email_verified ? "verified" : "unverified"} · ${user.disabled ? "disabled" : "enabled"} · ${date(user.created_at)}</span></div><select data-role><option value="user">user</option><option value="paid">paid</option><option value="admin">admin</option></select><button class="secondary-button" data-disable type="button">${user.disabled ? "Enable" : "Disable"}</button></article>`).join("");
  els.adminUsersList.querySelectorAll(".user-row").forEach((row, index) => {
    const user = users[index];
    row.querySelector("[data-role]").value = user.role;
    row.querySelector("[data-role]").onchange = async (event) => { await api(`/api/admin/users/${user.id}/role`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ role: event.target.value }) }); toast("Role updated."); };
    row.querySelector("[data-disable]").onclick = async () => { await api(`/api/admin/users/${user.id}/disabled`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ disabled: !user.disabled }) }); await refreshAdminUsers(); toast("User status updated."); };
  });
}

function renderLibrarySections() {
  const novels = state.novels.slice();
  const last = loadReaderMemory();
  const featured = novels.find((novel) => novel.novel_id === last.novel_id) || novels[0];
  const mostTranslated = sortNovels(novels.slice(), "translated").slice(0, 4);
  const recentlyUpdated = sortNovels(novels.slice(), "updated").slice(0, 4);
  const needsTranslation = novels.filter((novel) => novel.counts.remaining_chapters > 0).slice(0, 4);
  const complete = novels.filter((novel) => progressPercent(novel.counts) >= 100).slice(0, 4);
  const rated = sortNovels(novels.slice(), "rating").filter((novel) => ratingFor(novel.novel_id)).slice(0, 4);
  const cards = (items) => items.length ? items.map((novel) => `<button class="mini-novel-card" type="button" data-novel="${esc(novel.novel_id)}"><strong>${esc(novel.title)}</strong><span>${progressPercent(novel.counts)}% translated · ${ratingFor(novel.novel_id) || "No"} rating</span></button>`).join("") : '<div class="empty-state compact-empty">Nothing here yet.</div>';
  const featuredHtml = featured ? `${coverMarkup(featured, "featured-cover")}<div><p class="eyebrow">Featured / Continue Reading</p><h2>${esc(featured.title)}</h2><p>${esc(featured.summary || "Ready when you are.")}</p><div class="progress-track"><div class="progress-fill" style="width:${progressPercent(featured.counts)}%"></div></div><div class="hero-actions"><button class="primary-button" data-continue="${esc(featured.novel_id)}" type="button">Resume ${last.chapter ? `Chapter ${last.chapter}` : "Reading"}</button><button class="secondary-button" data-browse-all type="button">Browse Novels</button></div></div>` : '<div class="empty-state">Choose a novel to start reading.</div>';
  const rankingHtml = `<section class="discovery-grid" id="rankings-section"><div class="discovery-panel"><p class="eyebrow">Most Translated</p>${cards(mostTranslated)}</div><div class="discovery-panel"><p class="eyebrow">Highest Rated</p>${cards(rated)}</div><div class="discovery-panel"><p class="eyebrow">Recently Updated</p>${cards(recentlyUpdated)}</div><div class="discovery-panel"><p class="eyebrow">Needs Translation</p>${cards(needsTranslation)}</div><div class="discovery-panel"><p class="eyebrow">Completed / Fully Translated</p>${cards(complete)}</div></section>`;
  const updatesHtml = `<section class="discovery-grid" id="updates-section"><div class="discovery-panel"><p class="eyebrow">Recently Updated</p>${cards(recentlyUpdated)}</div><div class="discovery-panel"><p class="eyebrow">Latest AI Translations</p>${cards(mostTranslated.filter((novel) => novel.counts.translated_chapters > 0))}</div><div class="discovery-panel"><p class="eyebrow">Continue Reading</p>${featured ? cards([featured]) : '<div class="empty-state compact-empty">Choose a novel to start reading.</div>'}</div></section>`;
  const titles = { home: "Recommendations", browse: "Browse Novels", library: "My Library", rankings: "Rankings", updates: "Updates" };
  els.librarySections.innerHTML = state.libraryMode === "home"
    ? `<section class="featured-card" id="continue-section">${featuredHtml}</section><section class="section-head"><h2>Recommendations</h2><button class="secondary-button" data-browse-all type="button">Open Browse</button></section>${rankingHtml}${updatesHtml}`
    : state.libraryMode === "rankings"
      ? `<section class="section-head"><h2>Rankings</h2><p>Ranked from your local library data.</p></section>${rankingHtml}`
      : state.libraryMode === "updates"
        ? `<section class="section-head"><h2>Updates</h2><p>Recently updated novels and reading shortcuts.</p></section>${updatesHtml}`
        : `<section class="section-head"><h2>${titles[state.libraryMode] || "Browse Novels"}</h2><p>${state.libraryMode === "library" ? "Saved novels from your local bookmarks." : "Search, sort, and filter the available novels."}</p></section>`;
  els.librarySections.querySelectorAll("[data-manage]").forEach((button) => button.onclick = () => openNovel(button.dataset.manage));
  els.librarySections.querySelectorAll("[data-continue]").forEach((button) => button.onclick = async () => { await openNovel(button.dataset.continue, { initialTab: "reader" }); const memory = loadReaderMemory(button.dataset.continue); openReader(memory.chapter || firstReadableChapter(), memory.mode || state.readerTab); });
  els.librarySections.querySelectorAll("[data-novel]").forEach((button) => button.onclick = () => openNovel(button.dataset.novel));
  els.librarySections.querySelectorAll("[data-browse-all]").forEach((button) => button.onclick = () => applyBrowse("all"));
}

function renderNovels() {
  const q = els.novelSearch.value.toLowerCase();
  const sort = els.novelSort.value;
  const filter = state.libraryMode === "library" ? "bookmarked" : els.browseFilter.value;
  let novels = state.novels.filter((novel) => novelMatchesBrowse(novel, filter) && `${novel.title} ${novel.summary || ""} ${defaultTags(novel).join(" ")}`.toLowerCase().includes(q));
  novels = sortNovels(novels, sort);
  renderLibrarySections();
  els.libraryToolbar.hidden = !["browse", "library"].includes(state.libraryMode);
  if (state.libraryMode === "home") novels = sortNovels(state.novels.slice(), "updated").slice(0, 6);
  if (state.libraryMode === "rankings" || state.libraryMode === "updates") {
    els.novelGrid.innerHTML = "";
    return;
  }
  els.novelGrid.innerHTML = novels.length ? "" : filter === "bookmarked" ? '<div class="empty-state">No saved novels yet. Browse novels and bookmark one.</div>' : '<div class="empty-state">No novels found for this view.</div>';
  for (const novel of novels) {
    const card = document.createElement("article");
    card.className = "novel-card";
    const percent = progressPercent(novel.counts);
    const noChapters = Number(novel.counts?.original_files || 0) === 0 && Number(novel.counts?.reference_files || 0) === 0 && Number(novel.counts?.translated_chapters || 0) === 0;
    card.innerHTML = `${coverMarkup(novel, "library-cover")}<div class="novel-card-body"><div class="card-title-row"><h2>${esc(novel.title)}</h2><button class="bookmark-button card-bookmark ${isNovelBookmarked(novel.novel_id) ? "active" : ""}" type="button">${isNovelBookmarked(novel.novel_id) ? "Bookmarked" : "Bookmark"}</button></div><p class="card-meta">${esc(novel.summary || "Novel ready for reading.")}</p>${noChapters ? '<div class="warning public-empty-note">No chapters imported yet.</div>' : ""}<div class="card-rating">${starMarkup(novel.novel_id)}</div><div class="tag-row">${defaultTags(novel).slice(0, 4).map((tag) => `<span>${esc(tag)}</span>`).join("")}</div><div class="progress-track"><div class="progress-fill" style="width:${percent}%"></div></div><div class="card-stats"><div><span>Original</span><strong>${novel.counts.original_files}</strong></div><div><span>Reference</span><strong>${novel.counts.reference_files}</strong></div><div><span>AI</span><strong>${novel.counts.translated_chapters}</strong></div><div><span>Remaining</span><strong>${novel.counts.remaining_chapters}</strong></div></div><p class="card-meta">Updated ${date(novel.updated_at)} · ${percent}% translated · ${readCountFor(novel.novel_id)} read</p><div class="card-actions"><button class="primary-button continue-card" type="button">Continue Reading</button><button class="secondary-button reader-card" type="button">Open Reader</button><button class="secondary-button manage-card admin-only" type="button">Manage</button></div></div>`;
    card.querySelector(".card-bookmark").addEventListener("click", () => toggleNovelBookmark(novel.novel_id));
    card.querySelector(".manage-card").addEventListener("click", () => openNovel(novel.novel_id));
    card.querySelector(".reader-card").addEventListener("click", async () => { await openNovel(novel.novel_id, { initialTab: "reader" }); openReader(firstReadableChapter(), state.readerTab); });
    card.querySelector(".continue-card").addEventListener("click", async () => { await openNovel(novel.novel_id, { initialTab: "reader" }); const memory = loadReaderMemory(novel.novel_id); openReader(memory.chapter || firstReadableChapter(), memory.mode || state.readerTab); });
    els.novelGrid.appendChild(card);
  }
}

function renderRepairReport(report) {
  const audit = report.audit || report;
  const counts = audit.counts || {};
  const warnings = [...(audit.warnings || []), ...(report.warnings || [])];
  const details = (label, values) => `<details><summary>${label}: ${(values || []).length}</summary><pre>${esc((values || []).slice(0, 40).map((value) => typeof value === "string" ? value : JSON.stringify(value)).join("\n") || "None")}</pre></details>`;
  els.repairReport.innerHTML = `<strong>${report.dry_run === false ? "Repair applied" : "Audit / dry run"}</strong><br>Originals ${counts.originals || 0}; References ${counts.references || 0}; AI ${counts.ai_translations || 0}; Prompts ${counts.prompts || 0}<br>Old paths ${(audit.old_paths || []).length}; Unknown paths ${(audit.unknown_paths || []).length}; Suspicious ${(audit.suspicious_files || []).length}; Duplicates ${(audit.duplicates || []).length}${warnings.length ? `<br><span class="warning-inline">${warnings.map(esc).join("<br>")}</span>` : ""}${details("Old paths", audit.old_paths)}${details("Unknown paths", audit.unknown_paths)}${details("Suspicious files", audit.suspicious_files)}${details("Duplicates", audit.duplicates)}${report.actions ? details("Repair actions", report.actions) : ""}`;
}

async function auditContent() {
  if (!state.currentNovel) return toast("Open a novel first.", true);
  renderRepairReport(await api(`/api/admin/novels/${state.currentNovel.novel_id}/content-audit`));
}

async function repairContent(dryRun) {
  if (!state.currentNovel) return toast("Open a novel first.", true);
  if (!dryRun && !window.confirm("Apply conservative repair? This does not delete files.")) return;
  const report = await api(`/api/admin/novels/${state.currentNovel.novel_id}/repair-content-map`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ dry_run: dryRun, rebuild_index: true }) });
  renderRepairReport(report);
  if (!dryRun) await openNovel(state.currentNovel.novel_id, { skipHistory: true, skipSave: true, initialTab: "settings" });
  toast(dryRun ? "Repair dry-run complete." : "Repair applied.");
}

async function openNovel(id, options = {}) {
  if (!options.skipSave) saveCurrentWorkspace();
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
  switchTab(options.initialTab || "overview");
  renderWorkspaces();
  if (!options.skipHistory) pushRoute(novelRoute(id));
}

function renderDetail() {
  const n = state.currentNovel, c = n.counts;
  const percent = progressPercent(c);
  els.novelTitle.textContent = n.title;
  els.novelSummary.textContent = n.summary || "No summary yet.";
  els.novelBookmarkButton.textContent = isNovelBookmarked(n.novel_id) ? "Bookmarked" : "Bookmark";
  els.novelBookmarkButton.classList.toggle("active", isNovelBookmarked(n.novel_id));
  els.novelRating.innerHTML = starMarkup(n.novel_id, true);
  els.novelRating.querySelectorAll("[data-rating]").forEach((button) => button.onclick = () => setRating(n.novel_id, Number(button.dataset.rating)));
  els.novelTags.innerHTML = defaultTags(n).length ? defaultTags(n).map((tag) => `<span>${esc(tag)}</span>`).join("") : "<span>Novel</span>";
  els.metricStorage.textContent = n.storage_mode;
  els.metricOriginal.textContent = c.original_files;
  els.metricReference.textContent = c.reference_files;
  els.metricTranslated.textContent = c.translated_chapters;
  els.metricRemaining.textContent = c.remaining_chapters;
  els.metricPercent.textContent = `${percent}%`;
  els.metricUpdated.textContent = date(n.updated_at);
  els.metricBackup.textContent = date(n.last_backup_at);
  els.metricModel.textContent = n.current_model;
  els.metricStatus.textContent = status(n.status);
  els.novelProgress.style.width = `${percent}%`;
  els.backupSummary.textContent = `Original ${c.original_files} · Reference ${c.reference_files} · AI ${c.translated_chapters} · Remaining ${c.remaining_chapters} · Last backup ${date(n.last_backup_at)}`;
  els.dashboardCover.innerHTML = n.cover_url ? `<img src="${esc(n.cover_url)}" alt="">` : `<span>${esc(n.title.slice(0, 2).toUpperCase() || "IG")}</span>`;
  els.downloadOriginal.href = `/api/novels/${n.novel_id}/download/original`;
  els.downloadReference.href = `/api/novels/${n.novel_id}/download/reference`;
  els.downloadEnglish.href = `/api/novels/${n.novel_id}/download/ai`;
  els.downloadPrompts.href = `/api/novels/${n.novel_id}/download/prompts`;
  els.settingsTitle.value = n.title;
  els.settingsSummary.value = n.summary || "";
  els.settingsTags.value = defaultTags(n).join(", ");
  els.sourceLanguage.value = n.source_language || "Chinese";
  els.targetLanguage.value = n.target_language || "English";
  els.defaultModel.value = n.current_model || "gpt-4o-mini";
  els.storageModeDisplay.value = n.storage_mode || "";
  els.dataDirDisplay.value = n.data_dir || "";
}

function modeBadge(label, available) { return `<span class="badge ${available ? "translated" : "missing"}">${label}: ${available ? "available" : "missing"}</span>`; }
function chapterMatchesFilter(chapter, filter) { const novelId = state.currentNovel?.novel_id; if (filter === "has-original") return chapter.has_original; if (filter === "has-reference") return chapter.has_reference; if (filter === "has-ai") return chapter.has_translation; if (filter === "missing-ai") return !chapter.has_translation; if (filter === "missing-reference") return !chapter.has_reference; if (filter === "bookmarked") return isChapterBookmarked(novelId, chapter.chapter); if (filter === "recently-read") return Boolean(chapterHistory(novelId, chapter.chapter)); if (filter === "ready") return chapter.has_original && !chapter.has_translation; if (filter === "failed") return status(chapter.status) === "failed"; return true; }
function filteredChapters() {
  const q = els.chapterSearch.value.toLowerCase();
  const f = els.chapterFilter.value;
  const sort = els.chapterSort.value;
  const chapters = state.chapters.filter((c) => chapterMatchesFilter(c, f) && `${c.chapter} ${c.title}`.toLowerCase().includes(q));
  return chapters.sort((a, b) => {
    if (sort === "desc") return b.chapter - a.chapter;
    if (sort === "missing-ai") return Number(a.has_translation) - Number(b.has_translation) || a.chapter - b.chapter;
    if (sort === "translated") return Number(b.has_translation) - Number(a.has_translation) || a.chapter - b.chapter;
    if (sort === "title") return String(a.title || "").localeCompare(String(b.title || "")) || a.chapter - b.chapter;
    return a.chapter - b.chapter;
  });
}

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
    const key = chapterKey(state.currentNovel.novel_id, c.chapter);
    const read = chapterHistory(state.currentNovel.novel_id, c.chapter);
    const row = document.createElement("article");
    row.className = "chapter-row";
    row.innerHTML = `<div class="chapter-select"><input type="checkbox" ${state.selectedChapters.has(key) ? "checked" : ""} aria-label="Select chapter ${c.chapter}"><button class="bookmark-button chapter-bookmark ${isChapterBookmarked(state.currentNovel.novel_id, c.chapter) ? "active" : ""}" type="button">${isChapterBookmarked(state.currentNovel.novel_id, c.chapter) ? "★" : "☆"}</button></div><div><div class="chapter-title">${String(c.chapter).padStart(4, "0")} - ${esc(c.title || "Untitled")}</div><div class="chapter-meta mode-badges">${modeBadge("Original", c.has_original)} ${modeBadge("Reference", c.has_reference)} ${modeBadge("AI", c.has_translation)} <span class="badge ${esc(status(c.status))}">${esc(status(c.status))}</span> ${read ? `<span class="badge translated">Read ${date(read.updated_at)}</span>` : '<span class="badge missing">Unread</span>'}</div></div><div class="chapter-actions"></div>`;
    row.querySelector("input").addEventListener("change", (event) => { if (event.target.checked) state.selectedChapters.add(key); else state.selectedChapters.delete(key); renderSelectedCount(); });
    row.querySelector(".chapter-bookmark").addEventListener("click", () => toggleChapterBookmark(state.currentNovel.novel_id, c.chapter));
    const readButton = document.createElement("button");
    readButton.className = "primary-button";
    readButton.textContent = "Open Reader";
    readButton.addEventListener("click", () => openReader(c.chapter, state.readerTab));
    row.addEventListener("dblclick", () => openReader(c.chapter, state.readerTab));
    row.querySelector(".chapter-actions").appendChild(readButton);
    els.chapterList.appendChild(row);
  }
  renderSelectedCount();
  renderChapterPicker();
}

async function openReader(chapter, tab = state.readerTab, options = {}) {
  if (!chapter) { toast("No chapters are available yet.", true); return; }
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
  const sorted = state.chapters.slice().sort((a, b) => a.chapter - b.chapter);
  const position = sorted.findIndex((item) => Number(item.chapter) === Number(c.chapter)) + 1;
  els.readerProgress.textContent = `Chapter ${position || 1} of ${sorted.length} · ${progressPercent(state.currentNovel?.counts)}% AI translated · Mode: ${state.readerTab === "ai" ? "AI Translation" : state.readerTab === "reference" ? "Reference Translation" : "Original Story"}`;
  updateReaderBookmarkState();
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
  if (!options.skipHistory && state.currentNovel) pushRoute(readerRoute(state.currentNovel.novel_id, state.readerChapter, state.readerTab));
  saveReaderMemory();
  api("/api/reader/last", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ novel_id: state.currentNovel.novel_id, chapter: state.readerChapter }) }).catch(() => {});
}

async function loadReaderText() {
  const endpoint = state.readerTab === "ai" ? "english" : state.readerTab;
  const missing = { original: "No Original Story content for this chapter.", reference: "No Reference Translation content for this chapter.", ai: "No AI Translation content for this chapter." };
  els.readerContent.textContent = "Loading...";
  try {
    const data = await api(`/api/novels/${state.currentNovel.novel_id}/chapters/${state.readerChapter}/${endpoint}`);
    setReaderText(data.text && data.text.trim() ? data.text : missing[state.readerTab]);
  } catch (_error) {
    setReaderText(missing[state.readerTab] || "Chapter text not available.");
  }
}
function setReaderText(text) {
  const paragraphs = String(text || "").split(/\n\s*\n/).map((part) => part.trim()).filter(Boolean);
  els.readerContent.innerHTML = paragraphs.length ? paragraphs.map((part) => `<p>${esc(part)}</p>`).join("") : "";
}

function renderSelectedCount() { if (els.selectedChapterCount) els.selectedChapterCount.textContent = `${state.selectedChapters.size} selected`; }
function updateReaderBookmarkState() {
  const bookmarked = state.currentNovel && state.readerChapter ? isChapterBookmarked(state.currentNovel.novel_id, state.readerChapter) : false;
  els.centerChapterPicker.classList.toggle("bookmarked", bookmarked);
  els.readerBookmarkButton.classList.toggle("active", bookmarked);
  els.readerBookmarkButton.textContent = bookmarked ? "Bookmarked" : "Bookmark";
}
function adjacent(offset) { const chapters = state.chapters.slice().sort((a, b) => a.chapter - b.chapter); const i = chapters.findIndex((c) => c.chapter === state.readerChapter); if (chapters[i + offset]) openReader(chapters[i + offset].chapter, state.readerTab); }
function pickerChapters() {
  const q = state.pickerSearch.toLowerCase();
  const chapters = state.chapters.filter((chapter) => `${chapter.chapter} ${chapter.title}`.toLowerCase().includes(q));
  chapters.sort((a, b) => state.pickerNewest ? b.chapter - a.chapter : a.chapter - b.chapter);
  return chapters;
}
function renderChapterPicker() {
  if (!els.chapterPickerPanel || !state.currentNovel) return;
  const chapters = pickerChapters();
  const totalPages = Math.max(1, Math.ceil(chapters.length / state.pickerPageSize));
  state.pickerPage = Math.min(Math.max(1, state.pickerPage), totalPages);
  const start = (state.pickerPage - 1) * state.pickerPageSize;
  const page = chapters.slice(start, start + state.pickerPageSize);
  els.chapterPickerPanel.innerHTML = `<div class="picker-head"><div><p class="eyebrow">Chapter selector</p><strong>${chapters.length} chapters</strong></div><button class="icon-button" data-picker-close type="button">x</button></div><div class="picker-tools"><input data-picker-search type="search" placeholder="Search chapter" value="${esc(state.pickerSearch)}"><select data-picker-size><option value="25">25</option><option value="50">50</option><option value="100">100</option></select><button class="secondary-button" data-picker-sort type="button">${state.pickerNewest ? "Newest first" : "Oldest first"}</button><button class="secondary-button" data-picker-bookmarks type="button">Bookmarked</button></div><div class="picker-list">${page.length ? page.map((c) => `<button class="chapter-picker-item ${c.chapter === state.readerChapter ? "active" : ""}" type="button" data-chapter="${c.chapter}"><span>${isChapterBookmarked(state.currentNovel.novel_id, c.chapter) ? "★" : "☆"} ${String(c.chapter).padStart(4, "0")} ${esc(c.title || "")}</span><small>${c.has_translation ? "AI" : "Missing AI"}${chapterHistory(state.currentNovel.novel_id, c.chapter) ? " · Read" : ""}</small></button>`).join("") : '<div class="empty-state compact-empty">No chapters match.</div>'}</div><div class="pager"><button class="secondary-button" data-picker-prev type="button">Previous</button><span>Page ${state.pickerPage} of ${totalPages}</span><button class="secondary-button" data-picker-next type="button">Next</button></div>`;
  els.chapterPickerPanel.querySelector("[data-picker-size]").value = String(state.pickerPageSize);
  els.chapterPickerPanel.querySelector("[data-picker-close]").onclick = () => { els.chapterPickerPanel.hidden = true; };
  els.chapterPickerPanel.querySelector("[data-picker-search]").oninput = (event) => { state.pickerSearch = event.target.value; state.pickerPage = 1; clearTimeout(state.searchTimer); state.searchTimer = setTimeout(renderChapterPicker, 120); };
  els.chapterPickerPanel.querySelector("[data-picker-size]").onchange = (event) => { state.pickerPageSize = Number(event.target.value || 50); state.pickerPage = 1; renderChapterPicker(); };
  els.chapterPickerPanel.querySelector("[data-picker-sort]").onclick = () => { state.pickerNewest = !state.pickerNewest; state.pickerPage = 1; renderChapterPicker(); };
  els.chapterPickerPanel.querySelector("[data-picker-bookmarks]").onclick = () => { state.pickerSearch = ""; const first = state.chapters.find((c) => isChapterBookmarked(state.currentNovel.novel_id, c.chapter)); if (first) openReader(first.chapter, state.readerTab); else toast("No bookmarked chapters yet.", true); };
  els.chapterPickerPanel.querySelector("[data-picker-prev]").onclick = () => { state.pickerPage -= 1; renderChapterPicker(); };
  els.chapterPickerPanel.querySelector("[data-picker-next]").onclick = () => { state.pickerPage += 1; renderChapterPicker(); };
  els.chapterPickerPanel.querySelectorAll("[data-chapter]").forEach((button) => button.addEventListener("click", () => { els.chapterPickerPanel.hidden = true; openReader(Number(button.dataset.chapter), state.readerTab); }));
}

async function upload(kind, button = null) { const input = kind === "original" ? els.originalFiles : els.referenceFiles; if (!input.files.length) return toast("Choose files first.", true); await withBusy(button, async () => { const form = new FormData(); for (const file of input.files) form.append(kind, file); await api(`/api/novels/${state.currentNovel.novel_id}/upload/${kind}`, { method: "POST", body: form, timeoutMs: 120000 }); input.value = ""; await openNovel(state.currentNovel.novel_id); switchTab("translate"); toast(kind === "original" ? "Original Story uploaded." : "Reference Translation uploaded."); }); }
function settings(startNow = false) { return { model: els.model.value, max_total_budget: els.maxTotalBudget.value, max_cost_per_chapter: els.maxCostPerChapter.value, retry_failed_chapters: Number(els.retryFailedChapters.value || 0), batch_size: Number(els.batchSize.value || 25), stop_when_budget_reached: els.stopWhenBudgetReached.checked, show_estimate_before_starting: true, test_chapter_only: false, start_now: startNow }; }
async function buildEstimate() { await withBusy(els.estimateBatch, async () => { try { state.currentJob = await api(`/api/novels/${state.currentNovel.novel_id}/translate/batch`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(settings(false)), timeoutMs: 60000 }); els.startBatch.disabled = false; renderQueue(); toast("Cost estimate ready. Translation has not started."); } catch (error) { els.startBatch.disabled = true; throw error; } }); }
async function startBatch() { await withBusy(els.startBatch, async () => { if (!state.currentJob) await buildEstimate(); if (!window.confirm("Start paid translation for this estimated batch?")) return; await api(`/api/novels/${state.currentNovel.novel_id}/jobs/${state.currentJob.job_id}/start`, { method: "POST", timeoutMs: 60000 }); toast("Batch started."); pollJob().catch((err) => toast(err.message, true)); }); }
async function pollJob() {
  if (!state.currentJob) return;
  clearTimeout(state.pollTimer);
  try {
    state.currentJob = await api(`/api/novels/${state.currentNovel.novel_id}/jobs/${state.currentJob.job_id}`, { timeoutMs: 20000 });
    renderQueue();
    if (["queued", "running"].includes(state.currentJob.status)) state.pollTimer = setTimeout(() => pollJob().catch((err) => toast(err.message, true)), 3000);
  } catch (error) {
    els.estimateBox.innerHTML = `<strong>Polling paused.</strong><br>${esc(error.message)}<br><button class="secondary-button" id="retryJobPoll" type="button">Retry job status</button>`;
    $("#retryJobPoll")?.addEventListener("click", () => pollJob().catch((err) => toast(err.message, true)));
    toast(error.message, true);
  }
}
function renderQueue() { const job = state.currentJob; if (!job) { els.estimateBox.textContent = "No batch estimate yet."; els.jobProgress.style.width = "0%"; els.queueList.innerHTML = '<div class="empty-state">Build a cost estimate to preview the next batch queue.</div>'; return; } const total = job.counts?.total || 0, done = job.counts?.completed || 0; els.jobProgress.style.width = `${total ? Math.round((done / total) * 100) : 0}%`; els.estimateBox.innerHTML = `<strong>${status(job.status)}</strong><br>Chapters: ${total}. Cheapest estimate: ${money(job.estimate?.cheapest_total_cost)}. Recommended estimate: ${money(job.estimate?.recommended_total_cost)}.`; els.queueList.innerHTML = ""; for (const c of job.chapters || []) { const row = document.createElement("article"); row.className = "chapter-row"; row.innerHTML = `<div><div class="chapter-title">${String(c.chapter).padStart(4, "0")} - ${esc(c.title || "")}</div><div class="chapter-meta">${esc(c.error || "Ready")}</div></div><span class="badge ${c.status}">${status(c.status)}</span>`; els.queueList.appendChild(row); } }

function renderBackupJob(job) {
  if (!els.backupJobStatus) return;
  clearTimeout(state.backupPollTimer);
  if (!job) {
    state.backupJobId = null;
    els.backupJobProgress.style.width = "0%";
    els.cancelFullBackupButton.disabled = true;
    els.startFullBackupButton.disabled = false;
    els.backupJobStatus.textContent = "No backup job running.";
    return;
  }
  const active = ["queued", "running"].includes(job.status);
  state.backupJobId = job.job_id;
  els.backupJobProgress.style.width = `${Number(job.progress || 0)}%`;
  els.cancelFullBackupButton.disabled = !active;
  els.startFullBackupButton.disabled = active;
  const download = job.status === "complete" ? `<br><a href="/api/admin/backups/jobs/${encodeURIComponent(job.job_id)}/download">Download completed full backup ZIP</a>` : "";
  const warnings = (job.warnings || []).length ? `<br>Warnings: ${esc((job.warnings || []).join("; "))}` : "";
  els.backupJobStatus.innerHTML = `<strong>${esc(job.status || "unknown")}</strong> - ${esc(job.message || job.stage || "")}<br>Job: ${esc(job.job_id || "")}${download}${warnings}`;
  if (active) state.backupPollTimer = setTimeout(() => pollBackupJob().catch((err) => toast(err.message, true)), 2500);
}

function renderJobHistory(jobs = []) {
  if (!els.backupJobList) return;
  const rows = jobs.slice(0, 8).map((job) => {
    const download = job.status === "complete" && job.type === "full_backup" ? ` <a href="/api/admin/backups/jobs/${encodeURIComponent(job.job_id)}/download">Download</a>` : "";
    return `<div class="job-history-row"><span class="badge ${esc(job.status || "unknown")}">${esc(job.status || "unknown")}</span><strong>${esc(job.type || "job")}</strong><small>${esc(job.stage || "")} ${esc(job.message || "")}${download}</small></div>`;
  });
  els.backupJobList.innerHTML = rows.length ? rows.join("") : "No recent jobs yet.";
}

async function refreshBackupJobs() {
  const data = await api("/api/admin/backups/jobs");
  const jobs = data.jobs || [];
  renderBackupJob(jobs.find((job) => job.type === "full_backup") || jobs[0] || null);
  renderRestoreJob(jobs.find((job) => job.type === "full_restore") || null);
  renderJobHistory(jobs);
}

async function startFullBackup() {
  await withBusy(els.startFullBackupButton, async () => {
    const job = await api("/api/admin/backups/full/start", { method: "POST", timeoutMs: 60000 });
    renderBackupJob(job);
    toast("Full backup job started.");
  });
}

async function pollBackupJob() {
  if (!state.backupJobId) return refreshBackupJobs();
  try {
    renderBackupJob(await api(`/api/admin/backups/jobs/${encodeURIComponent(state.backupJobId)}`, { timeoutMs: 20000 }));
    refreshBackupJobs().catch(() => {});
  } catch (error) {
    clearTimeout(state.backupPollTimer);
    els.backupJobStatus.innerHTML = `<strong>Polling paused.</strong><br>${esc(error.message)}<br><button class="secondary-button" id="retryBackupPoll" type="button">Retry backup status</button>`;
    $("#retryBackupPoll")?.addEventListener("click", () => pollBackupJob().catch((err) => toast(err.message, true)));
    toast(error.message, true);
  }
}

async function cancelFullBackup() {
  if (!state.backupJobId) return;
  renderBackupJob(await api(`/api/admin/backups/jobs/${encodeURIComponent(state.backupJobId)}/cancel`, { method: "POST" }));
  toast("Backup cancellation requested.");
}

function renderRestoreJob(job) {
  if (!els.restoreJobStatus) return;
  clearTimeout(state.restorePollTimer);
  if (!job) {
    state.restoreJobId = null;
    els.restoreJobProgress.style.width = "0%";
    els.restoreDryRunButton.disabled = false;
    els.restoreConfirmButton.disabled = true;
    els.restoreJobStatus.textContent = "No restore job running.";
    return;
  }
  const active = ["queued", "running"].includes(job.status);
  state.restoreJobId = job.job_id;
  els.restoreJobProgress.style.width = `${Number(job.progress || 0)}%`;
  els.restoreDryRunButton.disabled = active;
  els.restoreConfirmButton.disabled = active || !(job.dry_run && job.status === "complete");
  state.restoreDryRunComplete = Boolean(job.dry_run && job.status === "complete");
  const counts = job.counts ? `<br>Originals ${job.counts.originals_written || 0}; References ${job.counts.references_written || 0}; AI ${job.counts.ai_translations_written || 0}; Prompts ${job.counts.prompts_written || 0}; Conflicts ${job.counts.conflicts || 0}; Skipped ${job.counts.skipped || 0}` : "";
  const warnings = (job.warnings || []).length ? `<br>Warnings: ${esc((job.warnings || []).join("; "))}` : "";
  els.restoreJobStatus.innerHTML = `<strong>${esc(job.status || "unknown")}</strong> - ${esc(job.message || job.stage || "")}<br>Job: ${esc(job.job_id || "")}; ${job.dry_run ? "Dry run" : "Real restore"}; ${esc(job.conflict_mode || "")}${counts}${warnings}`;
  if (active) state.restorePollTimer = setTimeout(() => pollRestoreJob().catch((err) => toast(err.message, true)), 2500);
}

async function startFullRestore(dryRun) {
  if (!els.restoreFile.files.length) return toast("Choose a full backup ZIP first.", true);
  if (!dryRun && !state.restoreDryRunComplete) return toast("Run and review a restore dry-run first.", true);
  if (!dryRun && !window.confirm("Restore this backup now? Existing files are handled by the selected conflict mode. No files are deleted.")) return;
  await withBusy(dryRun ? els.restoreDryRunButton : els.restoreConfirmButton, async () => {
    const form = new FormData();
    form.append("backup", els.restoreFile.files[0]);
    form.append("dry_run", dryRun ? "true" : "false");
    form.append("conflict_mode", els.restoreConflictMode.value || "write_missing_only");
    renderRestoreJob(await api("/api/admin/backups/full/restore", { method: "POST", body: form, timeoutMs: 120000 }));
    toast(dryRun ? "Restore dry-run started." : "Restore started.");
  });
}

async function pollRestoreJob() {
  if (!state.restoreJobId) return;
  try {
    const job = await api(`/api/admin/backups/jobs/${encodeURIComponent(state.restoreJobId)}`, { timeoutMs: 20000 });
    renderRestoreJob(job);
    if (job.status === "complete" && !job.dry_run) {
      await loadNovels();
      if (state.currentNovel) await openNovel(state.currentNovel.novel_id, { skipHistory: true, skipSave: true, initialTab: "backups" });
    }
  } catch (error) {
    clearTimeout(state.restorePollTimer);
    els.restoreJobStatus.innerHTML = `<strong>Polling paused.</strong><br>${esc(error.message)}<br><button class="secondary-button" id="retryRestorePoll" type="button">Retry restore status</button>`;
    $("#retryRestorePoll")?.addEventListener("click", () => pollRestoreJob().catch((err) => toast(err.message, true)));
    toast(error.message, true);
  }
}

function importMessage(result, label) {
  const warnings = (result.warnings || []).length ? ` Warnings: ${(result.warnings || []).join(" ")}` : "";
  return `Imported ${result.imported || 0} ${label}. Skipped ${result.skipped || result.duplicates || 0}. Invalid ${result.invalid || 0}. Destination: ${result.destination_category || label}.${warnings}`;
}

async function guardedImport(button, work) { return withBusy(button, work); }

async function importOriginalZip(event) { event.preventDefault(); if (!els.importOriginalFile.files.length) return toast("Choose an Original Story ZIP first.", true); await guardedImport(els.importOriginalButton, async () => { const form = new FormData(); form.append("original_zip", els.importOriginalFile.files[0]); const result = await api(`/api/novels/${state.currentNovel.novel_id}/import/original`, { method: "POST", body: form, timeoutMs: 120000 }); els.importOriginalFile.value = ""; await openNovel(state.currentNovel.novel_id); switchTab("backups"); toast(importMessage(result, "original chapters"), (result.warnings || []).length > 0); }); }
async function importReferenceZip(event) { event.preventDefault(); if (!els.importReferenceFile.files.length) return toast("Choose a Reference Translation ZIP first.", true); await guardedImport(els.importReferenceButton, async () => { const form = new FormData(); form.append("reference_zip", els.importReferenceFile.files[0]); const result = await api(`/api/novels/${state.currentNovel.novel_id}/import/reference`, { method: "POST", body: form, timeoutMs: 120000 }); els.importReferenceFile.value = ""; await openNovel(state.currentNovel.novel_id); switchTab("backups"); toast(importMessage(result, "reference chapters"), (result.warnings || []).length > 0); }); }
async function importAiTranslations(event) { event.preventDefault(); if (!els.importAiFile.files.length) return toast("Choose an AI translated chapters ZIP first.", true); await guardedImport(els.importAiButton, async () => { const form = new FormData(); form.append("translated_zip", els.importAiFile.files[0]); const result = await api(`/api/novels/${state.currentNovel.novel_id}/import/ai-translations`, { method: "POST", body: form, timeoutMs: 120000 }); els.importAiFile.value = ""; await openNovel(state.currentNovel.novel_id); switchTab("backups"); toast(importMessage(result, "AI translated chapters"), (result.warnings || []).length > 0); }); }
async function uploadCover(event) { event.preventDefault(); if (!els.coverFile.files.length) return toast("Choose a cover image first.", true); await withBusy(els.coverUploadButton, async () => { const form = new FormData(); form.append("cover", els.coverFile.files[0]); const result = await api(`/api/novels/${state.currentNovel.novel_id}/cover`, { method: "POST", body: form, timeoutMs: 60000 }); els.coverFile.value = ""; state.currentNovel = result.novel; state.chapters = result.chapters || state.chapters; await loadNovels(); renderDetail(); toast("Cover uploaded."); }); }
async function uploadAppIcon(event) { event.preventDefault(); if (!els.appIconFile.files.length) return toast("Choose an app icon first.", true); const form = new FormData(); form.append("icon", els.appIconFile.files[0]); state.appInfo = await api("/api/admin/app-icon", { method: "POST", body: form }); els.appIconFile.value = ""; applyAppInfo(); toast("App icon uploaded."); }
async function saveAppAppearance(event) {
  event.preventDefault();
  state.appInfo = await api("/api/admin/app-settings", { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: els.appDisplayName.value, subtitle: els.appSubtitleInput.value, theme: { main_accent: els.themeMainAccent.value, highlight: els.themeHighlight.value, logo_accent: els.themeLogoAccent.value, card_background: els.themeCardBackground.value, page_background: els.themePageBackground.value, reader_background: els.themeReaderBackground.value, reader_text: els.themeReaderText.value } }) });
  applyAppInfo();
  toast("Appearance saved.");
}
async function resetAppAppearance() {
  state.appInfo = await api("/api/admin/app-settings/reset", { method: "POST" });
  applyAppInfo();
  toast("Theme reset.");
}
async function saveSettings(event) { event.preventDefault(); state.currentNovel = await api(`/api/novels/${state.currentNovel.novel_id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title: els.settingsTitle.value, summary: els.settingsSummary.value, tags: els.settingsTags.value, source_language: els.sourceLanguage.value, target_language: els.targetLanguage.value, settings: { model: els.defaultModel.value } }) }); await loadNovels(); renderDetail(); toast("Settings saved."); }

async function login(event) { event.preventDefault(); await api("/api/admin/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password: els.adminPassword.value }) }); els.adminPassword.value = ""; els.adminDialog.close(); await loadAdminStatus(); toast("Admin unlocked."); }
async function logout() { await api("/api/admin/logout", { method: "POST" }); await loadAdminStatus(); toast("Admin locked."); }

function debounceChapters() { clearTimeout(state.searchTimer); state.searchTimer = setTimeout(() => { state.chapterPage = 1; renderChapters(); }, 180); }
async function openCurrentReader() { if (!state.currentNovel) { const last = loadReaderMemory(); if (last.novel_id) return openNovel(last.novel_id, { initialTab: "reader" }).then(() => openReader(last.chapter || firstReadableChapter(), last.mode || state.readerTab)); return toast("Open a novel first.", true); } return openReader(targetReaderChapter(), loadReaderMemory().mode || state.readerTab); }
async function refreshCurrentNovel(tab = activePanelName()) { if (!state.currentNovel) return; await openNovel(state.currentNovel.novel_id, { initialTab: tab, skipSave: true, skipHistory: true }); toast("Novel data refreshed."); }
function scrollLibrarySection(id) { showLibrary(); requestAnimationFrame(() => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" })); }
function setLibraryMode(mode, filter = null, query = "") { state.libraryMode = mode; if (filter !== null) els.browseFilter.value = filter; if (query !== null) els.novelSearch.value = query; showLibrary(); updateMainNav(mode === "home" ? "home" : mode); }
function applyBrowse(filter = "all", query = "") { setLibraryMode("browse", filter, query); requestAnimationFrame(() => els.novelGrid.scrollIntoView({ behavior: "smooth", block: "start" })); }
function cycleTheme() { const next = document.body.classList.contains("dark") ? "light" : "dark"; setTheme(next); toast(`Theme set to ${next}.`); }
function bind() {
  if (!els.rebuildIndexButton && els.migrateSupabaseButton) {
    els.rebuildIndexButton = document.createElement("button");
    els.rebuildIndexButton.className = "secondary-button";
    els.rebuildIndexButton.type = "button";
    els.rebuildIndexButton.textContent = "Rebuild Supabase Index";
    els.migrateSupabaseButton.insertAdjacentElement("afterend", els.rebuildIndexButton);
  }
  els.homeButton.onclick = () => showLibrary();
  els.backToLibrary.onclick = () => showLibrary();
  els.supportButton.onclick = () => { els.supportPanel.hidden = !els.supportPanel.hidden; };
  els.novelSearch.oninput = renderNovels;
  els.globalSearch.oninput = () => { if (state.currentNovel && els.detailView.classList.contains("active")) { els.chapterSearch.value = els.globalSearch.value; debounceChapters(); switchTab("chapters"); } else { els.novelSearch.value = els.globalSearch.value; renderNovels(); } };
  els.browseFilter.onchange = renderNovels;
  els.novelSort.onchange = renderNovels;
  els.chapterSearch.oninput = debounceChapters;
  els.chapterFilter.onchange = () => { state.chapterPage = 1; renderChapters(); };
  els.chapterSort.onchange = () => { state.chapterPage = 1; renderChapters(); };
  els.chapterPageSize.onchange = () => { state.pageSize = Number(els.chapterPageSize.value || 50); state.chapterPage = 1; renderChapters(); };
  els.chapterJump.onchange = () => { const chapter = Number(els.chapterJump.value); const index = filteredChapters().findIndex((c) => c.chapter === chapter); if (index >= 0) { state.chapterPage = Math.floor(index / state.pageSize) + 1; renderChapters(); } };
  els.prevPage.onclick = () => { state.chapterPage -= 1; renderChapters(); };
  els.nextPage.onclick = () => { state.chapterPage += 1; renderChapters(); };
  els.selectMissingAi.onclick = () => { state.selectedChapters = new Set(state.chapters.filter((c) => !c.has_translation).map((c) => chapterKey(state.currentNovel.novel_id, c.chapter))); renderChapters(); };
  els.selectCurrentPage.onclick = () => { const start = (state.chapterPage - 1) * state.pageSize; state.filteredChapters.slice(start, start + state.pageSize).forEach((c) => state.selectedChapters.add(chapterKey(state.currentNovel.novel_id, c.chapter))); renderChapters(); };
  els.clearSelectedChapters.onclick = () => { state.selectedChapters.clear(); renderChapters(); };
  document.querySelector("[data-home-browse]").onclick = () => applyBrowse("all");
  document.querySelector("[data-home-continue]").onclick = () => openCurrentReader().catch((err) => toast(err.message, true));
  document.querySelector("[data-home-login]").onclick = () => els.adminButton.click();
  els.themeToggle.onclick = cycleTheme;
  els.mainNav.forEach((button) => button.onclick = () => {
    const target = button.dataset.mainNav;
    if (target === "home") return setLibraryMode("home");
    if (target === "library") return setLibraryMode("library", "bookmarked");
    if (target === "browse") return applyBrowse("all");
    if (target === "rankings") return setLibraryMode("rankings");
    if (target === "updates") return setLibraryMode("updates");
    if (!state.currentNovel) return toast("Open a novel first.", true);
    if (target === "reader") return openCurrentReader().catch((err) => toast(err.message, true));
    switchTab(target);
  });
  els.quickReaderButton.onclick = () => openCurrentReader().catch((err) => toast(err.message, true));
  els.quickTranslateButton.onclick = () => state.currentNovel ? switchTab("translate") : toast("Open a novel first.", true);
  els.quickBackupButton.onclick = (event) => { event.preventDefault(); state.currentNovel ? switchTab("backups") : toast("Open a novel first.", true); };
  els.continueReadingButton.onclick = () => openCurrentReader().catch((err) => toast(err.message, true));
  els.novelBookmarkButton.onclick = () => state.currentNovel && toggleNovelBookmark(state.currentNovel.novel_id);
  els.overviewReaderButton.onclick = () => openCurrentReader().catch((err) => toast(err.message, true));
  els.openChaptersButton.onclick = () => switchTab("chapters");
  els.refreshNovelButton.onclick = () => refreshCurrentNovel(activePanelName()).catch((err) => toast(err.message, true));
  els.overviewTranslateButton.onclick = () => switchTab("translate");
  els.overviewBackupButton.onclick = () => switchTab("backups");
  tabs.forEach((button) => button.onclick = () => switchTab(button.dataset.tab));
  readerTabs.forEach((button) => button.onclick = () => openReader(state.readerChapter, button.dataset.readerTab));
  els.readerBack.onclick = () => backToNovelWorkspace().catch((err) => toast(err.message, true));
  els.readerLibrary.onclick = () => showLibrary();
  els.prevChapter.onclick = () => adjacent(-1);
  els.nextChapter.onclick = () => adjacent(1);
  els.prevChapterBottom.onclick = () => adjacent(-1);
  els.nextChapterBottom.onclick = () => adjacent(1);
  els.chapterPickerBottom.onclick = () => { renderChapterPicker(); els.chapterPickerPanel.hidden = false; };
  els.centerChapterPicker.onclick = () => { renderChapterPicker(); els.chapterPickerPanel.hidden = false; };
  els.centerChapterPicker.oncontextmenu = (event) => { event.preventDefault(); if (state.currentNovel && state.readerChapter) toggleChapterBookmark(state.currentNovel.novel_id, state.readerChapter); };
  els.readerBookmarkButton.onclick = () => { if (state.currentNovel && state.readerChapter) toggleChapterBookmark(state.currentNovel.novel_id, state.readerChapter); };
  els.backToTopButton.onclick = () => els.readerShell.scrollIntoView({ behavior: "smooth", block: "start" });
  els.chapterPickerButton.onclick = () => { renderChapterPicker(); els.chapterPickerPanel.hidden = !els.chapterPickerPanel.hidden; };
  els.fullscreenReader.onclick = () => { if (document.fullscreenElement) document.exitFullscreen(); else if (els.readerShell.requestFullscreen) els.readerShell.requestFullscreen(); };
  els.fontDown.onclick = () => { state.readerSize = Math.max(15, state.readerSize - 1); document.documentElement.style.setProperty("--reader-size", `${state.readerSize}px`); };
  els.fontUp.onclick = () => { state.readerSize = Math.min(24, state.readerSize + 1); document.documentElement.style.setProperty("--reader-size", `${state.readerSize}px`); };
  els.widthToggle.onclick = () => { state.readerWide = !state.readerWide; els.readerContent.classList.toggle("wide", state.readerWide); };
  els.readerTheme.onchange = () => { state.readerPrefs.theme = els.readerTheme.value; state.readerPrefs.background = readerThemeBackground(els.readerTheme.value); saveReaderPrefs(); };
  els.readerSettingsButton.onclick = () => { els.readerSettingsDrawer.hidden = false; };
  els.closeReaderSettings.onclick = () => { els.readerSettingsDrawer.hidden = true; };
  [["fontFamily", els.readerFontFamily], ["fontSize", els.readerFontSize], ["lineHeight", els.readerLineHeight], ["paragraphSpacing", els.readerParagraphSpacing], ["pageWidth", els.readerPageWidth], ["textAlign", els.readerTextAlign], ["background", els.readerBackground], ["accent", els.readerAccent]].forEach(([key, input]) => { input.oninput = () => { state.readerPrefs[key] = ["fontSize", "paragraphSpacing"].includes(key) ? Number(input.value) : key === "lineHeight" ? Number(input.value) : input.value; saveReaderPrefs(); }; });
  els.readerAllowCopy.onchange = () => { state.readerPrefs.allowCopy = els.readerAllowCopy.checked; saveReaderPrefs(); };
  els.adminButton.onclick = () => state.admin.authenticated ? logout().catch((err) => toast(err.message, true)) : (els.adminDialog.showModal ? els.adminDialog.showModal() : els.adminPassword.focus());
  els.adminForm.onsubmit = (event) => login(event).catch((err) => toast(err.message, true));
  els.accountButton.onclick = () => openAccountDialog(state.auth.authenticated ? "settings" : "login");
  els.registerButton.onclick = () => openAccountDialog("register");
  els.accountForm.onsubmit = (event) => submitAccount(event).catch((err) => toast(err.message, true));
  els.accountModeButton.onclick = () => openAccountDialog(state.accountMode === "register" ? "login" : "register");
  els.forgotPasswordButton.onclick = () => openAccountDialog("reset");
  els.logoutAccountButton.onclick = () => logoutAccount().catch((err) => toast(err.message, true));
  els.resendVerificationButton.onclick = async () => { await api("/api/auth/resend-verification", { method: "POST" }); toast("Verification email requested."); };
  els.accountDialog.addEventListener("click", (event) => { if (event.target === els.accountDialog) els.accountDialog.close(); });
  els.checkStorageButton.onclick = () => refreshStorageHealth().catch((err) => toast(err.message, true));
  els.migrateStorageButton.onclick = async () => { if (!window.confirm("Copy old local data into the configured DATA_DIR? Existing different files will be skipped, not overwritten.")) return; const report = await api("/api/admin/storage/migrate-local-data", { method: "POST" }); await refreshStorageHealth(); toast(`Migration copied ${report.copied || 0}, skipped ${report.skipped_existing || 0}, conflicts ${report.conflicts || 0}.`); };
  els.migrateSupabaseButton.onclick = async () => { if (!window.confirm("Migrate local novel data to Supabase Storage? This copies files and skips existing different files.")) return; const report = await api("/api/admin/storage/migrate-to-supabase", { method: "POST" }); await refreshStorageHealth(); toast(`Supabase migration: originals ${report.originals || 0}, references ${report.references || 0}, AI ${report.ai_translations || 0}, skipped ${report.skipped || 0}, conflicts ${report.conflicts || 0}.`); };
  els.rebuildIndexButton.onclick = async () => { const report = await api("/api/admin/index/rebuild", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ novel_id: state.currentNovel?.novel_id || null }), timeoutMs: 60000 }); await loadNovels(); if (state.currentNovel) await openNovel(state.currentNovel.novel_id, { skipHistory: true, skipSave: true, initialTab: "settings" }); await refreshStorageHealth(); toast(`Index rebuilt for ${(report.novels || []).length || 0} novel(s).`); };
  els.auditContentButton.onclick = () => auditContent().catch((err) => toast(err.message, true));
  els.dryRunRepairButton.onclick = () => repairContent(true).catch((err) => toast(err.message, true));
  els.applyRepairButton.onclick = () => repairContent(false).catch((err) => toast(err.message, true));
  els.startFullBackupButton.onclick = () => startFullBackup().catch((err) => toast(err.message, true));
  els.cancelFullBackupButton.onclick = () => cancelFullBackup().catch((err) => toast(err.message, true));
  els.refreshBackupJobsButton.onclick = () => refreshBackupJobs().catch((err) => toast(err.message, true));
  els.originalUploadForm.onsubmit = (event) => { event.preventDefault(); upload("original", event.submitter).catch((err) => toast(err.message, true)); };
  els.referenceUploadForm.onsubmit = (event) => { event.preventDefault(); upload("reference", event.submitter).catch((err) => toast(err.message, true)); };
  els.estimateBatch.onclick = () => buildEstimate().catch((err) => toast(err.message, true));
  els.startBatch.onclick = () => startBatch().catch((err) => toast(err.message, true));
  els.importOriginalForm.onsubmit = (event) => importOriginalZip(event).catch((err) => toast(err.message, true));
  els.importReferenceForm.onsubmit = (event) => importReferenceZip(event).catch((err) => toast(err.message, true));
  els.importAiForm.onsubmit = (event) => importAiTranslations(event).catch((err) => toast(err.message, true));
  els.coverUploadForm.onsubmit = (event) => uploadCover(event).catch((err) => toast(err.message, true));
  els.appIconForm.onsubmit = (event) => uploadAppIcon(event).catch((err) => toast(err.message, true));
  els.appAppearanceForm.onsubmit = (event) => saveAppAppearance(event).catch((err) => toast(err.message, true));
  els.resetThemeButton.onclick = () => resetAppAppearance().catch((err) => toast(err.message, true));
  els.restoreNovelForm.onsubmit = (event) => { event.preventDefault(); startFullRestore(true).catch((err) => toast(err.message, true)); };
  els.restoreConfirmButton.onclick = () => startFullRestore(false).catch((err) => toast(err.message, true));
  els.novelSettingsForm.onsubmit = (event) => saveSettings(event).catch((err) => toast(err.message, true));
  els.recoveryRetry.onclick = () => bootAppData().catch(showRecovery);
  els.recoveryCheckHealth.onclick = async () => {
    try {
      await api("/api/health", { timeoutMs: 12000 });
      els.recoveryMessage.textContent = "Health check passed. Retry loading the app.";
      toast("Health check passed.");
    } catch (error) {
      showRecovery(error);
    }
  };
  els.recoveryClearCache.onclick = () => clearFrontendCache().catch((err) => toast(err.message, true));
  els.addNovelButton.onclick = () => els.addNovelDialog.showModal ? els.addNovelDialog.showModal() : els.newNovelTitle.focus();
  els.cancelAddNovel.onclick = () => closeAddNovelDialog();
  els.addNovelDialog.addEventListener("click", (event) => { if (event.target === els.addNovelDialog) closeAddNovelDialog(); });
  els.addNovelDialog.addEventListener("close", () => els.addNovelForm.reset());
  els.addNovelForm.onsubmit = async (event) => { event.preventDefault(); if (!els.addNovelForm.reportValidity()) return; const title = els.newNovelTitle.value.trim(); const novel = await api("/api/novels", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title }) }); closeAddNovelDialog(); await loadNovels(); openNovel(novel.novel_id); };
  document.querySelectorAll("[data-footer-nav]").forEach((button) => button.onclick = () => {
    const target = button.dataset.footerNav;
    if (target === "rankings") return setLibraryMode("rankings");
    if (target === "updates") return setLibraryMode("updates");
    if (target === "reader") return openCurrentReader().catch((err) => toast(err.message, true));
    if (target === "backups" || target === "settings") return state.currentNovel ? switchTab(target) : toast("Open a novel first.", true);
    setLibraryMode("home");
  });
  document.querySelectorAll("[data-category]").forEach((button) => button.onclick = () => applyBrowse(button.dataset.category === "Completed" ? "completed" : `tag:${button.dataset.category}`));
  document.querySelectorAll("[data-admin-tab]").forEach((button) => button.onclick = () => state.currentNovel ? switchTab(button.dataset.adminTab) : toast("Open a novel first.", true));
  document.addEventListener("keydown", (event) => {
    if (event.target && ["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName)) return;
    if (event.key === "ArrowLeft" && els.readerPanel.classList.contains("active")) adjacent(-1);
    if (event.key === "ArrowRight" && els.readerPanel.classList.contains("active")) adjacent(1);
    if (event.key === "Escape") { els.chapterPickerPanel.hidden = true; els.readerSettingsDrawer.hidden = true; }
  });
  window.addEventListener("popstate", handleRouteChange);
  window.addEventListener("hashchange", handleRouteChange);
}

function registerServiceWorker() { if (!("serviceWorker" in navigator)) return; navigator.serviceWorker.register("/service-worker.js?v=75").then((registration) => registration.update()).catch(() => {}); }
async function bootAppData() {
  hideRecovery();
  els.novelGrid.innerHTML = '<div class="empty-state">Loading library...</div>';
  await loadAppInfo();
  await loadAdminStatus();
  await loadAuthState();
  try {
    await apiWithRetry("/api/health", { timeoutMs: 12000 });
    els.apiStatus.textContent = "Online";
    els.apiStatus.classList.add("ok");
  } catch (error) {
    els.apiStatus.textContent = "Waking";
    els.apiStatus.classList.remove("ok");
    throw error;
  }
  await loadNovels();
  if (state.auth.authenticated) await loadBackendLibrary().catch((err) => toast(err.message, true));
  await applyRouteFromLocation();
}
async function init() {
  registerServiceWorker();
  if (!window.location.hash) pushRoute(libraryRoute(), true);
  setTheme(localStorage.getItem("igt-theme") || "dark");
  loadLocalUiState();
  bind();
  loadReaderPrefs();
  renderWorkspaces();
  await bootAppData();
}
init().catch(showRecovery);

