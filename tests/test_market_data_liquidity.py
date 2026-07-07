"""
MarketHunter

Tests for liquid USDT perpetual Futures selection.
"""

from __future__ import annotations

import unittest

from services.market_data import MarketDataService


class FakeBinanceClient:
    """
    Deterministic Binance client substitute.
    """

    async def get_futures_exchange_info(self) -> dict:
        return {
            "symbols": [
                {
                    "symbol": "BTCUSDT",
                    "baseAsset": "BTC",
                    "quoteAsset": "USDT",
                    "status": "TRADING",
                    "contractType": "PERPETUAL",
                },
                {
                    "symbol": "ETHUSDT",
                    "baseAsset": "ETH",
                    "quoteAsset": "USDT",
                    "status": "TRADING",
                    "contractType": "PERPETUAL",
                },
                {
                    "symbol": "LOWUSDT",
                    "baseAsset": "LOW",
                    "quoteAsset": "USDT",
                    "status": "TRADING",
                    "contractType": "PERPETUAL",
                },
                {
                    "symbol": "DELIVERYUSDT",
                    "baseAsset": "DELIVERY",
                    "quoteAsset": "USDT",
                    "status": "TRADING",
                    "contractType": "CURRENT_QUARTER",
                },
                {
                    "symbol": "PAUSEDUSDT",
                    "baseAsset": "PAUSED",
                    "quoteAsset": "USDT",
                    "status": "BREAK",
                    "contractType": "PERPETUAL",
                },
                {
                    "symbol": "BTCBUSD",
                    "baseAsset": "BTC",
                    "quoteAsset": "BUSD",
                    "status": "TRADING",
                    "contractType": "PERPETUAL",
                },
            ]
        }

    async def get_futures_ticker_24h(self) -> list[dict]:
        return [
            {
                "symbol": "BTCUSDT",
                "quoteVolume": "50000000",
            },
            {
                "symbol": "ETHUSDT",
                "quoteVolume": "20000000",
            },
            {
                "symbol": "LOWUSDT",
                "quoteVolume": "500000",
            },
            {
                "symbol": "DELIVERYUSDT",
                "quoteVolume": "90000000",
            },
            {
                "symbol": "PAUSEDUSDT",
                "quoteVolume": "90000000",
            },
            {
                "symbol": "BTCBUSD",
                "quoteVolume": "90000000",
            },
        ]


class MarketDataLiquidityTests(
    unittest.IsolatedAsyncioTestCase,
):
    """
    Test Futures liquidity filtering.
    """

    async def test_returns_only_liquid_perpetual_usdt_symbols(
        self,
    ) -> None:
        """
        Low-volume, non-perpetual and inactive contracts are excluded.
        """

        service = MarketDataService(
            client=FakeBinanceClient(),
        )

        symbols = await service.load_liquid_futures_symbols(
            min_quote_volume_usdt=10_000_000.0,
        )

        self.assertEqual(
            [
                symbol.symbol
                for symbol in symbols
            ],
            [
                "BTCUSDT",
                "ETHUSDT",
            ],
        )

        self.assertTrue(
            all(
                symbol.market == "futures"
                for symbol in symbols
            )
        )

    async def test_max_symbols_returns_most_liquid_contracts(
        self,
    ) -> None:
        """
        Result limit keeps the highest-volume symbols first.
        """

        service = MarketDataService(
            client=FakeBinanceClient(),
        )

        symbols = await service.load_liquid_futures_symbols(
            min_quote_volume_usdt=10_000_000.0,
            max_symbols=1,
        )

        self.assertEqual(
            len(symbols),
            1,
        )

        self.assertEqual(
            symbols[0].symbol,
            "BTCUSDT",
        )


if __name__ == "__main__":
    unittest.main()