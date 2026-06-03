"""A small context-aware logger for browser-stealth-py.

Ported from Scrapling's ``core.utils._utils`` logger. Exposes a module-level
``log`` proxy plus ``set_logger`` / ``reset_logger`` so callers can swap the
logger per context (e.g. to silence output or route it elsewhere).
"""

import logging
from contextvars import ContextVar, Token
from functools import lru_cache


@lru_cache(1, typed=True)
def setup_logger() -> logging.Logger:
    """Create and configure the default logger with a standard format."""
    logger = logging.getLogger("browser_stealth")
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        fmt="[%(asctime)s] %(levelname)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    if not logger.handlers:
        logger.addHandler(console_handler)

    return logger


_current_logger: ContextVar[logging.Logger] = ContextVar("browser_stealth_logger", default=setup_logger())


class LoggerProxy:
    """Resolves attribute access against whatever logger is current in this context."""

    def __getattr__(self, name: str):
        return getattr(_current_logger.get(), name)


log = LoggerProxy()


def set_logger(logger: logging.Logger) -> Token:
    """Set the current context logger. Returns a token usable with ``reset_logger``."""
    return _current_logger.set(logger)


def reset_logger(token: Token) -> None:
    """Reset the logger to its previous state using a token from ``set_logger``."""
    _current_logger.reset(token)
