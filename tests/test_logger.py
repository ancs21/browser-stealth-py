"""Unit tests for the context-var-swappable logger in ``browser_stealth._logger``."""

import logging

from browser_stealth import log, reset_logger, set_logger


def test_default_log_proxies_to_the_browser_stealth_logger():
    assert log.name == "browser_stealth"


def test_set_logger_swaps_the_active_logger():
    token = set_logger(logging.getLogger("test-custom"))
    try:
        assert log.name == "test-custom"
    finally:
        reset_logger(token)


def test_reset_logger_restores_the_previous_logger():
    original_name = log.name
    token = set_logger(logging.getLogger("test-temp"))
    reset_logger(token)
    assert log.name == original_name


def test_log_proxy_forwards_standard_methods():
    assert callable(log.info)
    assert callable(log.warning)
    assert callable(log.error)
