"""A lightweight, parser-free ``Response`` object.

Scrapling's ``Response`` subclasses its full ``Selector`` parser engine. To keep
this package standalone we drop that dependency entirely: ``Response`` here is a
plain container exposing the HTTP metadata plus the raw ``body``/decoded
``text``. Parse the HTML with whatever you prefer (lxml, parsel, BeautifulSoup).
"""

from functools import lru_cache
from types import MappingProxyType
from typing import Any, Dict, List, Tuple

from ._logger import log


class Response:
    """Unified response returned by the stealth engine.

    :param url: Final URL of the page.
    :param content: Raw response body (``str`` is encoded to bytes using ``encoding``).
    :param status: HTTP status code.
    :param reason: HTTP status message.
    :param cookies: Response cookies.
    :param headers: Response headers.
    :param request_headers: Request headers sent with the request.
    :param encoding: Body text encoding (default ``utf-8``).
    :param method: HTTP method used.
    :param history: List of redirect ``Response`` objects, if any.
    :param meta: Metadata dictionary (e.g. the proxy used).
    """

    __slots__ = (
        "url",
        "status",
        "reason",
        "cookies",
        "headers",
        "request_headers",
        "encoding",
        "method",
        "history",
        "meta",
        "captured_xhr",
        "_body",
    )

    def __init__(
        self,
        url: str,
        content: str | bytes,
        status: int,
        reason: str,
        cookies: Tuple[Dict[str, str], ...] | Dict[str, str],
        headers: Dict,
        request_headers: Dict,
        encoding: str = "utf-8",
        method: str = "GET",
        history: List | None = None,
        meta: Dict[str, Any] | None = None,
    ):
        if isinstance(content, str):
            content = content.encode(encoding or "utf-8")

        self.url = url
        self.status = status
        self.reason = reason
        self.cookies = cookies
        self.headers = headers
        self.request_headers = request_headers
        self.encoding = encoding or "utf-8"
        self.method = method
        self.history = history or []
        self._body: bytes = content

        if meta and not isinstance(meta, dict):
            raise TypeError(f"Response meta should be dictionary but got {type(meta).__name__} instead!")
        self.meta: Dict[str, Any] = meta or {}
        self.captured_xhr: List["Response"] = []

        # For easier debugging while working from a Python shell
        log.info(f"Fetched ({status}) <{method} {url}> (referer: {request_headers.get('referer')})")

    @property
    def body(self) -> bytes:
        """Return the raw body of the response as bytes."""
        return self._body

    @property
    def text(self) -> str:
        """Return the decoded body of the response as a string."""
        return self._body.decode(self.encoding, errors="replace")

    def __str__(self) -> str:
        return f"<{self.status} {self.url}>"

    def __repr__(self) -> str:
        return f"<Response [{self.status} {self.reason}] {self.url}>"


class StatusText:
    """Maps HTTP status codes to their reason phrases.

    Reference: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status
    """

    _phrases = MappingProxyType(
        {
            100: "Continue",
            101: "Switching Protocols",
            102: "Processing",
            103: "Early Hints",
            200: "OK",
            201: "Created",
            202: "Accepted",
            203: "Non-Authoritative Information",
            204: "No Content",
            205: "Reset Content",
            206: "Partial Content",
            207: "Multi-Status",
            208: "Already Reported",
            226: "IM Used",
            300: "Multiple Choices",
            301: "Moved Permanently",
            302: "Found",
            303: "See Other",
            304: "Not Modified",
            305: "Use Proxy",
            307: "Temporary Redirect",
            308: "Permanent Redirect",
            400: "Bad Request",
            401: "Unauthorized",
            402: "Payment Required",
            403: "Forbidden",
            404: "Not Found",
            405: "Method Not Allowed",
            406: "Not Acceptable",
            407: "Proxy Authentication Required",
            408: "Request Timeout",
            409: "Conflict",
            410: "Gone",
            411: "Length Required",
            412: "Precondition Failed",
            413: "Payload Too Large",
            414: "URI Too Long",
            415: "Unsupported Media Type",
            416: "Range Not Satisfiable",
            417: "Expectation Failed",
            418: "I'm a teapot",
            421: "Misdirected Request",
            422: "Unprocessable Entity",
            423: "Locked",
            424: "Failed Dependency",
            425: "Too Early",
            426: "Upgrade Required",
            428: "Precondition Required",
            429: "Too Many Requests",
            431: "Request Header Fields Too Large",
            451: "Unavailable For Legal Reasons",
            500: "Internal Server Error",
            501: "Not Implemented",
            502: "Bad Gateway",
            503: "Service Unavailable",
            504: "Gateway Timeout",
            505: "HTTP Version Not Supported",
            506: "Variant Also Negotiates",
            507: "Insufficient Storage",
            508: "Loop Detected",
            510: "Not Extended",
            511: "Network Authentication Required",
        }
    )

    @classmethod
    @lru_cache(maxsize=128)
    def get(cls, status_code: int) -> str:
        """Get the phrase for a given HTTP status code."""
        return cls._phrases.get(status_code, "Unknown Status Code")


__all__ = ["Response", "StatusText"]
