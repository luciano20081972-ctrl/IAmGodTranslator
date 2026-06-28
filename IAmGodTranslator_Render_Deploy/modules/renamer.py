from pathlib import Path
import shutil


def safe_name(name: str) -> str:
    """
    Remove characters that are illegal in Windows filenames.
    """

    bad = '<>:"/\\|?*'

    for c in bad:
        name = name.replace(c, "")

    return name.strip()


def rename_chapters(chapters, dry_run=True):
    """
    Rename chapters into:

        0001 - Chapter Title.txt

    If dry_run=True nothing is actually renamed.
    """

    renamed = 0
    skipped = 0

    print()
    print("=" * 50)
    print("Smart Renamer")
    print("=" * 50)

    for chapter in chapters:

        number = chapter["number"]

        if number is None:
            skipped += 1
            continue

        old_path = Path(chapter["path"])

        title = safe_name(chapter["title"])

        new_name = f"{number:04d} - {title}.txt"

        new_path = old_path.parent / new_name

        if old_path.name == new_name:
            skipped += 1
            continue

        print(f"{old_path.name}")
        print(f"  -> {new_name}")

        if not dry_run:

            if not new_path.exists():
                shutil.move(str(old_path), str(new_path))
                renamed += 1

    print()
    print(f"Would rename : {renamed}")
    print(f"Skipped      : {skipped}")
