"""Logging configuration for the application."""
from __future__ import annotations

import logging
import sys


def setup_logging() -> None:
    """Configure logging for the whole application."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
