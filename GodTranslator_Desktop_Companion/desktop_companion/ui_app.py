from __future__ import annotations

import queue
import subprocess
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

from . import APP_NAME, APP_VERSION
from .adapters import adapter_descriptors
from .jobs import JobManager
from .models import WebsiteConnectionProfile
from .packs import build_pack, validate_pack
from .paths import app_paths
from .recovery import load_recovery_request
from .storage import CompanionStore
from .sync import SyncManager


NAV_ITEMS = [
    "Dashboard",
    "Downloads",
    "Library",
    "New Novel",
    "Recovery",
    "Packs",
    "Sync",
    "Activity",
    "Settings",
    "Advanced Logs",
]


def run() -> None:
    try:
        import customtkinter as ctk
    except Exception as exc:
        raise SystemExit("CustomTkinter is required. Run SETUP_ONCE.bat first.") from exc
    paths = app_paths()
    store = CompanionStore(paths)
    manager = JobManager(store, paths)
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("green")
    app = DesktopCompanionApp(ctk, store, manager)
    app.mainloop()


class DesktopCompanionApp:
    def __init__(self, ctk, store: CompanionStore, manager: JobManager) -> None:
        self.ctk = ctk
        self.store = store
        self.manager = manager
        self.sync = SyncManager(store)
        self.paths = store.paths
        self.events: queue.Queue[str] = queue.Queue()
        self.recovery_request = None
        self.root = ctk.CTk()
        self.root.title(f"{APP_NAME} {APP_VERSION}")
        self.root.geometry("1180x760")
        self.root.minsize(980, 620)
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)
        self.nav = ctk.CTkFrame(self.root, width=220, corner_radius=0)
        self.nav.grid(row=0, column=0, sticky="nsew")
        self.content = ctk.CTkFrame(self.root, corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(1, weight=1)
        self._build_nav()
        self.show_home()
        self.root.after(1000, self._pump_events)

    def mainloop(self) -> None:
        self.root.mainloop()

    def _build_nav(self) -> None:
        self.ctk.CTkLabel(self.nav, text="GodTranslator", font=("Segoe UI", 22, "bold")).pack(anchor="w", padx=18, pady=(20, 2))
        self.ctk.CTkLabel(self.nav, text="Desktop Companion", text_color="#9fb7aa").pack(anchor="w", padx=18, pady=(0, 20))
        routes = {
            "Dashboard": self.show_home,
            "Downloads": self.show_downloads,
            "Library": self.show_desktop_library,
            "New Novel": self.show_new_novel,
            "Recovery": self.show_recovery_requests,
            "Packs": self.show_export_packs,
            "Sync": self.show_sync_center,
            "Activity": self.show_activity,
            "Settings": self.show_settings,
            "Advanced Logs": self.show_logs,
        }
        for label in NAV_ITEMS:
            self.ctk.CTkButton(self.nav, text=label, anchor="w", command=routes[label]).pack(fill="x", padx=12, pady=4)

    def _clear(self, title: str, subtitle: str) -> None:
        self.current_view = title
        for widget in self.content.winfo_children():
            widget.destroy()
        header = self.ctk.CTkFrame(self.content, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 10))
        self.ctk.CTkLabel(header, text=title, font=("Segoe UI", 28, "bold")).pack(anchor="w")
        self.ctk.CTkLabel(header, text=subtitle, text_color="#9fb7aa").pack(anchor="w")
        self.body = self.ctk.CTkScrollableFrame(self.content)
        self.body.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 24))
        self.body.grid_columnconfigure(0, weight=1)

    def show_home(self) -> None:
        self._clear("Dashboard", "Download, package, and sync novels without manual ZIP handling.")
        jobs = self.store.jobs()
        active = [job for job in jobs if job.status in {"queued", "starting", "opening_browser", "waiting_cloudflare", "downloading", "paused", "retrying"}]
        failed = [job for job in jobs if job.status == "failed"]
        completed = [job for job in jobs if job.status == "completed"]
        pack_count = len(list(self.paths.packs_dir.glob("*.zip")))
        sync = self.sync.center_snapshot()
        self._metrics([("Connection", sync["connection_health"]), ("Current jobs", len(active)), ("Failed jobs", len(failed)), ("Packs ready", pack_count), ("Pending uploads", sync["pending_uploads"]), ("Last sync", sync["last_sync"])])
        actions = self.ctk.CTkFrame(self.body)
        actions.grid(row=1, column=0, sticky="ew", pady=14)
        for text, command in (
            ("Download New Novel", self.show_new_novel),
            ("Open Recovery Request", self.open_recovery_request),
            ("Sync", self.show_sync_center),
            ("Open Downloads Folder", lambda: open_folder(Path(self.store.settings().get("downloads_folder") or self.paths.downloads_dir))),
        ):
            self.ctk.CTkButton(actions, text=text, command=command).pack(side="left", padx=8, pady=12)
        self._jobs_table("Recent Download Jobs", jobs[:8], row=2)

    def show_downloads(self) -> None:
        self._clear("Downloads", "Modern queue with progress, ETA, retries, workers, and upload state.")
        self._jobs_table("Jobs", self.store.jobs(), row=0, with_actions=True)

    def show_new_novel(self) -> None:
        self._clear("New Novel", "Paste a novel URL, download chapters, build packs, send to GodTranslator, then open the imported novel.")
        form = self.ctk.CTkFrame(self.body)
        form.grid(row=0, column=0, sticky="ew", pady=8)
        for column in range(2):
            form.grid_columnconfigure(column, weight=1)
        self.new_title = self._entry(form, "Novel title", 0, 0)
        self.new_author = self._entry(form, "Author", 0, 1)
        self.new_url = self._entry(form, "Source URL", 1, 0)
        self.new_reference_url = self._entry(form, "Optional Reference URL", 1, 1)
        self.new_language = self._entry(form, "Language", 2, 0, default="Chinese")
        self.new_range = self._entry(form, "Chapter range", 2, 1, default="1-10")
        self.new_folder = self._entry(form, "Download folder", 3, 0, default=str(self.paths.downloads_dir))
        self.new_adapter = self.ctk.CTkOptionMenu(form, values=[item.name for item in adapter_descriptors()])
        self.new_adapter.set("novelfire")
        self.new_adapter.grid(row=4, column=0, sticky="ew", padx=8, pady=8)
        self.new_auto_upload = self.ctk.CTkCheckBox(form, text="Send to GodTranslator after download")
        self.new_auto_upload.grid(row=4, column=1, sticky="w", padx=8, pady=8)
        self.mode_switch = self.ctk.CTkSegmentedButton(form, values=["Simple", "Advanced"])
        self.mode_switch.set("Simple")
        self.mode_switch.grid(row=3, column=1, sticky="ew", padx=8, pady=8)
        self.ctk.CTkButton(form, text="Detect Source", command=self.detect_source_from_form).grid(row=5, column=0, sticky="ew", padx=8, pady=12)
        self.ctk.CTkButton(form, text="Download Chapters", command=self.create_download_job_from_form).grid(row=5, column=1, sticky="ew", padx=8, pady=12)
        self.ctk.CTkButton(form, text="Send Latest Pack to GodTranslator", command=self.queue_latest_pack_upload).grid(row=6, column=0, sticky="ew", padx=8, pady=12)
        self.ctk.CTkButton(form, text="Open Imported Novel", command=self.open_current_novel_on_website).grid(row=6, column=1, sticky="ew", padx=8, pady=12)

    def show_recovery_requests(self) -> None:
        self._clear("Recovery", "Open a GodTranslator Recovery Request JSON, download missing chapters, and build a recovery pack.")
        self.ctk.CTkButton(self.body, text="Open Recovery Request JSON", command=self.open_recovery_request).grid(row=0, column=0, sticky="ew", pady=8)
        self.recovery_card = self.ctk.CTkFrame(self.body)
        self.recovery_card.grid(row=1, column=0, sticky="ew", pady=8)
        self._render_recovery_card()

    def show_export_packs(self) -> None:
        self._clear("Packs", "Build GodTranslator-compatible ZIP packs from verified local chapter files.")
        form = self.ctk.CTkFrame(self.body)
        form.grid(row=0, column=0, sticky="ew", pady=8)
        form.grid_columnconfigure(1, weight=1)
        self.pack_source = self._entry(form, "Source folder", 0, 0, default=str(self.paths.downloads_dir))
        self.pack_novel_id = self._entry(form, "Novel identifier", 1, 0, default="i-am-god")
        self.pack_novel_title = self._entry(form, "Novel title", 2, 0, default="I Am God")
        self.pack_mode = self.ctk.CTkOptionMenu(form, values=["reference", "original", "english", "mixed", "new_novel"])
        self.pack_mode.set("reference")
        self.pack_mode.grid(row=3, column=0, sticky="ew", padx=8, pady=8)
        self.ctk.CTkButton(form, text="Build Pack", command=self.build_pack_from_form).grid(row=4, column=0, sticky="ew", padx=8, pady=12)

    def show_sync_center(self) -> None:
        self._clear("Sync", "Connect to the website, preview uploads, execute imports, and review recent sync activity.")
        profiles = self.store.connection_profiles()
        profile = profiles[0]
        snapshot = self.sync.center_snapshot()
        self._metrics([
            ("Connected website", snapshot["connected_website"]),
            ("Connection health", snapshot["connection_health"]),
            ("Last sync", snapshot["last_sync"]),
            ("Pending uploads", snapshot["pending_uploads"]),
            ("Failed uploads", snapshot["failed_uploads"]),
            ("Queued uploads", snapshot["queued_uploads"]),
            ("Desktop version", snapshot["desktop_version"]),
            ("Website version", snapshot["website_version"]),
            ("API compatible", "Yes" if snapshot["version_compatible"] else "Needs check"),
        ])
        form = self.ctk.CTkFrame(self.body)
        form.grid(row=1, column=0, sticky="ew", pady=8)
        self.sync_url = self._entry(form, "Website URL", 0, 0, default=profile.base_url)
        self.sync_token = self._entry(form, "Manual bearer token (kept in memory only)", 1, 0, default=profile.auth_token, show="*")
        self.ctk.CTkButton(form, text="Remember Website", command=self.remember_website).grid(row=2, column=0, sticky="ew", padx=8, pady=8)
        self.ctk.CTkButton(form, text="Test Connection", command=self.test_connection).grid(row=2, column=1, sticky="ew", padx=8, pady=8)
        self.ctk.CTkButton(form, text="Authenticate", command=self.check_authentication).grid(row=3, column=0, sticky="ew", padx=8, pady=8)
        self.ctk.CTkButton(form, text="Upload Pack", command=self.select_pack_for_upload).grid(row=3, column=1, sticky="ew", padx=8, pady=8)
        self.ctk.CTkButton(form, text="Manual Sync", command=self.refresh_sync_status).grid(row=4, column=0, sticky="ew", padx=8, pady=8)
        self.sync_result = self.ctk.CTkTextbox(self.body, height=220)
        self.sync_result.grid(row=2, column=0, sticky="ew", pady=8)
        self._uploads_table(row=3)

    def show_desktop_library(self) -> None:
        self._clear("Library", "Downloaded novels with download, website, and import status.")
        jobs = self.store.jobs()
        if not jobs:
            self._plain_text("No downloaded novels yet.")
            return
        self._jobs_table("Downloaded Novels", jobs, row=0, with_actions=True)

    def show_activity(self) -> None:
        self._clear("Activity", "Recent local job and pack activity.")
        self._jobs_table("Recent Jobs", self.store.jobs()[:20], row=0)

    def show_settings(self) -> None:
        self._clear("Settings", "Local settings stay under %LOCALAPPDATA%\\GodTranslatorDesktop.")
        settings = self.store.settings()
        self._plain_text(f"Local data:\n{self.paths.root}\n\nDownloads folder:\n{settings.get('downloads_folder')}\n\nMode:\n{settings.get('mode')}\n\nWebsite:\n{settings.get('default_website_url')}")

    def show_logs(self) -> None:
        self._clear("Advanced Logs", "Local activity log.")
        path = self.paths.logs_dir / "activity.log"
        self._plain_text(path.read_text(encoding="utf-8") if path.exists() else "No log entries yet.")

    def _metrics(self, items: list[tuple[str, object]]) -> None:
        frame = self.ctk.CTkFrame(self.body)
        frame.grid(row=0, column=0, sticky="ew")
        for label, value in items:
            card = self.ctk.CTkFrame(frame)
            card.pack(side="left", expand=True, fill="x", padx=6, pady=10)
            self.ctk.CTkLabel(card, text=label, text_color="#9fb7aa").pack(anchor="w", padx=12, pady=(10, 0))
            self.ctk.CTkLabel(card, text=str(value), font=("Segoe UI", 20, "bold")).pack(anchor="w", padx=12, pady=(0, 10))

    def _jobs_table(self, title: str, jobs, row: int = 0, with_actions: bool = False) -> None:
        frame = self.ctk.CTkFrame(self.body)
        frame.grid(row=row, column=0, sticky="ew", pady=10)
        self.ctk.CTkLabel(frame, text=title, font=("Segoe UI", 18, "bold")).pack(anchor="w", padx=12, pady=(12, 4))
        if not jobs:
            self.ctk.CTkLabel(frame, text="No jobs yet.", text_color="#9fb7aa").pack(anchor="w", padx=12, pady=12)
            return
        for job in jobs:
            active = job.status in {"starting", "opening_browser", "waiting_cloudflare", "downloading", "retrying"}
            card = self.ctk.CTkFrame(frame)
            card.pack(fill="x", padx=10, pady=8)
            top = self.ctk.CTkFrame(card, fg_color="transparent")
            top.pack(fill="x", padx=10, pady=(10, 4))
            self.ctk.CTkLabel(top, text=job.novel_title, font=("Segoe UI", 16, "bold"), anchor="w").pack(side="left", fill="x", expand=True)
            self.ctk.CTkLabel(top, text=format_status(job.status), text_color=status_color(job.status), font=("Segoe UI", 13, "bold")).pack(side="right", padx=8)

            progress = self.ctk.CTkProgressBar(card)
            progress.pack(fill="x", padx=10, pady=4)
            progress.set(job_progress_fraction(job))

            details = (
                f"Current Novel: {job.novel_title} | Current Chapter: {job.current_chapter or '-'} | "
                f"Last downloaded chapter: {job.last_downloaded_chapter or '-'} | Remaining chapters: {job.remaining} | "
                f"Downloaded chapters: {len(job.downloaded_chapters) or job.completed} | Failed chapters: {len(job.failed_chapters) or job.failed} | "
                f"Retries: {job.retry_events} | Elapsed: {format_seconds(job.elapsed_seconds)} | "
                f"Average: {job.download_speed_cpm:.1f} chapters/minute | ETA: {format_seconds(job.estimated_remaining_seconds)}"
            )
            self.ctk.CTkLabel(card, text=details, anchor="w", wraplength=900, justify="left").pack(fill="x", padx=10, pady=2)
            state_line = (
                f"Browser state: {job.browser_state} | Worker state: {job.worker_state} | "
                f"Current URL: {short_text(job.current_url or job.source_url, 120)} | Current output folder: {job.output_dir}"
            )
            self.ctk.CTkLabel(card, text=state_line, text_color="#9fb7aa", anchor="w", wraplength=900, justify="left").pack(fill="x", padx=10, pady=2)
            if job.live_log:
                log_box = self.ctk.CTkTextbox(card, height=92)
                log_box.insert("1.0", "\n".join(job.live_log[-8:]))
                log_box.configure(state="disabled")
                log_box.pack(fill="x", padx=10, pady=(4, 8))
            if with_actions:
                actions = self.ctk.CTkFrame(card, fg_color="transparent")
                actions.pack(fill="x", padx=8, pady=(0, 10))
                primary = self.ctk.CTkFrame(actions, fg_color="transparent")
                secondary = self.ctk.CTkFrame(actions, fg_color="transparent")
                primary.pack(fill="x")
                secondary.pack(fill="x")
                self._job_button(primary, "Start", "start", job.id, job.status in {"queued", "failed"})
                self._job_button(primary, "Pause", "pause", job.id, active)
                self._job_button(primary, "Resume", "resume", job.id, job.status in {"paused", "stopped"})
                self._job_button(primary, "Stop", "stop", job.id, active)
                self._job_button(primary, "Retry Failed", "retry", job.id, bool(job.failed or job.failed_chapters or job.errors))
                self._job_button(primary, "Restart Job", "restart", job.id, not active)
                self._job_button(secondary, "Duplicate Job", "duplicate", job.id, True)
                self._job_button(secondary, "Delete Job", "delete", job.id, not active)
                self._job_button(secondary, "Build Pack", "build_pack", job.id, not active, width=104)
                self._job_button(secondary, "Send to GodTranslator", "send", job.id, bool(job.packs_built) or Path(job.output_dir).exists(), width=160)
                self.ctk.CTkButton(secondary, text="Open Output Folder", width=132, command=lambda folder=job.novel_root_dir or job.output_dir: open_folder(Path(folder))).pack(side="left", padx=2, pady=2)
                self.ctk.CTkButton(secondary, text="Copy Output Path", width=126, command=lambda text=job.output_dir: self.copy_text(text)).pack(side="left", padx=2, pady=2)
                self._job_button(secondary, "Reveal Current Chapter", "reveal", job.id, bool(job.current_chapter or job.last_downloaded_chapter), width=150)

    def _job_button(self, parent, text: str, action: str, job_id: str, enabled: bool, width: int = 96) -> None:
        self.ctk.CTkButton(
            parent,
            text=text,
            width=width,
            state="normal" if enabled else "disabled",
            command=lambda jid=job_id, act=action: self._job_action(act, jid),
        ).pack(side="left", padx=2, pady=2)

    def _entry(self, parent, label: str, row: int, column: int, default: str = "", show: str | None = None):
        wrapper = self.ctk.CTkFrame(parent, fg_color="transparent")
        wrapper.grid(row=row, column=column, sticky="ew", padx=8, pady=6)
        self.ctk.CTkLabel(wrapper, text=label, text_color="#9fb7aa").pack(anchor="w")
        entry = self.ctk.CTkEntry(wrapper, show=show)
        entry.insert(0, default)
        entry.pack(fill="x")
        return entry

    def _plain_text(self, text: str) -> None:
        box = self.ctk.CTkTextbox(self.body, height=420)
        box.insert("1.0", text)
        box.configure(state="disabled")
        box.grid(row=0, column=0, sticky="nsew", pady=8)

    def create_download_job_from_form(self) -> None:
        try:
            chapters = parse_chapter_range(self.new_range.get())
            profile = self.sync.profile()
            job = self.manager.create_job(
                novel_title=self.new_title.get() or "Untitled Novel",
                source_url=self.new_url.get(),
                chapters=chapters,
                output_dir=Path(self.new_folder.get()),
                source_adapter=self.new_adapter.get(),
                website_url=profile.base_url,
                auto_upload=bool(self.new_auto_upload.get()),
                browser_mode=True,
            )
            self.store.append_log(f"Created job {job.id}")
            self.manager.start(job.id)
            messagebox.showinfo(APP_NAME, f"Job started: {job.id}")
            self.show_downloads()
        except Exception as exc:
            messagebox.showerror(APP_NAME, friendly_error(exc))

    def copy_text(self, value: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        self.store.append_log(f"Copied output path {value}")

    def reveal_current_chapter(self, job_id: str) -> None:
        job = self.manager.require_job(job_id)
        path = chapter_file_path(job)
        if path and path.exists():
            subprocess.run(["explorer", "/select,", str(path)], check=False)
            return
        open_folder(Path(job.output_dir))

    def detect_source_from_form(self) -> None:
        url = self.new_url.get().lower()
        if "novelfire" in url:
            self.new_adapter.set("novelfire")
            messagebox.showinfo(APP_NAME, "Source detected: NovelFire")
            return
        messagebox.showinfo(APP_NAME, "Source not recognized yet. Use NovelFire or choose an advanced adapter.")

    def open_recovery_request(self) -> None:
        path_text = filedialog.askopenfilename(title="Open Recovery Request", filetypes=[("JSON files", "*.json")])
        if not path_text:
            return
        try:
            self.recovery_request = load_recovery_request(Path(path_text))
            self.store.append_log(f"Opened Recovery Request {path_text}")
            self.show_recovery_requests()
        except Exception as exc:
            messagebox.showerror(APP_NAME, friendly_error(exc))

    def _render_recovery_card(self) -> None:
        for widget in self.recovery_card.winfo_children():
            widget.destroy()
        if not self.recovery_request:
            self.ctk.CTkLabel(self.recovery_card, text="No Recovery Request opened yet.", text_color="#9fb7aa").pack(anchor="w", padx=12, pady=12)
            return
        info = self.recovery_request
        lines = [
            f"Novel: {info.novel_title} ({info.novel_id})",
            f"Source: {info.source_type} | {info.source_url or 'not provided'}",
            f"Target mode: {info.target_mode}",
            f"Missing chapters: {len(info.chapters)}",
            f"Chapter URL template: {info.chapter_url_template or 'not provided'}",
            f"Request created: {info.created_at or 'not included'}",
        ]
        self.ctk.CTkLabel(self.recovery_card, text="\n".join(lines), justify="left").pack(anchor="w", padx=12, pady=12)
        self.ctk.CTkButton(self.recovery_card, text="Download Missing Chapters", command=self.create_job_from_recovery).pack(anchor="w", padx=12, pady=6)
        self.ctk.CTkButton(self.recovery_card, text="Upload Recovery Pack", command=self.queue_latest_pack_upload).pack(anchor="w", padx=12, pady=6)

    def create_job_from_recovery(self) -> None:
        if not self.recovery_request:
            return
        info = self.recovery_request
        output_dir = self.paths.downloads_dir / info.novel_id / "reference"
        job = self.manager.create_job(
            novel_title=info.novel_title,
            source_url=info.source_url,
            chapters=info.chapters,
            output_dir=output_dir,
            source_adapter=info.source_type or "novelfire",
            target_mode=info.target_mode,
            website_url=self.sync.profile().base_url,
            novel_id=info.novel_id,
            auto_upload=True,
            browser_mode=True,
        )
        self.store.append_log(f"Created recovery job {job.id}")
        self.manager.start(job.id)
        self.show_downloads()

    def build_pack_from_form(self) -> None:
        try:
            result = build_pack(
                source_dir=Path(self.pack_source.get()),
                output_dir=self.paths.packs_dir,
                novel_id=self.pack_novel_id.get() or "i-am-god",
                novel_title=self.pack_novel_title.get() or "I Am God",
                target_mode=self.pack_mode.get(),
            )
            validate_pack(result.path)
            self.store.append_log(f"Built pack {result.path}")
            messagebox.showinfo(APP_NAME, f"Pack created:\n{result.path}")
        except Exception as exc:
            messagebox.showerror(APP_NAME, friendly_error(exc))

    def test_connection(self) -> None:
        self.sync.save_profile(self.sync_url.get(), self.sync_token.get())
        self.sync_result.delete("1.0", "end")
        self.sync_result.insert("1.0", "Testing connection...\n")

        def worker() -> None:
            try:
                payload = self.sync.test_connection()
                self.events.put(f"Website health OK: {payload}")
            except Exception as exc:
                self.events.put(f"Website health failed: {friendly_error(exc)}")

        threading.Thread(target=worker, daemon=True).start()

    def remember_website(self) -> None:
        profile = self.sync.save_profile(self.sync_url.get(), self.sync_token.get())
        self.store.append_log(f"Remembered website {profile.base_url}")
        self.sync_result.insert("end", f"Remembered website: {profile.base_url}\n")

    def check_authentication(self) -> None:
        self.remember_website()

        def worker() -> None:
            try:
                self.events.put(f"Authentication OK: {self.sync.auth_check()}")
            except Exception as exc:
                self.events.put(f"Authentication failed: {friendly_error(exc)}")

        threading.Thread(target=worker, daemon=True).start()

    def refresh_sync_status(self) -> None:
        self.remember_website()

        def worker() -> None:
            try:
                self.events.put(f"Sync status: {self.sync.sync_status()}")
            except Exception as exc:
                self.events.put(f"Sync failed: {friendly_error(exc)}")

        threading.Thread(target=worker, daemon=True).start()

    def select_pack_for_upload(self) -> None:
        path_text = filedialog.askopenfilename(title="Upload GodTranslator Pack", filetypes=[("ZIP packs", "*.zip")])
        if not path_text:
            return
        novel_id = Path(path_text).name.split("-")[0] or "imported-novel"
        upload = self.sync.queue_upload(Path(path_text), novel_id=novel_id, content_type="original")
        self.preview_and_execute_upload(upload.id)

    def queue_latest_pack_upload(self) -> None:
        packs = sorted(self.paths.packs_dir.glob("*.zip"), key=lambda path: path.stat().st_mtime, reverse=True)
        if not packs:
            messagebox.showinfo(APP_NAME, "No packs are ready yet.")
            return
        novel_id = packs[0].name.split("-")[0] or "imported-novel"
        upload = self.sync.queue_upload(packs[0], novel_id=novel_id, content_type="original")
        self.preview_and_execute_upload(upload.id)

    def preview_and_execute_upload(self, upload_id: str) -> None:
        if hasattr(self, "sync_result"):
            self.sync_result.insert("end", f"Previewing upload {upload_id}...\n")

        def worker() -> None:
            try:
                preview = self.sync.preview_upload(upload_id)
                self.events.put(f"Preview ready: {preview.preview.get('estimated_import') or preview.preview.get('summary')}")
                self.events.put("Import not applied yet. Review the preview, then use Execute Import in Sync.")
            except Exception as exc:
                self.events.put(f"Upload failed: {friendly_error(exc)}")

        threading.Thread(target=worker, daemon=True).start()

    def open_current_novel_on_website(self) -> None:
        self.sync.open_imported_novel(safe_slug(self.new_title.get() or "imported-novel"))

    def _uploads_table(self, row: int = 0) -> None:
        uploads = self.store.uploads()[:8]
        frame = self.ctk.CTkFrame(self.body)
        frame.grid(row=row, column=0, sticky="ew", pady=10)
        self.ctk.CTkLabel(frame, text="Recent Imports", font=("Segoe UI", 18, "bold")).pack(anchor="w", padx=12, pady=(12, 4))
        if not uploads:
            self.ctk.CTkLabel(frame, text="No uploads yet.", text_color="#9fb7aa").pack(anchor="w", padx=12, pady=12)
            return
        for upload in uploads:
            row_frame = self.ctk.CTkFrame(frame, fg_color="transparent")
            row_frame.pack(fill="x", padx=12, pady=5)
            line = f"{Path(upload.pack_path).name} | {upload.status} | {upload.progress_percent}% | {upload.last_activity}"
            self.ctk.CTkLabel(row_frame, text=line, anchor="w").pack(side="left", fill="x", expand=True)
            self.ctk.CTkButton(row_frame, text="Preview", width=82, state="normal" if upload.status in {"queued", "failed"} else "disabled", command=lambda uid=upload.id: self.preview_upload_action(uid)).pack(side="left", padx=2)
            self.ctk.CTkButton(row_frame, text="Execute Import", width=116, state="normal" if upload.status == "previewed" else "disabled", command=lambda uid=upload.id: self.execute_upload_action(uid)).pack(side="left", padx=2)
            self.ctk.CTkButton(row_frame, text="Retry", width=72, state="normal" if upload.status == "failed" else "disabled", command=lambda uid=upload.id: self.retry_upload_action(uid)).pack(side="left", padx=2)
            self.ctk.CTkButton(row_frame, text="Open Novel", width=96, state="normal" if upload.status == "imported" else "disabled", command=lambda nid=upload.novel_id: self.sync.open_imported_novel(nid)).pack(side="left", padx=2)

    def preview_upload_action(self, upload_id: str) -> None:
        self.preview_and_execute_upload(upload_id)

    def execute_upload_action(self, upload_id: str) -> None:
        if hasattr(self, "sync_result"):
            self.sync_result.insert("end", f"Executing import {upload_id}...\n")

        def worker() -> None:
            try:
                imported = self.sync.execute_upload(upload_id)
                self.events.put(f"Import summary: {imported.result.get('summary')}")
            except Exception as exc:
                self.events.put(f"Import failed: {friendly_error(exc)}")

        threading.Thread(target=worker, daemon=True).start()

    def retry_upload_action(self, upload_id: str) -> None:
        try:
            self.sync.retry_upload(upload_id)
            if hasattr(self, "sync_result"):
                self.sync_result.insert("end", f"Retry queued: {upload_id}\n")
            self.show_sync_center()
        except Exception as exc:
            messagebox.showerror(APP_NAME, friendly_error(exc))

    def _pump_events(self) -> None:
        while not self.events.empty():
            message = self.events.get()
            self.store.append_log(message)
            if hasattr(self, "sync_result"):
                self.sync_result.insert("end", message + "\n")
        if getattr(self, "current_view", "") == "Downloads" and any(job.status in {"starting", "opening_browser", "waiting_cloudflare", "downloading", "retrying"} for job in self.store.jobs()):
            self.show_downloads()
        self.root.after(1000, self._pump_events)

    def _job_action(self, action: str, job_id: str) -> None:
        try:
            if action == "pause":
                self.manager.pause(job_id)
            elif action == "resume":
                self.manager.start(self.manager.resume(job_id).id)
            elif action == "start":
                self.manager.start(job_id)
            elif action == "retry":
                self.manager.start(self.manager.retry_failed(job_id).id)
            elif action == "restart":
                self.manager.start(self.manager.restart_job(job_id).id)
            elif action == "duplicate":
                self.manager.duplicate_job(job_id)
            elif action == "delete":
                if messagebox.askyesno(APP_NAME, "Delete this job from the local queue? Output files will not be deleted."):
                    self.manager.delete_job(job_id)
            elif action == "build_pack":
                job = self.manager.build_pack_for_job(job_id)
                messagebox.showinfo(APP_NAME, f"Pack ready:\n{job.packs_built[-1] if job.packs_built else 'No pack path recorded'}")
            elif action == "send":
                self.queue_pack_upload_for_job(job_id)
            elif action == "reveal":
                self.reveal_current_chapter(job_id)
            elif action == "stop":
                self.manager.stop(job_id)
            self.show_downloads()
        except Exception as exc:
            messagebox.showerror(APP_NAME, friendly_error(exc))

    def queue_pack_upload_for_job(self, job_id: str) -> None:
        job = self.manager.require_job(job_id)
        pack_path = latest_pack_for_job(job)
        if pack_path is None:
            job = self.manager.build_pack_for_job(job_id)
            pack_path = latest_pack_for_job(job)
        if pack_path is None:
            raise ValueError("Build a pack before sending this job.")
        upload = self.sync.queue_upload(pack_path, novel_id=job.novel_id or safe_slug(job.novel_title), content_type=job.target_mode)
        self.store.append_log(f"Queued pack upload {upload.id} from job {job.id}")
        self.preview_and_execute_upload(upload.id)


def parse_chapter_range(value: str) -> list[int]:
    chapters: set[int] = set()
    for part in value.replace(";", ",").split(","):
        text = part.strip()
        if not text:
            continue
        if "-" in text:
            left, right = text.split("-", 1)
            start, end = int(left), int(right)
            chapters.update(range(min(start, end), max(start, end) + 1))
        else:
            chapters.add(int(text))
    if not chapters:
        raise ValueError("Enter at least one chapter.")
    return sorted(chapters)


def open_folder(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    import os

    os.startfile(str(path))


def format_seconds(value: float | None) -> str:
    if value is None:
        return "Unknown"
    seconds = int(max(0, value))
    minutes, seconds = divmod(seconds, 60)
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def job_progress_fraction(job) -> float:
    total = len(job.chapters)
    if total <= 0:
        return 0.0
    finished = min(total, job.completed + job.skipped + job.failed)
    return max(0.0, min(1.0, finished / total))


def format_status(status: str) -> str:
    labels = {
        "queued": "Queued",
        "starting": "Starting",
        "opening_browser": "Opening Browser",
        "waiting_cloudflare": "Waiting Cloudflare",
        "downloading": "Downloading",
        "paused": "Paused",
        "retrying": "Retrying",
        "completed": "Completed",
        "stopped": "Stopped",
        "failed": "Failed",
        "cancelled": "Stopped",
    }
    return labels.get(status, status.replace("_", " ").title())


def status_color(status: str) -> str:
    if status == "completed":
        return "#6ee7b7"
    if status in {"failed", "cancelled"}:
        return "#fca5a5"
    if status in {"paused", "stopped"}:
        return "#fbbf24"
    if status in {"retrying", "waiting_cloudflare"}:
        return "#93c5fd"
    return "#d1fae5"


def short_text(value: str, limit: int) -> str:
    text = value or ""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def chapter_file_path(job) -> Path | None:
    chapter = job.current_chapter or job.last_downloaded_chapter
    if chapter is None:
        return None
    width = max(4, len(str(max(job.chapters) if job.chapters else chapter)))
    return Path(job.output_dir) / f"{chapter:0{width}d}.txt"


def latest_pack_for_job(job) -> Path | None:
    for path_text in reversed(job.packs_built):
        path = Path(path_text)
        if path.exists():
            return path
    pack_dir = Path(job.novel_root_dir or Path(job.output_dir).parent) / "Packs"
    packs = sorted(pack_dir.glob("*.zip"), key=lambda path: path.stat().st_mtime, reverse=True) if pack_dir.exists() else []
    return packs[0] if packs else None


def safe_slug(value: str) -> str:
    text = "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")
    while "--" in text:
        text = text.replace("--", "-")
    return text[:80] or "imported-novel"


def friendly_error(exc: Exception) -> str:
    text = str(exc) or exc.__class__.__name__
    if "\n" in text:
        text = text.splitlines()[0]
    return text[:300]
