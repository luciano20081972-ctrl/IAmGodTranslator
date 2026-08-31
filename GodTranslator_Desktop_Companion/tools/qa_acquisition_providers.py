from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop_companion.acquisition import (  # noqa: E402
    AcquisitionError,
    AcquisitionRequest,
    ApifyProvider,
    BrowserProvider,
    FirecrawlProvider,
    ProviderPolicy,
    SourceAcquisitionProfile,
    choose_provider,
)
from desktop_companion.adapters import adapter_names  # noqa: E402


def require(name: str, condition: bool, failures: list[str]) -> None:
    if not condition:
        failures.append(name)


def main() -> int:
    failures: list[str] = []
    adapters = adapter_names()
    require("firecrawl adapter registered", "firecrawl" in adapters, failures)
    require("apify adapter registered", "apify" in adapters, failures)
    require("browser provider supports js", BrowserProvider.capabilities.supports_js_rendering, failures)
    require("firecrawl supports map/discovery", FirecrawlProvider.capabilities.supports_chapter_discovery, failures)
    require("firecrawl bounded crawl capability", FirecrawlProvider.capabilities.supports_bounded_crawl, failures)
    require("apify requires external credit", ApifyProvider.capabilities.requires_external_credit, failures)

    local = choose_provider("novelfire", "auto", browser_mode=True, policy=ProviderPolicy())
    require("auto novelfire stays local browser", local.provider == "browser", failures)
    no_cloud = choose_provider(
        "generic",
        "auto",
        browser_mode=True,
        policy=ProviderPolicy(allow_cloud_providers=False),
        profile=SourceAcquisitionProfile(preferred_provider="firecrawl", requires_js=True),
    )
    require("auto does not spend cloud by default", no_cloud.provider == "browser", failures)
    cloud = choose_provider(
        "generic",
        "auto",
        browser_mode=True,
        policy=ProviderPolicy(allow_cloud_providers=True, allow_firecrawl_auto=True),
        profile=SourceAcquisitionProfile(preferred_provider="firecrawl", requires_js=True),
    )
    require("auto cloud explicit opt in", cloud.provider == "firecrawl", failures)

    try:
        FirecrawlProvider(api_key="test").fetch_page(AcquisitionRequest("http://169.254.169.254/latest/meta-data"))
        failures.append("firecrawl blocks metadata endpoint")
    except AcquisitionError as exc:
        require("firecrawl ssrf category", exc.category == "blocked_or_restricted", failures)

    live_firecrawl = os.getenv("IAGT_LIVE_FIRECRAWL_TEST") == "1"
    live_apify = os.getenv("IAGT_LIVE_APIFY_TEST") == "1"
    result = {
        "ok": not failures,
        "failures": failures,
        "live_firecrawl": "configured" if live_firecrawl else "LIVE FIRECRAWL TEST - OPERATOR CREDENTIAL REQUIRED",
        "live_apify": "configured" if live_apify else "LIVE APIFY TEST - OPERATOR CREDENTIAL REQUIRED",
        "openai_calls": False,
        "production_writes": False,
    }
    print(result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
