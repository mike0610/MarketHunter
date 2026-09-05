from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from market_data.foundation import MarketBar, MarketInstrument, MarketSeries
from research.breakout_validation import BreakoutObservation, BreakoutValidationSummary
from research.run_breakout_trend_exit_validation import simulate_filled_observations


def make_series(rows):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars = tuple(
        MarketBar(
            timestamp=start + timedelta(days=i),
            open=Decimal(str(o)),
            high=Decimal(str(h)),
            low=Decimal(str(l)),
            close=Decimal(str(c)),
            volume=Decimal("1000"),
        )
        for i, (o, h, l, c) in enumerate(rows)
    )
    return MarketSeries(
        instrument=MarketInstrument("SPY", "US_STOCK_OR_ETF", "USD"),
        timeframe="1d", bars=bars, provider="TEST", source_reference="fixture",
        observed_at=bars[-1].timestamp, available_at=bars[-1].timestamp,
    )


def filled(fill_index=19, fill="110", stop="100"):
    obs = BreakoutObservation(
        symbol="SPY", signal_index=18,
        signal_time=datetime(2026, 1, 19, tzinfo=timezone.utc),
        trigger_price=Decimal(fill), invalidation_price=Decimal(stop),
        status="FILLED", fill_price=Decimal(fill), fill_index=fill_index,
    )
    return BreakoutValidationSummary(1, 1, 0, 0, 0, (obs,))


class TrendExitTests(unittest.TestCase):
    def test_sma20_exit_only_after_fill_bar(self):
        rows = [(100, 112, 99, 110)] * 20
        rows += [(110, 111, 105, 105)]
        trade = simulate_filled_observations(make_series(rows), filled())[0]
        self.assertEqual(trade.exit_reason, "sma20_close")
        self.assertEqual(trade.holding_bars, 1)

    def test_structural_stop_wins_before_sma_exit(self):
        rows = [(100, 112, 101, 110)] * 20
        rows += [(99, 105, 95, 98)]
        trade = simulate_filled_observations(make_series(rows), filled())[0]
        self.assertEqual(trade.exit_reason, "structural_stop")
        self.assertTrue(trade.gap_stop)

    def test_missing_sma20_fails_closed(self):
        rows = [(100, 112, 101, 110)] * 10
        with self.assertRaises(ValueError):
            simulate_filled_observations(make_series(rows), filled(fill_index=8))


if __name__ == "__main__":
    unittest.main()
