"""Proxy usage patterns for browser-stealth-py.

Three correct ways to route through a proxy, plus the one important constraint.

  1. Static proxy  -> pass `proxy=` to the constructor / one-shot fetch.
  2. Rotation      -> pass `proxy_rotator=ProxyRotator([...])` to the constructor.
  3. Per-call proxy override on `session.fetch(url, proxy=...)` ONLY works when the
     session is in "browser mode" — i.e. it was created with a `proxy_rotator`
     or `cdp_url`. On a default (persistent-context) session it raises
     "Browser not initialized for proxy rotation mode", because the per-call
     override spins a fresh context off a detached browser that only exists in
     those modes.

A proxy may be a Playwright-style dict or a "scheme://user:pass@host:port" string.

  IMPORTANT — auth proxies and Chromium:
  Chromium only sends Basic proxy credentials AFTER it receives a
  `Proxy-Authenticate` challenge. Proxies that reject unauthenticated CONNECTs
  without that header (spider.cloud is one) won't authenticate from the browser
  and you'll get `net::ERR_TUNNEL_CONNECTION_FAILED`. For those, run a local
  auth-injecting relay — see examples/spider_cloud_proxy.py.
"""

import os

from browser_stealth import StealthyFetcher, StealthySession, ProxyRotator

# A proxy whose auth Chromium can complete (sends a Proxy-Authenticate challenge),
# or a no-auth / IP-whitelisted proxy. Adjust to your provider.
PROXY = os.environ.get("PROXY_URL", "http://user:pass@host:8080")
ECHO = "https://api.ipify.org?format=json"


def static_proxy_one_shot() -> None:
    """Static proxy on a one-shot fetch (proxy applied at the context level)."""
    page = StealthyFetcher.fetch(ECHO, headless=True, proxy=PROXY, network_idle=True, timeout=60000)
    print("one-shot:", page.status, page.text[:80])


def static_proxy_session() -> None:
    """Static proxy for a whole session — set it once at construction."""
    with StealthySession(headless=True, proxy=PROXY) as s:
        for path in ("", ""):  # every request in this session exits via PROXY
            print("session :", s.fetch(ECHO, network_idle=True).status)
            break


def rotating_proxies() -> None:
    """Rotate across upstreams. A `proxy_rotator` puts the session in browser
    mode, so each fetch gets a fresh context bound to the next proxy.
    """
    rotator = ProxyRotator(
        [
            "http://user:pass@proxy1:8080",
            "http://user:pass@proxy2:8080",
            {"server": "http://proxy3:8080", "username": "user", "password": "pass"},
        ]
    )
    with StealthySession(headless=True, proxy_rotator=rotator, max_pages=3) as s:
        for i in range(3):
            print(f"rotate {i}:", s.fetch(ECHO, network_idle=True).status)


if __name__ == "__main__":
    if PROXY == "http://user:pass@host:8080":
        raise SystemExit("Set PROXY_URL to a real proxy first, or see examples/spider_cloud_proxy.py.")
    static_proxy_one_shot()
    static_proxy_session()
    # rotating_proxies()
