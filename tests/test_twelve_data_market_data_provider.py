from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone

from market_data.twelve_data_provider import TwelveDataDailyProvider


class TwelveDataDailyProviderTests(unittest.IsolatedAsyncioTestCase):
    def _payload(self):
        values=[]
        for day in range(1, 61):
            values.append({
                "datetime": f"2026-09-{min(day,6):02d}" if day <= 6 else f"2026-08-{min(day-6,31):02d}",
                "open":"100","high":"102","low":"99","close":"101","volume":"1000000",
            })
        # deterministic unique valid dates, newest last
        values=[]
        start=datetime(2026,7,9,tzinfo=timezone.utc)
        from datetime import timedelta
        for i in range(60):
            d=(start+timedelta(days=i)).date().isoformat()
            values.append({"datetime":d,"open":"100","high":"102","low":"99","close":str(100+i/10),"volume":"1000000"})
        return json.dumps({"meta":{"symbol":"SPY"},"values":values,"status":"ok"})

    async def test_history_and_liquidity_use_one_provider_call_via_cache(self):
        calls=[]
        provider=TwelveDataDailyProvider(
            ("SPY",), api_key="secret", max_age_seconds=86400*10, history_limit=60,
            fetch_text=lambda url: calls.append(url) or self._payload(),
            clock=lambda: datetime(2026,9,6,12,tzinfo=timezone.utc),
        )
        instrument=(await provider.universe())[0]
        liquidity=await provider.liquidity(instrument)
        series=await provider.history(instrument,limit=60)
        self.assertEqual(len(calls),1)
        self.assertEqual(len(series.bars),60)
        self.assertGreater(liquidity.average_daily_volume,0)
        self.assertEqual(series.provider,"TWELVE_DATA")
        self.assertNotIn("secret",series.source_reference)

    async def test_provider_error_fails_closed(self):
        provider=TwelveDataDailyProvider(
            ("SPY",), api_key="secret", fetch_text=lambda _: json.dumps({"status":"error","message":"limit"})
        )
        instrument=(await provider.universe())[0]
        with self.assertRaises(Exception):
            await provider.history(instrument)

    async def test_provider_has_zero_execution_surface(self):
        provider=TwelveDataDailyProvider(("SPY",),api_key="secret",fetch_text=lambda _:"")
        for forbidden in ("place_order","submit_order","fill","order_intent"):
            self.assertFalse(hasattr(provider,forbidden))


if __name__=="__main__":
    unittest.main()
