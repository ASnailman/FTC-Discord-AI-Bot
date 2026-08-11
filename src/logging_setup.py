"""Central logging configuration.

`config.LOG_LEVEL` was previously read but never applied -- every module
used bare `print()` (see docs/deployment.md's "Logging" section). This
gives the new node pipeline (and, incidentally, existing modules) a real
`logging.getLogger(__name__)` target without touching the print-based
behavior of pre-existing modules.
"""
import logging

import config

_CONFIGURED = False


def configure() -> None:
    """Idempotent: safe to call from bot.py, scripts, and tests alike."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure()
    return logging.getLogger(name)
