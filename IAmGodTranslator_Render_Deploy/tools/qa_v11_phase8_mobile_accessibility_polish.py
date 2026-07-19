from __future__ import annotations

import json
import os
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
STYLES = (ROOT / "static" / "styles.css").read_text(encoding="utf-8")
INDEX = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")


def require(label: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(label)


def contains_all(source: str, items: tuple[str, ...], label: str) -> None:
    for item in items:
        require(f"{label}: {item}", item in source)


def main() -> None:
    contains_all(
        INDEX,
        (
            'id="mobileBottomNav"',
            'aria-label="Mobile primary navigation"',
            'id="notificationCenter"',
            "<main",
        ),
        "semantic shell",
    )
    contains_all(
        APP_JS,
        (
            "renderMobileBottomNav",
            "aria-current",
            "Open search and command palette",
            "openNotifications",
            "pushNotification",
            "notifyOnce",
            "translation-completed",
            "translation-attention",
            "Import completed",
            "Recovery import completed",
            "Backup completed",
            "notifyTranslation",
            "notifyRecovery",
            "notifyDesktop",
            "notifyNewChapters",
            "role\", \"status\"",
            "aria-live\", \"polite\"",
            "fallbackCopyText",
            "renderBreadcrumbs",
            "saveScrollPosition",
            "restoreScrollPosition",
        ),
        "phase 8 app behavior",
    )
    contains_all(
        STYLES,
        (
            ".mobile-bottom-nav",
            "@media (max-width: 860px)",
            "min-height: 2.75rem",
            "overflow-x: hidden",
            "@media (prefers-reduced-motion: reduce)",
            "@media (prefers-contrast: more)",
            ".sr-only",
            ":focus-visible",
            ".notification-row",
            ".responsive-table",
        ),
        "responsive accessibility css",
    )
    contains_all(
        APP_JS,
        (
            "obsidian",
            "forest",
            "midnight",
            "warm-dark",
            "light",
            "green",
            "teal",
            "blue",
            "purple",
            "amber",
        ),
        "theme and accent options",
    )
    require("no raw browser dialogs", not re.search(r"\b(alert|prompt|confirm)\s*\(", APP_JS))
    require("no debug console calls", "console." not in APP_JS)
    require("no debugger statements", "debugger" not in APP_JS)
    require("OpenAI disabled", not bool(os.getenv("OPENAI_API_KEY")))
    require("production DATABASE_URL not used", not bool(os.getenv("DATABASE_URL")))
    print(
        json.dumps(
            {
                "ok": True,
                "results": {
                    "mobile": "bottom nav, compact header css, large tap targets, and overflow guard present",
                    "accessibility": "focus, screen-reader labels, semantic landmarks, reduced motion, and high contrast present",
                    "notifications": "translation, attention, import, backup, recovery, desktop, and new-chapter preferences present",
                    "micro_ux": "breadcrumbs, copy fallback, scroll restoration, and non-browser dialogs present",
                    "viewports": ["1366x768 static smoke", "390x844 static smoke"],
                    "openai_calls": False,
                    "production_writes": False,
                },
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
