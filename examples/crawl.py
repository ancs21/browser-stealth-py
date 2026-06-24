"""A minimal async crawler on top of browser-stealth-py.

`browser-stealth-py` ships only the fetcher, not Scrapling's spider framework.
But `AsyncStealthySession` has a built-in page pool (`max_pages`), so you can
run N fetches concurrently and build a small Scheduler-less crawler yourself.

This mirrors the core of the Scrapling spider data-flow — frontier + dedup +
bounded concurrency + a parse callback that yields links and items — in ~40 lines.

    uv run python examples/crawl.py
"""

import asyncio
import re
from urllib.parse import urldefrag, urljoin, urlparse

from browser_stealth import AsyncStealthySession

HREF = re.compile(r'href="([^"#]+)"')
QUOTE = re.compile(r'<span class="text"[^>]*>(.*?)</span>', re.S)
# Skip non-HTML assets a real crawler shouldn't follow.
SKIP_EXT = (".css", ".js", ".json", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2", ".pdf")


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s)).strip()


async def crawl(start_url: str, *, limit: int = 8, concurrency: int = 4):
    """Same-domain BFS crawl. Returns (visited_pages, scraped_items)."""
    host = urlparse(start_url).netloc
    seen: set[str] = {start_url}
    frontier: list[str] = [start_url]
    visited: list[tuple[str, int]] = []
    items: list[str] = []

    # max_pages = concurrency lets the session pool serve N fetches at once.
    async with AsyncStealthySession(headless=True, max_pages=concurrency) as session:
        while frontier and len(visited) < limit:
            batch, frontier = frontier[:concurrency], frontier[concurrency:]

            async def fetch(u):
                return u, await session.fetch(u, load_dom=True, network_idle=False)

            for coro in asyncio.as_completed([fetch(u) for u in batch]):
                try:
                    url, page = await coro
                except Exception as e:  # a bad URL shouldn't kill the crawl
                    print("  ! error:", e)
                    continue

                visited.append((url, page.status))
                # --- "callback": yield items + follow links ---
                items.extend(_clean(q) for q in QUOTE.findall(page.text))
                for raw in HREF.findall(page.text):
                    link = urldefrag(urljoin(url, raw))[0]
                    if (
                        urlparse(link).netloc == host
                        and not link.lower().endswith(SKIP_EXT)
                        and link not in seen
                    ):
                        seen.add(link)
                        frontier.append(link)

    return visited, items


async def main() -> None:
    visited, items = await crawl("https://quotes.toscrape.com/", limit=8, concurrency=4)
    print(f"\ncrawled {len(visited)} pages, found {len(items)} quotes")
    for url, status in visited:
        print(f"  {status}  {url}")
    print("\nsample quotes:")
    for q in items[:5]:
        print("  -", q[:70])


if __name__ == "__main__":
    asyncio.run(main())
