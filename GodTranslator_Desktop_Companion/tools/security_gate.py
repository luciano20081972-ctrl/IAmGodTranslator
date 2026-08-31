from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SECRET_PATTERNS = {
    "openai_key": re.compile(r"sk-[A-Za-z0-9]{20,}"),
    "firecrawl_key": re.compile(r"fc-[A-Za-z0-9_-]{20,}"),
    "generic_private_key": re.compile(r"BEGIN (?:RSA |OPENSSH |EC |DSA |PRIVATE )?PRIVATE KEY"),
    "database_url": re.compile(r"postgres(?:ql)?://[^\s'\"}]+@[^\s'\"}]+"),
}
SAFE_EXTENSIONS = {".py", ".js", ".md", ".txt", ".toml", ".yaml", ".yml", ".json", ".html", ".css"}
SKIP_DIRS = {".git", ".venv", ".venv-cycle2", "__pycache__", "market-intelligence-lab"}


def tracked_files() -> list[Path]:
    result = subprocess.run(["git", "ls-files"], cwd=ROOT, check=True, capture_output=True, text=True)
    return [ROOT / line.strip() for line in result.stdout.splitlines() if line.strip()]


def is_scannable(path: Path) -> bool:
    if path.suffix.lower() not in SAFE_EXTENSIONS:
        return False
    return not any(part in SKIP_DIRS for part in path.parts)


def is_allowed_fixture_secret(path: Path, category: str, match: str) -> bool:
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    if rel == "GodTranslator_Desktop_Companion/tools/security_gate.py" and category == "database_url":
        return match.startswith("postgresql://postgres@127.0.0.1:") or match.startswith("postgresql://unused")
    if category == "database_url" and match.startswith("postgresql://postgres@127.0.0.1:"):
        return rel.startswith(".github/workflows/") or rel.startswith("IAmGodTranslator_Render_Deploy/tools/")
    if category == "database_url" and match.startswith("postgresql://unused"):
        return rel.startswith("IAmGodTranslator_Render_Deploy/tools/")
    return False


def main() -> int:
    findings: list[tuple[str, str]] = []
    for path in tracked_files():
        if not is_scannable(path):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for name, pattern in SECRET_PATTERNS.items():
            for match in pattern.findall(text):
                value = match if isinstance(match, str) else match[0]
                if is_allowed_fixture_secret(path, name, value):
                    continue
                findings.append((str(path.relative_to(ROOT)), name))
    if findings:
        print({"ok": False, "findings": findings})
        return 1
    print({"ok": True, "scanned": len([p for p in tracked_files() if is_scannable(p)]), "findings": []})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
