"""End-to-end tests: drive the real Chromium stack through the whole pipeline.

Unlike the rest of ``tests/`` (pure, browser-free units), these launch an actual
headless Chromium via patchright and fetch pages from a local stdlib HTTP server
— exercising ``fetcher -> _session -> _base -> navigation -> convertor ->
response`` with **no external network**. The local server makes the assertions
deterministic (known status, title, body, and a JS-injected node for the wait
machinery) instead of depending on a live site.

Excluded from the default run (``-m 'not e2e'`` in pyproject). Opt in with:

    uv run pytest -m e2e

Requires the browser binary once: ``uv run patchright install chromium``.
"""

import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from browser_stealth import StealthyFetcher

pytestmark = pytest.mark.e2e

# A node (#late) is injected 300 ms after load so wait_selector has something
# real to wait for — proving the page-stability path, not just a static GET.
PAGE = b"""<!doctype html><html><head><title>e2e</title></head>
<body><h1 id="marker">hello-e2e</h1>
<script>
setTimeout(function () {
  var d = document.createElement('div');
  d.id = 'late';
  d.textContent = 'ready';
  document.body.appendChild(d);
}, 300);
</script></body></html>"""

MISSING = b"<!doctype html><html><body>nope</body></html>"


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence per-request stderr noise
        pass

    def _send(self, status: int, body: bytes):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/missing":
            self._send(404, MISSING)
        else:
            self._send(200, PAGE)


@pytest.fixture(scope="session", autouse=True)
def _require_chromium():
    """Skip this module's tests if the Chromium binary isn't installed."""
    from patchright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            p.chromium.launch(headless=True).close()
    except Exception as exc:  # executable missing, launch failure, etc.
        pytest.skip(f"Chromium not launchable ({exc}); run `uv run patchright install chromium`")


@pytest.fixture(scope="module")
def base_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()


def test_sync_fetch_ok(base_url):
    page = StealthyFetcher.fetch(base_url + "/", headless=True)
    assert page.status == 200
    assert page.reason == "OK"
    assert page.url.rstrip("/") == base_url
    assert page.method == "GET"
    assert isinstance(page.body, bytes)
    assert "<title>e2e</title>" in page.text
    assert "hello-e2e" in page.text


def test_async_fetch_matches_sync(base_url):
    """The async mirror must return the same thing the sync path does."""
    page = asyncio.run(StealthyFetcher.async_fetch(base_url + "/", headless=True))
    assert page.status == 200
    assert page.reason == "OK"
    assert "hello-e2e" in page.text


def test_status_text_mapping_on_404(base_url):
    page = StealthyFetcher.fetch(base_url + "/missing", headless=True)
    assert page.status == 404
    assert page.reason == "Not Found"
    assert "nope" in page.text


def test_wait_selector_waits_for_js_injected_node(base_url):
    page = StealthyFetcher.fetch(base_url + "/", headless=True, wait_selector="#late")
    assert 'id="late"' in page.text
    assert "ready" in page.text
