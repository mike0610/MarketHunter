"""
MarketHunter

Tests for backtesting/execution_policy.py - the smallest
execution-realism baseline (AGGRESSIVE_TAKER vs PASSIVE_MAKER_SIMPLE),
kept explicitly separate from StrategyVersion signal logic. Also
covers backtesting/trade_simulator.py's resolve_exit() extraction,
proving the refactor is behavior-identical to the original inline
scan loop.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from backtesting.execution_policy import (
    EvidenceLevel,
    ExecutionMode,
    FillOutcome,
    attempt_aggressive_taker_entry,
    attempt_passive_maker_entry,
    compute_post_fill_markout,
    summarize_execution_policy,
)
from backtesting.trade_simulator import ExecutionAssumptions, TradeSimulator, resolve_exit
from models.candle import Candle
from models.position import Position


def _candle(open_=100.0, high=100.0, low=100.0, close=100.0) -> Candle:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return Candle(
        open_time=now,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=1000.0,
        close_time=now,
        quote_volume=1000.0,
        trades=10,
        taker_buy_base_volume=500.0,
        taker_buy_quote_volume=500.0,
    )


def _position(side="LONG", entry=100.0, stop=95.0, target=110.0, quantity=1.0) -> Position:
    return Position(
        symbol="BTCUSDT",
        market="FUTURES",
        side=side,
        quantity=quantity,
        entry=entry,
        stop_loss=stop,
        take_profit=target,
        opened_at=0.0,
        current_price=entry,
    )


class ResolveExitParityTests(unittest.TestCase):
    """resolve_exit() must reproduce TradeSimulator's own original inline behavior exactly."""

    def test_matches_trade_simulator_long_target_hit(self):
        position = _position(side="LONG")
        candles = [_candle(100, 105, 99, 102), _candle(102, 111, 101, 110)]
        via_simulator = TradeSimulator().long(position, candles)
        raw_exit, offset, reason = resolve_exit("LONG", position.stop_loss, position.take_profit, candles)
        self.assertEqual((raw_exit, offset, reason), (110.0, 1, "target"))
        self.assertEqual(via_simulator.exit_offset, offset)
        self.assertEqual(via_simulator.exit_reason, reason)

    def test_matches_trade_simulator_short_stop_hit(self):
        position = _position(side="SHORT", entry=100.0, stop=105.0, target=90.0)
        candles = [_candle(100, 106, 99, 101)]
        via_simulator = TradeSimulator().short(position, candles)
        raw_exit, offset, reason = resolve_exit("SHORT", position.stop_loss, position.take_profit, candles)
        self.assertEqual((raw_exit, offset, reason), (105.0, 0, "stop"))
        self.assertEqual(via_simulator.exit_reason, reason)

    def test_ambiguous_candle_defaults_to_stop_first(self):
        position = _position(side="LONG", entry=100.0, stop=95.0, target=110.0)
        candles = [_candle(100, 112, 94, 105)]  # both stop and target touched on the same bar
        raw_exit, offset, reason = resolve_exit("LONG", position.stop_loss, position.take_profit, candles)
        self.assertEqual(reason, "stop")

    def test_target_first_policy_is_honored(self):
        raw_exit, offset, reason = resolve_exit(
            "LONG", 95.0, 110.0, [_candle(100, 112, 94, 105)], ambiguous_candle_policy="target_first"
        )
        self.assertEqual(reason, "target")

    def test_falls_through_to_window_close(self):
        candles = [_candle(100, 101, 99, 100.5)]
        raw_exit, offset, reason = resolve_exit("LONG", 50.0, 200.0, candles)
        self.assertEqual((raw_exit, offset, reason), (100.5, 0, "window_close"))

    def test_raises_on_empty_candles(self):
        with self.assertRaises(ValueError):
            resolve_exit("LONG", 95.0, 110.0, [])

    def test_raises_on_unsupported_policy(self):
        with self.assertRaises(ValueError):
            resolve_exit("LONG", 95.0, 110.0, [_candle()], ambiguous_candle_policy="worst_first")


