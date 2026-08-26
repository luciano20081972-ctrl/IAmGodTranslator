"""Cycle 3 QA for secure hybrid acquisition contracts and fixture adapters."""

from __future__ import annotations

import json
import sys
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from app.acquisition import (  # noqa: E402
    AcquisitionHttpClient,
    AcquisitionJob,
    AcquisitionStatus,
    ChapterRequestMode,
    ExecutionStrategy,
    FetchResponse,
    FixtureNovelAdapter,
    HostPolicy,
    RateLimitPolicy,
    content_sha256,
    run_fixture_acquisition,
    validate_url,
)


PUBLIC_IP = "93.184.216.34"
PRIVATE_IP = "10.0.0.5"


def require(label: str, condition: bool, failures: list[str]) -> None:
    if not condition:
        failures.append(label)


def expect_reject(label: str, func, failures: list[str]) -> None:
    try:
        func()
    except Exception:
        return
    failures.append(label)


def resolver_factory(mapping: dict[str, list[str]]):
    def resolver(host: str) -> list[str]:
        return mapping.get(host, [PUBLIC_IP])

    return resolver


def fixture_pages(duplicate: bool = False) -> dict[str, FetchResponse]:
    chapter_1 = "<html><h1>Chapter 1: Arrival</h1><article>Chapter 1\n\n" + ("original fixture text " * 20) + "</article></html>"
    chapter_2_body = chapter_1 if duplicate else "<html><h1>第2章 蓝色门</h1><article>第2章\n\n" + ("unicode fixture text " * 20) + "</article></html>"
    return {
        "http://fixture.local/novel/demo/chapters": FetchResponse(
            "http://fixture.local/novel/demo/chapters",
            200,
            {"content-type": "text/html; charset=utf-8"},
            b'<a data-chapter="1" href="/novel/demo/1">Chapter 1: Arrival</a><a data-chapter="2" href="/novel/demo/2">\xe7\xac\xac2\xe7\xab\xa0 \xe8\x93\x9d\xe8\x89\xb2\xe9\x97\xa8</a>',
        ),
        "http://fixture.local/novel/demo/1": FetchResponse(
            "http://fixture.local/novel/demo/1",
            200,
            {"content-type": "text/html; charset=utf-8"},
            chapter_1.encode("utf-8"),
        ),
        "http://fixture.local/novel/demo/2": FetchResponse(
            "http://fixture.local/novel/demo/2",
            200,
            {"content-type": "text/html; charset=utf-8"},
            chapter_2_body.encode("utf-8"),
        ),
    }


