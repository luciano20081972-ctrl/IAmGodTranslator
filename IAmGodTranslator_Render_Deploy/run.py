import json
import sys
from pathlib import Path

from modules.translator import process_chapter

PROJECT_ROOT = Path(__file__).resolve().parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.scanner import scan_folder, print_summary
from modules.matcher import match_chapters, print_matches
from modules.renamer import rename_chapters
from modules.indexer import build_index, save_index
from modules.queue import build_queue, save_queue

print("=" * 50)
print(" I Am God Translation Project")
print("=" * 50)

config_path = PROJECT_ROOT / "config.json"

if not config_path.exists():
    raise FileNotFoundError("config.json not found.")

with open(config_path, "r", encoding="utf-8") as f:
    config = json.load(f)

print()
print(f"Book Title : {config['book_title']}")
print(f"Author     : {config['author']}")
print(f"Language   : {config['source_language']} -> {config['target_language']}")
print()

folders = config["folders"]

for folder in folders.values():
    (PROJECT_ROOT / folder).mkdir(exist_ok=True)

print("Folders verified.\n")

print("Scanning folders...\n")

chinese = scan_folder(PROJECT_ROOT / folders["chinese"])
novelfire = scan_folder(PROJECT_ROOT / folders["novelfire"])

print_summary(chinese, novelfire)

matches = match_chapters(chinese, novelfire)

print_matches(matches)

print("\nPreviewing Chinese file renaming...")
rename_chapters(chinese, dry_run=True)

print("\nPreviewing NovelFire file renaming...")
rename_chapters(novelfire, dry_run=True)

# ------------------------------
# Chapter Database
# ------------------------------

logs_folder = PROJECT_ROOT / "Logs"
logs_folder.mkdir(exist_ok=True)

index = build_index(matches)

index_file = logs_folder / "chapter_index.json"
save_index(index, index_file)

# ------------------------------
# Translation Queue
# ------------------------------

queue = build_queue(index)

queue_file = logs_folder / "translation_queue.json"
save_queue(queue, queue_file)


# ------------------------------
# Prompt Generation
# ------------------------------

print()
print("=" * 50)
print("Generating Translation Prompts")
print("=" * 50)

english_lookup = {}

for chapter in novelfire:
    if chapter["number"] is not None:
        english_lookup[chapter["number"]] = chapter

generated = 0

for chapter in chinese:

    reference = english_lookup.get(chapter["number"])

    process_chapter(
        chapter,
        reference
    )

    generated += 1

print()
print(f"Generated {generated} prompt(s).")

print()
print("Pipeline finished successfully.")