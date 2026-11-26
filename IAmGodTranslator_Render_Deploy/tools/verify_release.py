"""Run the approved offline release checks and verify their evidence."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile


WEBSITE = "IAmGodTranslator_Render_Deploy"
DESKTOP = "GodTranslator_Desktop_Companion"
RUNNER = f"{WEBSITE}/tools/verify_release.py"
BROWSER = "browser-smoke"
SCREENSHOTS = ("browser-home-desktop.png", "browser-home-mobile.png")
SHA = re.compile(r"[0-9a-f]{40}")
UNITTEST_SUMMARY = re.compile(rb"^Ran (\d+) tests? in ", re.MULTILINE)


@dataclass(frozen=True)
class Check:
    id: str
    cwd: str
    tool: str
    args: tuple[str, ...]
    files: tuple[str, ...]
    unittest: bool = False


def website_check(name: str, script: str, *, unittest: bool = False) -> Check:
    path = f"tools/{script}.py"
    return Check(name, WEBSITE, "python", (path,), (path,), unittest)


FAST = (
    website_check("startup-routes", "qa_fastapi_startup_routes"),
    Check("javascript-syntax", WEBSITE, "node", ("--check", "static/app.js"), ("static/app.js",)),
    Check(
        "desktop-foundation", DESKTOP, "python", ("-m", "unittest", "discover", "-s", "tests", "-v"),
        ("tests/test_foundation.py",), True,
    ),
)
REGRESSION = FAST + (
    website_check("frontend-build", "frontend_build"),
    website_check("frontend-build-controls", "test_frontend_build", unittest=True),
    website_check("resource-registry", "validate_resource_registry"),
    website_check("translation-scheduler", "qa_v10_3_translation_scheduler"),
    website_check("translation-performance", "qa_v10_4_translation_performance"),
    website_check("translation-selector", "qa_v10_6_translation_selector"),
    website_check("content-import", "qa_v10_5_content_import_editions", unittest=True),
    website_check("backup-manifest", "qa_backup_manifest_hotfix"),
    website_check("desktop-integration", "qa_v10_6_desktop_integration", unittest=True),
    website_check("reader-search", "qa_v11_4_minisearch"),
    Check("service-worker", WEBSITE, "node", ("--test", "tools/qa_service_worker.test.js"),
          ("static/sw.js", "tools/qa_service_worker.test.js")),
    Check("pwa-browser", WEBSITE, "python", ("tools/verify_release_browser.py", "--pwa"),
          ("tools/verify_release_browser.py", "tools/browser_v11_6_pwa_smoke.py",
           "tools/browser_v11_6_reader_cache_smoke.py", "tools/profile_v11_6_seeded.py",
           "tools/qa_v11_rc1_real_app_smoke.py")),
    website_check("reader-performance", "qa_v11_6_cycle4_reader_performance"),
    Check(
        BROWSER, WEBSITE, "python", ("tools/verify_release_browser.py",),
        ("tools/verify_release_browser.py", "tools/qa_v11_rc1_real_app_smoke.py",
         "tools/qa_v11_rc1_browser_smoke.js"),
    ),
)
PROFILES = {"fast": FAST, "regression": REGRESSION}
STATUSES = {"PASS", "FAIL", "SKIPPED", "UNVERIFIED"}
EXIT = {"PASS": 0, "FAIL": 1, "UNVERIFIED": 2}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_identity(root: Path, staged: bool, expected: str) -> dict:
    head = git(root, "rev-parse", "--verify", "HEAD^{commit}")
    return {
        "expected_sha": expected,
        "head_sha": head,
        "tree_sha": git(root, "write-tree") if staged else git(root, "rev-parse", "HEAD^{tree}"),
        "mode": "staged" if staged else "committed",
    }


def export_source(root: Path, source: dict, snapshot: Path) -> None:
    archive = snapshot.parent / "source.tar"
    subprocess.run(
        ["git", "-C", str(root), "archive", "--format=tar", "-o", str(archive), source["tree_sha"]],
        check=True,
    )
    with tarfile.open(archive) as tar:
        tar.extractall(snapshot, filter="data")
    # Catch export attributes or links that would substitute a different launcher.
    runner = snapshot / RUNNER
    if runner.is_symlink() or not runner.is_file() or runner.read_bytes() != Path(__file__).read_bytes():
        raise ValueError("the running verifier differs from the selected Git tree")


def fixture_environment(work: Path, python: str, node: str) -> dict[str, str]:
    work.mkdir()
    return {
        "PATH": os.pathsep.join((str(Path(python).parent), str(Path(node).parent), os.defpath)),
        "HOME": str(work),
        "TMPDIR": str(work),
        "XDG_CONFIG_HOME": str(work / "config"),
        "XDG_CACHE_HOME": str(work / "cache"),
        "XDG_DATA_HOME": str(work / "data"),
        "XDG_STATE_HOME": str(work / "state"),
        "LOCALAPPDATA": str(work),
        "LANG": "C.UTF-8",
        "TZ": "UTC",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "GT_SQLITE_PATH": str(work / "fixture.sqlite"),
        "GT_BACKUP_WORK_DIR": str(work / "backups"),
        "GT_DESKTOP_TEST_WEBSITE": "0",
        "TRANSLATION_AUTOSTART": "false",
    }


def execute(command: list[str], cwd: Path, env: dict[str, str], stdout: Path, stderr: Path) -> dict:
    started = utc_now()
    timer = time.monotonic()
    result = {"exit_code": None, "reason": ""}
    with stdout.open("wb") as out, stderr.open("wb") as err:
        try:
            with subprocess.Popen(
                command, cwd=cwd, env=env, stdout=out, stderr=err, start_new_session=True,
            ) as process:
                try:
                    result["exit_code"] = process.wait(timeout=180)
                except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
                    os.killpg(process.pid, signal.SIGKILL)
                    result["exit_code"] = process.wait()
                    result["reason"] = "interrupted" if isinstance(exc, KeyboardInterrupt) else "timeout"
        except OSError as exc:
            result["reason"] = f"could not launch command ({type(exc).__name__})"
    result.update(started_utc=started, duration_seconds=round(time.monotonic() - timer, 3))
    return result


def logs(check_id: str) -> tuple[str, str]:
    return f"{check_id}.stdout", f"{check_id}.stderr"


def evidence_names(report: dict) -> set[str]:
    return {"report.txt"} | {
        name for check_id in report["selection"] for name in logs(check_id)
    } | set(report["browser_attachments"])


def browser_tools(snapshot: Path, work: Path, args: argparse.Namespace, env: dict) -> tuple[dict, str]:
    if args.node_modules:
        env["NODE_PATH"] = str(Path(args.node_modules).absolute())
    probe = [
        args.node, "-e",
        'console.log(JSON.stringify({playwright: require("playwright/package.json").version, '
        'bundled_chromium: require("playwright").chromium.executablePath()}))',
    ]
    details = {"playwright_probe_command": probe, "playwright_probe_environment": dict(env)}
    try:
        done = subprocess.run(
            probe, cwd=snapshot / WEBSITE, env=env, capture_output=True, text=True, timeout=15,
        )
        details.update(playwright_probe_exit_code=done.returncode, playwright_probe_stderr=done.stderr)
        if done.returncode:
            return details, "Node Playwright unavailable. Supply --node-modules if installed elsewhere."
        found = json.loads(done.stdout)
        details["playwright"] = found["playwright"]
        chromium = args.chromium or found["bundled_chromium"]
        if not os.access(chromium, os.X_OK) and not args.chromium:
            chromium = shutil.which("chromium") or shutil.which("google-chrome") or chromium
        version_command = [os.path.abspath(chromium), "--version"]
        details["chromium_version_command"] = version_command
        version = subprocess.run(
            version_command, cwd=snapshot / WEBSITE, env=env, capture_output=True, text=True, timeout=15,
        )
        details.update(chromium_version_exit_code=version.returncode, chromium_version_stderr=version.stderr)
        if version.returncode:
            return details, "Chromium version probe failed."
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return details, "Could not identify Node Playwright or an executable Chromium."
    details["chromium"] = version.stdout.strip()
    env.update(
        GT_VERIFY_NODE=args.node,
        GT_VERIFY_CHROMIUM=version_command[0],
        GT_VERIFY_SCREENSHOTS=str(work),
    )
    return details, ""


def check_records(args: argparse.Namespace, snapshot: Path, runtime: Path, output: Path,
                  selection: tuple[Check, ...], preflight: list[str], manifest: dict) -> list[dict]:
    missing = {}
    if not preflight:
        missing = {
            check.id: [item for item in check.files if not (snapshot / check.cwd / item).is_file()
                       or (snapshot / check.cwd / item).is_symlink()]
            for check in selection
        }
        preflight.extend(f"{check_id}: missing required input {', '.join(items)}"
                         for check_id, items in missing.items() if items)
    records = []
    for check in selection:
        out, err = (output / name for name in logs(check.id))
        out.touch()
        err.touch()
        record = {
            "id": check.id, "status": "UNVERIFIED", "exit_code": None,
            "started_utc": None, "duration_seconds": None,
            "reason": "", "command": None, "cwd": None, "environment": None,
        }
        records.append(record)
        if preflight:
            record["reason"] = "preflight rejected this run"
            if missing.get(check.id):
                record.update(status="FAIL", reason=f"missing required input: {', '.join(missing[check.id])}")
            continue
        work = runtime / check.id
        env = fixture_environment(work, args.python, args.node)
        command = [args.python if check.tool == "python" else args.node, *check.args]
        cwd = snapshot / check.cwd
        record.update(command=command, cwd=str(cwd), environment=env)
        if check.id in {BROWSER, "pwa-browser"}:
            details, reason = browser_tools(snapshot, work, args, env)
            manifest["dependencies"]["browser"] = details
            if reason:
                record["reason"] = reason
                continue
        record.update(execute(command, cwd, env, out, err))
        if record["reason"] == "interrupted":
            preflight.append("run interrupted")
        if record["exit_code"] is None:
            continue
        record["status"] = "PASS" if record["exit_code"] == 0 and not record["reason"] else "FAIL"
        if check.unittest:
            test_output = err.read_bytes() + b"\n" + out.read_bytes()
            summaries = UNITTEST_SUMMARY.findall(test_output)
            count = int(summaries[0]) if len(summaries) == 1 else 0
            skipped = re.findall(rb"skipped=(\d+)", test_output)
            record.update(tests_run=count, tests_skipped=int(skipped[-1]) if skipped else 0)
            if record["status"] == "PASS" and count <= record["tests_skipped"]:
                record.update(status="FAIL", reason="no unittest cases executed")
        if check.id == BROWSER:
            for name in SCREENSHOTS:
                image = work / name
                if image.is_file() and not image.is_symlink():
                    shutil.copyfile(image, output / name)
                    manifest["browser_attachments"].append(name)
            if record["status"] == "PASS" and set(manifest["browser_attachments"]) != set(SCREENSHOTS):
                record.update(status="FAIL", reason="browser smoke did not produce both screenshots")
    return records


def outcome(manifest: dict) -> str:
    statuses = {check["status"] for check in manifest["checks"]}
    if manifest["preflight_errors"] or "FAIL" in statuses:
        return "FAIL"
    return "UNVERIFIED" if "UNVERIFIED" in statuses else "PASS"


def write_evidence(output: Path, manifest: dict) -> Path:
    lines = [
        f"{manifest['status']} — {manifest['profile']} verification",
        f"HEAD {manifest['source']['head_sha']}",
        f"Git tree {manifest['source']['tree_sha']}",
        *(f"FAIL  preflight  {problem}" for problem in manifest["preflight_errors"]),
    ]
    for check in manifest["checks"]:
        suffix = f"  {check['reason']}" if check["reason"] else ""
        lines.append(f"{check['status']}  {check['id']}{suffix}")
        if check.get("tests_skipped"):
            lines.append(f"SKIPPED  {check['id']}  {check['tests_skipped']} of {check['tests_run']} unittest cases")
    (output / "report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    files = evidence_names(manifest)
    manifest["attachments"] = {name: digest((output / name).read_bytes()) for name in sorted(files)}
    data = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    (output / "manifest.json").write_bytes(data)
    (output / "manifest.sha256").write_text(f"{digest(data)}  manifest.json\n", encoding="ascii")
    archive = output.with_name(output.name + ".zip")
    fd = os.open(archive, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "wb") as target, ZipFile(target, "w", compression=ZIP_DEFLATED) as bundle:
        for name in sorted(files | {"manifest.json", "manifest.sha256"}):
            bundle.write(output / name, name)
    return archive


def run(args: argparse.Namespace) -> int:
    root = Path(git(Path(__file__).parent, "rev-parse", "--show-toplevel"))
    source = source_identity(root, args.staged, args.expect_sha)
    output = args.output.resolve()
    if output.is_relative_to(root):
        raise ValueError("choose an evidence directory outside the checkout")
    if output.with_name(output.name + ".zip").exists():
        raise ValueError("evidence archive already exists")
    output.mkdir(mode=0o700)
    args.python = sys.executable
    args.node = os.path.abspath(args.node)
    selection = PROFILES[args.profile]
    preflight = []
    if source["head_sha"] != source["expected_sha"]:
        preflight.append("source SHA mismatch")
    if args.expect_tree and source["tree_sha"] != args.expect_tree:
        preflight.append("source tree mismatch")
    source["expected_tree"] = args.expect_tree
    packages = sorted(
        {f"{distribution.metadata['Name']}=={distribution.version}"
         for distribution in importlib.metadata.distributions() if distribution.metadata["Name"]},
        key=str.lower,
    )
    manifest = {
        "schema_version": 1,
        "source": source,
        "profile": args.profile,
        "selection": [check.id for check in selection],
        "started_utc": utc_now(),
        "preflight_errors": preflight,
        "dependencies": {
            "python": sys.version,
            "python_executable": args.python,
            "python_distributions": packages,
            "platform": sys.platform,
            "node_executable": args.node,
        },
        "browser_attachments": [],
    }
    with tempfile.TemporaryDirectory(prefix="iagt-verify-", dir="/tmp") as directory:
        runtime = Path(directory)
        snapshot = runtime / "source"
        snapshot.mkdir()
        if not preflight:
            try:
                export_source(root, source, snapshot)
            except (OSError, tarfile.TarError, subprocess.CalledProcessError, ValueError) as exc:
                preflight.append(f"source export failed: {exc}")
        if not preflight:
            work = runtime / "dependencies"
            env = fixture_environment(work, args.python, args.node)
            command = [args.node, "--version"]
            try:
                probe = subprocess.run(command, env=env, check=True, capture_output=True, text=True, timeout=15)
                manifest["dependencies"]["node"] = probe.stdout.strip()
            except (OSError, subprocess.SubprocessError):
                manifest["dependencies"]["node"] = None
            manifest["dependencies"]["node_version_probe"] = {"command": command, "environment": env}
        manifest["checks"] = check_records(args, snapshot, runtime, output, selection, preflight, manifest)
    if args.profile == "fast":
        manifest["checks"].append({"id": BROWSER, "status": "SKIPPED", "reason": "regression profile only"})
    manifest["finished_utc"] = utc_now()
    manifest["status"] = outcome(manifest)
    archive = write_evidence(output, manifest)
    print((output / "report.txt").read_text(encoding="utf-8"), end="")
    print(f"Evidence written to {archive}")
    return EXIT[manifest["status"]]


def validate_evidence(names: list[str], read, expected_sha: str | None) -> dict:
    if len(names) != len(set(names)):
        raise ValueError("duplicate evidence attachment")
    data = read("manifest.json")
    if read("manifest.sha256") != f"{digest(data)}  manifest.json\n".encode():
        raise ValueError("manifest checksum mismatch")
    manifest = json.loads(data)
    if manifest["schema_version"] != 1:
        raise ValueError("unsupported evidence schema")
    profile = manifest["profile"]
    selection = [check.id for check in PROFILES[profile]]
    if manifest["selection"] != selection:
        raise ValueError("test-selection omission or substitution")
    checks = manifest["checks"]
    expected_records = selection + ([BROWSER] if profile == "fast" else [])
    if [check["id"] for check in checks] != expected_records:
        raise ValueError("missing or unexpected test result")
    for check in checks:
        if check["status"] not in STATUSES:
            raise ValueError("unknown check status")
        if check["id"] in selection and check["status"] == "SKIPPED":
            raise ValueError("required check marked skipped")
        if check["status"] == "PASS" and check["exit_code"] != 0:
            raise ValueError("passing check lacks a successful exit")
    source = manifest["source"]
    if any(not SHA.fullmatch(source[field]) for field in ("head_sha", "expected_sha", "tree_sha")):
        raise ValueError("invalid source identity")
    if expected_sha and source["head_sha"] != expected_sha:
        raise ValueError("evidence source SHA mismatch")
    if source["head_sha"] != source["expected_sha"] and not manifest["preflight_errors"]:
        raise ValueError("run failed to detect a source SHA mismatch")
    expected_tree = source.get("expected_tree")
    if expected_tree and (not SHA.fullmatch(expected_tree) or
                          (expected_tree != source["tree_sha"] and "source tree mismatch" not in manifest["preflight_errors"])):
        raise ValueError("invalid expected source tree or unreported tree mismatch")
    screenshots = manifest["browser_attachments"]
    if len(screenshots) != len(set(screenshots)) or set(screenshots) - set(SCREENSHOTS):
        raise ValueError("unexpected browser evidence")
    if profile == "fast" and (checks[-1]["status"] != "SKIPPED" or screenshots):
        raise ValueError("invalid fast-profile browser record")
    if checks[-1]["id"] == BROWSER and checks[-1]["status"] == "PASS" and set(screenshots) != set(SCREENSHOTS):
        raise ValueError("passing browser result is missing screenshots")
    required = evidence_names(manifest)
    if set(manifest["attachments"]) != required or set(names) != required | {"manifest.json", "manifest.sha256"}:
        raise ValueError("missing or unexpected evidence attachments")
    for name in sorted(required):
        if digest(read(name)) != manifest["attachments"][name]:
            raise ValueError(f"attachment checksum mismatch: {name}")
    if manifest["status"] != outcome(manifest):
        raise ValueError("overall status disagrees with check results")
    return manifest


def check_evidence(path: Path, expected: str | None) -> dict:
    if path.is_dir():
        def read(name: str) -> bytes:
            attachment = path / name
            if attachment.is_symlink() or not attachment.is_file():
                raise ValueError(f"missing or unsafe attachment: {name}")
            return attachment.read_bytes()

        return validate_evidence([entry.name for entry in path.iterdir()], read, expected)
    with ZipFile(path) as bundle:
        return validate_evidence(bundle.namelist(), bundle.read, expected)


def full_sha(value: str) -> str:
    if not SHA.fullmatch(value):
        raise argparse.ArgumentTypeError("supply a full lowercase Git commit SHA")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="action", required=True)
    run_parser = subcommands.add_parser("run")
    run_parser.add_argument("--profile", choices=PROFILES, default="fast")
    run_parser.add_argument("--expect-sha", required=True, type=full_sha)
    run_parser.add_argument("--output", required=True, type=Path)
    run_parser.add_argument("--expect-tree", type=full_sha, help="expected content of the committed or staged snapshot")
    run_parser.add_argument("--staged", action="store_true")
    run_parser.add_argument("--node", default=shutil.which("node") or "/usr/bin/node")
    run_parser.add_argument("--node-modules", type=Path)
    run_parser.add_argument("--chromium", type=Path)
    check_parser = subcommands.add_parser("check-evidence")
    check_parser.add_argument("path", type=Path)
    check_parser.add_argument("--expect-sha", type=full_sha)
    check_parser.add_argument("--expect-tree", type=full_sha)
    args = parser.parse_args()
    try:
        if args.action == "run":
            if os.name != "posix":
                raise ValueError("the verifier requires a POSIX host")
            return run(args)
        evidence = check_evidence(args.path, args.expect_sha)
        if args.expect_tree and evidence["source"]["tree_sha"] != args.expect_tree:
            raise ValueError("evidence source tree mismatch")
        print(f"Evidence intact. Recorded result: {evidence['status']}")
        return 0
    except (OSError, ValueError, TypeError, KeyError, BadZipFile, subprocess.SubprocessError) as exc:
        print(f"Verification error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
