"""Local runtime profiling for the v11.6 self-hosted/PWA foundation.

Run this against a locally started FastAPI process using isolated test data.
It measures response status, elapsed time, payload size, cache headers, and
gzip behavior without touching production services.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from typing import Any

import requests


ROUTES = [
    ("/", "html", True),
    ("/healthz", "api", False),
    ("/api/health", "api", False),
    ("/api/desktop/health", "api", False),
    ("/manifest.webmanifest", "pwa", False),
    ("/sw.js", "pwa", False),
    ("/static/app.js?v=11.6.0", "static", True),
    ("/static/styles.css?v=11.6.0", "static", True),
    ("/static/icons/dark-hour-icon.svg", "static", False),
]


@dataclass
class RouteMetric:
    path: str
    category: str
    status: int
    elapsed_ms: float
    bytes_received: int
    content_encoding: str
    cache_control: str
    content_type: str


def request_metric(base_url: str, path: str, category: str, gzip: bool) -> RouteMetric:
    headers = {"Accept-Encoding": "gzip"} if gzip else {"Accept-Encoding": "identity"}
    start = time.perf_counter()
    response = requests.get(f"{base_url.rstrip('/')}{path}", headers=headers, timeout=10, stream=True)
    response.raw.decode_content = False
    body = response.raw.read()
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    return RouteMetric(
        path=path,
        category=category,
        status=response.status_code,
        elapsed_ms=elapsed_ms,
        bytes_received=len(body),
        content_encoding=response.headers.get("Content-Encoding", ""),
        cache_control=response.headers.get("Cache-Control", ""),
        content_type=response.headers.get("Content-Type", ""),
    )


def validate(metrics: list[RouteMetric]) -> list[str]:
    failures: list[str] = []
    by_path = {item.path: item for item in metrics}
    for item in metrics:
        if item.status != 200:
            failures.append(f"{item.path} returned {item.status}")
    if "no-store" not in by_path["/api/health"].cache_control:
        failures.append("/api/health must be no-store")
    if "no-store" not in by_path["/api/desktop/health"].cache_control:
        failures.append("/api/desktop/health must be no-store")
    if "no-store" not in by_path["/healthz"].cache_control:
        failures.append("/healthz must be no-store")
    if "no-cache" not in by_path["/"].cache_control:
        failures.append("HTML shell must be no-cache")
    if "no-cache" not in by_path["/sw.js"].cache_control:
        failures.append("service worker must be no-cache")
    if "max-age" not in by_path["/static/app.js?v=11.6.0"].cache_control:
        failures.append("app.js static cache header missing")
    if "max-age" not in by_path["/manifest.webmanifest"].cache_control:
        failures.append("manifest cache header missing")
    if by_path["/static/app.js?v=11.6.0"].content_encoding != "gzip":
        failures.append("app.js did not return gzip content encoding")
    if by_path["/healthz"].content_encoding:
        failures.append("/healthz should stay uncompressed under the threshold")
    return failures


def profile(base_url: str) -> dict[str, Any]:
    metrics = [request_metric(base_url, path, category, gzip) for path, category, gzip in ROUTES]
    failures = validate(metrics)
    return {
        "ok": not failures,
        "base_url": base_url,
        "failures": failures,
        "metrics": [asdict(item) for item in metrics],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8007")
    args = parser.parse_args()
    result = profile(args.base_url)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
