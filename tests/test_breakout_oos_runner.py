from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from market_data.foundation import MarketBar, MarketInstrument, MarketSeries
from research.run_breakout_validation import DEVELOPMENT_FRACTION, split_and_validate


def make_series(n=300):
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    bars = []
    price = Decimal("100")
    for i in range(n):
        price += Decimal("0.1")
        bars.append(MarketBar(
            timestamp=start + timedelta(days=i),
            open=price, high=price + 1, low=price - 1, close=price,
            volume=Decimal("1000000"),
        ))
    return MarketSeries(
        MarketInstrument("SPY", "US_STOCK_OR_ETF", "USD"),
        "1d", tuple(bars), "TEST", "fixture", bars[-1].timestamp, bars[-1].timestamp,
    )


class BreakoutOOSRunnerTests(unittest.TestCase):
    def test_split_is_single_predeclared_70_30_rule(self):
        result = split_and_validate(make_series())
        self.assertEqual(DEVELOPMENT_FRACTION, Decimal("0.70"))
        self.assertEqual(result.split_index, 210)
        self.assertEqual(result.total_bars, 300)

    def test_insufficient_history_fails_closed(self):
        with self.assertRaises(ValueError):
            split_and_validate(make_series(200))

    def test_oos_observations_exclude_warmup_signals(self):
        result = split_and_validate(make_series())
        oos_length = result.total_bars - result.split_index
        for observation in result.out_of_sample.observations:
            self.assertGreaterEqual(observation.signal_index, 50)
            self.assertLess(observation.signal_index, oos_length + 50)


if __name__ == "__main__":
    unittest.main()
