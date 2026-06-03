"""browser-stealth-py — standalone stealth browser fetching extracted from Scrapling.

Quick start::

    from browser_stealth import StealthyFetcher

    page = StealthyFetcher.fetch("https://example.com", headless=True)
    print(page.status, page.url)
    html = page.text
"""

from ._logger import log, set_logger, reset_logger
from .fetcher import StealthyFetcher
from ._session import StealthySession, AsyncStealthySession
from .proxy_rotation import ProxyRotator, cyclic_rotation, is_proxy_error
from .response import Response, StatusText

__version__ = "0.2.0"

__all__ = [
    "StealthyFetcher",
    "StealthySession",
    "AsyncStealthySession",
    "Response",
    "StatusText",
    "ProxyRotator",
    "cyclic_rotation",
    "is_proxy_error",
    "log",
    "set_logger",
    "reset_logger",
    "__version__",
]
