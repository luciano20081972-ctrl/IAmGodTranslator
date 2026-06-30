from pathlib import Path

from modules.chapter import parse_chapter


def scan_folder(folder_name):
    """
    Scan every .txt file in a folder and return
    parsed chapter information.
    """

    folder = Path(folder_name)

    if not folder.exists() or not folder.is_dir():
        return []

    chapters = []

    txt_files = sorted(folder.glob("*.txt"))

    for txt in txt_files:

        try:
            chapter = parse_chapter(txt)
            chapters.append(chapter)

        except Exception as e:

            print(f"Failed to scan {txt.name}")
            print(e)

    return chapters


def print_summary(chinese, novelfire):

    print()
    print("=" * 50)
    print("Chapter Scanner")
    print("=" * 50)

    print(f"Chinese chapters   : {len(chinese)}")
    print(f"NovelFire chapters : {len(novelfire)}")

    print("=" * 50)

    if chinese:

        print()
        print("Chinese Preview")

        for chapter in chinese[:5]:

            print(
                f"#{chapter['number']}  "
                f"{chapter['title']}"
            )

    if novelfire:

        print()
        print("NovelFire Preview")

        for chapter in novelfire[:5]:

            print(
                f"#{chapter['number']}  "
                f"{chapter['title']}"
            )
