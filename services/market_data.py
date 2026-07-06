"""
MarketHunter

services/market_data.py
"""

from __future__ import annotations

from exchange.binance_client import BinanceClient
from models.candle import Candle
from models.market_symbol import MarketSymbol


class MarketDataService:
    """Service for loading market data from Binance."""

    def __init__(self) -> None:
        self.client = BinanceClient()

    async def ping(self) -> bool:
        """Check Binance API availability."""

        return await self.client.ping()

    async def load_symbols(self) -> list[MarketSymbol]:
        """Load all active Spot and Futures USDT symbols."""

        symbols: list[MarketSymbol] = []

        #
        # Spot
        #

        spot_info = await self.client.get(
            "/api/v3/exchangeInfo"
        )

        for item in spot_info["symbols"]:

            if item["status"] != "TRADING":
                continue

            if item["quoteAsset"] != "USDT":
                continue

            symbols.append(
                MarketSymbol(
                    symbol=item["symbol"],
                    base_asset=item["baseAsset"],
                    quote_asset=item["quoteAsset"],
                    market="spot",
                )
            )

        #
        # Futures
        #

        futures_info = await self.client.get(
            "/fapi/v1/exchangeInfo",
            base_url="https://fapi.binance.com",
        )

        for item in futures_info["symbols"]:

            if item["status"] != "TRADING":
                continue

            if item["quoteAsset"] != "USDT":
                continue

            symbols.append(
                MarketSymbol(
                    symbol=item["symbol"],
                    base_asset=item["baseAsset"],
                    quote_asset=item["quoteAsset"],
                    market="futures",
                )
            )

        return sorted(
            symbols,
            key=lambda x: (
                x.market,
                x.symbol,
            ),
        )

    async def load_candles(
        self,
        symbol: MarketSymbol,
        interval: str = "1d",
        limit: int = 365,
    ) -> list[Candle]:
        """
        Load historical candles.
        """

        return await self.client.get_klines(
            symbol=symbol.symbol,
            interval=interval,
            limit=limit,
            futures=symbol.is_futures,
        )

    async def close(self) -> None:
        """Close Binance client."""

        await self.client.close()