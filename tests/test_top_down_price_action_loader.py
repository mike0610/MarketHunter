from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from models.candle import Candle
from models.market_symbol import MarketSymbol
from research.price_action.loader import TopDownPriceActionLoader
from research.price_action.top_down import TopDownPriceActionEngine


def candles(count, step_hours):
    result = []
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    for i in range(count):
        base = 100 + i * 0.5
        t = start + timedelta(hours=i * step_hours)
        result.append(
            Candle(
                t,
                base,
                base + 2,
                base - 2,
                base + 1,
                1000,
                t + timedelta(hours=step_hours),
                100000,
                100,
                500,
                50000,
            )
        )
    return result


class FakeMarketData:
    def __init__(self):
        self.calls = []

    async def load_candles(self, symbol, interval, limit):
        self.calls.append((symbol.symbol, interval, limit))
        counts = {
            "1M": 36,
            "1w": 80,
            "1d": 220,
            "1h": 220,
        }
        steps = {
            "1M": 24 * 30,
            "1w": 24 * 7,
            "1d": 24,
            "1h": 1,
        }
        return candles(counts[interval], steps[interval])


class TopDownPriceActionLoaderTests(unittest.IsolatedAsyncioTestCase):
    async def test_loader_fetches_all_required_timeframes(self):
        market_data = FakeMarketData()
        loader = TopDownPriceActionLoader(
            market_data,
            engine=TopDownPriceActionEngine(),
        )
        symbol = MarketSymbol(
            symbol="BTCUSDT",
            base_asset="BTC",
            quote_asset="USDT",
            market="futures",
        )

        context = await loader.analyze_symbol(symbol)

        self.assertEqual(
            [call[1] for call in market_data.calls],
            ["1M", "1w", "1d", "1h"],
        )
        self.assertEqual(context.monthly.regime.value, "transition")
        self.assertEqual(context.weekly.regime.value, "transition")
        self.assertEqual(context.daily.regime.value, "transition")
        self.assertEqual(context.hourly.regime.value, "transition")

    async def test_loader_uses_bounded_default_limits(self):
        market_data = FakeMarketData()
        loader = TopDownPriceActionLoader(market_data)
        symbol = MarketSymbol(
            symbol="ETHUSDT",
            base_asset="ETH",
            quote_asset="USDT",
            market="spot",
        )

        await loader.analyze_symbol(symbol)

        self.assertEqual(
            market_data.calls,
            [
                ("ETHUSDT", "1M", 120),
                ("ETHUSDT", "1w", 260),
                ("ETHUSDT", "1d", 365),
                ("ETHUSDT", "1h", 500),
            ],
        )


if __name__ == "__main__":
    unittest.main()
