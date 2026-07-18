from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
INDEX = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "styles.css").read_text(encoding="utf-8")


def require(label: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(label)


def main() -> None:
    require("cache strings updated", "app.js?v=10.6.1" in INDEX and "styles.css?v=10.6.1" in INDEX)
    require("theme removed from top-level shell", "personalizeBtn" not in INDEX and ">Theme<" not in INDEX)
    require("profile menu shell exists", 'id="profileMenu"' in INDEX and 'id="profileMenuItems"' in INDEX)

    for label in ("Home", "Library", "Continue Reading"):
        require(f"top nav includes {label}", label in APP_JS)
    require("activity hidden unless relevant", "jobButton.hidden = !canTranslate()" in APP_JS)

    for label in (
        "My Account",
        "Reading History",
        "Bookmarks",
        "Favorites",
        "Collections",
        "Desktop Sync",
        "Notifications",
        "Accessibility",
        "Translator Workspace",
        "Exit Admin Mode",
        "Sign Out",
    ):
        require(f"profile menu includes {label}", label in APP_JS)
    require("admin exit and account signout separate", "profileExitAdmin" in APP_JS and "profileSignOut" in APP_JS)

    for label in (
        "Continue Reading",
        "Recently Read",
        "Favorites",
        "Bookmarks",
        "Reading Statistics",
        "Recently Added",
        "Operations",
    ):
        require(f"home contains {label}", label in APP_JS)
    require("home admin widgets gated", "state.admin ? metric(\"Imports\"" in APP_JS and "state.admin ? metric(\"Backup\"" in APP_JS)
    require("home translator widgets gated", "canTranslate() ? metric(\"Running Jobs\"" in APP_JS)

    for route in (
        "appearance",
        "reader",
        "library",
        "notifications",
        "accessibility",
        "keyboard",
        "account",
        "privacy",
        "desktop",
        "advanced",
    ):
        require(f"settings route {route}", f'"{route}"' in APP_JS and f"#/settings/{route}" in APP_JS)
    for key in (
        "notifyJobs",
        "keyboardShortcuts",
        "saveLocalHistory",
        "desktopSyncPrompts",
        "settingsDepth",
    ):
        require(f"preference {key}", key in APP_JS)

    require("command sections used", "command-section" in APP_JS and "Settings Commands" in APP_JS)
    require("settings commands explicit", "Settings: Reader" in APP_JS and "Settings: Desktop" in APP_JS)
    require("novel matches separate", "Novel: ${novel.title}" in APP_JS and "Settings:" not in APP_JS.split("const novelMatches", 1)[1].split("const chapterMatches", 1)[0])

    require("profile menu css exists", ".profile-menu-items" in CSS and ".avatar-mini" in CSS)
    require("mobile profile menu constrained", "position: fixed" in CSS and "profile-menu-items" in CSS)
    require("mobile nav overflow controlled", "overflow-x: auto" in CSS and ".top-nav" in CSS)
    require("settings mobile grid exists", ".settings-nav { position: static; grid-template-columns: repeat(2" in CSS)

    print({
        "ok": True,
        "navigation": "passed",
        "profile_menu": "passed",
        "home_role_widgets": "passed",
        "settings_sections": "passed",
        "search_grouping": "passed",
        "responsive_static_guards": "passed",
    })


if __name__ == "__main__":
    main()
