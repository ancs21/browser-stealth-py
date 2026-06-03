"""The public ``StealthyFetcher`` entry point.

A thin wrapper around ``StealthySession`` / ``AsyncStealthySession`` for the
common one-shot fetch case.
"""

from ._session import StealthySession, AsyncStealthySession
from ._types import Unpack, StealthSession
from .response import Response


class StealthyFetcher:
    """A completely stealthy fetcher built on top of Chromium (via patchright).

    It behaves like a real browser, passing almost all online bot tests/protections,
    with many customization options.
    """

    @classmethod
    def fetch(cls, url: str, **kwargs: Unpack[StealthSession]) -> Response:
        """Open a browser and perform a stealthy request.

        :param url: Target url.
        :param headless: Run the browser in headless/hidden (default), or headful/visible mode.
        :param disable_resources: Drop requests for unnecessary resources for a speed boost.
            Requests dropped are of type `font`, `image`, `media`, `beacon`, `object`, `imageset`, `texttrack`, `websocket`, `csp_report`, and `stylesheet`.
        :param blocked_domains: A set of domain names to block requests to. Subdomains are also matched (e.g. ``"example.com"`` blocks ``"sub.example.com"`` too).
        :param block_ads: Block requests to ~3,500 known ad/tracking domains. Can be combined with ``blocked_domains``.
        :param dns_over_https: Route DNS queries through Cloudflare's DNS-over-HTTPS to prevent DNS leaks when using proxies.
        :param useragent: Pass a useragent string to be used. Otherwise the fetcher will generate a real Useragent of the same browser and use it.
        :param cookies: Set cookies for the next request.
        :param network_idle: Wait for the page until there are no network connections for at least 500 ms.
        :param timeout: The timeout in milliseconds used in all operations and waits through the page. The default is 30,000.
        :param wait: The time (milliseconds) the fetcher will wait after everything finishes before closing the page and returning the ``Response`` object.
        :param page_action: A function that takes the `page` object, runs after navigation, and does the automation you need.
        :param page_setup: A function that takes the `page` object, runs before navigation. Use it to register event listeners or routes that must be set up before the page loads.
        :param wait_selector: Wait for a specific CSS selector to be in a specific state.
        :param init_script: An absolute path to a JavaScript file to be executed on page creation for all pages in this session.
        :param locale: Specify user locale, e.g. `en-GB`, `de-DE`, etc. Affects navigator.language, Accept-Language, and number/date formatting. Defaults to the system locale.
        :param timezone_id: Changes the timezone of the browser. Defaults to the system timezone.
        :param wait_selector_state: The state to wait for the selector given with `wait_selector`. The default state is `attached`.
        :param solve_cloudflare: Solves all types of Cloudflare's Turnstile/Interstitial challenges before returning the response to you.
        :param real_chrome: If you have a Chrome browser installed, enable this and the fetcher will launch an instance of your browser and use it.
        :param hide_canvas: Add random noise to canvas operations to prevent fingerprinting.
        :param block_webrtc: Forces WebRTC to respect proxy settings to prevent local IP address leak.
        :param allow_webgl: Enabled by default. Disabling it disables WebGL and WebGL 2.0 support entirely. Not recommended as many WAFs now check if WebGL is enabled.
        :param load_dom: Enabled by default, wait for all JavaScript on page(s) to fully load and execute.
        :param cdp_url: Instead of launching a new browser instance, connect to this CDP URL to control real browsers through CDP.
        :param google_search: Enabled by default, set a Google referer header.
        :param extra_headers: A dictionary of extra headers to add to the request. _The referer set by `google_search` takes priority over the referer set here if used together._
        :param proxy: The proxy to be used with requests; a string or a dict with the keys 'server', 'username', and 'password' only.
        :param user_data_dir: Path to a User Data Directory, which stores browser session data like cookies and local storage. The default is to create a temporary directory.
        :param extra_flags: A list of additional browser flags to pass to the browser on launch.
        :param additional_args: Additional arguments to be passed to Playwright's context as additional settings; takes higher priority than this package's settings.
        :return: A ``Response`` object.
        """
        with StealthySession(**kwargs) as engine:
            return engine.fetch(url)

    @classmethod
    async def async_fetch(cls, url: str, **kwargs: Unpack[StealthSession]) -> Response:
        """Open a browser and perform a stealthy request (async).

        Accepts the same keyword arguments as :meth:`fetch`.

        :param url: Target url.
        :return: A ``Response`` object.
        """
        async with AsyncStealthySession(**kwargs) as engine:
            return await engine.fetch(url)
