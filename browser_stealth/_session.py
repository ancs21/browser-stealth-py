"""Stealthy browser session managers (sync + async).

Ported from Scrapling's ``engines/_browsers/_stealth.py``. Behaviour is
unchanged; only imports and the (parser-free) ``ResponseFactory`` call sites
differ.
"""

from asyncio import sleep as asyncio_sleep
from random import randint
from re import compile as re_compile
from time import sleep as time_sleep
from typing import Any, List, Optional

from playwright.sync_api import Locator, Page
from playwright.async_api import Page as async_Page, Locator as AsyncLocator
from patchright.sync_api import sync_playwright
from patchright.async_api import async_playwright

from ._base import SyncSession, AsyncSession, StealthySessionMixin
from ._logger import log
from ._types import ProxyType, Unpack, StealthSession, StealthFetchParams
from ._validators import validate_fetch as _validate, StealthConfig
from .convertor import ResponseFactory
from .proxy_rotation import is_proxy_error
from .response import Response

__CF_PATTERN__ = re_compile(r"^https?://challenges\.cloudflare\.com/cdn-cgi/challenge-platform/.*")


class StealthySession(SyncSession, StealthySessionMixin):
    """A Stealthy Browser session manager with page pooling."""

    __slots__ = (
        "_config",
        "_context_options",
        "_browser_options",
        "_user_data_dir",
        "_headers_keys",
        "max_pages",
        "page_pool",
        "_max_wait_for_page",
        "playwright",
        "context",
    )

    def __init__(self, **kwargs: Unpack[StealthSession]):
        """A Browser session manager with page pooling, using a persistent browser Context by default with a temporary user profile directory.

        See ``StealthyFetcher.fetch`` for the full list of supported keyword arguments.
        """
        self.__validate__(**kwargs)
        super().__init__()

    def start(self) -> None:
        """Create a browser for this instance and context."""
        if not self.playwright:
            self.playwright = sync_playwright().start()

            try:
                if self._config.cdp_url:  # pragma: no cover
                    self.browser = self.playwright.chromium.connect_over_cdp(endpoint_url=self._config.cdp_url)
                    if not self._config.proxy_rotator:
                        assert self.browser is not None
                        self.context = self.browser.new_context(**self._context_options)
                elif self._config.proxy_rotator:
                    self.browser = self.playwright.chromium.launch(**self._browser_options)
                else:
                    persistent_options = (
                        self._browser_options | self._context_options | {"user_data_dir": self._user_data_dir}
                    )
                    self.context = self.playwright.chromium.launch_persistent_context(**persistent_options)

                if self.context:
                    self.context = self._initialize_context(self._config, self.context)

                self._is_alive = True
            except Exception:
                # Clean up playwright if browser setup fails
                self.playwright.stop()
                self.playwright = None
                raise
        else:
            raise RuntimeError("Session has been already started")

    def _cloudflare_solver(self, page: Page) -> None:  # pragma: no cover
        """Solve the cloudflare challenge displayed on the playwright page passed.

        :param page: The targeted page
        """
        self._wait_for_networkidle(page, timeout=5000)
        challenge_type = self._detect_cloudflare(ResponseFactory._get_page_content(page))
        if not challenge_type:
            log.error("No Cloudflare challenge found.")
            return None
        else:
            log.info(f'The turnstile version discovered is "{challenge_type}"')
            if challenge_type == "non-interactive":
                while "<title>Just a moment...</title>" in (ResponseFactory._get_page_content(page)):
                    log.info("Waiting for Cloudflare wait page to disappear.")
                    page.wait_for_timeout(1000)
                    page.wait_for_load_state()
                log.info("Cloudflare captcha is solved")
                return None

            else:
                box_selector = "#cf_turnstile div, #cf-turnstile div, .turnstile>div>div"
                if challenge_type != "embedded":
                    box_selector = ".main-content p+div>div>div"
                    while "Verifying you are human." in ResponseFactory._get_page_content(page):
                        # Waiting for the verify spinner to disappear, checking every 1s if it disappeared
                        page.wait_for_timeout(500)

                outer_box: Any = {}
                iframe = page.frame(url=__CF_PATTERN__)
                if iframe is not None:
                    self._wait_for_page_stability(iframe, True, False)

                    if challenge_type != "embedded":
                        while not iframe.frame_element().is_visible():
                            # Double-checking that the iframe is loaded
                            page.wait_for_timeout(500)

                    outer_box = iframe.frame_element().bounding_box()

                if not iframe or not outer_box:
                    if "<title>Just a moment...</title>" not in (ResponseFactory._get_page_content(page)):
                        log.info("Cloudflare captcha is solved")
                        return None

                    outer_box = page.locator(box_selector).last.bounding_box()

                # Calculate the Captcha coordinates for any viewport
                captcha_x, captcha_y = outer_box["x"] + randint(26, 28), outer_box["y"] + randint(25, 27)

                # Move the mouse to the center of the window, then press and hold the left mouse button
                page.mouse.click(captcha_x, captcha_y, delay=randint(100, 200), button="left")
                self._wait_for_networkidle(page)

                if challenge_type != "embedded":
                    attempts = 0
                    while "<title>Just a moment...</title>" in ResponseFactory._get_page_content(page):
                        # Wait for the page
                        if attempts >= 100:
                            log.info("Cloudflare page didn't disappear after 10s, continuing...")
                            break
                        page.wait_for_timeout(100)
                        attempts += 1

                self._wait_for_page_stability(page, True, False)

                if "<title>Just a moment...</title>" not in (ResponseFactory._get_page_content(page)):
                    log.info("Cloudflare captcha is solved")
                    return None
                else:
                    log.info("Looks like Cloudflare captcha is still present, solving again")
                    return self._cloudflare_solver(page)

    def fetch(self, url: str, **kwargs: Unpack[StealthFetchParams]) -> Response:
        """Opens up the browser and does your request based on your chosen options.

        :param url: The target url.
        :return: A ``Response`` object.
        """
        static_proxy = kwargs.pop("proxy", None)

        params = _validate(kwargs, self, StealthConfig)
        if not self._is_alive:  # pragma: no cover
            raise RuntimeError("Context manager has been closed")

        request_headers_keys = {h.lower() for h in params.extra_headers.keys()} if params.extra_headers else set()
        referer = (
            "https://www.google.com/" if (params.google_search and "referer" not in request_headers_keys) else None
        )

        for attempt in range(self._config.retries):
            proxy: Optional[ProxyType] = None
            if self._config.proxy_rotator and static_proxy is None:
                proxy = self._config.proxy_rotator.get_proxy()
            else:
                proxy = static_proxy

            with self._page_generator(
                params.timeout, params.extra_headers, params.disable_resources, proxy, params.blocked_domains
            ) as page_info:
                final_response: List = [None]
                xhr_captured: List = []
                page = page_info.page
                page.on(
                    "response",
                    self._create_response_handler(
                        page_info,
                        final_response,
                        xhr_pattern=self._config.capture_xhr,
                        xhr_container=xhr_captured,
                    ),
                )

                if params.page_setup:
                    try:
                        params.page_setup(page)
                    except Exception as e:  # pragma: no cover
                        log.error(f"Error executing page_setup: {e}")

                try:
                    first_response = page.goto(url, referer=referer)
                    self._wait_for_page_stability(page, params.load_dom, params.network_idle)

                    if not first_response:
                        raise RuntimeError(f"Failed to get response for {url}")

                    if params.solve_cloudflare:
                        self._cloudflare_solver(page)
                        # Make sure the page is fully loaded after the captcha
                        self._wait_for_page_stability(page, params.load_dom, params.network_idle)

                    if params.page_action:
                        try:
                            _ = params.page_action(page)
                        except Exception as e:  # pragma: no cover
                            log.error(f"Error executing page_action: {e}")

                    if params.wait_selector:
                        try:
                            waiter: Locator = page.locator(params.wait_selector)
                            waiter.first.wait_for(state=params.wait_selector_state)
                            self._wait_for_page_stability(page, params.load_dom, params.network_idle)
                        except Exception as e:  # pragma: no cover
                            log.error(f"Error waiting for selector {params.wait_selector}: {e}")

                    page.wait_for_timeout(params.wait)

                    response = ResponseFactory.from_playwright_response(
                        page,
                        first_response,
                        final_response[0],
                        meta={"proxy": proxy},
                        xhr_captured=xhr_captured,
                    )
                    return response

                except Exception as e:
                    page_info.mark_error()
                    if attempt < self._config.retries - 1:
                        if is_proxy_error(e):
                            log.warning(
                                f"Proxy '{proxy}' failed (attempt {attempt + 1}) | Retrying in {self._config.retry_delay}s..."
                            )
                        else:
                            log.warning(
                                f"Attempt {attempt + 1} failed: {e}. Retrying in {self._config.retry_delay}s..."
                            )
                        time_sleep(self._config.retry_delay)
                    else:
                        log.error(f"Failed after {self._config.retries} attempts: {e}")
                        raise

        raise RuntimeError("Request failed")  # pragma: no cover


