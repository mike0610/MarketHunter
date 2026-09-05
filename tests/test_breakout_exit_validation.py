from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from market_data.foundation import MarketBar, MarketInstrument, MarketSeries
from research.breakout_validation import BreakoutObservation, BreakoutValidationSummary
from research.run_breakout_exit_validation import simulate_filled_observations, summarize


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
        timeframe="1d",
        bars=bars,
        provider="TEST",
        source_reference="fixture",
        observed_at=bars[-1].timestamp,
        available_at=bars[-1].timestamp,
    )


def summary(fill_price="105", stop="100", fill_index=0):
    obs = BreakoutObservation(
        symbol="SPY",
        signal_index=0,
        signal_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        trigger_price=Decimal(fill_price),
        invalidation_price=Decimal(stop),
        status="FILLED",
        fill_price=Decimal(fill_price),
        fill_index=fill_index,
    )
    return BreakoutValidationSummary(
        signals=1,
        fills=1,
        expired=0,
        invalidated_before_fill=0,
        gap_entries=0,
        observations=(obs,),
    )


class BreakoutExitValidationTests(unittest.TestCase):
    def test_fixed_3r_target_uses_structural_stop(self):
        series = make_series([(105, 121, 104, 120)])
        trade = simulate_filled_observations(series, summary())[0]
        self.assertEqual(trade.stop, 100.0)
        self.assertEqual(trade.target, 120.0)
        self.assertEqual(trade.exit_reason, "target")

    def test_same_bar_stop_and_target_uses_existing_stop_first_policy(self):
        series = make_series([(105, 121, 99, 110)])
        trade = simulate_filled_observations(series, summary())[0]
        self.assertEqual(trade.exit_reason, "stop")
        self.assertTrue(trade.ambiguous_stop_target_bar)

    def test_no_exit_is_reported_unresolved_not_promoted_to_win(self):
        series = make_series([(105, 110, 102, 108), (108, 112, 103, 109)])
        trade = simulate_filled_observations(series, summary())[0]
        self.assertEqual(trade.exit_reason, "window_close")
        metrics = summarize((trade,))
        self.assertEqual(metrics.unresolved, 1)
        self.assertEqual(metrics.wins, 0)
        self.assertEqual(metrics.losses, 0)

    def test_invalid_structural_risk_fails_closed(self):
        series = make_series([(105, 110, 104, 108)])
        with self.assertRaises(ValueError):
            simulate_filled_observations(series, summary(fill_price="100", stop="100"))


if __name__ == "__main__":
    unittest.main()
