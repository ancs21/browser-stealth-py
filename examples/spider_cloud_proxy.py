"""Use the spider.cloud proxy with the stealth browser.

WHY THIS FILE EXISTS
--------------------
spider.cloud authenticates proxy users with HTTP Basic credentials
(username = API key, password = params like "proxy=residential&country_code=US").
But its proxy answers an unauthenticated CONNECT with `401` and **no
`Proxy-Authenticate` header**. Chromium (and therefore Playwright/patchright)
only sends Basic proxy credentials *after* it receives such a challenge, so it
never authenticates and you get `net::ERR_TUNNEL_CONNECTION_FAILED`. `curl`
works only because it sends the credentials *preemptively*.

The fix is a tiny localhost relay that injects the `Proxy-Authorization`
header preemptively, then forwards to spider.cloud. We point the browser at the
relay with **no** credentials, so Chromium never needs the challenge.

(If you instead enable IP-whitelist auth in the spider.cloud dashboard, you can
skip the relay and use `proxy={"server": "http://proxy.spider.cloud:8888"}`
directly with no username/password.)

    cp .env.example .env        # then put your key in .env (gitignored)
    uv run --env-file .env python examples/spider_cloud_proxy.py

(or just: export SPIDER_API_KEY="sk-..." && uv run python examples/spider_cloud_proxy.py)
"""

import base64
import os
import re
import select
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from browser_stealth import StealthyFetcher

UPSTREAM_HOST = "proxy.spider.cloud"
UPSTREAM_PORT = 8888
# pool + geo; see spider.cloud docs. Country defaults to US; override e.g. PROXY_COUNTRY=VN.
PROXY_PARAMS = f"proxy=residential&country_code={os.environ.get('PROXY_COUNTRY', 'US')}"
IP_ECHO = "https://api.ipify.org?format=json"


class _AuthInjectingProxy(BaseHTTPRequestHandler):
    """Localhost CONNECT relay that forwards to an upstream proxy with preemptive Basic auth."""

    upstream = (UPSTREAM_HOST, UPSTREAM_PORT)
    auth_header = ""  # "Basic <base64>" — set on the server instance

    def do_CONNECT(self):  # noqa: N802 (http.server naming)
        try:
            up = socket.create_connection(self.upstream, timeout=30)
        except OSError:
            self.send_error(502, "Upstream connect failed")
            return

        connect_req = (
            f"CONNECT {self.path} HTTP/1.1\r\n"
            f"Host: {self.path}\r\n"
            f"Proxy-Authorization: {self.auth_header}\r\n"
            f"Proxy-Connection: Keep-Alive\r\n\r\n"
        )
        up.sendall(connect_req.encode())

        # Read the upstream CONNECT response (status line + headers)
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = up.recv(4096)
            if not chunk:
                break
            resp += chunk

        if b" 200 " not in resp.split(b"\r\n", 1)[0]:
            self.send_error(502, "Upstream refused CONNECT")
            up.close()
            return

        # Tell the browser the tunnel is established, then splice raw bytes.
        self.send_response(200, "Connection Established")
        self.end_headers()
        self._splice(self.connection, up)

    @staticmethod
    def _splice(client: socket.socket, upstream: socket.socket) -> None:
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

    def log_message(self, *args):  # silence access logging
        pass


def start_local_relay(api_key: str, params: str) -> tuple[ThreadingHTTPServer, str]:
    """Start the relay on an ephemeral localhost port. Returns (server, proxy_url)."""
    token = base64.b64encode(f"{api_key}:{params}".encode()).decode()
    handler = type("Handler", (_AuthInjectingProxy,), {"auth_header": f"Basic {token}"})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host, port = server.server_address
    return server, f"http://{host}:{port}"


def _ip(page) -> str | None:
    m = re.search(r'"ip"\s*:\s*"([^"]+)"', page.text)
    return m.group(1) if m else None


def main() -> None:
    api_key = os.environ.get("SPIDER_API_KEY")
    if not api_key:
        raise SystemExit("Set SPIDER_API_KEY in your environment (export SPIDER_API_KEY=sk-...).")

    # Baseline: your real IP, no proxy.
    direct = StealthyFetcher.fetch(IP_ECHO, headless=True, network_idle=True, timeout=60000)
    print(f"direct egress     : {_ip(direct)}")

    # Through spider.cloud via the local auth-injecting relay.
    server, relay_url = start_local_relay(api_key, PROXY_PARAMS)
    try:
        proxied = StealthyFetcher.fetch(
            IP_ECHO,
            headless=True,
            proxy=relay_url,        # no credentials here — the relay adds them
            network_idle=True,
            timeout=60000,
        )
        print(f"spider.cloud egress: {_ip(proxied)}   [{PROXY_PARAMS}]")
        print(f"egress changed    : {_ip(direct) != _ip(proxied)}")
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
