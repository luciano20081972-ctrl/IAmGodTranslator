"""Verify or refresh the checked-in frontend build using only local files."""
import argparse
import base64
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def sri(data):
    return "sha256-" + base64.b64encode(hashlib.sha256(data).digest()).decode("ascii")


def block(text, start, end, content):
    if text.count(start) != 1 or text.count(end) != 1 or text.index(start) >= text.index(end):
        raise ValueError(f"missing or ambiguous generated block: {start}")
    before, rest = text.split(start)
    _, after = rest.split(end)
    return before + start + "\n" + content + "\n" + end + after


class ShellLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        fields = dict(attrs)
        if tag == "script" and "src" in fields:
            self.urls.append(fields["src"])
        if tag == "link" and fields.get("rel") in ("stylesheet", "manifest", "icon"):
            self.urls.append(fields.get("href"))


def build(root, write=False):
    html_file = root / "templates/index.html"
    worker_file = root / "static/sw.js"
    identity_file = root / "config/frontend_build_id"
    html = html_file.read_text(encoding="utf-8")
    worker = worker_file.read_text(encoding="utf-8")
    js = (root / "static/app.js").read_bytes()
    version = re.search(rb'^const APP_VERSION = "(\d+\.\d+\.\d+)";$', js, re.M)
    if not version:
        raise ValueError("missing frontend release version")
    release = version[1].decode()
    if f'VERSION = "{release}"' not in (root / "app/main.py").read_text().splitlines():
        raise ValueError("backend and browser release versions disagree")

    # Map exact URLs to the bytes and MIME types accepted by the worker.
    assets = {}

    def asset(url, content, *types):
        assets[url] = (types, sri(content))
        return url

    css = (root / "static/styles.css").read_bytes()
    css_url = asset(f"/static/styles.css?v={release}-{sha(css)}", css, "text/css")
    js_types = ("text/javascript", "application/javascript")
    registry = json.loads((root / "config/resource_registry.json").read_bytes())["resources"]
    scripts = []
    provenance = {}
    for name in ("@supabase/supabase-js", "MiniSearch"):
        records = [item for item in registry if item["name"] == name]
        if len(records) != 1:
            raise ValueError(f"expected one registry entry for {name}")
        record = records[0]
        version = record["version_or_revision"]
        if not re.fullmatch(r"\d+\.\d+\.\d+", version):
            raise ValueError(f"expected exact version for {name}")
        local = record["vendored_path"]
        if name == "MiniSearch":
            expected = f"static/vendor/minisearch/minisearch-{version}.min.js"
        else:
            expected = f"static/vendor/supabase/supabase-{version}.js"
            license_data = (root / "static/vendor/supabase/LICENSE").read_bytes()
            if (record["license"] != "MIT" or record["license_path"] != "static/vendor/supabase/LICENSE"
                    or record["license_checksum"] != "sha256:" + sha(license_data)
                    or record["tarball"] != f"https://registry.npmjs.org/{name}/-/supabase-js-{version}.tgz"
                    or record["archive_member"] != "package/dist/umd/supabase.js"
                    or not re.fullmatch(r"sha512-[A-Za-z0-9+/]{86}==", record["tarball_integrity"])):
                raise ValueError("invalid Supabase provenance or license")
        if local != expected:
            raise ValueError(f"unexpected vendored path for {name}")
        data = (root / local).read_bytes()
        if record.get("checksum") != "sha256:" + sha(data):
            raise ValueError(f"{name} checksum mismatch")
        if name == "@supabase/supabase-js":
            provenance = {k: record[k] for k in ("source", "version_or_revision", "tarball", "tarball_integrity",
                                                  "archive_member", "license_checksum", "checksum")}
        url = "/" + local
        if name == "MiniSearch":
            url += "?v=" + version
        scripts.append(asset(url, data, *js_types))
    scripts.append(asset(f"/static/app.js?v={release}-{sha(js)}", js, *js_types))
    new_html = block(html, "<!-- build:styles -->", "  <!-- end:styles -->",
                     f'  <link rel="stylesheet" href="{css_url}" integrity="{assets[css_url][1]}">')
    tags = [f'  <script src="{url}" integrity="{assets[url][1]}"></script>' for url in scripts]
    new_html = block(new_html, "<!-- build:scripts -->", "  <!-- end:scripts -->", "\n".join(tags))
    asset("/manifest.webmanifest", (root / "config/manifest.webmanifest").read_bytes(), "application/json", "application/manifest+json")
    icon = "/static/icons/dark-hour-icon.svg"
    asset(icon, (root / icon[1:]).read_bytes(), "image/svg+xml")
    links = ShellLinks()
    links.feed(new_html)
    if sorted(links.urls) != sorted(assets):
        raise ValueError("HTML references differ from the approved asset inventory")
    asset("/", new_html.encode(), "text/html")
    inventory = ",\n".join("  " + json.dumps([url, value]) for url, value in assets.items())
    marker = "// Generated shell inventory."
    end = "// End shell inventory."
    normalized = block(worker, marker, end, f"const APP_SHELL = new Map([\n{inventory}\n]);")
    # Hash the worker logic and asset inventory before inserting the derived cache name.
    identity = sha(normalized.encode() + b"\0" + json.dumps(provenance, sort_keys=True).encode())
    cache = f'iagt-app-shell-{release}-{identity}'
    new_worker = normalized.replace(marker, marker + f'\nconst GT_CACHE_VERSION = "{cache}";', 1)
    expected = [(html_file, new_html), (worker_file, new_worker), (identity_file, identity + "\n")]
    for path, content in expected:
        if write:
            path.write_bytes(content.encode())
        elif not path.is_file() or path.read_bytes() != content.encode():
            raise ValueError(f"stale or missing {path.relative_to(root)}")
    return {"release": release, "frontend_build_id": identity, "worker_sha256": sha(new_worker.encode()),
            "cache": cache, "asset_integrity": {url: entry[1] for url, entry in assets.items()}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="refresh generated references after reviewing input changes")
    args = parser.parse_args()
    try:
        print(json.dumps(build(ROOT, args.write), indent=2))
    except (OSError, KeyError, ValueError) as exc:
        sys.exit(f"Frontend build verification failed: {exc}")
