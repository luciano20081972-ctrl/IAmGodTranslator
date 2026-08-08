"""Validate the third-party resource registry and vendored dependency integrity."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = APP_ROOT / "config" / "resource_registry.json"

REQUIRED_FIELDS = {
    "name",
    "category",
    "source",
    "version_or_revision",
    "license",
    "status",
    "usage",
    "runtime_or_dev",
    "vendored_path",
    "checksum",
    "network_required",
    "user_data_shared",
    "fallback",
    "rollback",
    "last_reviewed",
    "notes",
}

VALID_STATUSES = {"ADOPTED", "PROTOTYPE", "BENCHMARK", "REFERENCE", "REJECTED", "DEFERRED"}
VALID_RUNTIMES = {"runtime", "dev", "architecture"}


def _read_for_checksum(path: Path, normalization: str) -> bytes:
    data = path.read_bytes()
    if normalization == "lf":
        return data.replace(b"\r\n", b"\n")
    if normalization in {"", "raw"}:
        return data
    raise ValueError(f"unsupported checksum_normalization {normalization!r}")


def validate_registry(registry_path: Path = REGISTRY_PATH) -> dict:
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    warnings: list[str] = []

    if data.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    resources = data.get("resources")
    if not isinstance(resources, list) or not resources:
        errors.append("resources must be a non-empty list")
        resources = []

    names: set[str] = set()
    adopted = 0
    checked_files = 0

    for index, resource in enumerate(resources):
        prefix = f"resources[{index}]"
        if not isinstance(resource, dict):
            errors.append(f"{prefix} must be an object")
            continue

        missing = sorted(REQUIRED_FIELDS - set(resource))
        if missing:
            errors.append(f"{prefix} missing required fields: {', '.join(missing)}")

        name = str(resource.get("name", "")).strip()
        if not name:
            errors.append(f"{prefix}.name is required")
        elif name in names:
            errors.append(f"duplicate resource name: {name}")
        names.add(name)

        status = resource.get("status")
        if status not in VALID_STATUSES:
            errors.append(f"{name or prefix}.status must be one of {sorted(VALID_STATUSES)}")
        runtime = resource.get("runtime_or_dev")
        if runtime not in VALID_RUNTIMES:
            errors.append(f"{name or prefix}.runtime_or_dev must be one of {sorted(VALID_RUNTIMES)}")

        if not isinstance(resource.get("network_required"), bool):
            errors.append(f"{name or prefix}.network_required must be boolean")
        if not isinstance(resource.get("user_data_shared"), bool):
            errors.append(f"{name or prefix}.user_data_shared must be boolean")

        if status == "ADOPTED":
            adopted += 1
            for field in ("license", "source", "version_or_revision", "fallback", "rollback"):
                if not str(resource.get(field, "")).strip():
                    errors.append(f"{name}.ADOPTED resource must define {field}")

        vendored_path = str(resource.get("vendored_path", "")).strip()
        checksum = str(resource.get("checksum", "")).strip()
        if vendored_path:
            vendored_file = APP_ROOT / vendored_path
            if not vendored_file.exists():
                errors.append(f"{name}.vendored_path missing: {vendored_path}")
            elif checksum:
                try:
                    algorithm, expected = checksum.split(":", 1)
                except ValueError:
                    errors.append(f"{name}.checksum must use algorithm:hex format")
                else:
                    if algorithm != "sha256":
                        errors.append(f"{name}.checksum unsupported algorithm: {algorithm}")
                    else:
                        normalization = str(resource.get("checksum_normalization", "raw")).strip() or "raw"
                        actual = hashlib.sha256(_read_for_checksum(vendored_file, normalization)).hexdigest()
                        if actual.lower() != expected.lower():
                            errors.append(
                                f"{name}.checksum mismatch for {vendored_path}: expected {expected}, actual {actual}"
                            )
                        checked_files += 1
            license_path = str(resource.get("license_path", "")).strip()
            if license_path and not (APP_ROOT / license_path).exists():
                errors.append(f"{name}.license_path missing: {license_path}")
            if not license_path:
                warnings.append(f"{name}.vendored_path has no license_path")
        elif checksum:
            warnings.append(f"{name}.checksum is set but vendored_path is empty")

    return {
        "registry": str(registry_path),
        "resource_count": len(resources),
        "adopted_count": adopted,
        "checked_files": checked_files,
        "errors": errors,
        "warnings": warnings,
        "ok": not errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate resource registry and vendored checksums.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output.")
    args = parser.parse_args()
    result = validate_registry()
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["ok"]:
        warning_text = f" warnings={len(result['warnings'])}" if result["warnings"] else ""
        print(
            f"PASS resource_registry resources={result['resource_count']} "
            f"adopted={result['adopted_count']} checked_files={result['checked_files']}{warning_text}"
        )
    else:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
