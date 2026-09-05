from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from market_data.foundation import MarketBar, MarketInstrument, MarketSeries
from research.validation_core import ValidationSpec, chronological_split, validate_chronologically


def make_series(n=300):
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    bars = tuple(
        MarketBar(
            timestamp=start + timedelta(days=i),
            open=Decimal("100"), high=Decimal("101"), low=Decimal("99"),
            close=Decimal("100"), volume=Decimal("1000"),
        )
        for i in range(n)
    )
    return MarketSeries(
        MarketInstrument("SPY", "US_STOCK_OR_ETF", "USD"), "1d", bars,
        "TEST", "fixture", bars[-1].timestamp, bars[-1].timestamp,
    )


class ValidationCoreTests(unittest.TestCase):
    def test_default_split_is_fixed_70_30_with_50_bar_oos_warmup(self):
        split = chronological_split(make_series())
        self.assertEqual(split.development_end, 210)
        self.assertEqual(split.oos_start, 160)
        self.assertEqual(split.warmup_bars, 50)

    def test_insufficient_history_fails_closed(self):
        with self.assertRaises(ValueError):
            chronological_split(make_series(200))

    def test_core_is_strategy_agnostic_and_filters_warmup(self):
        def evaluator(series):
            return tuple(range(len(series.bars)))

        def filter_oos(values, warmup):
            return tuple(v for v in values if v >= warmup)

        result = validate_chronologically(make_series(), evaluator, filter_oos=filter_oos)
        self.assertEqual(len(result.development), 210)
        self.assertEqual(result.out_of_sample[0], 50)

    def test_invalid_specs_fail_closed(self):
        with self.assertRaises(ValueError):
            ValidationSpec(development_fraction=Decimal("1"))
        with self.assertRaises(ValueError):
            ValidationSpec(minimum_bars=50, warmup_bars=50)


if __name__ == "__main__":
    unittest.main()
