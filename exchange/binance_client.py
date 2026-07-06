"""
MarketHunter

exchange/binance_client.py
"""

from __future__ import annotations

from models.candle import Candle

from exchange.base_client import BaseClient
from exchange.endpoints import (
    PING,
    SPOT_BASE_URL,
    FUTURES_BASE_URL,
    SPOT_EXCHANGE_INFO,
    FUTURES_EXCHANGE_INFO,
    SPOT_KLINES,
    FUTURES_KLINES,
    TICKER_24H,
)


class BinanceClient(BaseClient):
    """Binance REST API client."""

    def __init__(self) -> None:
        super().__init__(SPOT_BASE_URL)

    async def ping(self) -> bool:
        """Check Binance Spot API availability."""

        await self.get(PING)

        return True

    async def get_spot_symbols(self) -> list[str]:
        """Return all active Spot USDT pairs."""

        data = await self.get(
            SPOT_EXCHANGE_INFO,
        )

        return sorted(
            symbol["symbol"]
            for symbol in data["symbols"]
            if symbol["status"] == "TRADING"
            and symbol["quoteAsset"] == "USDT"
        )

    async def get_futures_symbols(self) -> list[str]:
        """Return all active USDT Futures pairs."""

        data = await self.get(
            FUTURES_EXCHANGE_INFO,
            base_url=FUTURES_BASE_URL,
        )

        return sorted(
            symbol["symbol"]
            for symbol in data["symbols"]
            if symbol["status"] == "TRADING"
            and symbol["quoteAsset"] == "USDT"
        )

    async def get_klines(
        self,
        symbol: str,
        interval: str = "1d",
        limit: int = 365,
        futures: bool = False,
    ) -> list[Candle]:
        """
        Download historical candles.
        """

        data = await self.get(
            FUTURES_KLINES if futures else SPOT_KLINES,
            base_url=FUTURES_BASE_URL if futures else SPOT_BASE_URL,
            params={
                "symbol": symbol,
                "interval": interval,
                "limit": limit,
            },
        )

        return [Candle.from_binance(candle) for candle in data]

    async def get_ticker_24h(self):
        """
        Get 24h statistics for all Spot symbols.
        """

        return await self.get(TICKER_24H)