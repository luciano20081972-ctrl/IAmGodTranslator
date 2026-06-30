from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SOURCE = PROJECT_ROOT / "Source"

CHINESE = SOURCE / "Chinese"
NOVELFIRE = SOURCE / "NovelFire"

TRANSLATION = PROJECT_ROOT / "Translation"

DRAFTS = TRANSLATION / "Drafts"
REVIEWED = TRANSLATION / "Reviewed"
FINAL = TRANSLATION / "Final"

PROMPTS = PROJECT_ROOT / "Prompts"

LOGS = PROJECT_ROOT / "Logs"

OUTPUT = PROJECT_ROOT / "Output"

CONFIG = PROJECT_ROOT / "Config"

MEMORY = PROJECT_ROOT / "Memory"


def create_folders():

    folders = [
        SOURCE,
        CHINESE,
        NOVELFIRE,
        TRANSLATION,
        DRAFTS,
        REVIEWED,
        FINAL,
        PROMPTS,
        LOGS,
        OUTPUT,
        CONFIG,
        MEMORY,
    ]

    for folder in folders:
        folder.mkdir(parents=True, exist_ok=True)