class AggressiveTakerEntryTests(unittest.TestCase):
    def test_always_fills_and_matches_trade_simulator_numbers_exactly(self):
        position = _position(side="LONG")
        candles = [_candle(100, 105, 99, 102), _candle(102, 111, 101, 110)]
        assumptions = ExecutionAssumptions()

        attempt = attempt_aggressive_taker_entry(position, candles, assumptions)
        reference = TradeSimulator(assumptions).long(position, candles)

        self.assertEqual(attempt.mode, ExecutionMode.AGGRESSIVE_TAKER)
        self.assertEqual(attempt.outcome, FillOutcome.FULL_FILL)
        self.assertEqual(attempt.evidence_level, EvidenceLevel.OHLC)
        self.assertEqual(attempt.filled_quantity, position.quantity)
        self.assertEqual(attempt.residual_quantity, 0.0)
        self.assertEqual(attempt.simulation, reference)

    def test_execution_blocked_on_no_candle_evidence(self):
        attempt = attempt_aggressive_taker_entry(_position(), [])
        self.assertEqual(attempt.outcome, FillOutcome.EXECUTION_BLOCKED)
        self.assertIsNone(attempt.simulation)
        self.assertEqual(attempt.residual_quantity, 1.0)


class PassiveMakerEntryTests(unittest.TestCase):
    def test_long_fills_only_when_the_entry_candle_trades_through_the_limit(self):
        position = _position(side="LONG", entry=100.0)
        entry_candle = _candle(101, 102, 99.99, 100.5)  # low < 100 -> traded through
        attempt = attempt_passive_maker_entry(position, entry_candle, [entry_candle, _candle(100.5, 111, 100, 110)])
        self.assertEqual(attempt.outcome, FillOutcome.FULL_FILL)
        self.assertEqual(attempt.mode, ExecutionMode.PASSIVE_MAKER_SIMPLE)

    def test_long_does_not_fill_on_exact_touch_only(self):
        position = _position(side="LONG", entry=100.0)
        entry_candle = _candle(101, 102, 100.0, 101.0)  # low == 100, touch only, not through
        attempt = attempt_passive_maker_entry(position, entry_candle, [entry_candle])
        self.assertEqual(attempt.outcome, FillOutcome.NO_FILL)
        self.assertIsNone(attempt.simulation)
        self.assertEqual(attempt.filled_quantity, 0.0)
        self.assertEqual(attempt.residual_quantity, position.quantity)

    def test_long_does_not_fill_when_price_never_approaches_the_limit(self):
        position = _position(side="LONG", entry=100.0)
        entry_candle = _candle(105, 106, 104, 105.5)  # never gets near 100
        attempt = attempt_passive_maker_entry(position, entry_candle, [entry_candle])
        self.assertEqual(attempt.outcome, FillOutcome.NO_FILL)

    def test_short_fills_only_when_the_entry_candle_trades_through_the_limit(self):
        position = _position(side="SHORT", entry=100.0, stop=105.0, target=90.0)
        entry_candle = _candle(99, 100.01, 98, 99.5)  # high > 100 -> traded through
        attempt = attempt_passive_maker_entry(position, entry_candle, [entry_candle, _candle(99.5, 99.6, 89, 90)])
        self.assertEqual(attempt.outcome, FillOutcome.FULL_FILL)

    def test_short_does_not_fill_on_exact_touch_only(self):
        position = _position(side="SHORT", entry=100.0, stop=105.0, target=90.0)
        entry_candle = _candle(99, 100.0, 98, 99.5)  # high == 100, touch only
        attempt = attempt_passive_maker_entry(position, entry_candle, [entry_candle])
        self.assertEqual(attempt.outcome, FillOutcome.NO_FILL)

    def test_a_maker_fill_never_incurs_adverse_entry_slippage(self):
        position = _position(side="LONG", entry=100.0, stop=95.0, target=110.0)
        entry_candle = _candle(101, 102, 99.0, 101.5)
        assumptions = ExecutionAssumptions(slippage_bps_per_side=50.0)  # deliberately large, would be obvious if misapplied
        attempt = attempt_passive_maker_entry(position, entry_candle, [entry_candle, _candle(101.5, 111, 101, 110)], assumptions)
        self.assertEqual(attempt.simulation.entry_fill, 100.0)  # exact resting price, no slippage

    def test_a_maker_fill_still_incurs_adverse_exit_slippage_on_the_exit_leg(self):
        position = _position(side="LONG", entry=100.0, stop=95.0, target=110.0)
        entry_candle = _candle(101, 102, 99.0, 101.5)
        assumptions = ExecutionAssumptions(slippage_bps_per_side=50.0)
        attempt = attempt_passive_maker_entry(position, entry_candle, [entry_candle, _candle(101.5, 111, 101, 110)], assumptions)
        expected_exit_fill = 110.0 * (1.0 - 50.0 / 10_000.0)
        self.assertAlmostEqual(attempt.simulation.exit_fill, expected_exit_fill)

    def test_execution_blocked_when_filled_but_no_remaining_candles(self):
        position = _position(side="LONG", entry=100.0)
        entry_candle = _candle(101, 102, 99.0, 101.5)
        attempt = attempt_passive_maker_entry(position, entry_candle, [])
        self.assertEqual(attempt.outcome, FillOutcome.EXECUTION_BLOCKED)
        self.assertIsNone(attempt.simulation)

    def test_never_produces_partial_fill_across_a_range_of_inputs(self):
        # No L2/queue evidence exists anywhere in this repo - this
        # OHLC-only baseline must never fabricate a partial-fill
        # outcome. Exercised across several distinct scenarios rather
        # than asserted from reading the code alone.
        scenarios = [
            (_position(side="LONG", entry=100.0), _candle(101, 102, 99.99, 101.0), True),
            (_position(side="LONG", entry=100.0), _candle(101, 102, 100.5, 101.0), False),
            (_position(side="SHORT", entry=100.0, stop=105.0, target=90.0), _candle(99, 100.5, 98, 99.5), True),
            (_position(side="SHORT", entry=100.0, stop=105.0, target=90.0), _candle(99, 99.5, 98, 99.2), False),
        ]
        for position, entry_candle, has_remaining in scenarios:
            remaining = [entry_candle, _candle(99, 111, 89, 100)] if has_remaining else [entry_candle]
            attempt = attempt_passive_maker_entry(position, entry_candle, remaining)
            self.assertNotEqual(attempt.outcome, FillOutcome.PARTIAL_FILL)


