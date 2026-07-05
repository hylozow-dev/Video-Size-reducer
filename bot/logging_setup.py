"""Logging configuration for the bot."""
from __future__ import annotations

import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    """Configure root logging with a concise, readable format."""
    root = logging.getLogger()
    root.setLevel(level.upper())

    handler = logging.StreamHandler(stream=sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    # Avoid duplicate handlers if setup_logging is called more than once.
    root.handlers.clear()
    root.addHandler(handler)

    # Quiet down noisy third-party loggers.
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
