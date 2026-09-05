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

    async def test_long_history_requests_bounded_research_source_range(self):
        seen_urls = []
        timestamps = [int(datetime(2020, 1, 1, 20, tzinfo=timezone.utc).timestamp()),
                      int(datetime(2026, 9, 5, 20, tzinfo=timezone.utc).timestamp())]
        raw = json.dumps({"chart":{"result":[{"timestamp":timestamps,"indicators":{"quote":[{
            "open":[100,200],"high":[101,201],"low":[99,199],"close":[100,200],"volume":[1000,2000]
        }]}}],"error":None}})

        def fetch(url):
            seen_urls.append(url)
            return raw

        provider = YahooChartDailyProvider(("SPY",), max_age_seconds=86400, fetch_text=fetch)
        instrument = (await provider.universe())[0]
        await provider.history(instrument, limit=1300)
        self.assertIn("range=10y", seen_urls[0])

    async def test_short_history_preserves_existing_one_year_source_range(self):
        seen_urls = []
        timestamps = [int(datetime(2026, 9, 5, 20, tzinfo=timezone.utc).timestamp())]
        raw = json.dumps({"chart":{"result":[{"timestamp":timestamps,"indicators":{"quote":[{
            "open":[100],"high":[101],"low":[99],"close":[100],"volume":[1000]
        }]}}],"error":None}})
        provider = YahooChartDailyProvider(("SPY",), max_age_seconds=86400, fetch_text=lambda url: seen_urls.append(url) or raw)
        instrument = (await provider.universe())[0]
        await provider.history(instrument, limit=120)
        self.assertIn("range=1y", seen_urls[0])

    async def test_provider_has_zero_execution_surface(self):
        provider = YahooChartDailyProvider(("SPY",), fetch_text=lambda _: "")
        for forbidden in ("place_order", "submit_order", "fill", "order_intent"):
            self.assertFalse(hasattr(provider, forbidden))


if __name__ == "__main__":
    unittest.main()
