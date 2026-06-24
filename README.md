# browser-stealth-py

A **standalone** stealth browser fetcher. It drives Chromium through
[patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright) (a stealth-patched
Playwright fork) and layers on anti-fingerprint browser flags, a real generated
User-Agent, resource/ad blocking, proxy rotation, and a Cloudflare Turnstile solver. You
get back a lightweight `Response` (status, headers, cookies, URL, raw `body`, decoded
`text`) — parse the HTML with whatever you like (lxml, parsel, BeautifulSoup).

> For **authorized** scraping, QA, and research. Respect each site's Terms of Service
> and `robots.txt`.

## Install (uv)

```bash
uv venv
uv pip install -e .
uv run patchright install chromium   # one-time browser binary install
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

Async — same arguments, `await`ed:

```python
page = await StealthyFetcher.async_fetch("https://example.com", headless=True)
```

Run the demo: `uv run python examples/basic.py`.

### Secrets / `.env`

Keep API keys out of source. Copy the template and load it with uv's `--env-file`:

```bash
cp .env.example .env          # .env is gitignored; .env.example is tracked
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

- **Per-call override** `s.fetch(url, proxy=...)` only works in *browser mode* (a session
  created with `proxy_rotator` or `cdp_url`). On a default persistent-context session it
  raises *"Browser not initialized for proxy rotation mode"* — set the static `proxy=` at
  construction instead.
- **Auth proxies + Chromium:** Chromium only sends Basic proxy credentials *after* a
  `Proxy-Authenticate` challenge, so a provider that rejects an unauthenticated CONNECT
  fails (`net::ERR_TUNNEL_CONNECTION_FAILED`) even though `curl` works. Use IP-whitelist
  auth, or a tiny local relay that injects the auth preemptively — see
  [`examples/spider_cloud_proxy.py`](examples/spider_cloud_proxy.py) (a tested,
  dependency-free relay) and [`examples/proxy.py`](examples/proxy.py).

## Cloudflare

```python
page = StealthyFetcher.fetch(url, solve_cloudflare=True)  # auto-bumps timeout to ≥60s
```

Handles non-interactive / managed / interactive / embedded Turnstile challenges by
detecting the type and clicking the checkbox with human-like randomized offsets.

## Key options

| Option | Default | What it does |
|---|---|---|
| `headless` | `True` | Hidden vs visible browser |
| `solve_cloudflare` | `False` | Solve Turnstile/Interstitial challenges |
| `block_webrtc` | `False` | Force WebRTC to respect proxy (no local-IP leak) |
| `hide_canvas` | `False` | Add canvas fingerprint noise |
| `block_ads` | `False` | Block ~3,500 ad/tracker domains |
| `blocked_domains` | `None` | Extra domains to block (subdomains matched) |
| `disable_resources` | `False` | Drop fonts/images/media/etc. for speed |
| `dns_over_https` | `False` | Route DNS via Cloudflare DoH (no DNS leak) |
| `proxy` / `proxy_rotator` | `None` | Static proxy or a rotator |
| `network_idle` / `load_dom` | `False` / `True` | Page-stability waits |
| `wait_selector` (+ `_state`) | `None` | Wait for a CSS selector |
| `page_setup` / `page_action` | `None` | Hooks before / after navigation |
| `real_chrome` | `False` | Use your installed Chrome instead of Chromium |
| `cdp_url` | `None` | Attach to an existing browser over CDP |

See the docstrings on `StealthyFetcher.fetch` for the full list.

## Tests

```bash
uv run pytest              # fast, browser-free unit suite
uv run pytest -m e2e       # end-to-end: launches real Chromium (needs the binary above)
```

`pytest` is installed automatically by `uv run` (it lives in the `dev` dependency group).

## License

BSD-3-Clause — see [LICENSE](LICENSE).
