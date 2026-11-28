from __future__ import annotations

import hashlib
from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any
import urllib.error
import urllib.request

from .models import default_website_url, normalize_website_base_url
from .packs import MAX_PACK_BYTES


class NoWebsiteRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass
class WebsiteClient:
    base_url: str = ""
    auth_token: str = ""
    timeout: int = 20

    def __post_init__(self) -> None:
        self.base_url = normalize_website_base_url(self.base_url or os.getenv("GT_WEBSITE_URL") or default_website_url())

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers

    def test_connection(self) -> dict[str, Any]:
        return self._get_json("/api/health")

    def desktop_health(self) -> dict[str, Any]:
        return self._get_json("/api/desktop/health")

    def admin_session(self) -> dict[str, Any]:
        return self._get_json("/api/admin/session")

    def desktop_auth_check(self) -> dict[str, Any]:
        return self._get_json("/api/desktop/auth/check")

    def sync_status(self, novel_id: str = "") -> dict[str, Any]:
        suffix = f"?novel_id={quote(novel_id)}" if novel_id else ""
        return self._get_json(f"/api/desktop/sync/status{suffix}")

    def import_history(self, novel_id: str = "", limit: int = 20) -> dict[str, Any]:
        params = f"?limit={int(limit)}"
        if novel_id:
            params += f"&novel_id={quote(novel_id)}"
        return self._get_json(f"/api/desktop/import-history{params}")

    def preview_content_pack(
        self,
        pack_path: Path,
        novel_id: str = "",
        content_type: str = "",
        novel_title: str = "",
        progress: Any | None = None,
        expected_sha256: str = "",
    ) -> dict[str, Any]:
        return self._upload_pack(
            "/api/desktop/import/preview-pack",
            pack_path,
            novel_id=novel_id,
            content_type=content_type,
            novel_title=novel_title,
            progress=progress,
            expected_sha256=expected_sha256,
        )

    def execute_content_pack(
        self,
        pack_path: Path,
        novel_id: str = "",
        content_type: str = "",
        novel_title: str = "",
        overwrite_existing: bool = False,
        dry_run: bool = False,
        progress: Any | None = None,
        expected_sha256: str = "",
    ) -> dict[str, Any]:
        return self._upload_pack(
            "/api/desktop/import/execute-pack",
            pack_path,
            novel_id=novel_id,
            content_type=content_type,
            novel_title=novel_title,
            overwrite_existing=overwrite_existing,
            dry_run=dry_run,
            progress=progress,
            expected_sha256=expected_sha256,
        )

    def preview_recovery_pack(self, novel_id: str, pack_path: Path) -> dict[str, Any]:
        try:
            import requests
        except Exception as exc:
            raise RuntimeError("Pack upload requires requests. Run SETUP_ONCE.bat first.") from exc
        url = f"{self.base_url.rstrip('/')}/api/novels/{novel_id}/recovery/preview"
        with pack_path.open("rb") as handle:
            response = requests.post(url, headers=self._headers(), files={"files": (pack_path.name, handle, "application/zip")}, timeout=max(self.timeout, 60))
        response.raise_for_status()
        return response.json()

    def apply_recovery_import(self, novel_id: str, job_id: str) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/api/novels/{novel_id}/recovery/import/{job_id}",
            headers=self._headers(),
            method="POST",
        )
        with urllib.request.build_opener(NoWebsiteRedirect()).open(request, timeout=self.timeout) as response:
            return json.loads(response.read(MAX_PACK_BYTES).decode("utf-8"))

    def novel_url(self, novel_id: str) -> str:
        return f"{self.base_url.rstrip('/')}/#/novel/{quote(novel_id)}"

    def _upload_pack(
        self,
        path: str,
        pack_path: Path,
        **params: Any,
    ) -> dict[str, Any]:
        try:
            import requests
        except Exception as exc:
            raise RuntimeError("Pack upload requires requests. Run SETUP_ONCE.bat first.") from exc
        pack_path = Path(pack_path)
        query = urlencode({key: value for key, value in params.items() if key not in {"progress", "expected_sha256"} and value not in {None, ""}})
        url = f"{self.base_url.rstrip('/')}{path}"
        if query:
            url = f"{url}?{query}"
        progress = params.get("progress")
        with pack_path.open("rb") as handle:
            reader = ProgressReader(handle, pack_path.stat().st_size, progress, params.get("expected_sha256", ""))
            response = requests.post(
                url,
                headers=self._headers(),
                files={"files": (pack_path.name, reader, "application/zip")},
                timeout=max(self.timeout, 120),
                allow_redirects=False,
            )
        if response.status_code in {401, 403}:
            raise RuntimeError("Website authorization failed. Verify the administrator token and retry the preview.")
        if not response.ok or 300 <= response.status_code < 400:
            raise RuntimeError(f"Website pack request failed with HTTP {response.status_code}.")
        if progress:
            progress(100)
        return response.json()

    def _get_json(self, path: str) -> dict[str, Any]:
        request = urllib.request.Request(f"{self.base_url.rstrip('/')}{path}", headers=self._headers(), method="GET")
        try:
            with urllib.request.build_opener(NoWebsiteRedirect()).open(request, timeout=self.timeout) as response:
                return json.loads(response.read(MAX_PACK_BYTES).decode("utf-8"))
        except urllib.error.HTTPError as exc:
            exc.close()
            raise RuntimeError(f"Website request failed: HTTP {exc.code}") from None


class ProgressReader:
    def __init__(self, handle: Any, total: int, callback: Any | None = None, expected_sha256: str = "") -> None:
        self.handle = handle
        self.total = max(1, total)
        self.callback = callback
        self.sent = 0
        self.expected_sha256 = expected_sha256

    def read(self, size: int = -1) -> bytes:
        chunk = self.handle.read(MAX_PACK_BYTES + 1 if size == -1 else size)
        if self.sent + len(chunk) > MAX_PACK_BYTES:
            raise ValueError("Pack exceeds the 64 MiB transfer limit.")
        # requests reads each multipart file in one call before sending.
        if self.expected_sha256 and (size != -1 or hashlib.sha256(chunk).hexdigest() != self.expected_sha256):
            raise ValueError("Pack changed before transfer. Preview the current pack again.")
        self.sent += len(chunk)
        if self.callback:
            self.callback(min(99, round(self.sent / self.total * 100)))
        return chunk

    def __len__(self) -> int:
        return self.total


def quote(value: str) -> str:
    from urllib.parse import quote as url_quote

    return url_quote(str(value), safe="")


def urlencode(values: dict[str, Any]) -> str:
    from urllib.parse import urlencode as url_encode

    return url_encode(values)
