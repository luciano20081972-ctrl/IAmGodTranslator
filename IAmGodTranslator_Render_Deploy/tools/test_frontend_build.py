"""Exercise the public build verification command on isolated, mutated assets."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from frontend_build import ROOT


class BuildIdentityControls(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name in ("config", "templates", "static"):
            shutil.copytree(ROOT / name, self.root / name)
        for name in ("app/main.py", "tools/frontend_build.py"):
            path = self.root / name
            path.parent.mkdir()
            shutil.copyfile(ROOT / name, path)

    def verify(self, error=None, *args):
        result = subprocess.run([sys.executable, self.root / "tools/frontend_build.py", *args],
                                capture_output=True, text=True)
        if error:
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(error, result.stderr)
        else:
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)

    def change(self, name, before, after):
        path = self.root / name
        text = path.read_text()
        self.assertIn(before, text)
        path.write_text(text.replace(before, after, 1))

    def test_reproducible(self):
        before = self.verify()
        self.assertEqual(before, self.verify(None, "--write"))
        self.assertEqual(before, self.verify())

    def test_javascript_version(self):
        self.change("templates/index.html", "app.js?v=", "app.js?v=stale-")
        self.verify("templates/index.html")

    def test_css_version(self):
        self.change("templates/index.html", "styles.css?v=", "styles.css?v=stale-")
        self.verify("templates/index.html")

    def test_cache_version(self):
        self.change("static/sw.js", "iagt-app-shell-11.", "iagt-app-shell-10.")
        self.verify("static/sw.js")

    def test_modified_asset_requires_new_cache(self):
        before = self.verify()
        with (self.root / "static/app.js").open("a") as script:
            script.write("\n// fixture change\n")
        self.verify("templates/index.html")
        after = self.verify(None, "--write")
        self.assertNotEqual(before["cache"], after["cache"])

    def test_worker_logic_requires_new_cache(self):
        with (self.root / "static/sw.js").open("a") as script:
            script.write("\n// fixture worker revision\n")
        self.verify("static/sw.js")

    def test_missing_asset(self):
        (self.root / "static/icons/dark-hour-icon.svg").unlink()
        self.verify("dark-hour-icon.svg")

    def test_dependency_metadata(self):
        path = self.root / "config/resource_registry.json"
        registry = json.loads(path.read_bytes())
        sdk = next(r for r in registry["resources"] if r["name"] == "@supabase/supabase-js")
        for value in ("sha256:" + "0" * 64, None):
            with self.subTest(value=value):
                if value:
                    sdk["checksum"] = value
                else:
                    del sdk["checksum"]
                path.write_text(json.dumps(registry))
                self.verify("checksum mismatch")

    def test_missing_browser_integrity(self):
        self.change("templates/index.html", 'integrity="sha256-', 'data-ignored="sha256-')
        self.verify("templates/index.html")


if __name__ == "__main__":
    unittest.main(verbosity=2)