class SummarizeExecutionPolicyTests(unittest.TestCase):
    def test_counts_and_fill_ratio_across_mixed_outcomes(self):
        full = attempt_aggressive_taker_entry(_position(), [_candle(100, 105, 99, 102), _candle(102, 111, 101, 110)])
        blocked = attempt_aggressive_taker_entry(_position(), [])
        summary = summarize_execution_policy([full, blocked])

        self.assertEqual(summary.attempted, 2)
        self.assertEqual(summary.full_fill, 1)
        self.assertEqual(summary.blocked, 1)
        self.assertEqual(summary.no_fill, 0)
        self.assertEqual(summary.partial_fill, 0)
        self.assertAlmostEqual(summary.fill_ratio, 0.5)

    def test_a_no_fill_contributes_zero_to_pnl_never_a_realized_trade(self):
        position = _position(side="LONG", entry=100.0)
        no_fill = attempt_passive_maker_entry(position, _candle(105, 106, 104, 105.5), [])
        summary = summarize_execution_policy([no_fill])
        self.assertEqual(summary.gross_pnl, 0.0)
        self.assertEqual(summary.net_pnl, 0.0)
        self.assertEqual(summary.total_fees, 0.0)

    def test_raises_on_empty_results(self):
        with self.assertRaises(ValueError):
            summarize_execution_policy([])

    def test_raises_when_results_mix_modes(self):
        aggressive = attempt_aggressive_taker_entry(_position(), [_candle(100, 105, 99, 102), _candle(102, 111, 101, 110)])
        passive = attempt_passive_maker_entry(_position(entry=100.0), _candle(101, 102, 99.0, 101.5), [_candle(101, 102, 99.0, 101.5), _candle(101.5, 111, 101, 110)])
        with self.assertRaises(ValueError):
            summarize_execution_policy([aggressive, passive])


class PostFillMarkoutTests(unittest.TestCase):
    def test_long_positive_markout_when_price_moves_favorably(self):
        candles = [_candle(close=101.0), _candle(close=103.0)]
        markout = compute_post_fill_markout("LONG", fill_price=100.0, candles_after_fill=candles, horizon_bars=2)
        self.assertAlmostEqual(markout, 3.0)

    def test_long_negative_markout_when_price_moves_adversely(self):
        candles = [_candle(close=99.0)]
        markout = compute_post_fill_markout("LONG", fill_price=100.0, candles_after_fill=candles, horizon_bars=1)
        self.assertAlmostEqual(markout, -1.0)

    def test_short_positive_markout_when_price_falls(self):
        candles = [_candle(close=97.0)]
        markout = compute_post_fill_markout("SHORT", fill_price=100.0, candles_after_fill=candles, horizon_bars=1)
        self.assertAlmostEqual(markout, 3.0)

    def test_returns_none_needs_data_when_horizon_exceeds_available_candles(self):
        markout = compute_post_fill_markout("LONG", fill_price=100.0, candles_after_fill=[_candle()], horizon_bars=5)
        self.assertIsNone(markout)

    def test_rejects_a_non_positive_horizon(self):
        with self.assertRaises(ValueError):
            compute_post_fill_markout("LONG", 100.0, [_candle()], horizon_bars=0)


if __name__ == "__main__":
    unittest.main()
