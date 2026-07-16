from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4


JobStatus = Literal["queued", "running", "paused", "completed", "failed", "cancelled"]
TargetMode = Literal["reference", "original", "english", "mixed", "new_novel"]
UploadStatus = Literal["queued", "previewed", "imported", "failed", "cancelled"]


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


@dataclass
class DownloadJob:
    id: str
    novel_title: str
    source_adapter: str
    source_url: str
    output_dir: str
    chapters: list[int]
    website_url: str = ""
    novel_id: str = ""
    status: JobStatus = "queued"
    target_mode: TargetMode = "reference"
    browser_mode: bool = True
    skip_existing: bool = True
    resume_existing: bool = True
    auto_build_packs: bool = True
    auto_upload: bool = False
    delay_seconds: float = 3.0
    retry_count: int = 2
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    current_chapter: int | None = None
    last_activity: str = ""
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    started_at: str | None = None
    finished_at: str | None = None
    elapsed_seconds: float = 0.0
    estimated_remaining_seconds: float | None = None
    download_speed_cpm: float = 0.0
    current_worker: str = "local"
    packs_built: list[str] = field(default_factory=list)
    website_import_status: str = "not_uploaded"
    last_sync_at: str | None = None
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def remaining(self) -> int:
        return max(0, len(self.chapters) - self.completed - self.failed - self.skipped)

    @property
    def chapter_range_label(self) -> str:
        if not self.chapters:
            return "No chapters"
        if len(self.chapters) == 1:
            return str(self.chapters[0])
        return f"{min(self.chapters)}-{max(self.chapters)}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DownloadJob":
        return cls(
            id=str(payload.get("id") or new_id("job")),
            novel_title=str(payload.get("novel_title") or "Untitled Novel"),
            source_adapter=str(payload.get("source_adapter") or "novelfire"),
            source_url=str(payload.get("source_url") or ""),
            output_dir=str(payload.get("output_dir") or ""),
            chapters=[int(chapter) for chapter in payload.get("chapters", [])],
            website_url=str(payload.get("website_url") or ""),
            novel_id=str(payload.get("novel_id") or ""),
            status=payload.get("status") if payload.get("status") in {"queued", "running", "paused", "completed", "failed", "cancelled"} else "queued",
            target_mode=payload.get("target_mode") if payload.get("target_mode") in {"reference", "original", "english", "mixed", "new_novel"} else "reference",
            browser_mode=bool(payload.get("browser_mode", True)),
            skip_existing=bool(payload.get("skip_existing", True)),
            resume_existing=bool(payload.get("resume_existing", True)),
            auto_build_packs=bool(payload.get("auto_build_packs", True)),
            auto_upload=bool(payload.get("auto_upload", False)),
            delay_seconds=float(payload.get("delay_seconds") or 0),
            retry_count=int(payload.get("retry_count") or 0),
            completed=int(payload.get("completed") or 0),
            failed=int(payload.get("failed") or 0),
            skipped=int(payload.get("skipped") or 0),
            current_chapter=payload.get("current_chapter"),
            last_activity=str(payload.get("last_activity") or ""),
            created_at=str(payload.get("created_at") or utc_now()),
            updated_at=str(payload.get("updated_at") or utc_now()),
            started_at=payload.get("started_at"),
            finished_at=payload.get("finished_at"),
            elapsed_seconds=float(payload.get("elapsed_seconds") or 0),
            estimated_remaining_seconds=payload.get("estimated_remaining_seconds"),
            download_speed_cpm=float(payload.get("download_speed_cpm") or 0),
            current_worker=str(payload.get("current_worker") or "local"),
            packs_built=[str(path) for path in payload.get("packs_built", [])],
            website_import_status=str(payload.get("website_import_status") or "not_uploaded"),
            last_sync_at=payload.get("last_sync_at"),
            errors={str(k): str(v) for k, v in dict(payload.get("errors") or {}).items()},
        )


@dataclass(frozen=True)
class RecoveryRequestInfo:
    path: str
    novel_id: str
    novel_title: str
    target_mode: TargetMode
    source_type: str
    source_url: str
    chapter_url_template: str
    chapters: list[int]
    created_at: str | None = None

    @property
    def missing_count(self) -> int:
        return len(self.chapters)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PackResult:
    path: Path
    manifest: dict[str, Any]
    file_count: int
    total_characters: int


@dataclass
class UploadJob:
    id: str
    pack_path: str
    novel_id: str
    content_type: str = "original"
    website_url: str = "https://iamgodtranslator.onrender.com"
    status: UploadStatus = "queued"
    preview: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    progress_percent: int = 0
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    last_activity: str = "Queued"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "UploadJob":
        return cls(
            id=str(payload.get("id") or new_id("upload")),
            pack_path=str(payload.get("pack_path") or ""),
            novel_id=str(payload.get("novel_id") or ""),
            content_type=str(payload.get("content_type") or "original"),
            website_url=str(payload.get("website_url") or "https://iamgodtranslator.onrender.com"),
            status=payload.get("status") if payload.get("status") in {"queued", "previewed", "imported", "failed", "cancelled"} else "queued",
            preview=dict(payload.get("preview") or {}),
            result=dict(payload.get("result") or {}),
            error=str(payload.get("error") or ""),
            progress_percent=int(payload.get("progress_percent") or 0),
            created_at=str(payload.get("created_at") or utc_now()),
            updated_at=str(payload.get("updated_at") or utc_now()),
            last_activity=str(payload.get("last_activity") or "Queued"),
        )


@dataclass
class WebsiteConnectionProfile:
    name: str = "Production"
    base_url: str = "https://iamgodtranslator.onrender.com"
    auth_token: str = ""
    last_health: str = "Not tested"
    last_sync_at: str = ""

    def safe_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "base_url": self.base_url,
            "has_token": bool(self.auth_token),
            "last_health": self.last_health,
            "last_sync_at": self.last_sync_at,
        }
