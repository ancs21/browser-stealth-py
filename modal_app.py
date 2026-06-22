"""Deploy browser-stealth-py on Modal — stealth fetch behind a geo proxy.

    modal run modal_app.py --url https://example.com --proxy-country VN
    modal deploy modal_app.py          # also exposes the HTTP endpoint below

    # HTTP (after deploy) — query params: url, proxy, proxy_type, proxy_country, output, key
    curl "https://<you>--browser-stealth-web.modal.run/?url=https://example.com&proxy_country=VN&key=$TOKEN"

SECURITY: the HTTP endpoint fetches arbitrary URLs through your paid residential
proxy — an open one is an open proxy + SSRF hole + a way to burn your quota. So
it is token-gated (PROXY_API_TOKEN in the secret) and refuses private/loopback/
metadata hosts. For stronger, platform-level auth use requires_proxy_auth=True.

This is a STANDALONE deploy recipe, deliberately separate from the library:
the package stays vendor-neutral and parser-free; the spider.cloud proxy knobs
(type/country) and the Modal plumbing live only here, never in the public API.

Params (all on `fetch`):
  url           target page
  proxy         explicit proxy (str/dict) — wins over the spider.cloud builder
  proxy_type    spider.cloud pool: residential | datacenter | mobile | isp
  proxy_country ISO country for the exit IP, e.g. "VN" (omit = provider default)
  output        "html"  → return the page HTML   (default)
                "meta"  → return status/headers only (no body)
                "<path>"→ save HTML to the Volume at that path, return metadata
                (markdown/text-extraction is intentionally NOT here — the library
                 is parser-free; convert client-side from the returned HTML.)

WHY A RELAY (the spider.cloud + Chromium gotcha)
------------------------------------------------
spider.cloud authenticates with HTTP Basic creds (username=API key,
password=pool params), but answers an unauthenticated CONNECT with 401 and *no*
`Proxy-Authenticate` header. Chromium only sends proxy creds after such a
challenge, so it never authenticates (ERR_TUNNEL_CONNECTION_FAILED). We run a
tiny localhost relay in the container that injects `Proxy-Authorization`
preemptively and forward to spider.cloud; the browser points at the relay with
no creds. (IP-whitelist auth would skip the relay, but Modal egress IPs are
dynamic, so the relay is required here.)

ponytail: relay inlined (one deploy file, no import gymnastics); resources sized
for one Chromium (4 GiB). UNTESTED here — no Modal CLI in this env; deploy below.
"""
from __future__ import annotations

import base64
import json
import os
import select
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import modal

DATA = "/data"
UPSTREAM = ("proxy.spider.cloud", 8888)

IMAGE = (
    modal.Image.debian_slim(python_version="3.12")
    .run_commands(
        # browser-stealth-py's pinned deps (it isn't on PyPI — source shipped below)
        "pip install playwright==1.60.0 patchright==1.60.1 'browserforge>=1.2.4' 'msgspec>=0.21.1'",
        "playwright install-deps chromium",   # OS libraries (apt)
        "patchright install chromium",        # patchright's stealth Chromium build
    )
    .add_local_python_source("browser_stealth")  # ship the local package (runtime)
)

app = modal.App("browser-stealth", image=IMAGE)
SECRET = modal.Secret.from_name("spider-cloud")  # SPIDER_API_KEY (+ optional PROXY_API_TOKEN)
VOL = modal.Volume.from_name("browser-stealth-out", create_if_missing=True)

# Web front is thin (no Chromium) — it just authorizes and calls fetch.remote().
WEB_IMAGE = modal.Image.debian_slim(python_version="3.12").pip_install("fastapi[standard]")


def _safe_url(u: str) -> bool:
    """Reject non-http(s) and private/loopback/metadata targets (SSRF guard)."""
    import ipaddress
    from urllib.parse import urlparse

    p = urlparse(u)
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    host = p.hostname.lower()
    if host in ("localhost", "metadata.google.internal"):
        return False
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False  # covers 127.0.0.0/8, 10/8, 192.168, 169.254.169.254, …
    except ValueError:
        pass  # a hostname, not a literal IP — the proxy resolves it
    return True


# ── spider.cloud auth-injecting CONNECT relay ──────────────────────────────
class _Relay(BaseHTTPRequestHandler):
    upstream = UPSTREAM
    auth = ""  # "Basic <b64>" — set per server subclass

    def do_CONNECT(self):  # noqa: N802
        try:
            up = socket.create_connection(self.upstream, timeout=30)
        except OSError:
            return self.send_error(502, "upstream connect failed")
        up.sendall(
            f"CONNECT {self.path} HTTP/1.1\r\nHost: {self.path}\r\n"
            f"Proxy-Authorization: {self.auth}\r\nProxy-Connection: Keep-Alive\r\n\r\n".encode()
        )
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = up.recv(4096)
            if not chunk:
                break
            resp += chunk
        if b" 200 " not in resp.split(b"\r\n", 1)[0]:
            up.close()
            return self.send_error(502, "upstream refused CONNECT")
        self.send_response(200, "Connection Established")
        self.end_headers()
        self._splice(self.connection, up)

    @staticmethod
    def _splice(client, upstream):
        socks = [client, upstream]
        try:
            while True:
                readable, _, _ = select.select(socks, [], [], 60)
                if not readable:
                    break
                for s in readable:
                    data = s.recv(8192)
                    if not data:
                        return
                    (upstream if s is client else client).sendall(data)
        except OSError:
            pass
        finally:
            for s in socks:
                try:
                    s.close()
                except OSError:
                    pass

    def log_message(self, *_):  # silence
        pass


