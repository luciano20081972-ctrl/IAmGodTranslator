"""End-to-end controls using a disposable repository and synthetic scripts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile


from verify_release import BROWSER, PROFILES, check_records, outcome


RUNNER = "IAmGodTranslator_Render_Deploy/tools/verify_release.py"
STARTUP = "IAmGodTranslator_Render_Deploy/tools/qa_fastapi_startup_routes.py"


class VerificationControls(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="iagt-verify-control-", dir="/tmp")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.repo = self.directory / "repo"
        self.repo.mkdir()
        self.output = self.directory / "evidence"

        self.git("init", "--quiet", "--template=")
        self.write(RUNNER, Path(__file__).with_name("verify_release.py").read_text(encoding="utf-8"))
        self.write(STARTUP, 'print("synthetic startup passed")\n')
        self.write("IAmGodTranslator_Render_Deploy/static/app.js", '"use strict";\n')
        self.write("GodTranslator_Desktop_Companion/tests/test_foundation.py", """
import unittest

class Fixture(unittest.TestCase):
    def test_pass(self):
        self.assertEqual(1 + 1, 2)
""")
        self.commit()

    def write(self, name: str, contents: str) -> None:
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    def git(self, *args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=self.repo, text=True).strip()

    def commit(self) -> None:
        self.git("add", "-A")
        self.git(
            "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
            "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "Synthetic fixture",
        )
        self.head = self.git("rev-parse", "HEAD")

    def cli(self, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(self.repo / RUNNER), *args],
            cwd=self.repo, env=env, capture_output=True, text=True, timeout=30, check=False,
        )

    def verify(self, expected: int = 0, sha: str | None = None, env: dict | None = None,
               *extra: str) -> dict:
        result = self.cli(
            "run", "--expect-sha", sha or self.head, "--output", str(self.output), *extra, env=env,
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return json.loads((self.output / "manifest.json").read_bytes())

    def assert_invalid(self, reason: str) -> None:
        result = self.cli("check-evidence", str(self.output))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(reason, result.stderr)

    def test_fixture_only_archive_and_successful_round_trip(self) -> None:
        self.write(".env", "FAKE_SECRET=untracked-control-marker")
        env = dict(os.environ, FAKE_SECRET="ambient-control-marker")
        self.write(STARTUP, """
