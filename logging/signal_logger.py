"""
MarketHunter

logging/signal_logger.py
"""

from __future__ import annotations

from loguru import logger

from models.signal import Signal


class SignalLogger:

    def log(
        self,
        signal: Signal,
    ) -> None:

        logger.info(
            "[{}] {} {} Score:{}",
            signal.strategy,
            signal.symbol,
            signal.direction,
            signal.score,
        )

        for reason in signal.reasons:

            logger.info(
                "    • {}",
                reason,
            )