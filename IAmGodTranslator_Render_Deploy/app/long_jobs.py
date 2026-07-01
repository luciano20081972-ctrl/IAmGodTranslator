from __future__ import annotations

import json
import logging
import threading
import uuid
from pathlib import Path
from typing import Any, Callable

from app.services import utc_now


logger = logging.getLogger(__name__)


class LongJobManager:
    def __init__(self, data_dir: Path):
        self.root = data_dir / "long_jobs"
        self.root.mkdir(parents=True, exist_ok=True)
        self._threads: dict[str, threading.Thread] = {}

    def path(self, kind: str, job_id: str) -> Path:
        return self.root / kind / f"{job_id}.json"

    def write(self, kind: str, job_id: str, state: dict[str, Any]) -> dict[str, Any]:
        state["updated_at"] = utc_now()
        path = self.path(kind, job_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        return state

    def read(self, kind: str, job_id: str) -> dict[str, Any] | None:
        path = self.path(kind, job_id)
        if not path.exists():
            return None
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if state.get("status") in {"queued", "running"} and job_id not in self._threads:
            state["status"] = "failed"
            state["stage"] = "interrupted"
            state.setdefault("warnings", []).append("The server restarted while this job was running. Start a new job if needed.")
            self.write(kind, job_id, state)
        return state

    def active(self, kind: str, **match: Any) -> dict[str, Any] | None:
        folder = self.root / kind
        if not folder.exists():
            return None
        for path in sorted(folder.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
            state = self.read(kind, path.stem)
            if not state or state.get("status") not in {"queued", "running"}:
                continue
            if all(state.get(key) == value for key, value in match.items()):
                return state
        return None

    def start(self, kind: str, title: str, worker: Callable[[Callable[..., dict[str, Any]], dict[str, Any]], dict[str, Any]], metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        job_id = uuid.uuid4().hex
        state: dict[str, Any] = {
            "ok": True,
            "job_id": job_id,
            "kind": kind,
            "title": title,
            "status": "queued",
            "progress": 0,
            "stage": "queued",
            "checked": 0,
            "total": 0,
            "copied": 0,
            "skipped": 0,
            "failed": 0,
            "warnings": [],
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }
        if metadata:
            state.update(metadata)
        self.write(kind, job_id, state)

        def update(**changes: Any) -> dict[str, Any]:
            current = self.read(kind, job_id) or state
            current.update(changes)
            return self.write(kind, job_id, current)

        def run() -> None:
            try:
                update(status="running", stage="starting")
                result = worker(update, state)
                current = self.read(kind, job_id) or state
                current.update({"status": "complete", "progress": 100, "stage": "complete", "result": result})
                self.write(kind, job_id, current)
            except Exception as exc:  # pragma: no cover - defensive for background thread safety.
                logger.warning("Long job %s/%s failed: %s", kind, job_id, exc.__class__.__name__)
                current = self.read(kind, job_id) or state
                current.update({"status": "failed", "stage": "failed", "error": str(exc) or exc.__class__.__name__})
                self.write(kind, job_id, current)
            finally:
                self._threads.pop(job_id, None)

        thread = threading.Thread(target=run, name=f"{kind}-{job_id[:8]}", daemon=True)
        self._threads[job_id] = thread
        thread.start()
        return state
