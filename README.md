# browser-stealth-py

A **standalone** stealth browser fetcher — the stealth engine extracted from
[Scrapling](https://github.com/D4Vinci/Scrapling), with its parser dependency
removed so it stands on its own.

It drives Chromium through [patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright)
(a stealth-patched Playwright fork) and layers on anti-fingerprint browser flags,
a real generated User-Agent, resource/ad blocking, proxy rotation, and a
Cloudflare Turnstile solver. You get back a lightweight `Response` (status,
headers, cookies, URL, raw `body`, decoded `text`) — parse the HTML with whatever
you like (lxml, parsel, BeautifulSoup).

> This package is for **authorized** scraping, QA, and research. Respect each
> site's Terms of Service and `robots.txt`.

## Install (uv)

```bash
uv venv
uv pip install -e .
# install the browser binary (one-time)
uv run patchright install chromium
```

For convenience HTML parsers: `uv pip install -e ".[parse]"`.

## Quick start

```python
from browser_stealth import StealthyFetcher

page = StealthyFetcher.fetch(
    "https://example.com",
    headless=True,
    network_idle=True,
    block_ads=True,      # block ~3,500 ad/tracker domains
    hide_canvas=True,    # canvas fingerprint noise
    block_webrtc=True,   # prevent local-IP leak behind a proxy
)
print(page.status, page.reason, page.url)
html = page.text         # decoded HTML; parse it however you prefer
```

Async:

```python
import asyncio
from browser_stealth import StealthyFetcher

async def main():
    page = await StealthyFetcher.async_fetch("https://example.com", headless=True)
    print(page.status)

asyncio.run(main())
```

Run the example:

```bash
uv run python examples/basic.py
```

### Secrets / `.env`

Keep API keys out of source. Copy the template and load it with uv's `--env-file`:

```bash
cp .env.example .env          # .env is gitignored; .env.example is tracked
# edit .env, then:
uv run --env-file .env python examples/spider_cloud_proxy.py
```

## Sessions & proxies

Reuse one browser across many requests with a session. Set a **static** proxy at
construction, or pass a **rotator** to cycle proxies per request:

```python
from browser_stealth import StealthyFetcher, StealthySession, ProxyRotator

# static — applied to the whole session/context
StealthyFetcher.fetch("https://example.com", proxy="http://u:p@host:8080")

# rotation — a fresh context per request, next proxy each call
rotator = ProxyRotator(["http://u:p@proxy1:8080", "http://u:p@proxy2:8080"])
with StealthySession(headless=True, proxy_rotator=rotator, max_pages=4) as s:
    a = s.fetch("https://example.com/1")
    b = s.fetch("https://example.com/2")  # next proxy in the rotation
```

A proxy is a `"scheme://user:pass@host:port"` string or a Playwright dict
`{"server", "username", "password"}`.

**Constraint:** a per-call override `s.fetch(url, proxy=...)` only works when the
session is in *browser mode* — created with a `proxy_rotator` or `cdp_url`. On a
default persistent-context session it raises *"Browser not initialized for proxy
rotation mode"*; set the static proxy at construction instead.

**Auth proxies + Chromium (gotcha):** Chromium only sends Basic proxy
credentials *after* a `Proxy-Authenticate` challenge. Providers that reject an
unauthenticated CONNECT without that header — **spider.cloud** is one — won't
authenticate from the browser (`net::ERR_TUNNEL_CONNECTION_FAILED`), even though
`curl` works (it sends creds preemptively). Workarounds: enable IP-whitelist
auth, or run a tiny local relay that injects the auth preemptively. See
[`examples/spider_cloud_proxy.py`](examples/spider_cloud_proxy.py) for a tested,
dependency-free relay. The general patterns live in
[`examples/proxy.py`](examples/proxy.py).

## Cloudflare

```python
page = StealthyFetcher.fetch(url, solve_cloudflare=True)  # auto-bumps timeout to ≥60s
```

Handles non-interactive / managed / interactive / embedded Turnstile challenges
by detecting the challenge type and clicking the checkbox with human-like
randomized offsets.

## Key options

| Option | Default | What it does |
|---|---|---|
| `headless` | `True` | Hidden vs visible browser |
| `solve_cloudflare` | `False` | Solve Turnstile/Interstitial challenges |
| `block_webrtc` | `False` | Force WebRTC to respect proxy (no local-IP leak) |
| `hide_canvas` | `False` | Add canvas fingerprint noise |
| `allow_webgl` | `True` | Disabling turns off WebGL (not recommended) |
| `block_ads` | `False` | Block ~3,500 ad/tracker domains |
| `blocked_domains` | `None` | Extra domains to block (subdomains matched) |
| `disable_resources` | `False` | Drop fonts/images/media/etc. for speed |
| `dns_over_https` | `False` | Route DNS via Cloudflare DoH (no DNS leak) |
| `google_search` | `True` | Send a Google referer header |
| `proxy` / `proxy_rotator` | `None` | Static proxy or a rotator |
| `network_idle` / `load_dom` | `False` / `True` | Page-stability waits |
| `wait_selector` (+ `_state`) | `None` | Wait for a CSS selector |
| `page_setup` / `page_action` | `None` | Hooks before / after navigation |
| `real_chrome` | `False` | Use your installed Chrome instead of Chromium |
| `cdp_url` | `None` | Attach to an existing browser over CDP |

See the docstrings on `StealthyFetcher.fetch` for the full list.

## How it differs from Scrapling

- **No parser.** Scrapling's `Response` subclasses its `Selector` engine; here
  `Response` is a plain container (`body`/`text` + HTTP metadata). This drops the
  entire `parser`/`translator`/`storage` dependency tree.
- **Cloudflare embedded-challenge detection** uses a regex instead of the
  Scrapling selector. Behaviour is otherwise identical.
- Everything else (flags, fingerprint context, proxy rotation, the Turnstile
  solver, page pooling, retries) is ported faithfully.

## Layout

```
browser_stealth/
  fetcher.py        StealthyFetcher (public API)
  _session.py       StealthySession / AsyncStealthySession (fetch loop, CF solver)
  _base.py          session bases + StealthySessionMixin (flag/fingerprint generation)
  _validators.py    msgspec config schemas (StealthConfig)
  _types.py         type aliases + TypedDict parameter schemas
  constants.py      DEFAULT_ARGS / STEALTH_ARGS / HARMFUL_ARGS / resource set
  fingerprints.py   browserforge header/UA generation
  navigation.py     route interception + proxy dict normalization
  proxy_rotation.py ProxyRotator
  ad_domains.py     ~3,500 ad/tracker domains (block_ads)
  convertor.py      Playwright response -> Response
  response.py       lightweight Response + StatusText
  _page.py          PagePool / PageInfo
```

## Tests

A small `pytest` suite covers the parser-free, browser-free logic — proxy rotation,
`Response`/status mapping, proxy & domain normalization, config validation, and the
logger:

```bash
uv run pytest
```

`pytest` is installed automatically by `uv run` (it lives in the `dev` dependency group).
The suite intentionally doesn't drive a real browser — those paths need the Chromium
binary and live network.

## Credits & license

The stealth engine, browser flags, and Cloudflare solver originate from
**[Scrapling](https://github.com/D4Vinci/Scrapling)** by Karim Shoair, BSD-3-Clause.
This is an extraction/repackaging of that work.
