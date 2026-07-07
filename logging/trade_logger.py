"""
MarketHunter

logging/trade_logger.py
"""

from __future__ import annotations

from loguru import logger


class TradeLogger:

    def opened(
        self,
        symbol: str,
        side: str,
        entry: float,
    ) -> None:

        logger.info(
            "OPEN {} {} @ {}",
            side,
            symbol,
            entry,
        )

    def closed(
        self,
        symbol: str,
        pnl: float,
    ) -> None:

        logger.info(
            "CLOSE {} PnL {:.2f}",
            symbol,
            pnl,
        )