class AsyncStealthySession(AsyncSession, StealthySessionMixin):
    """An async Stealthy Browser session manager with page pooling."""

    __slots__ = (
        "_config",
        "_context_options",
        "_browser_options",
        "_user_data_dir",
        "_headers_keys",
    )

    def __init__(self, **kwargs: Unpack[StealthSession]):
        """A Browser session manager with page pooling, using a persistent browser Context by default with a temporary user profile directory.

        See ``StealthyFetcher.async_fetch`` for the full list of supported keyword arguments.
        """
        self.__validate__(**kwargs)
        super().__init__(max_pages=self._config.max_pages)

    async def start(self) -> None:
        """Create a browser for this instance and context."""
        if not self.playwright:
            self.playwright = await async_playwright().start()
            try:
                if self._config.cdp_url:
                    self.browser = await self.playwright.chromium.connect_over_cdp(endpoint_url=self._config.cdp_url)
                    if not self._config.proxy_rotator:
                        assert self.browser is not None
                        self.context = await self.browser.new_context(**self._context_options)
                elif self._config.proxy_rotator:
                    self.browser = await self.playwright.chromium.launch(**self._browser_options)
                else:
                    persistent_options = (
                        self._browser_options | self._context_options | {"user_data_dir": self._user_data_dir}
                    )
                    self.context = await self.playwright.chromium.launch_persistent_context(**persistent_options)

                if self.context:
                    self.context = await self._initialize_context(self._config, self.context)

                self._is_alive = True
            except Exception:
                # Clean up playwright if browser setup fails
                await self.playwright.stop()
                self.playwright = None
                raise
        else:
            raise RuntimeError("Session has been already started")

    async def _cloudflare_solver(self, page: async_Page) -> None:  # pragma: no cover
        """Solve the cloudflare challenge displayed on the playwright page passed.

        :param page: The targeted page
        """
        await self._wait_for_networkidle(page, timeout=5000)
        challenge_type = self._detect_cloudflare(await ResponseFactory._get_async_page_content(page))
        if not challenge_type:
            log.error("No Cloudflare challenge found.")
            return None
        else:
            log.info(f'The turnstile version discovered is "{challenge_type}"')
            if challenge_type == "non-interactive":
                while "<title>Just a moment...</title>" in (await ResponseFactory._get_async_page_content(page)):
                    log.info("Waiting for Cloudflare wait page to disappear.")
                    await page.wait_for_timeout(1000)
                    await page.wait_for_load_state()
                log.info("Cloudflare captcha is solved")
                return None

            else:
                box_selector = "#cf_turnstile div, #cf-turnstile div, .turnstile>div>div"
                if challenge_type != "embedded":
                    box_selector = ".main-content p+div>div>div"
                    while "Verifying you are human." in (await ResponseFactory._get_async_page_content(page)):
                        # Waiting for the verify spinner to disappear, checking every 1s if it disappeared
                        await page.wait_for_timeout(500)

                outer_box: Any = {}
                iframe = page.frame(url=__CF_PATTERN__)
                if iframe is not None:
                    await self._wait_for_page_stability(iframe, True, False)

                    if challenge_type != "embedded":
                        while not await (await iframe.frame_element()).is_visible():
                            # Double-checking that the iframe is loaded
                            await page.wait_for_timeout(500)

                    outer_box = await (await iframe.frame_element()).bounding_box()

                if not iframe or not outer_box:
                    if "<title>Just a moment...</title>" not in (await ResponseFactory._get_async_page_content(page)):
                        log.info("Cloudflare captcha is solved")
                        return None

                    outer_box = await page.locator(box_selector).last.bounding_box()

                # Calculate the Captcha coordinates for any viewport
                captcha_x, captcha_y = outer_box["x"] + randint(26, 28), outer_box["y"] + randint(25, 27)

                # Move the mouse to the center of the window, then press and hold the left mouse button
                await page.mouse.click(captcha_x, captcha_y, delay=randint(100, 200), button="left")
                await self._wait_for_networkidle(page)

                if challenge_type != "embedded":
                    attempts = 0
                    while "<title>Just a moment...</title>" in (await ResponseFactory._get_async_page_content(page)):
                        # Wait for the page
                        if attempts >= 100:
                            log.info("Cloudflare page didn't disappear after 10s, continuing...")
                            break
                        await page.wait_for_timeout(100)
                        attempts += 1

                await self._wait_for_page_stability(page, True, False)

                if "<title>Just a moment...</title>" not in (await ResponseFactory._get_async_page_content(page)):
                    log.info("Cloudflare captcha is solved")
                    return None
                else:
                    log.info("Looks like Cloudflare captcha is still present, solving again")
                    return await self._cloudflare_solver(page)

    async def fetch(self, url: str, **kwargs: Unpack[StealthFetchParams]) -> Response:
        """Opens up the browser and does your request based on your chosen options.

        :param url: The target url.
        :return: A ``Response`` object.
        """
        static_proxy = kwargs.pop("proxy", None)

        params = _validate(kwargs, self, StealthConfig)

        if not self._is_alive:  # pragma: no cover
            raise RuntimeError("Context manager has been closed")

        request_headers_keys = {h.lower() for h in params.extra_headers.keys()} if params.extra_headers else set()
        referer = (
            "https://www.google.com/" if (params.google_search and "referer" not in request_headers_keys) else None
        )

        for attempt in range(self._config.retries):
            proxy: Optional[ProxyType] = None
            if self._config.proxy_rotator and static_proxy is None:
                proxy = self._config.proxy_rotator.get_proxy()
            else:
                proxy = static_proxy

            async with self._page_generator(
                params.timeout, params.extra_headers, params.disable_resources, proxy, params.blocked_domains
            ) as page_info:
                final_response: List = [None]
                xhr_captured: List = []
                page = page_info.page
                page.on(
                    "response",
                    self._create_response_handler(
                        page_info,
                        final_response,
                        xhr_pattern=self._config.capture_xhr,
                        xhr_container=xhr_captured,
                    ),
                )

                if params.page_setup:
                    try:
                        await params.page_setup(page)
                    except Exception as e:  # pragma: no cover
                        log.error(f"Error executing page_setup: {e}")

                try:
                    first_response = await page.goto(url, referer=referer)
                    await self._wait_for_page_stability(page, params.load_dom, params.network_idle)

                    if not first_response:
                        raise RuntimeError(f"Failed to get response for {url}")

                    if params.solve_cloudflare:
                        await self._cloudflare_solver(page)
                        # Make sure the page is fully loaded after the captcha
                        await self._wait_for_page_stability(page, params.load_dom, params.network_idle)

                    if params.page_action:
                        try:
                            _ = await params.page_action(page)
                        except Exception as e:  # pragma: no cover
                            log.error(f"Error executing page_action: {e}")

                    if params.wait_selector:
                        try:
                            waiter: AsyncLocator = page.locator(params.wait_selector)
                            await waiter.first.wait_for(state=params.wait_selector_state)
                            await self._wait_for_page_stability(page, params.load_dom, params.network_idle)
                        except Exception as e:  # pragma: no cover
                            log.error(f"Error waiting for selector {params.wait_selector}: {e}")

                    await page.wait_for_timeout(params.wait)

                    response = await ResponseFactory.from_async_playwright_response(
                        page,
                        first_response,
                        final_response[0],
                        meta={"proxy": proxy},
                        xhr_captured=xhr_captured,
                    )
                    return response

                except Exception as e:
                    page_info.mark_error()
                    if attempt < self._config.retries - 1:
                        if is_proxy_error(e):
                            log.warning(
                                f"Proxy '{proxy}' failed (attempt {attempt + 1}) | Retrying in {self._config.retry_delay}s..."
                            )
                        else:
                            log.warning(
                                f"Attempt {attempt + 1} failed: {e}. Retrying in {self._config.retry_delay}s..."
                            )
                        await asyncio_sleep(self._config.retry_delay)
                    else:
                        log.error(f"Failed after {self._config.retries} attempts: {e}")
                        raise

        raise RuntimeError("Request failed")  # pragma: no cover
