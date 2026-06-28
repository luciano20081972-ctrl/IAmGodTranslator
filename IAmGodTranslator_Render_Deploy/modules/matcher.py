def build_index(chapters):
    """
    Converts a chapter list into:
        {chapter_number: chapter_info}
    """

    index = {}

    for chapter in chapters:
        number = chapter["number"]

        if number is None:
            continue

        index[number] = chapter

    return index


def match_chapters(chinese, novelfire):
    """
    Returns a list of matched chapters.
    """

    chinese_index = build_index(chinese)
    english_index = build_index(novelfire)

    results = []

    all_numbers = sorted(chinese_index.keys())

    for number in all_numbers:

        results.append({
            "number": number,
            "chinese": chinese_index.get(number),
            "english": english_index.get(number),
            "translated": number in english_index
        })

    return results


def print_matches(matches):

    print()
    print("=" * 50)
    print("Chapter Matching")
    print("=" * 50)

    translated = 0

    for item in matches:

        if item["translated"]:
            translated += 1
            status = "✓"
        else:
            status = "Missing"

        print(f"Chapter {item['number']:>4} : {status}")

    print("=" * 50)
    print(f"Matched Chapters : {translated}")
    print(f"Need Translation : {len(matches)-translated}")
    
