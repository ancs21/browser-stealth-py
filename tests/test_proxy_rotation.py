"""Unit tests for ``browser_stealth.proxy_rotation``."""

import pytest

from browser_stealth.proxy_rotation import ProxyRotator, cyclic_rotation, is_proxy_error


class TestCyclicRotation:
    def test_iterates_sequentially(self):
        proxy, next_index = cyclic_rotation(["a", "b", "c"], 0)
        assert proxy == "a"
        assert next_index == 1

    def test_wraps_around_at_the_end(self):
        proxy, next_index = cyclic_rotation(["a", "b", "c"], 2)
        assert proxy == "c"
        assert next_index == 0

    def test_modulo_normalizes_an_out_of_range_index(self):
        proxy, next_index = cyclic_rotation(["a", "b"], 5)  # 5 % 2 == 1
        assert proxy == "b"
        assert next_index == 0


class TestProxyRotator:
    def test_rotates_through_all_proxies_then_wraps(self):
        rotator = ProxyRotator(["p1", "p2", "p3"])
        assert [rotator.get_proxy() for _ in range(4)] == ["p1", "p2", "p3", "p1"]

    def test_len_reports_proxy_count(self):
        assert len(ProxyRotator(["p1", "p2"])) == 2

    def test_proxies_property_returns_a_defensive_copy(self):
        rotator = ProxyRotator(["p1"])
        rotator.proxies.append("mutated")
        assert rotator.proxies == ["p1"]

    def test_accepts_playwright_dict_proxies(self):
        rotator = ProxyRotator([{"server": "http://host:8080"}])
        assert rotator.get_proxy() == {"server": "http://host:8080"}

    def test_a_custom_strategy_overrides_rotation(self):
        rotator = ProxyRotator(["p1", "p2"], strategy=lambda proxies, idx: (proxies[0], 0))
        assert [rotator.get_proxy() for _ in range(3)] == ["p1", "p1", "p1"]

    def test_empty_proxy_list_raises_value_error(self):
        with pytest.raises(ValueError):
            ProxyRotator([])

    def test_non_callable_strategy_raises_type_error(self):
        with pytest.raises(TypeError):
            ProxyRotator(["p1"], strategy="not-callable")

    def test_dict_proxy_without_server_raises_value_error(self):
        with pytest.raises(ValueError):
            ProxyRotator([{"username": "u"}])

    def test_unsupported_proxy_type_raises_type_error(self):
        with pytest.raises(TypeError):
            ProxyRotator([12345])


class TestIsProxyError:
    @pytest.mark.parametrize(
        "message",
        [
            "net::ERR_PROXY_CONNECTION_FAILED",
            "net::ERR_TUNNEL_CONNECTION_FAILED",
            "Connection refused",
            "Could not resolve proxy",
        ],
    )
    def test_detects_proxy_errors_case_insensitively(self, message):
        assert is_proxy_error(Exception(message)) is True

    def test_returns_false_for_unrelated_errors(self):
        assert is_proxy_error(Exception("404 Not Found")) is False
