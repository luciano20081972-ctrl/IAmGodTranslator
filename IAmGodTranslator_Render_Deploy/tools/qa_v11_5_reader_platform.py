"""Focused QA for v11.5 Reader platform architecture and resource intelligence."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parent

DELIVERABLES = [
    "V11_5_CURRENT_READER_ARCHITECTURE.md",
    "V11_5_READER_CAPABILITY_MATRIX.md",
    "V11_5_BUILD_VS_BORROW.md",
    "V11_5_TARGET_READER_ARCHITECTURE.md",
    "V11_5_READER_FEATURE_DISCOVERY.md",
    "V11_5_TRANSLATION_READER_DESIGN.md",
    "V11_5_RESOURCE_INTELLIGENCE_REPORT.md",
    "V12_PRODUCT_COMPLETION_ROADMAP.md",
    "THIRD_PARTY_ENGINEERING_POLICY.md",
    "config/resource_registry.json",
]

REQUIRED_DOC_TERMS = [
    "Readium",
    "Foliate",
    "Komga",
    "Kavita",
    "BookLore",
    "Calibre-Web",
    "epub.js",
    "EPUBCheck",
    "OPDS",
    "Web Annotation",
    "DOMPurify",
    "axe-core",
    "Workbox",
]


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run_command(args: list[str]) -> dict:
    proc = subprocess.run(args, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    return {
        "args": args,
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def main() -> int:
    failures: list[str] = []
    warnings: list[str] = []

    missing = [name for name in DELIVERABLES if not (APP_ROOT / name).exists()]
    if missing:
        failures.append(f"missing deliverables: {missing}")

    adr_dir = APP_ROOT / "docs" / "adr"
    adr_files = sorted(adr_dir.glob("*.md")) if adr_dir.exists() else []
    if len(adr_files) < 6:
        failures.append("expected at least 6 ADR files")

    combined_docs = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in [APP_ROOT / name for name in DELIVERABLES if (APP_ROOT / name).exists()]
    )
    for term in REQUIRED_DOC_TERMS:
        if term not in combined_docs:
            failures.append(f"required research term missing from docs: {term}")

    app_js = (APP_ROOT / "static" / "app.js").read_text(encoding="utf-8", errors="replace")
    main_py = (APP_ROOT / "app" / "main.py").read_text(encoding="utf-8", errors="replace")
    if "escapeHtml(clean)" not in app_js:
        failures.append("Reader text rendering no longer proves escaped paragraph text")
    if "compare_chapter" not in main_py or "can_view_reference" not in main_py:
        failures.append("Reference permission boundary evidence missing in app/main.py")
    if "gt-reader-scroll:" not in app_js or "gt-chapter-state:" not in app_js:
        failures.append("Reader progress local-state evidence missing in app.js")

    registry_module = load_module(APP_ROOT / "tools" / "validate_resource_registry.py", "validate_resource_registry")
    registry_result = registry_module.validate_registry()
    if not registry_result["ok"]:
        failures.extend(registry_result["errors"])
    if registry_result["warnings"]:
        warnings.extend(registry_result["warnings"])

    lab_module = load_module(APP_ROOT / "tools" / "reader_lab" / "reader_lab_benchmark.py", "reader_lab_benchmark")
    lab_result = lab_module.run_benchmark()
    if lab_result["fixtures"]["private_content_used"]:
        failures.append("reader lab used private content")
    if lab_result["renderers"]["current_escaped_paragraphs"]["paragraphs"] < 200:
        failures.append("reader lab standard fixture is too small")
    if not lab_result["locator_restore"]["restored_text_matches"]:
        failures.append("reader lab locator restore did not match source text")

    registry = json.loads((APP_ROOT / "config" / "resource_registry.json").read_text(encoding="utf-8"))
    adopted = [resource for resource in registry["resources"] if resource["status"] == "ADOPTED"]
    if [resource["name"] for resource in adopted] != ["MiniSearch"]:
        failures.append("v11.5 must not mark new runtime projects as ADOPTED")

    git_names = run_command(["git", "diff", "--name-only"])
    changed_names = set(git_names["stdout"].splitlines())
    forbidden_suffixes = (".zip", ".sqlite", ".sqlite3", ".db", ".log", ".env")
    forbidden_dirs = ("node_modules/", ".venv/", "venv/", "__pycache__/", "qa_screenshots")
    bad_changed = [
        name
        for name in changed_names
        if name.endswith(forbidden_suffixes) or any(part in name.replace("\\", "/") for part in forbidden_dirs)
    ]
    if bad_changed:
        failures.append(f"forbidden artifacts changed: {bad_changed}")

    result = {
        "ok": not failures,
        "failures": failures,
        "warnings": warnings,
        "deliverables": DELIVERABLES,
        "adr_count": len(adr_files),
        "registry": registry_result,
        "reader_lab": lab_result,
    }
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
