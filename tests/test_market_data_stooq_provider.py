from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from market_data.foundation import MarketDataStale, MarketInstrument
from market_data.stooq_provider import StooqDailyProvider


CSV = """Date,Open,High,Low,Close,Volume
2026-09-02,100,102,99,101,1000000
2026-09-03,101,104,100,103,2000000
2026-09-04,103,105,102,104,3000000
"""


class StooqProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_universe_history_liquidity_and_provenance(self):
        provider = StooqDailyProvider(("AAPL",), fetch_text=lambda url: CSV)
        universe = await provider.universe()
        self.assertEqual(universe[0].symbol, "AAPL")

        fixed_now = datetime(2026, 9, 4, 22, 0, tzinfo=timezone.utc)
        with patch("market_data.stooq_provider.datetime") as dt:
            dt.now.return_value = fixed_now
            dt.strptime.side_effect = datetime.strptime
            dt.combine.side_effect = datetime.combine
            series = await provider.history(universe[0], limit=3)

        self.assertEqual(series.provider, "STOOQ")
        self.assertIn("aapl.us", series.source_reference)
        self.assertEqual(len(series.bars), 3)

        liquidity = await provider.liquidity(universe[0])
        self.assertEqual(str(liquidity.average_daily_volume), "2000000")
        self.assertEqual(str(liquidity.last_price), "104")

    async def test_stale_data_fails_closed(self):
        old_csv = """Date,Open,High,Low,Close,Volume
2020-01-02,10,11,9,10,1000
"""
        provider = StooqDailyProvider(("AAPL",), max_age_seconds=60, fetch_text=lambda url: old_csv)
        instrument = MarketInstrument("AAPL", "US_STOCK_OR_ETF", "USD")
        with self.assertRaises(MarketDataStale):
            await provider.history(instrument)

    async def test_no_execution_capability(self):
        provider = StooqDailyProvider(("AAPL",), fetch_text=lambda url: CSV)
        self.assertFalse(hasattr(provider, "place_order"))
        self.assertFalse(hasattr(provider, "submit_order"))


if __name__ == "__main__":
    unittest.main()
