"""Build :class:`Response` objects from Playwright responses.

Ported from Scrapling's ``engines/toolbelt/convertor.py``, trimmed to the
browser paths and the lightweight (parser-free) ``Response``. The
``from_http_request`` path and all ``parser_arguments`` plumbing are dropped.
"""

from functools import lru_cache
from re import compile as re_compile
from typing import Dict, List, Optional

from playwright._impl._errors import Error as PlaywrightError
from playwright.sync_api import Page as SyncPage, Response as SyncResponse
from playwright.async_api import Page as AsyncPage, Response as AsyncResponse

from ._logger import log
from .response import Response, StatusText

__CHARSET_RE__ = re_compile(r"charset=([\w-]+)")


class ResponseFactory:
    """Factory for creating ``Response`` objects from Playwright responses."""

    @classmethod
    @lru_cache(maxsize=16)
    def __extract_browser_encoding(cls, content_type: str | None, default: str = "utf-8") -> str:
        """Extract encoding from a content-type header.

        Ex: "content-type: text/html; charset=utf-8" -> "utf-8".
        """
        if content_type:
            match = __CHARSET_RE__.search(content_type)
            return match.group(1) if match else default
        return default

    @classmethod
    def _process_response_history(cls, first_response: SyncResponse) -> List[Response]:
        """Walk the redirect chain to build a list of ``Response`` objects."""
        history: List[Response] = []
        current_request = first_response.request.redirected_from

        try:
            while current_request:
                try:
                    current_response = current_request.response()
                    history.insert(
                        0,
                        Response(
                            url=current_request.url,
                            # current_response.text() raises on redirect responses (body unavailable)
                            content="",
                            status=current_response.status if current_response else 301,
                            reason=(current_response.status_text or StatusText.get(current_response.status))
                            if current_response
                            else StatusText.get(301),
                            encoding=cls.__extract_browser_encoding(current_response.headers.get("content-type", ""))
                            if current_response
                            else "utf-8",
                            cookies=tuple(),
                            headers=current_response.all_headers() if current_response else {},
                            request_headers=current_request.all_headers(),
                        ),
                    )
                except Exception as e:  # pragma: no cover
                    log.error(f"Error processing redirect: {e}")
                    break

                current_request = current_request.redirected_from
        except Exception as e:  # pragma: no cover
            log.error(f"Error processing response history: {e}")

        return history

    @classmethod
    def from_playwright_response(
        cls,
        page: Optional[SyncPage],
        first_response: SyncResponse,
        final_response: Optional[SyncResponse],
        meta: Optional[Dict] = None,
        xhr_captured: Optional[List[SyncResponse]] = None,
        collect_history: bool = True,
    ) -> Response:
        """Transform a sync Playwright response into a ``Response`` object."""
        # In case we didn't catch a document type somehow
        final_response = final_response if final_response else first_response
        if not final_response:
            raise ValueError("Failed to get a response from the page")

        encoding = cls.__extract_browser_encoding(final_response.headers.get("content-type", ""))
        # Playwright sometimes gives empty status text
        status_text = final_response.status_text or StatusText.get(final_response.status)

        history = cls._process_response_history(first_response) if collect_history else []
        try:
            if page and "html" in final_response.all_headers().get("content-type", ""):
                page_content = cls._get_page_content(page).encode("utf-8")
            else:
                page_content = final_response.body()
        except Exception as e:  # pragma: no cover
            log.error(f"Error getting page content: {e}")
            page_content = b""

        response = Response(
            url=page.url if page else first_response.url,
            content=page_content,
            status=final_response.status,
            reason=status_text,
            encoding=encoding,
            cookies=tuple(dict(cookie) for cookie in page.context.cookies()) if page else {},
            headers=first_response.all_headers(),
            request_headers=first_response.request.all_headers(),
            history=history,
            meta=meta,
        )
        if xhr_captured:
            response.captured_xhr = [
                cls.from_playwright_response(None, p, None, collect_history=False) for p in xhr_captured
            ]
        return response

    @classmethod
    async def _async_process_response_history(cls, first_response: AsyncResponse) -> List[Response]:
        """Walk the redirect chain to build a list of ``Response`` objects (async)."""
        history: List[Response] = []
        current_request = first_response.request.redirected_from

        try:
            while current_request:
                try:
                    current_response = await current_request.response()
                    history.insert(
                        0,
                        Response(
                            url=current_request.url,
                            content="",
                            status=current_response.status if current_response else 301,
                            reason=(current_response.status_text or StatusText.get(current_response.status))
                            if current_response
                            else StatusText.get(301),
                            encoding=cls.__extract_browser_encoding(current_response.headers.get("content-type", ""))
                            if current_response
                            else "utf-8",
                            cookies=tuple(),
                            headers=await current_response.all_headers() if current_response else {},
                            request_headers=await current_request.all_headers(),
                        ),
                    )
                except Exception as e:  # pragma: no cover
                    log.error(f"Error processing redirect: {e}")
                    break

                current_request = current_request.redirected_from
        except Exception as e:  # pragma: no cover
            log.error(f"Error processing response history: {e}")

        return history

    @classmethod
    def _get_page_content(cls, page: SyncPage, max_retries: int = 20) -> str:
        """Workaround for the Playwright ``page.content()`` flake on Windows.

        Ref.: https://github.com/microsoft/playwright/issues/16108
        """
        for _ in range(max_retries):
            try:
                return page.content() or ""
            except PlaywrightError:
                page.wait_for_timeout(500)
        raise RuntimeError(f"Failed to retrieve the page content after retrying for {max_retries * 500}ms.")

    @classmethod
    async def _get_async_page_content(cls, page: AsyncPage, max_retries: int = 20) -> str:
        """Async workaround for the Playwright ``page.content()`` flake on Windows.

        Ref.: https://github.com/microsoft/playwright/issues/16108
        """
        for _ in range(max_retries):
            try:
                return (await page.content()) or ""
            except PlaywrightError:
                await page.wait_for_timeout(500)
        raise RuntimeError(f"Failed to retrieve the page content after retrying for {max_retries * 500}ms.")

    @classmethod
    async def from_async_playwright_response(
        cls,
        page: Optional[AsyncPage],
        first_response: AsyncResponse,
        final_response: Optional[AsyncResponse],
        meta: Optional[Dict] = None,
        xhr_captured: Optional[List[AsyncResponse]] = None,
        collect_history: bool = True,
    ) -> Response:
        """Transform an async Playwright response into a ``Response`` object."""
        # In case we didn't catch a document type somehow
        final_response = final_response if final_response else first_response
        if not final_response:
            raise ValueError("Failed to get a response from the page")

        encoding = cls.__extract_browser_encoding(final_response.headers.get("content-type", ""))
        status_text = final_response.status_text or StatusText.get(final_response.status)

        history = await cls._async_process_response_history(first_response) if collect_history else []
        try:
            if page and "html" in (await final_response.all_headers()).get("content-type", ""):
                page_content = (await cls._get_async_page_content(page)).encode("utf-8")
            else:
                page_content = await final_response.body()
        except Exception as e:  # pragma: no cover
            log.error(f"Error getting page content in async: {e}")
            page_content = b""

        response = Response(
            url=page.url if page else first_response.url,
            content=page_content,
            status=final_response.status,
            reason=status_text,
            encoding=encoding,
            cookies=tuple(dict(cookie) for cookie in await page.context.cookies()) if page else {},
            headers=await first_response.all_headers(),
            request_headers=await first_response.request.all_headers(),
            history=history,
            meta=meta,
        )
        if xhr_captured:
            response.captured_xhr = [
                await cls.from_async_playwright_response(None, p, None, collect_history=False) for p in xhr_captured
            ]
        return response