def _start_relay(api_key: str, params: str):
    token = base64.b64encode(f"{api_key}:{params}".encode()).decode()
    handler = type("Handler", (_Relay,), {"auth": f"Basic {token}"})
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    host, port = srv.server_address
    return srv, f"http://{host}:{port}"


def _resolve_proxy(proxy, proxy_type, proxy_country):
    """(proxy_arg, relay|None). Explicit proxy wins; else build a spider.cloud relay;
    else direct."""
    if proxy:
        return proxy, None
    if not proxy_type:
        return None, None
    params = f"proxy={proxy_type}" + (f"&country_code={proxy_country}" if proxy_country else "")
    return _start_relay(os.environ["SPIDER_API_KEY"], params)


@app.function(secrets=[SECRET], volumes={DATA: VOL}, cpu=2.0, memory=4096,
              timeout=300, retries=modal.Retries(max_retries=1))
def fetch(url: str, proxy=None, proxy_type: str = "residential",
          proxy_country: str | None = None, output: str = "html",
          solve_cloudflare: bool = True, timeout_ms: int = 90000) -> dict:
    from browser_stealth import StealthyFetcher

    proxy_arg, relay = _resolve_proxy(proxy, proxy_type, proxy_country)
    try:
        resp = StealthyFetcher.fetch(
            url, headless=True, proxy=proxy_arg, solve_cloudflare=solve_cloudflare,
            network_idle=True, timeout=timeout_ms,
            block_webrtc=True, dns_over_https=True,  # no IP/DNS leak around the proxy
        )
    finally:
        if relay:
            relay.shutdown()

    meta = {"url": resp.url, "status": resp.status, "reason": resp.reason,
            "proxy_type": (proxy_type if proxy_arg and not proxy else None),
            "country": proxy_country}
    if output == "meta":
        return {**meta, "headers": dict(resp.headers)}
    if output == "html":
        return {**meta, "html": resp.text}
    # otherwise treat `output` as a Volume-relative path to save the HTML
    dest = f"{DATA}/{output.lstrip('/')}"
    os.makedirs(os.path.dirname(dest) or DATA, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(resp.text)
    VOL.commit()
    return {**meta, "saved": output, "bytes": len(resp.body)}


@app.function(image=WEB_IMAGE, secrets=[SECRET])
@modal.fastapi_endpoint(method="GET")
def web(url: str, proxy: str = "", proxy_type: str = "residential",
        proxy_country: str = "", output: str = "html", key: str = ""):
    """GET /?url=...&proxy_type=...&proxy_country=...&output=...&key=..."""
    from fastapi import HTTPException
    from fastapi.responses import HTMLResponse

    token = os.environ.get("PROXY_API_TOKEN")
    if token and key != token:
        raise HTTPException(status_code=401, detail="bad or missing key")
    if not token:
        # fail closed: an unauthenticated open proxy is never the intended default
        raise HTTPException(status_code=503, detail="PROXY_API_TOKEN not configured")
    if not _safe_url(url):
        raise HTTPException(status_code=400, detail="url must be http(s) and not a private/metadata host")

    res = fetch.remote(url, proxy=proxy or None, proxy_type=proxy_type,
                       proxy_country=proxy_country or None, output=output)
    if "html" in res:  # serve the page directly so a browser/curl renders it
        return HTMLResponse(content=res["html"],
                            headers={"X-Final-URL": res["url"], "X-Status": str(res["status"])})
    return res  # meta / saved → JSON


@app.local_entrypoint()
def main(url: str, proxy_type: str = "residential", proxy_country: str = "VN",
         output: str = "html", proxy: str = ""):
    res = fetch.remote(url, proxy=proxy or None, proxy_type=proxy_type,
                       proxy_country=proxy_country, output=output)
    body = res.pop("html", None)
    print(json.dumps(res, indent=2, ensure_ascii=False))
    if body is not None:
        print(f"--- html ({len(body)} chars) ---\n{body[:800]}")


# ── Deploy ──────────────────────────────────────────────────────────────────
#   pip install modal && modal token new
#   modal secret create spider-cloud SPIDER_API_KEY=sk-... PROXY_API_TOKEN=$(openssl rand -hex 16)
#   modal run modal_app.py --url https://example.com --proxy-country VN        # CLI one-shot
#   modal deploy modal_app.py        # deploys fetch() AND the web endpoint; prints the URL
#   curl "https://<you>--browser-stealth-web.modal.run/?url=https://example.com&proxy_country=VN&key=$TOKEN"
