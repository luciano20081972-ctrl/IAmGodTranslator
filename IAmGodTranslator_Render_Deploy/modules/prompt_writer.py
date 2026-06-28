from __future__ import annotations

from pathlib import Path


def save_prompt(
    chapter_number: int,
    prompt: str,
    output_dir: str | Path = "Prompts",
) -> Path:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    filename = output / f"{chapter_number:04d}.txt"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(prompt)

    return filename
