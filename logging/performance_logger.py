"""
MarketHunter

logging/performance_logger.py
"""

from __future__ import annotations

from loguru import logger


class PerformanceLogger:

    def statistics(

        self,

        trades: int,

        winrate: float,

        profit: float,

    ) -> None:

        logger.info(
            "Trades:{} WinRate:{:.2f}% Profit:{:.2f}",
            trades,
            winrate,
            profit,
        )