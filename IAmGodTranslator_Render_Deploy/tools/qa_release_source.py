"""Compile tracked Python source and syntax-check release JavaScript without running it."""
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[2]
node = sys.argv[1]

for directory in ("IAmGodTranslator_Render_Deploy", "GodTranslator_Desktop_Companion"):
    sources = sorted((root / directory).rglob("*.py"))
    if not sources:
        sys.exit(f"No Python source found in {directory}.")
    for source in sources:
        compile(source.read_bytes(), str(source.relative_to(root)), "exec")
    print(f"Compiled {len(sources)} Python files in {directory}.")

website = root / "IAmGodTranslator_Render_Deploy"
for path in ("static/app.js", "static/sw.js", "tools/qa_v11_rc1_browser_smoke.js", "tools/qa_service_worker.test.js"):
    subprocess.run([node, "--check", path], cwd=website, check=True)
    print(f"JavaScript syntax verified for {path}.")
