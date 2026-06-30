from __future__ import annotations

from pathlib import Path


OUTPUT = Path("English")
OUTPUT.mkdir(exist_ok=True)


def save_translation(
    chapter: int,
    text: str,
    output_dir: str | Path | None = None,
) -> Path:
    output = Path(output_dir) if output_dir is not None else OUTPUT
    output.mkdir(parents=True, exist_ok=True)

    filename = output / f"{chapter:04d}.txt"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(text)

    return filename
