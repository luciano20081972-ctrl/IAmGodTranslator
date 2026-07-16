from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import RecoveryRequestInfo


SUPPORTED_FORMAT = "godtranslator-recovery-request-v1"


def load_recovery_request(path: Path) -> RecoveryRequestInfo:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return parse_recovery_request(payload, path)


def parse_recovery_request(payload: dict[str, Any], path: Path | None = None) -> RecoveryRequestInfo:
    if payload.get("format") != SUPPORTED_FORMAT:
        raise ValueError("Unsupported Recovery Request format.")
    target_mode = str(payload.get("target_mode") or "").lower()
    if target_mode != "reference":
        raise ValueError("This foundation supports Reference recovery requests only.")
    chapters = sorted({int(chapter) for chapter in payload.get("chapters", [])})
    if not chapters:
        raise ValueError("Recovery Request does not list missing chapters.")
    return RecoveryRequestInfo(
        path=str(path or ""),
        novel_id=str(payload.get("novel_id") or ""),
        novel_title=str(payload.get("novel_title") or payload.get("novel_id") or "Novel"),
        target_mode="reference",
        source_type=str(payload.get("source_type") or "novelfire"),
        source_url=str(payload.get("source_url") or ""),
        chapter_url_template=str(payload.get("chapter_url_template") or ""),
        chapters=chapters,
        created_at=payload.get("created_at") or payload.get("request_created_at"),
    )