def run() -> dict[str, object]:
    failures: list[str] = []
    policy = HostPolicy("fixture", ("fixture.local",), allow_http=True)
    resolver = resolver_factory({"fixture.local": [PUBLIC_IP]})

    safe = validate_url("HTTP://FIXTURE.LOCAL./novel/demo", policy, resolver)
    require("uppercase/trailing-dot host normalizes", safe.normalized == "http://fixture.local/novel/demo", failures)

    rejection_cases = {
        "localhost": "http://localhost/novel",
        "loopback": "http://127.0.0.1/novel",
        "ipv6_loopback": "http://[::1]/novel",
        "private_ipv4": "http://fixture.local/novel",
        "link_local": "http://169.254.1.1/novel",
        "metadata": "http://169.254.169.254/latest/meta-data",
        "unsupported_file": "file:///etc/passwd",
        "unsupported_data": "data:text/plain,hello",
        "unsupported_javascript": "javascript:alert(1)",
        "userinfo": "http://user:pass@fixture.local/novel",
        "encoded_hostname": "http://fixture%2elocal/novel",
        "malformed_hostname": "http://fixture.local%zz/novel",
        "deceptive_suffix": "http://fixture.local.attacker.test/novel",
        "https_required": "http://fixture.local/novel",
        "mixed_dns_private": "https://fixture.local/novel",
    }
    expect_reject("localhost rejected", lambda: validate_url(rejection_cases["localhost"], policy, resolver), failures)
    expect_reject("loopback rejected", lambda: validate_url(rejection_cases["loopback"], HostPolicy("ip", ("127.0.0.1",), allow_http=True), resolver_factory({"127.0.0.1": ["127.0.0.1"]})), failures)
    expect_reject("ipv6 loopback rejected", lambda: validate_url(rejection_cases["ipv6_loopback"], HostPolicy("ip", ("::1",), allow_http=True), resolver_factory({"::1": ["::1"]})), failures)
    expect_reject("private DNS rejected", lambda: validate_url(rejection_cases["private_ipv4"], policy, resolver_factory({"fixture.local": [PRIVATE_IP]})), failures)
    expect_reject("link local rejected", lambda: validate_url(rejection_cases["link_local"], HostPolicy("ip", ("169.254.1.1",), allow_http=True), resolver_factory({"169.254.1.1": ["169.254.1.1"]})), failures)
    expect_reject("metadata rejected", lambda: validate_url(rejection_cases["metadata"], HostPolicy("ip", ("169.254.169.254",), allow_http=True), resolver_factory({"169.254.169.254": ["169.254.169.254"]})), failures)
    expect_reject("file rejected", lambda: validate_url(rejection_cases["unsupported_file"], policy, resolver), failures)
    expect_reject("data rejected", lambda: validate_url(rejection_cases["unsupported_data"], policy, resolver), failures)
    expect_reject("javascript rejected", lambda: validate_url(rejection_cases["unsupported_javascript"], policy, resolver), failures)
    expect_reject("userinfo rejected", lambda: validate_url(rejection_cases["userinfo"], policy, resolver), failures)
    expect_reject("encoded hostname rejected", lambda: validate_url(rejection_cases["encoded_hostname"], policy, resolver), failures)
    expect_reject("malformed hostname rejected", lambda: validate_url(rejection_cases["malformed_hostname"], policy, resolver), failures)
    expect_reject("suffix domain rejected", lambda: validate_url(rejection_cases["deceptive_suffix"], policy, resolver), failures)
    expect_reject("http rejected when not allowed", lambda: validate_url(rejection_cases["https_required"], HostPolicy("fixture", ("fixture.local",)), resolver), failures)
    expect_reject("mixed public/private DNS rejected", lambda: validate_url(rejection_cases["mixed_dns_private"], HostPolicy("fixture", ("fixture.local",)), resolver_factory({"fixture.local": [PUBLIC_IP, PRIVATE_IP]})), failures)

    redirect_pages = {
        "http://fixture.local/redirect": FetchResponse("http://fixture.local/redirect", 302, {"location": "http://127.0.0.1/admin"}, b""),
    }
    client = AcquisitionHttpClient(
        policy,
        resolver=resolver_factory({"fixture.local": [PUBLIC_IP], "127.0.0.1": ["127.0.0.1"]}),
        transport=lambda url, _headers, _timeout: redirect_pages[url],
    )
    expect_reject("redirect to forbidden host rejected", lambda: client.get("http://fixture.local/redirect"), failures)

    oversized = AcquisitionHttpClient(
        policy,
        resolver=resolver,
        transport=lambda url, _headers, _timeout: FetchResponse(url, 200, {"content-type": "text/html"}, b"x" * 101),
        max_response_bytes=100,
    )
    expect_reject("oversized response rejected", lambda: oversized.get("http://fixture.local/novel/demo"), failures)

    blocked = AcquisitionHttpClient(
        policy,
        resolver=resolver,
        transport=lambda url, _headers, _timeout: FetchResponse(url, 200, {"content-type": "text/html"}, b"login to continue"),
    )
    expect_reject("block/login page rejected", lambda: blocked.get("http://fixture.local/novel/demo"), failures)

    adapter = FixtureNovelAdapter()
    require("fixture adapter handles allowed URL", adapter.can_handle("http://fixture.local/novel/demo"), failures)
    require("fixture adapter rejects unsupported URL", not adapter.can_handle("http://attacker.test/novel/demo"), failures)
    acquired = run_fixture_acquisition("http://fixture.local/novel/demo", fixture_pages())
    require("fixture acquisition fetched two chapters", len(acquired) == 2, failures)
    require("unicode title preserved", "蓝色门" in acquired[1].title, failures)
    require("content hashes are stable", acquired[0].content_sha256 == content_sha256(acquired[0].normalized_content), failures)
    expect_reject("duplicate chapter content rejected", lambda: run_fixture_acquisition("http://fixture.local/novel/demo", fixture_pages(duplicate=True)), failures)

    job = AcquisitionJob(
        id="acq_fixture",
        source="fixture_novel",
        input_url="http://fixture.local/novel/demo",
        requested_mode=ChapterRequestMode.RANGE,
        requested_range=(1, 2),
        execution_strategy=ExecutionStrategy.HTTP,
        status=AcquisitionStatus.PENDING,
    )
    serialized = job.to_dict()
    require("job model serializes explicit states", serialized["status"] == "PENDING" and serialized["execution_strategy"] == "HTTP", failures)
    require("rate policy is conservative", RateLimitPolicy().max_concurrency == 1, failures)

    return {
        "ok": not failures,
        "failures": failures,
        "ssrf_cases": 15,
        "fixture_chapters": len(acquired) if "acquired" in locals() else 0,
        "no_live_external_requests": True,
    }


def main() -> int:
    result = run()
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
