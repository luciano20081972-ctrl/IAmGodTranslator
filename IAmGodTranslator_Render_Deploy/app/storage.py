from __future__ import annotations

import logging
import mimetypes
import os
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


logger = logging.getLogger(__name__)


class SupabaseStorage:
    def __init__(self) -> None:
        url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
        bucket = os.getenv("SUPABASE_BUCKET") or "novel-data"
        if not url or not key:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required for Supabase storage.")
        self.bucket = bucket
        self.base_url = f"{url}/storage/v1"
        self.headers = {"Authorization": f"Bearer {key}", "apikey": key}

    def object_url(self, path: str) -> str:
        return f"{self.base_url}/object/{self.bucket}/{path.lstrip('/')}"

    def request(self, method: str, url: str, data: bytes | None = None, headers: dict[str, str] | None = None) -> tuple[int, bytes]:
        request = Request(url, data=data, headers={**self.headers, **(headers or {})}, method=method)
        try:
            with urlopen(request, timeout=60) as response:
                return response.status, response.read()
        except HTTPError as exc:
            if exc.code == 404:
                return 404, b""
            raise

    def read_bytes(self, path: str) -> bytes | None:
        status, data = self.request("GET", self.object_url(path))
        if status == 404:
            return None
        return data

    def read_text(self, path: str) -> str | None:
        data = self.read_bytes(path)
        return data.decode("utf-8") if data is not None else None

    def write_bytes(self, path: str, data: bytes, content_type: str | None = None) -> None:
        headers = {
            **self.headers,
            "x-upsert": "true",
            "Content-Type": content_type or mimetypes.guess_type(path)[0] or "application/octet-stream",
        }
        self.request("PUT", self.object_url(path), data=data, headers=headers)

    def write_text(self, path: str, text: str) -> None:
        self.write_bytes(path, text.encode("utf-8"), "text/plain; charset=utf-8")

    def delete(self, path: str) -> None:
        status, _data = self.request(
            "DELETE",
            f"{self.base_url}/object/{self.bucket}",
            data=json.dumps({"prefixes": [path.lstrip("/")]}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        if status not in {200, 404}:
            raise RuntimeError(f"Supabase delete failed with status {status}")

    def list_paths(self, prefix: str) -> list[str]:
        return self._list_paths(prefix.strip("/"))

    def _list_paths(self, prefix: str) -> list[str]:
        prefix = prefix.strip("/")
        paths: list[str] = []
        offset = 0
        while True:
            status, data = self.request(
                "POST",
                f"{self.base_url}/object/list/{self.bucket}",
                data=json.dumps({"prefix": prefix, "limit": 1000, "offset": offset, "sortBy": {"column": "name", "order": "asc"}}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            if status == 404:
                break
            items = json.loads(data.decode("utf-8"))
            if not items:
                break
            for item in items:
                name = item.get("name")
                if not name:
                    continue
                child = f"{prefix}/{name}" if prefix else name
                metadata = item.get("metadata")
                if item.get("id") is None or metadata is None:
                    paths.extend(self._list_paths(child))
                elif metadata.get("mimetype") != "inode/directory":
                    paths.append(f"{prefix}/{name}" if prefix else name)
            if len(items) < 1000:
                break
            offset += len(items)
        return paths

    def upload_tree(self, root: Path, prefix: str) -> dict[str, int]:
        counts = {"copied": 0, "failed": 0}
        if not root.exists():
            return counts
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            try:
                self.write_bytes(f"{prefix.rstrip('/')}/{path.relative_to(root).as_posix()}", path.read_bytes())
                counts["copied"] += 1
            except (OSError, HTTPError, URLError):
                counts["failed"] += 1
                logger.exception("Failed to upload %s to Supabase", path)
        return counts

    def download_tree(self, prefix: str, root: Path) -> dict[str, int]:
        counts = {"copied": 0, "failed": 0}
        for remote_path in self.list_paths(prefix):
            relative = Path(remote_path).relative_to(prefix.strip("/"))
            target = root / relative
            try:
                data = self.read_bytes(remote_path)
                if data is None:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                counts["copied"] += 1
            except (OSError, HTTPError, URLError, ValueError):
                counts["failed"] += 1
                logger.exception("Failed to download %s from Supabase", remote_path)
        return counts
