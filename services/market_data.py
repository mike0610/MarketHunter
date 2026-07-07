"""
MarketHunter

Module:
Market Data Service

Responsibilities:
- Load Spot and Futures symbol metadata.
- Select liquid USDT perpetual Futures contracts.
- Load OHLCV candles from Binance.
"""

from __future__ import annotations

import asyncio

from exchange.binance_client import BinanceClient
from models.candle import Candle
from models.market_symbol import MarketSymbol


class MarketDataService:
    """
    Service for loading public market data from Binance.
    """

    def __init__(
        self,
        client: BinanceClient | None = None,
    ) -> None:
        self.client = client or BinanceClient()

    async def ping(self) -> bool:
        """
        Check Binance API availability.
        """

        return await self.client.ping()

    async def load_symbols(self) -> list[MarketSymbol]:
        """
        Load all active Spot and Futures USDT symbols.

        This method keeps the broad universe available for future use.
        Scanner should normally use load_liquid_futures_symbols().
        """

        symbols: list[MarketSymbol] = []

        spot_info = await self.client.get(
            "/api/v3/exchangeInfo",
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

        futures_info = await self.client.get_futures_exchange_info()

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
            key=lambda item: (
                item.market,
                item.symbol,
            ),
        )

    async def load_liquid_futures_symbols(
        self,
        min_quote_volume_usdt: float,
        max_symbols: int | None = None,
    ) -> list[MarketSymbol]:
        """
        Return liquid USDT perpetual Futures contracts.

        Symbols are sorted by 24-hour quote volume, highest first.
        Delivery contracts, inactive symbols and low-volume contracts
        are excluded before scanning begins.
        """

        if min_quote_volume_usdt <= 0:
            raise ValueError(
                "Minimum quote volume must be greater than zero."
            )

        if max_symbols is not None and max_symbols <= 0:
            raise ValueError(
                "Maximum symbol count must be greater than zero."
            )

        futures_info, tickers = await asyncio.gather(
            self.client.get_futures_exchange_info(),
            self.client.get_futures_ticker_24h(),
        )

        quote_volume_by_symbol = {
            str(item.get("symbol", "")): self._to_float(
                item.get("quoteVolume", 0.0)
            )
            for item in tickers
        }

        liquid_symbols: list[tuple[MarketSymbol, float]] = []

        for item in futures_info["symbols"]:
            if item.get("status") != "TRADING":
                continue

            if item.get("quoteAsset") != "USDT":
                continue

            if item.get("contractType") != "PERPETUAL":
                continue

            symbol_name = str(item.get("symbol", ""))

            if not symbol_name:
                continue

            quote_volume = quote_volume_by_symbol.get(
                symbol_name,
                0.0,
            )

            if quote_volume < min_quote_volume_usdt:
                continue

            liquid_symbols.append(
                (
                    MarketSymbol(
                        symbol=symbol_name,
                        base_asset=str(
                            item.get("baseAsset", "")
                        ),
                        quote_asset="USDT",
                        market="futures",
                    ),
                    quote_volume,
                )
            )

        liquid_symbols.sort(
            key=lambda item: (
                -item[1],
                item[0].symbol,
            )
        )

        symbols = [
            market_symbol
            for market_symbol, _ in liquid_symbols
        ]

        if max_symbols is None:
            return symbols

        return symbols[:max_symbols]

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
        """
        Close Binance client.
        """

        await self.client.close()

    @staticmethod
    def _to_float(
        value: object,
    ) -> float:
        """
        Convert Binance numeric values safely.
        """

        try:
            return float(value)
        except (
            TypeError,
            ValueError,
        ):
            return 0.0