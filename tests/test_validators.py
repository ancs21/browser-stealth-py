"""Unit tests for the config-validation rules in ``browser_stealth._validators``.

These pin the behaviour of ``StealthConfig.__post_init__`` (proxy normalization,
mutually-exclusive proxy options, ad-block expansion, Cloudflare timeout bump)
and the ``validate`` error-translation wrapper.
"""

import pytest

from browser_stealth._validators import StealthConfig, validate
from browser_stealth.proxy_rotation import ProxyRotator


class TestProxyNormalization:
    def test_string_proxy_is_normalized_to_a_playwright_dict(self):
        config = StealthConfig(proxy="http://user:pass@host:8080")
        assert config.proxy == {
            "server": "http://host:8080",
            "username": "user",
            "password": "pass",
        }

    def test_proxy_and_proxy_rotator_together_is_rejected(self):
        with pytest.raises(ValueError):
            StealthConfig(
                proxy="http://host:8080",
                proxy_rotator=ProxyRotator(["http://other:8080"]),
            )

    def test_no_proxy_by_default(self):
        assert StealthConfig().proxy is None


class TestBlockAds:
    def test_block_ads_expands_into_blocked_domains(self):
        config = StealthConfig(block_ads=True)
        assert isinstance(config.blocked_domains, set)
        assert len(config.blocked_domains) > 100  # AD_DOMAINS is a large set

    def test_block_ads_merges_with_explicit_blocked_domains(self):
        config = StealthConfig(block_ads=True, blocked_domains={"custom.example"})
        assert "custom.example" in config.blocked_domains
        assert len(config.blocked_domains) > 1

    def test_blocked_domains_is_none_without_block_ads(self):
        assert StealthConfig().blocked_domains is None


class TestCloudflareTimeout:
    def test_solve_cloudflare_bumps_a_low_timeout_to_60s(self):
        assert StealthConfig(solve_cloudflare=True).timeout == 60_000

    def test_solve_cloudflare_preserves_a_higher_timeout(self):
        assert StealthConfig(solve_cloudflare=True, timeout=90_000).timeout == 90_000

    def test_timeout_is_unchanged_without_solve_cloudflare(self):
        assert StealthConfig(timeout=15_000).timeout == 15_000


class TestValidate:
    def test_accepts_valid_overrides(self):
        assert validate({"max_pages": 4}, StealthConfig).max_pages == 4

    def test_reraises_validation_error_as_type_error(self):
        # max_pages has a ge=1 constraint, so 0 fails msgspec validation.
        with pytest.raises(TypeError):
            validate({"max_pages": 0}, StealthConfig)
