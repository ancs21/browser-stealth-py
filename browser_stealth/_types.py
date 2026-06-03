"""Shared type aliases and ``TypedDict`` parameter schemas.

``from __future__ import annotations`` keeps every annotation here a lazy
string, which lets the ``StealthSession`` TypedDicts reference ``ProxyRotator``
for typing without importing it at runtime (avoiding an import cycle with
``proxy_rotation``).
"""

from __future__ import annotations

from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    Generator,
    Generic,
    List,
    Literal,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    TypeVar,
    TYPE_CHECKING,
    Union,
    cast,
    overload,
)
from typing import AsyncGenerator, TypedDict

try:  # ``Unpack``/``TypeAlias`` live in typing on 3.11+, typing_extensions otherwise
    from typing import TypeAlias, Unpack
except ImportError:  # pragma: no cover
    from typing_extensions import TypeAlias, Unpack  # type: ignore

if TYPE_CHECKING:
    from .proxy_rotation import ProxyRotator

__all__ = [
    "Any",
    "Awaitable",
    "Callable",
    "Dict",
    "Generator",
    "Generic",
    "List",
    "Literal",
    "Mapping",
    "Optional",
    "Sequence",
    "Set",
    "Tuple",
    "TypeVar",
    "TYPE_CHECKING",
    "Union",
    "cast",
    "overload",
    "AsyncGenerator",
    "TypedDict",
    "TypeAlias",
    "Unpack",
    "ProxyType",
    "SelectorWaitStates",
    "SetCookieParam",
    "StealthSession",
    "StealthFetchParams",
]

ProxyType = Union[str, Dict[str, str]]
SelectorWaitStates = Literal["attached", "detached", "hidden", "visible"]


# Copied from ``playwright._impl._api_structures.SetCookieParam``
class SetCookieParam(TypedDict, total=False):
    name: str
    value: str
    url: Optional[str]
    domain: Optional[str]
    path: Optional[str]
    expires: Optional[float]
    httpOnly: Optional[bool]
    secure: Optional[bool]
    sameSite: Optional[Literal["Lax", "None", "Strict"]]
    partitionKey: Optional[str]


class StealthSession(TypedDict, total=False):
    """Keyword arguments accepted when constructing a stealth session."""

    max_pages: int
    headless: bool
    disable_resources: bool
    network_idle: bool
    load_dom: bool
    wait_selector: Optional[str]
    wait_selector_state: SelectorWaitStates
    cookies: Sequence[SetCookieParam] | None
    google_search: bool
    wait: int | float
    timezone_id: str | None
    page_action: Optional[Callable]
    page_setup: Optional[Callable]
    proxy: Optional[str | Dict[str, str] | Tuple]
    proxy_rotator: Optional["ProxyRotator"]
    extra_headers: Optional[Dict[str, str]]
    timeout: int | float
    init_script: Optional[str]
    user_data_dir: str
    additional_args: Optional[Dict]
    locale: Optional[str]
    real_chrome: bool
    cdp_url: Optional[str]
    useragent: Optional[str]
    extra_flags: Optional[List[str]]
    blocked_domains: Optional[Set[str]]
    block_ads: bool
    retries: int
    retry_delay: int | float
    capture_xhr: str | None
    executable_path: Optional[str]
    dns_over_https: bool
    # Stealth-only knobs
    allow_webgl: bool
    hide_canvas: bool
    block_webrtc: bool
    solve_cloudflare: bool


class StealthFetchParams(TypedDict, total=False):
    """Keyword arguments accepted by ``session.fetch`` to override session config per call."""

    load_dom: bool
    wait: int | float
    network_idle: bool
    google_search: bool
    timeout: int | float
    disable_resources: bool
    wait_selector: Optional[str]
    page_action: Optional[Callable]
    page_setup: Optional[Callable]
    extra_headers: Optional[Dict[str, str]]
    wait_selector_state: SelectorWaitStates
    blocked_domains: Optional[Set[str]]
    proxy: Optional[str | Dict[str, str]]
    solve_cloudflare: bool
