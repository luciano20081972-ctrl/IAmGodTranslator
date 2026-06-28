from pathlib import Path
import re


def contains_chinese(text):

    return bool(re.search(r'[\u4e00-\u9fff]', text))


def review_translation(text):

    warnings = []

    if contains_chinese(text):
        warnings.append("Chinese characters still detected.")

    if len(text.strip()) < 500:
        warnings.append("Translation looks unusually short.")

    if "Chapter" not in text:
        warnings.append("Missing chapter header.")

    return warnings


def save_reviewed(chapter_number, text):

    folder = Path("Reviewed")
    folder.mkdir(exist_ok=True)

    filename = folder / f"{chapter_number:04d}.txt"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(text)

    return filename
