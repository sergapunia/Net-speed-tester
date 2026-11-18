#!/usr/bin/env python3
"""Sequential download speed test against a given URL."""

from __future__ import annotations

import argparse
import ssl
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


REQUESTS_COUNT = 10
USER_AGENT = (
    "Mozilla/5.0 (compatible; net-speed-test/1.0; "
    "+https://github.com/net-speed-test)"
)
CA_BUNDLE_CANDIDATES = (
    "/etc/ssl/cert.pem",
    "/opt/homebrew/etc/ca-certificates/cert.pem",
    "/etc/ssl/certs/ca-certificates.crt",
)


@dataclass
class RequestResult:
    bytes_downloaded: int
    elapsed_seconds: float


def build_ssl_context() -> ssl.SSLContext:
    """Prefer an explicit CA bundle so macOS Python installs work out of the box."""
    for candidate in CA_BUNDLE_CANDIDATES:
        path = Path(candidate)
        if path.is_file():
            return ssl.create_default_context(cafile=str(path))
    try:
        import certifi  # type: ignore

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def download_once(url: str, timeout: float, ssl_context: ssl.SSLContext) -> RequestResult:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT},
        method="GET",
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=timeout, context=ssl_context) as response:
        payload = response.read()
    elapsed = time.perf_counter() - started
    return RequestResult(bytes_downloaded=len(payload), elapsed_seconds=elapsed)


def format_bytes(size: int) -> str:
    units = ("B", "KB", "MB", "GB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{size} B"


def format_speed_mbps(total_bytes: int, total_seconds: float) -> str:
    if total_seconds <= 0:
        return "n/a"
    megabits_per_second = (total_bytes * 8) / total_seconds / 1_000_000
    return f"{megabits_per_second:.2f} Mbps"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Measure download speed by fetching a URL 10 times sequentially "
            "and waiting for each full response."
        )
    )
    parser.add_argument(
        "url",
        help="URL to download (for example a large image)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Per-request timeout in seconds (default: 60)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    url = args.url

    print(f"Target: {url}")
    print(f"Requests: {REQUESTS_COUNT} (sequential)")
    print("-" * 40)

    results: list[RequestResult] = []
    ssl_context = build_ssl_context()

    for index in range(1, REQUESTS_COUNT + 1):
        try:
            result = download_once(url, timeout=args.timeout, ssl_context=ssl_context)
        except urllib.error.HTTPError as exc:
            print(f"Request {index}/{REQUESTS_COUNT}: HTTP error {exc.code}", file=sys.stderr)
            return 1
        except urllib.error.URLError as exc:
            print(f"Request {index}/{REQUESTS_COUNT}: network error: {exc.reason}", file=sys.stderr)
            return 1
        except TimeoutError:
            print(f"Request {index}/{REQUESTS_COUNT}: timed out", file=sys.stderr)
            return 1
        except Exception as exc:  # noqa: BLE001 — show a clear console error
            print(f"Request {index}/{REQUESTS_COUNT}: failed: {exc}", file=sys.stderr)
            return 1

        results.append(result)
        print(
            f"Request {index}/{REQUESTS_COUNT}: "
            f"{result.elapsed_seconds:.3f} s, "
            f"{format_bytes(result.bytes_downloaded)}"
        )

    total_bytes = sum(item.bytes_downloaded for item in results)
    total_seconds = sum(item.elapsed_seconds for item in results)
    average_seconds = total_seconds / len(results)

    print("-" * 40)
    print(f"Average request time: {average_seconds:.3f} s")
    print(f"Total downloaded:     {format_bytes(total_bytes)} ({total_bytes} bytes)")
    print(f"Download speed:       {format_speed_mbps(total_bytes, total_seconds)}")
    print("Units: Mbps = megabits per second (1 Mbps = 1_000_000 bits/s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
