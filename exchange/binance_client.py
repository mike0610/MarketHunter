"""
MarketHunter

Module:
Binance Client

Responsibilities:
- Request public Spot and Futures market data from Binance.
- Load exchange metadata, candles and 24-hour ticker statistics.
"""

from __future__ import annotations

from models.candle import Candle

from exchange.base_client import BaseClient
from exchange.endpoints import (
    FUTURES_BASE_URL,
    FUTURES_EXCHANGE_INFO,
    FUTURES_KLINES,
    FUTURES_TICKER_24H,
    PING,
    SPOT_BASE_URL,
    SPOT_EXCHANGE_INFO,
    SPOT_KLINES,
    TICKER_24H,
)


class BinanceClient(BaseClient):
    """
    Binance REST API client for public market data.
    """

    def __init__(self) -> None:
        super().__init__(SPOT_BASE_URL)

    async def ping(self) -> bool:
        """
        Check Binance Spot API availability.
        """

        await self.get(PING)

        return True

    async def get_spot_symbols(self) -> list[str]:
        """
        Return all active Spot USDT pairs.
        """

        data = await self.get(
            SPOT_EXCHANGE_INFO,
        )

        return sorted(
            item["symbol"]
            for item in data["symbols"]
            if item["status"] == "TRADING"
            and item["quoteAsset"] == "USDT"
        )

    async def get_futures_exchange_info(self) -> dict:
        """
        Return complete Binance USDT-M Futures exchange metadata.
        """

        return await self.get(
            FUTURES_EXCHANGE_INFO,
            base_url=FUTURES_BASE_URL,
        )

    async def get_futures_symbols(self) -> list[str]:
        """
        Return active USDT perpetual Futures pairs.
        """

        data = await self.get_futures_exchange_info()

        return sorted(
            item["symbol"]
            for item in data["symbols"]
            if item["status"] == "TRADING"
            and item["quoteAsset"] == "USDT"
            and item.get("contractType") == "PERPETUAL"
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
            base_url=(
                FUTURES_BASE_URL
                if futures
                else SPOT_BASE_URL
            ),
            params={
                "symbol": symbol,
                "interval": interval,
                "limit": limit,
            },
        )

        return [
            Candle.from_binance(candle)
            for candle in data
        ]

    async def get_ticker_24h(self) -> list[dict]:
        """
        Get 24-hour Spot statistics.
        """

        data = await self.get(
            TICKER_24H,
            base_url=SPOT_BASE_URL,
        )

        if not isinstance(data, list):
            raise ValueError(
                "Binance Spot ticker response must be a list."
            )

        return data

    async def get_futures_ticker_24h(self) -> list[dict]:
        """
        Get 24-hour USDT-M Futures statistics.
        """

        data = await self.get(
            FUTURES_TICKER_24H,
            base_url=FUTURES_BASE_URL,
        )

        if not isinstance(data, list):
            raise ValueError(
                "Binance Futures ticker response must be a list."
            )

        return data