import os
from pathlib import Path
assert "FAKE_SECRET" not in os.environ
assert not Path("../.env").exists()
print("synthetic staged startup passed")
""")
        self.git("add", STARTUP)
        expected_tree = self.git("write-tree")
        manifest = self.verify(0, None, env, "--staged")
        self.assertEqual(manifest["source"]["tree_sha"], expected_tree)
        self.assertEqual(manifest["source"]["head_sha"], self.head)
        self.assertEqual(manifest["status"], "PASS")
        self.assertEqual(manifest["checks"][-1]["status"], "SKIPPED")
        self.assertEqual((self.output / "startup-routes.stdout").read_text(), "synthetic staged startup passed\n")
        archive = self.output.with_suffix(".zip")
        self.assertTrue(archive.is_file())
        result = self.cli("check-evidence", str(archive), "--expect-sha", self.head)
        self.assertEqual(result.returncode, 0, result.stderr)
        with ZipFile(archive) as bundle:
            self.assertEqual(set(bundle.namelist()), {p.name for p in self.output.iterdir()})
            for member in bundle.namelist():
                self.assertNotIn(b"control-marker", bundle.read(member))

    def test_deliberately_failing_test_preserves_raw_evidence(self) -> None:
        self.write(STARTUP, 'import sys\nprint("raw stdout")\nprint("raw stderr", file=sys.stderr)\nsys.exit(73)\n')
        self.commit()
        manifest = self.verify(1)
        self.assertEqual(manifest["status"], "FAIL")
        self.assertEqual(manifest["checks"][0]["exit_code"], 73)
        archive = self.output.with_suffix(".zip")
        with ZipFile(archive) as bundle:
            self.assertEqual(bundle.read("startup-routes.stdout"), b"raw stdout\n")
            self.assertEqual(bundle.read("startup-routes.stderr"), b"raw stderr\n")
        result = self.cli("check-evidence", str(archive), "--expect-sha", self.head)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Recorded result: FAIL", result.stdout)
        gate = self.cli("check-evidence", str(archive), "--expect-profile", "fast", "--require-pass")
        self.assertEqual(gate.returncode, 1)
        self.assertIn("required profile ended FAIL", gate.stderr)

    def test_fast_profile_cannot_satisfy_regression(self) -> None:
        self.verify()
        gate = self.cli("check-evidence", str(self.output), "--expect-profile", "regression", "--require-pass")
        self.assertEqual(gate.returncode, 1)
        self.assertIn("profile mismatch", gate.stderr)

    def test_frontend_build_id_mismatch(self) -> None:
        self.write("IAmGodTranslator_Render_Deploy/config/frontend_build_id", "a" * 64)
        self.commit()
        manifest = self.verify(1, None, None, "--expect-build-id", "b" * 64)
        self.assertEqual(manifest["preflight_errors"], ["frontend build ID mismatch"])

    def test_missing_node_leaves_required_check_unverified(self) -> None:
        manifest = self.verify(2, None, None, "--node", str(self.directory / "missing-node"))
        self.assertEqual(manifest["checks"][1]["status"], "UNVERIFIED")
        gate = self.cli("check-evidence", str(self.output), "--require-pass")
        self.assertEqual(gate.returncode, 1)
        self.assertIn("required profile ended UNVERIFIED", gate.stderr)

    def test_browser_command_failure_propagates_and_preserves_diagnostics(self) -> None:
        check = next(c for c in PROFILES["regression"] if c.id == BROWSER)
        for path in check.files:
            self.write(f"{check.cwd}/{path}", "# synthetic required input")
        self.write(f"{check.cwd}/{check.args[0]}", 'import sys\nprint("browser assertion failed", file=sys.stderr)\nsys.exit(27)\n')
        self.write("modules/playwright/package.json", '{"name":"playwright","version":"1.0.0","main":"index.js"}')
        self.write("modules/playwright/index.js", 'module.exports.chromium = {executablePath: () => "/usr/bin/true"};')
        self.output.mkdir()
        manifest = {"dependencies": {}, "preflight_errors": [], "browser_attachments": []}
        args = argparse.Namespace(python=sys.executable, node=shutil.which("node"), node_modules=self.repo / "modules", chromium=None)
        manifest["checks"] = check_records(args, self.repo, self.directory, self.output, (check,),
                                           manifest["preflight_errors"], manifest)
        self.assertEqual(outcome(manifest), "FAIL")
        self.assertEqual(manifest["checks"][0]["exit_code"], 27)
        self.assertIn("browser assertion failed", (self.output / "browser-smoke.stderr").read_text())

    def test_missing_required_script_rejects_the_run(self) -> None:
        (self.repo / STARTUP).unlink()
        self.commit()
        manifest = self.verify(1)
        self.assertIn("missing required input", manifest["preflight_errors"][0])
        self.assertEqual(manifest["checks"][0]["status"], "FAIL")
        self.assertIsNone(manifest["checks"][1]["command"])

    def test_source_tree_mismatch_rejects_the_run(self) -> None:
        manifest = self.verify(1, None, None, "--expect-tree", "0" * 40)
        self.assertEqual(manifest["preflight_errors"], ["source tree mismatch"])
        self.assertIsNone(manifest["checks"][0]["command"])

    def test_source_identity_mismatch_rejects_the_run(self) -> None:
        manifest = self.verify(1, "0" * 40)
        self.assertEqual(manifest["source"]["head_sha"], self.head)
        self.assertEqual(manifest["preflight_errors"], ["source SHA mismatch"])
        self.assertIsNone(manifest["checks"][0]["command"])
        self.assertEqual(manifest["checks"][0]["status"], "UNVERIFIED")
        result = self.cli("check-evidence", str(self.output), "--expect-sha", "0" * 40)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("evidence source SHA mismatch", result.stderr)

    def test_missing_attachment_is_detected(self) -> None:
        self.verify()
        (self.output / "desktop-foundation.stdout").unlink()
        self.assert_invalid("missing or unexpected evidence attachments")

    def test_altered_attachment_is_detected(self) -> None:
        self.verify()
        path = self.output / "startup-routes.stdout"
        path.write_bytes(path.read_bytes() + b"altered")
        self.assert_invalid("attachment checksum mismatch")

    def test_test_omission_is_detected_even_with_a_recomputed_manifest_digest(self) -> None:
        manifest = self.verify()
        omitted = manifest["selection"].pop(0)
        manifest["checks"].pop(0)
        for suffix in ("stdout", "stderr"):
            name = f"{omitted}.{suffix}"
            del manifest["attachments"][name]
            (self.output / name).unlink()
        data = json.dumps(manifest).encode()
        (self.output / "manifest.json").write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        (self.output / "manifest.sha256").write_text(f"{digest}  manifest.json\n", encoding="ascii")
        self.assert_invalid("test-selection omission")


if __name__ == "__main__":
    unittest.main()
