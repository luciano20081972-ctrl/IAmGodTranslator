import json


def build_index(matches):

    index = {}

    for chapter in matches:

        number = chapter["number"]

        index[str(number)] = {
            "chapter": number,
            "translated": chapter["translated"],
            "chinese": chapter["chinese"]["path"] if chapter["chinese"] else None,
            "novelfire": chapter["english"]["path"] if chapter["english"] else None,
            "title_cn": chapter["chinese"]["title"] if chapter["chinese"] else None,
            "title_en": chapter["english"]["title"] if chapter["english"] else None,
        }

    return index


def save_index(index, filename="chapter_index.json"):

    with open(filename, "w", encoding="utf-8") as f:

        json.dump(
            index,
            f,
            indent=4,
            ensure_ascii=False
        )

    print()
    print("=" * 50)
    print("Chapter Database")
    print("=" * 50)
    print(f"Saved {len(index)} chapters")
    print(f"File : {filename}")
    
