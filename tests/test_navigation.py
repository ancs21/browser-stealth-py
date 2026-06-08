"""Unit tests for ``browser_stealth.navigation``.

Covers proxy-string/dict normalization, the domain suffix-match helper, and the
sync route-interception handler (the async handler mirrors it 1:1).
"""

import pytest

from browser_stealth.navigation import (
    _is_domain_blocked,
    construct_proxy_dict,
    create_intercept_handler,
)


class TestConstructProxyDict:
    def test_parses_a_full_proxy_url(self):
        assert construct_proxy_dict("http://user:pass@host:8080") == {
            "server": "http://host:8080",
            "username": "user",
            "password": "pass",
        }

    def test_parses_a_url_without_credentials(self):
        assert construct_proxy_dict("http://host:8080") == {
            "server": "http://host:8080",
            "username": "",
            "password": "",
        }

    def test_parses_a_url_without_a_port(self):
        assert construct_proxy_dict("http://host")["server"] == "http://host"

    def test_supports_the_socks5_scheme(self):
        assert construct_proxy_dict("socks5://host:1080")["server"] == "socks5://host:1080"

    def test_normalizes_a_proxy_dict(self):
        assert construct_proxy_dict({"server": "http://host:8080"}) == {
            "server": "http://host:8080",
            "username": "",
            "password": "",
        }

    def test_rejects_an_unsupported_scheme(self):
        with pytest.raises(ValueError):
            construct_proxy_dict("ftp://host:21")

    def test_rejects_a_string_without_a_hostname(self):
        with pytest.raises(ValueError):
            construct_proxy_dict("http://")

    def test_dict_without_a_server_key_raises_type_error(self):
        with pytest.raises(TypeError):
            construct_proxy_dict({"username": "u"})

    def test_non_string_non_dict_raises_type_error(self):
        with pytest.raises(TypeError):
            construct_proxy_dict(12345)


class TestIsDomainBlocked:
    DOMAINS = frozenset({"doubleclick.net"})

    def test_exact_match_is_blocked(self):
        assert _is_domain_blocked("doubleclick.net", self.DOMAINS) is True

    def test_subdomain_is_blocked(self):
        assert _is_domain_blocked("ads.doubleclick.net", self.DOMAINS) is True

    def test_deep_subdomain_is_blocked(self):
        assert _is_domain_blocked("tracker.ads.doubleclick.net", self.DOMAINS) is True

    def test_lookalike_substring_is_not_blocked(self):
        assert _is_domain_blocked("notdoubleclick.net", self.DOMAINS) is False

    def test_unrelated_domain_is_not_blocked(self):
        assert _is_domain_blocked("example.com", self.DOMAINS) is False


class _FakeRequest:
    def __init__(self, url, resource_type):
        self.url = url
        self.resource_type = resource_type


class _FakeRoute:
    """Minimal stand-in for a Playwright sync Route, recording its dispatch."""

    def __init__(self, url="http://example.com/", resource_type="document"):
        self.request = _FakeRequest(url, resource_type)
        self.calls = []

    def abort(self):
        self.calls.append("abort")

    def continue_(self):
        self.calls.append("continue")


class TestInterceptHandler:
    def test_blocks_a_disabled_resource_type(self):
        handler = create_intercept_handler(disable_resources=True)
        route = _FakeRoute(resource_type="image")
        handler(route)
        assert route.calls == ["abort"]

    def test_allows_a_non_disabled_resource_type(self):
        handler = create_intercept_handler(disable_resources=True)
        route = _FakeRoute(resource_type="document")
        handler(route)
        assert route.calls == ["continue"]

    def test_blocks_a_request_to_a_blocked_domain(self):
        handler = create_intercept_handler(disable_resources=False, blocked_domains={"doubleclick.net"})
        route = _FakeRoute(url="http://ads.doubleclick.net/pixel")
        handler(route)
        assert route.calls == ["abort"]

    def test_allows_a_request_to_an_unblocked_domain(self):
        handler = create_intercept_handler(disable_resources=False, blocked_domains={"doubleclick.net"})
        route = _FakeRoute(url="http://example.com/page")
        handler(route)
        assert route.calls == ["continue"]

    def test_passes_through_when_nothing_is_configured(self):
        handler = create_intercept_handler(disable_resources=False)
        route = _FakeRoute()
        handler(route)
        assert route.calls == ["continue"]
