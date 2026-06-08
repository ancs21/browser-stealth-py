"""Generate real browser-like headers/user-agents using browserforge.

Ported from Scrapling's ``engines/toolbelt/fingerprints.py`` and merged with the
two browser-mode default user agents that lived in ``_config_tools.py``.
"""

from functools import lru_cache
from platform import system as platform_system
from typing import Dict, Literal, Tuple

from browserforge.headers import Browser, HeaderGenerator
from browserforge.headers.generator import SUPPORTED_OPERATING_SYSTEMS

__OS_NAME__ = platform_system()
OSName = Literal["linux", "macos", "windows"]
# Current versions hardcoded for now (Playwright doesn't allow knowing the version of a browser without launching it)
chromium_version = 148
chrome_version = 148


@lru_cache(1, typed=True)
def get_os_name():
    """Return the current OS in browserforge's format, or all supported OSes if unknown."""
    match __OS_NAME__:  # pragma: no cover
        case "Linux":
            return "linux"
        case "Darwin":
            return "macos"
        case "Windows":
            return "windows"
        case _:
            return SUPPORTED_OPERATING_SYSTEMS


def generate_headers(browser_mode: bool | str = False) -> Dict:
    """Generate real browser-like headers using browserforge's generator.

    :param browser_mode: When truthy, the headers are meant to back a real
        Chromium/Chrome launch, so only the OS and browser type are matched to
        avoid raising fingerprint inconsistency flags. ``"chrome"`` targets the
        Chrome channel; any other truthy value targets Chromium.
    :return: A dictionary of the generated headers.
    """
    os_name = get_os_name()
    ver = chrome_version if browser_mode and browser_mode == "chrome" else chromium_version
    browsers = [Browser(name="chrome", min_version=ver, max_version=ver)]
    if not browser_mode:
        os_name = ("windows", "macos", "linux")
        browsers.extend(
            [
                Browser(name="firefox", min_version=142),
                Browser(name="edge", min_version=140),
            ]
        )
    return HeaderGenerator(browser=browsers, os=os_name, device="desktop").generate()


# Default user agents used when launching headless (the headful UA is already correct).
__default_useragent__ = generate_headers(browser_mode=True).get("User-Agent")
__default_chrome_useragent__ = generate_headers(browser_mode="chrome").get("User-Agent")
