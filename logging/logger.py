"""
MarketHunter

logging/logger.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger


LOG_DIR = Path("logs")

LOG_DIR.mkdir(
    exist_ok=True,
)


logger.remove()


logger.add(
    sys.stdout,
    colorize=True,
    level="INFO",
)


logger.add(
    LOG_DIR / "markethunter.log",
    rotation="10 MB",
    retention="30 days",
    compression="zip",
    level="DEBUG",
)


logger.add(
    LOG_DIR / "errors.log",
    rotation="10 MB",
    retention="30 days",
    compression="zip",
    level="ERROR",
)


def get_logger():

    return logger