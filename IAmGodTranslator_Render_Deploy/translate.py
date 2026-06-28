import json
from pathlib import Path

from modules.api import translate
from modules.chapter import parse_chapter
from modules.context import build_context
from modules.prompt_builder import build_prompt
from modules.prompt_writer import save_prompt
from modules.save_translation import save_translation

ROOT = Path(__file__).resolve().parent

LOGS = ROOT / "Logs"
CHINESE = ROOT / "Chinese"
NOVELFIRE = ROOT / "NovelFire"


def load_queue():

    queue_file = LOGS / "translation_queue.json"

    if not queue_file.exists():
        return []

    with open(queue_file, "r", encoding="utf-8") as f:
        return json.load(f)


def save_queue(queue):

    queue_file = LOGS / "translation_queue.json"

    with open(queue_file, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=4)


def load_chapter(folder, number):

    files = sorted(folder.glob(f"{number:04d}*.txt"))

    if not files:
        return None

    return parse_chapter(files[0])


def translate_chapter(chapter):

    chinese = load_chapter(CHINESE, chapter)

    if chinese is None:
        raise FileNotFoundError(f"Chinese chapter {chapter} not found.")

    novelfire = load_chapter(NOVELFIRE, chapter)

    context = build_context(
        chinese,
        novelfire
    )

    prompt = build_prompt(context)

    save_prompt(chapter, prompt)

    print("Sending request to OpenAI...")

    translation = translate(prompt)

    filename = save_translation(
        chapter,
        translation
    )

    return filename


def main():

    queue = load_queue()

    if not queue:
        print("Translation queue completed.")
        return

    total = len(queue)

    while queue:

        chapter = queue[0]["chapter"]

        print()
        print("=" * 60)
        print(f"Chapter {chapter} ({total - len(queue) + 1}/{total})")
        print("=" * 60)

        try:

            filename = translate_chapter(chapter)

            print(f"Saved translation: {filename}")

            queue.pop(0)
            save_queue(queue)

            if queue:
                print(f"Next chapter: {queue[0]['chapter']}")
            else:
                print("Queue completed.")

        except Exception as e:

            print()
            print("Translation failed.")
            print(e)
            break


if __name__ == "__main__":
    main()
