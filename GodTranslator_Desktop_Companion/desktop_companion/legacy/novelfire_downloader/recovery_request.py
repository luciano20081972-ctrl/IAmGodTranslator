from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RecoveryRequest:
    novel_id: str
    novel_title: str
    target_mode: str
    source_url: str
    chapter_url_template: str
    chapters: list[int]


def load_recovery_request(path: Path) -> RecoveryRequest:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("format") != "godtranslator-recovery-request-v1":
        raise ValueError("Unsupported recovery request format.")
    if payload.get("target_mode") != "reference":
        raise ValueError("Only Reference recovery requests are supported.")
    chapters = sorted({int(chapter) for chapter in payload.get("chapters", [])})
    if not chapters:
        raise ValueError("Recovery request does not contain chapters.")
    return RecoveryRequest(
        novel_id=payload.get("novel_id") or "i-am-god",
        novel_title=payload.get("novel_title") or payload.get("novel_id") or "Novel",
        target_mode="reference",
        source_url=payload.get("source_url") or "",
        chapter_url_template=payload.get("chapter_url_template") or "",
        chapters=chapters,
    )
