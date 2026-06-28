from pathlib import Path


class FileSystem:

    def __init__(self):

        self.root = Path(__file__).resolve().parent.parent

        # -----------------------------
        # Source folders
        # -----------------------------

        self.source = self.root / "Source"

        self.chinese = self.source / "Chinese"
        self.novelfire = self.source / "NovelFire"

        # -----------------------------
        # Translation folders
        # -----------------------------

        self.translation = self.root / "Translation"

        self.drafts = self.translation / "Drafts"
        self.reviewed = self.translation / "Reviewed"
        self.english = self.translation / "Final"

        # -----------------------------
        # Other folders
        # -----------------------------

        self.prompts = self.root / "Prompts"
        self.logs = self.root / "Logs"
        self.output = self.root / "Output"

        self.create_folders()

    def create_folders(self):

        folders = [
            self.source,
            self.chinese,
            self.novelfire,
            self.translation,
            self.drafts,
            self.reviewed,
            self.english,
            self.prompts,
            self.logs,
            self.output,
        ]

        for folder in folders:
            folder.mkdir(parents=True, exist_ok=True)

    def chapter_file(self, folder: Path, chapter: int):

        files = sorted(folder.glob(f"{chapter:04d}*.txt"))

        if files:
            return files[0]

        return None

    def load_chapter(self, folder: Path, chapter: int):

        file = self.chapter_file(folder, chapter)

        if file is None:
            return None

        with open(file, "r", encoding="utf-8") as f:
            text = f.read()

        return {
            "number": chapter,
            "title": file.stem,
            "text": text,
            "path": file,
        }

    def save_text(self, folder: Path, chapter: int, text: str):

        folder.mkdir(parents=True, exist_ok=True)

        filename = folder / f"{chapter:04d}.txt"

        with open(filename, "w", encoding="utf-8") as f:
            f.write(text)

        return filename

    def prompt_file(self, chapter):
        return self.prompts / f"{chapter:04d}.txt"

    def draft_file(self, chapter):
        return self.drafts / f"{chapter:04d}.txt"

    def reviewed_file(self, chapter):
        return self.reviewed / f"{chapter:04d}.txt"

    def english_file(self, chapter):
        return self.english / f"{chapter:04d}.txt"
