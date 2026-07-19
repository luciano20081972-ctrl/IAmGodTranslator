from __future__ import annotations

from pathlib import Path
from typing import Any
import webbrowser

from . import APP_VERSION
from .models import UploadJob, WebsiteConnectionProfile, new_id, utc_now
from .storage import CompanionStore
from .website_api import WebsiteClient


class SyncManager:
    def __init__(self, store: CompanionStore) -> None:
        self.store = store
        self._session_token = ""

    def profile(self) -> WebsiteConnectionProfile:
        profile = self.store.connection_profiles()[0]
        profile.auth_token = self._session_token
        return profile

    def save_profile(self, base_url: str, auth_token: str = "") -> WebsiteConnectionProfile:
        current = self.profile()
        self._session_token = auth_token.strip()
        profile = WebsiteConnectionProfile(
            name=current.name or "Production",
            base_url=base_url.rstrip("/") or current.base_url,
            auth_token=self._session_token,
            last_health=current.last_health,
            last_sync_at=current.last_sync_at,
            website_version=current.website_version,
            desktop_api_version=current.desktop_api_version,
            last_auth=current.last_auth,
            token_storage="memory_only",
        )
        self.store.save_connection_profiles([profile])
        return profile

    def client(self) -> WebsiteClient:
        profile = self.profile()
        return WebsiteClient(profile.base_url, profile.auth_token)

    def test_connection(self) -> dict[str, Any]:
        profile = self.profile()
        payload = WebsiteClient(profile.base_url, profile.auth_token).desktop_health()
        profile.last_health = "Healthy" if payload.get("ok") else "Needs attention"
        profile.website_version = str(payload.get("version") or "")
        profile.desktop_api_version = str(payload.get("desktop_api") or "")
        self.store.save_connection_profiles([profile])
        return payload

    def auth_check(self) -> dict[str, Any]:
        payload = self.client().desktop_auth_check()
        profile = self.profile()
        profile.last_auth = "Authenticated" if payload.get("authenticated") else "Rejected"
        profile.website_version = str(payload.get("version") or profile.website_version or "")
        profile.desktop_api_version = str(payload.get("desktop_api") or profile.desktop_api_version or "")
        self.store.save_connection_profiles([profile])
        return payload

    def sync_status(self, novel_id: str = "") -> dict[str, Any]:
        payload = self.client().sync_status(novel_id=novel_id)
        profile = self.profile()
        profile.last_sync_at = utc_now()
        profile.last_health = "Healthy" if payload.get("ok") else "Needs attention"
        profile.website_version = str(payload.get("version") or profile.website_version or "")
        profile.desktop_api_version = str(payload.get("desktop_api") or profile.desktop_api_version or "")
        self.store.save_connection_profiles([profile])
        return payload

    def queue_upload(self, pack_path: Path, novel_id: str, content_type: str = "original") -> UploadJob:
        profile = self.profile()
        upload = UploadJob(
            id=new_id("upload"),
            pack_path=str(pack_path),
            novel_id=novel_id,
            content_type=content_type,
            website_url=profile.base_url,
            last_activity="Queued for preview",
        )
        return self.store.upsert_upload(upload)

    def preview_upload(self, upload_id: str) -> UploadJob:
        upload = self.require_upload(upload_id)
        upload.status = "previewing"
        upload.progress_percent = 0
        upload.error = ""
        upload.last_activity = "Preview upload started"
        self.store.upsert_upload(upload)

        def progress(value: int) -> None:
            upload.progress_percent = value
            upload.last_activity = f"Uploading preview {value}%"
            self.store.upsert_upload(upload)

        try:
            payload = self.client().preview_content_pack(
                Path(upload.pack_path),
                novel_id=upload.novel_id,
                content_type=upload.content_type,
                progress=progress,
            )
            upload.preview = payload
            upload.status = "previewed"
            upload.progress_percent = 100
            upload.last_activity = "Preview ready"
            return self.store.upsert_upload(upload)
        except Exception as exc:
            upload.status = "failed"
            upload.error = str(exc)
            upload.last_activity = "Preview failed"
            self.store.upsert_upload(upload)
            raise

    def execute_upload(self, upload_id: str) -> UploadJob:
        upload = self.require_upload(upload_id)
        upload.status = "uploading"
        upload.progress_percent = 0
        upload.error = ""
        upload.last_activity = "Import upload started"
        self.store.upsert_upload(upload)

        def progress(value: int) -> None:
            upload.progress_percent = value
            upload.last_activity = f"Uploading import {value}%"
            self.store.upsert_upload(upload)

        try:
            payload = self.client().execute_content_pack(
                Path(upload.pack_path),
                novel_id=upload.novel_id,
                content_type=upload.content_type,
                progress=progress,
            )
            upload.result = payload
            upload.status = "imported" if payload.get("ok") else "failed"
            upload.progress_percent = 100
            upload.last_activity = "Imported" if payload.get("ok") else "Import failed"
            if not payload.get("ok"):
                upload.error = str(payload.get("errors") or payload.get("detail") or "Import failed")
            return self.store.upsert_upload(upload)
        except Exception as exc:
            upload.status = "failed"
            upload.error = str(exc)
            upload.last_activity = "Import failed"
            self.store.upsert_upload(upload)
            raise

    def retry_upload(self, upload_id: str) -> UploadJob:
        upload = self.require_upload(upload_id)
        if upload.status != "failed":
            return upload
        upload.status = "queued"
        upload.error = ""
        upload.progress_percent = 0
        upload.last_activity = "Retry queued"
        return self.store.upsert_upload(upload)

    def open_imported_novel(self, novel_id: str) -> None:
        webbrowser.open(self.client().novel_url(novel_id))

    def center_snapshot(self) -> dict[str, Any]:
        profile = self.profile()
        uploads = self.store.uploads()
        pending_statuses = {"queued", "previewing", "previewed", "uploading"}
        connected = profile.last_health == "Healthy"
        return {
            "connected_website": profile.base_url,
            "connection_health": profile.last_health,
            "connection_state": "Connected" if connected else "Disconnected",
            "desktop_version": APP_VERSION,
            "website_version": profile.website_version or "Unknown",
            "desktop_api_version": profile.desktop_api_version or "Unknown",
            "version_compatible": version_compatible(APP_VERSION, profile.desktop_api_version),
            "last_auth": profile.last_auth,
            "auth_design": "Manual bearer token is kept in memory only; desktop device authorization is documented as the production token flow.",
            "token_storage": profile.token_storage,
            "last_sync": profile.last_sync_at or "Never",
            "pending_uploads": len([item for item in uploads if item.status in pending_statuses]),
            "failed_uploads": len([item for item in uploads if item.status == "failed"]),
            "queued_uploads": len([item for item in uploads if item.status == "queued"]),
            "uploading": len([item for item in uploads if item.status in {"previewing", "uploading"}]),
            "recent_imports": [item.to_dict() for item in uploads[:10]],
        }

    def require_upload(self, upload_id: str) -> UploadJob:
        upload = self.store.upload(upload_id)
        if upload is None:
            raise ValueError(f"Upload not found: {upload_id}")
        return upload


def version_compatible(desktop_version: str, desktop_api_version: str) -> bool:
    if not desktop_api_version or desktop_api_version == "Unknown":
        return False
    return str(desktop_version).split(".", 1)[0] == str(desktop_api_version).split(".", 1)[0]
