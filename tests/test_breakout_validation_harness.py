from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from market_data.foundation import MarketBar, MarketInstrument, MarketSeries
from research.breakout_validation import evaluate_entry, find_breakout_signals, modeled_entry_cost


def series(bars):
    instrument = MarketInstrument("SPY", "US_STOCK_OR_ETF", "USD")
    return MarketSeries(
        instrument=instrument,
        timeframe="1d",
        bars=tuple(bars),
        provider="TEST",
        source_reference="fixture",
        observed_at=bars[-1].timestamp,
        available_at=bars[-1].timestamp,
    )


def bar(day, o, h, l, c):
    return MarketBar(
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=day),
        open=Decimal(str(o)), high=Decimal(str(h)), low=Decimal(str(l)),
        close=Decimal(str(c)), volume=Decimal("1000000"),
    )


class BreakoutValidationHarnessTests(unittest.TestCase):
    def test_signal_bar_never_fills_itself_and_next_bar_can_trigger(self):
        bars = [bar(i, 100+i, 101+i, 99+i, 100+i) for i in range(51)]
        bars[50] = bar(50, 150, 155, 149, 154)
        bars += [bar(51, 154, 156, 153, 155), bar(52, 155, 157, 154, 156)]
        result = evaluate_entry(series(bars), 50, Decimal("149"))
        self.assertEqual(result.status, "FILLED")
        self.assertEqual(result.fill_index, 51)
        self.assertEqual(result.trigger_price, Decimal("155"))

    def test_gap_above_stop_trigger_fills_at_open_not_trigger(self):
        bars = [bar(i, 100, 101, 99, 100) for i in range(51)]
        bars[50] = bar(50, 100, 105, 99, 104)
        bars.append(bar(51, 110, 112, 109, 111))
        result = evaluate_entry(series(bars), 50, Decimal("100"))
        self.assertEqual(result.fill_price, Decimal("110"))

    def test_close_invalidation_before_trigger_cancels(self):
        bars = [bar(i, 100, 101, 99, 100) for i in range(51)]
        bars[50] = bar(50, 100, 105, 99, 104)
        bars.append(bar(51, 101, 104, 98, 99))
        result = evaluate_entry(series(bars), 50, Decimal("100"))
        self.assertEqual(result.status, "INVALIDATED_BEFORE_FILL")

    def test_same_daily_bar_trigger_and_close_invalidation_fails_closed(self):
        bars = [bar(i, 100, 101, 99, 100) for i in range(51)]
        bars[50] = bar(50, 100, 105, 99, 104)
        bars.append(bar(51, 104, 106, 98, 99))
        result = evaluate_entry(series(bars), 50, Decimal("100"))
        self.assertEqual(result.status, "AMBIGUOUS_NO_FILL")

    def test_exact_three_bar_expiry_is_fixed(self):
        bars = [bar(i, 100, 101, 99, 100) for i in range(55)]
        bars[50] = bar(50, 100, 105, 99, 104)
        for i in (51, 52, 53):
            bars[i] = bar(i, 102, 104, 101, 103)
        bars[54] = bar(54, 106, 107, 105, 106)
        result = evaluate_entry(series(bars), 50, Decimal("100"))
        self.assertEqual(result.status, "EXPIRED")
        with self.assertRaises(ValueError):
            evaluate_entry(series(bars), 50, Decimal("100"), expiry_bars=4)

    def test_existing_cost_assumptions_are_used_without_tuning(self):
        self.assertEqual(modeled_entry_cost(Decimal("100")), Decimal("0.06"))


if __name__ == "__main__":
    unittest.main()
