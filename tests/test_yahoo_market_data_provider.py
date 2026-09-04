from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone

from market_data.yahoo_provider import YahooChartDailyProvider


class YahooChartDailyProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_history_and_liquidity_parse_read_only_chart_evidence(self):
        timestamps = [int(datetime(2026, 9, d, 20, tzinfo=timezone.utc).timestamp()) for d in (1, 2, 3, 4)]
        raw = json.dumps({"chart":{"result":[{"timestamp":timestamps,"indicators":{"quote":[{
            "open":[100,101,102,103],"high":[102,103,104,105],"low":[99,100,101,102],
            "close":[101,102,103,104],"volume":[1000000,1100000,1200000,1300000]
        }]}}],"error":None}})
        provider = YahooChartDailyProvider(("SPY",), max_age_seconds=86400, fetch_text=lambda _: raw)
        instrument = (await provider.universe())[0]
        series = await provider.history(instrument, limit=3)
        self.assertEqual(len(series.bars), 3)
        self.assertEqual(series.provider, "YAHOO_CHART")
        liquidity = await provider.liquidity(instrument)
        self.assertGreater(liquidity.average_daily_volume, 0)

    async def test_provider_has_zero_execution_surface(self):
        provider = YahooChartDailyProvider(("SPY",), fetch_text=lambda _: "")
        for forbidden in ("place_order", "submit_order", "fill", "order_intent"):
            self.assertFalse(hasattr(provider, forbidden))


if __name__ == "__main__":
    unittest.main()
