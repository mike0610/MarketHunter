"""
MarketHunter

logging/error_logger.py
"""

from __future__ import annotations

from loguru import logger


class ErrorLogger:

    def exception(
        self,
        exc: Exception,
    ) -> None:

        logger.exception(exc)

    def message(
        self,
        text: str,
    ) -> None:

        logger.error(text)