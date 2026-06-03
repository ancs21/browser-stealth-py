"""Minimal usage of browser-stealth-py.

Run after installing the package and its browser (uv):
    uv venv
    uv pip install -e .
    uv run patchright install chromium
    uv run python examples/basic.py
"""

import asyncio

from browser_stealth import StealthyFetcher


def sync_example() -> None:
    page = StealthyFetcher.fetch(
        "https://example.com",
        headless=True,
        network_idle=True,
        block_ads=True,        # block ~3,500 ad/tracker domains
        hide_canvas=True,      # add canvas fingerprint noise
        block_webrtc=True,     # prevent local-IP leak behind a proxy
    )
    print("sync :", page.status, page.reason, "->", page.url)
    print("bytes:", len(page.body))
    # `page.text` is the decoded HTML — parse it with lxml/parsel/bs4 as you like.


async def async_example() -> None:
    page = await StealthyFetcher.async_fetch("https://example.com", headless=True)
    print("async:", page.status, "->", page.url)


def cloudflare_example() -> None:
    # solve_cloudflare auto-bumps timeout to >= 60s
    page = StealthyFetcher.fetch(
        "https://nopecha.com/demo/cloudflare",
        headless=True,
        solve_cloudflare=True,
        network_idle=True,
    )
    print("cf   :", page.status, "->", page.url)


if __name__ == "__main__":
    sync_example()
    asyncio.run(async_example())
    # cloudflare_example()  # uncomment to try the Turnstile solver
