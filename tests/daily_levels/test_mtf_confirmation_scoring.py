"""
MarketHunter

Tests for MTF Confirmation Bonus v1: a confirmed 1h entry context now
adds a small, capped +4 bonus to the daily signal's score via
DailyLevelsStrategy._apply_mtf_confirmation_bonus(), applied inside
analyze_with_entry_candles() after timestamp alignment and 1h
Confirmation Context v1 scoring. An unconfirmed, insufficient, or
otherwise non-confirming context never changes the score - there is
no penalty, only an optional bonus.
"""

from __future__ import annotations

import unittest
from datetime import timedelta

from strategies.daily_levels import DailyLevelsStrategy

from .helpers import build_candles, make_candle, make_snapshot
from .test_mtf_timestamp_alignment import entry_candle_at


def flat_candle(price: float, day_index: int):
    return make_candle(price, price + 0.05, price - 0.05, price, day_index)


class DailyLevelsMtfConfirmationScoringTests(unittest.IsolatedAsyncioTestCase):
    """
    Tests for MTF Confirmation Bonus v1.
    """

    def setUp(self) -> None:
        self.strategy = DailyLevelsStrategy()

    # -- confirmed patterns each get +4 -----------------------------

    async def test_confirmed_long_breakout_gets_bonus(self) -> None:
        signal_candle = make_candle(
            104.0, 106.5, 103.5, 106.0, day_index=61,
        )
        snapshot = make_snapshot(build_candles(signal_candle))

        plain_signal = await self.strategy.analyze(
            make_snapshot(build_candles(signal_candle)),
        )

        entry_candles = [
            flat_candle(104.8, day_index=100),
            make_candle(105.0, 105.5, 104.9, 105.3, day_index=101),
            flat_candle(105.3, day_index=102),
        ]

        signal = await self.strategy.analyze_with_entry_candles(
            snapshot, entry_candles=entry_candles,
        )

        self.assertIsNotNone(signal)
        self.assertTrue(
            signal.metadata["mtf_entry_confirmation_is_confirmed"],
        )
        self.assertEqual(signal.score, plain_signal.score + 4)
        self._assert_bonus_metadata(
            signal, plain_signal.score, 4.0, plain_signal.score + 4,
        )

    async def test_confirmed_short_breakdown_gets_bonus(self) -> None:
        signal_candle = make_candle(
            101.0, 101.5, 98.5, 99.0, day_index=61,
        )
        snapshot = make_snapshot(build_candles(signal_candle))

        plain_signal = await self.strategy.analyze(
            make_snapshot(build_candles(signal_candle)),
        )
        self.assertEqual(
            plain_signal.metadata["setup_type"], "daily_breakdown",
        )

        entry_candles = [
            flat_candle(100.2, day_index=100),
            make_candle(100.0, 100.05, 99.6, 99.7, day_index=101),
            flat_candle(99.7, day_index=102),
        ]

        signal = await self.strategy.analyze_with_entry_candles(
            snapshot, entry_candles=entry_candles,
        )

        self.assertIsNotNone(signal)
        self.assertTrue(
            signal.metadata["mtf_entry_confirmation_is_confirmed"],
        )
        self.assertEqual(signal.score, plain_signal.score + 4)
        self._assert_bonus_metadata(
            signal, plain_signal.score, 4.0, plain_signal.score + 4,
        )

    async def test_confirmed_bounce_gets_bonus(self) -> None:
        signal_candle = make_candle(
            99.9, 101.0, 99.9, 100.7, day_index=61,
        )
        snapshot = make_snapshot(build_candles(signal_candle))

        plain_signal = await self.strategy.analyze(
            make_snapshot(build_candles(signal_candle)),
        )
        self.assertEqual(
            plain_signal.metadata["setup_type"], "daily_support_bounce",
        )

        entry_candles = [
            flat_candle(100.5, day_index=100),
            make_candle(99.95, 100.40, 99.90, 100.30, day_index=101),
            flat_candle(100.30, day_index=102),
        ]

        signal = await self.strategy.analyze_with_entry_candles(
            snapshot, entry_candles=entry_candles,
        )

        self.assertIsNotNone(signal)
        self.assertTrue(
            signal.metadata["mtf_entry_confirmation_is_confirmed"],
        )
        self.assertEqual(signal.score, plain_signal.score + 4)
        self._assert_bonus_metadata(
            signal, plain_signal.score, 4.0, plain_signal.score + 4,
        )

    async def test_confirmed_false_break_reclaim_gets_bonus(self) -> None:
        signal_candle = make_candle(
            104.8, 106.5, 103.0, 103.5, day_index=61,
        )
        snapshot = make_snapshot(build_candles(signal_candle))

        plain_signal = await self.strategy.analyze(
            make_snapshot(build_candles(signal_candle)),
        )
        self.assertEqual(
            plain_signal.metadata["setup_type"],
            "daily_false_breakout_confirmed",
        )

        entry_candles = [
            flat_candle(105.1, day_index=100),
            make_candle(105.2, 105.3, 104.5, 104.7, day_index=101),
            flat_candle(104.7, day_index=102),
        ]

        signal = await self.strategy.analyze_with_entry_candles(
            snapshot, entry_candles=entry_candles,
        )

        self.assertIsNotNone(signal)
        self.assertTrue(
            signal.metadata["mtf_entry_confirmation_is_confirmed"],
        )
        self.assertEqual(signal.score, plain_signal.score + 4)
        self._assert_bonus_metadata(
            signal, plain_signal.score, 4.0, plain_signal.score + 4,
        )

    def _assert_bonus_metadata(
        self,
        signal,
        expected_base: float,
        expected_delta: float,
        expected_final: float,
    ) -> None:
        self.assertEqual(
            signal.metadata["mtf_entry_confirmation_policy_version"],
            "bonus_v1",
        )
        self.assertEqual(
            signal.metadata["mtf_entry_confirmation_base_score"],
            expected_base,
        )
        self.assertEqual(
            signal.metadata["mtf_entry_confirmation_score_delta"],
            expected_delta,
        )
        self.assertEqual(
            signal.metadata["mtf_entry_confirmation_final_score"],
            expected_final,
        )
        self.assertEqual(
            signal.metadata["mtf_entry_confirmation_applied"],
            expected_delta > 0,
        )

    # -- no bonus for weak / insufficient contexts -------------------

    async def test_weak_context_gives_zero_delta(self) -> None:
        signal_candle = make_candle(
            104.0, 106.5, 103.5, 106.0, day_index=61,
        )
        snapshot = make_snapshot(build_candles(signal_candle))

        plain_signal = await self.strategy.analyze(
            make_snapshot(build_candles(signal_candle)),
        )

        entry_candles = [
            flat_candle(104.8, day_index=100),
            # close < open - not a decisive LONG candle.
            make_candle(105.3, 105.6, 104.9, 105.1, day_index=101),
            flat_candle(105.1, day_index=102),
        ]

        signal = await self.strategy.analyze_with_entry_candles(
            snapshot, entry_candles=entry_candles,
        )

        self.assertIsNotNone(signal)
        self.assertFalse(
            signal.metadata["mtf_entry_confirmation_is_confirmed"],
        )
        self.assertEqual(signal.score, plain_signal.score)
        self._assert_bonus_metadata(
            signal, plain_signal.score, 0.0, plain_signal.score,
        )

    async def test_insufficient_data_gives_zero_delta(self) -> None:
        signal_candle = make_candle(
            104.0, 106.5, 103.5, 106.0, day_index=61,
        )
        snapshot = make_snapshot(build_candles(signal_candle))

        plain_signal = await self.strategy.analyze(
            make_snapshot(build_candles(signal_candle)),
        )

        entry_candles = [
            flat_candle(104.8, day_index=100),
            flat_candle(105.0, day_index=101),
        ]

        signal = await self.strategy.analyze_with_entry_candles(
            snapshot, entry_candles=entry_candles,
        )

        self.assertIsNotNone(signal)
        self.assertEqual(
            signal.metadata["mtf_entry_confirmation_type"],
            "insufficient_data",
        )
        self.assertEqual(signal.score, plain_signal.score)
        self._assert_bonus_metadata(
            signal, plain_signal.score, 0.0, plain_signal.score,
        )

    # -- score cap and the applied/confirmed distinction --------------

    def test_score_never_exceeds_one_hundred(self) -> None:
        score_delta, final_score, applied = (
            self.strategy._apply_mtf_confirmation_bonus(98.0, True)
        )

        self.assertEqual(score_delta, 4.0)
        self.assertEqual(final_score, 100.0)
        self.assertTrue(applied)

    def test_applied_is_false_when_already_at_cap_despite_confirmed(
        self,
    ) -> None:
        """
        mtf_entry_confirmation_applied means "the bonus actually
        changed the score", not merely "confirmation was observed".
        A base_score already at the 100 cap (unreachable by any
        current setup's own scoring, but not assumed impossible)
        leaves final_score == base_score even when is_confirmed=True.
        """

        score_delta, final_score, applied = (
            self.strategy._apply_mtf_confirmation_bonus(100.0, True)
        )

        self.assertEqual(score_delta, 4.0)
        self.assertEqual(final_score, 100.0)
        self.assertFalse(applied)

    def test_unconfirmed_never_applies_a_bonus(self) -> None:
        score_delta, final_score, applied = (
            self.strategy._apply_mtf_confirmation_bonus(76.0, False)
        )

        self.assertEqual(score_delta, 0.0)
        self.assertEqual(final_score, 76.0)
        self.assertFalse(applied)

    # -- direction / setup_type / reasons stay untouched --------------

    async def test_confirmed_bonus_does_not_change_direction_setup_or_reasons(
        self,
    ) -> None:
        signal_candle = make_candle(
            104.0, 106.5, 103.5, 106.0, day_index=61,
        )
        snapshot = make_snapshot(build_candles(signal_candle))

        plain_signal = await self.strategy.analyze(
            make_snapshot(build_candles(signal_candle)),
        )

        entry_candles = [
            flat_candle(104.8, day_index=100),
            make_candle(105.0, 105.5, 104.9, 105.3, day_index=101),
            flat_candle(105.3, day_index=102),
        ]

        signal = await self.strategy.analyze_with_entry_candles(
            snapshot, entry_candles=entry_candles,
        )

        self.assertIsNotNone(signal)
        self.assertNotEqual(signal.score, plain_signal.score)
        self.assertEqual(signal.direction, plain_signal.direction)
        self.assertEqual(
            signal.metadata["setup_type"],
            plain_signal.metadata["setup_type"],
        )
        self.assertEqual(signal.reasons, plain_signal.reasons)

    # -- the time machine lock, once more, at the scoring layer -------

    async def test_old_preclose_candles_cannot_earn_a_bonus(self) -> None:
        """
        A perfect pre-close breakout_close pair must not earn the
        bonus just because it would occupy entry_candles[-2]/[-3] by
        raw list position - timestamp alignment removes it before
        confirmation (and therefore scoring) ever sees it.
        """

        signal_candle = make_candle(
            104.0, 106.5, 103.5, 106.0, day_index=61,
        )
        snapshot = make_snapshot(build_candles(signal_candle))
        daily_close_time = snapshot.candles[-2].close_time

        plain_signal = await self.strategy.analyze(
            make_snapshot(build_candles(signal_candle)),
        )

        stale_previous = entry_candle_at(
            daily_close_time - timedelta(hours=3),
            open_price=104.8, high=104.85, low=104.75, close=104.8,
        )
        stale_last = entry_candle_at(
            daily_close_time - timedelta(hours=2),
            open_price=105.0, high=105.5, low=104.9, close=105.3,
        )

        signal = await self.strategy.analyze_with_entry_candles(
            snapshot,
            entry_candles=[stale_previous, stale_last],
        )

        self.assertIsNotNone(signal)
        self.assertEqual(
            signal.metadata["mtf_entry_confirmation_type"],
            "insufficient_data",
        )
        self.assertFalse(
            signal.metadata["mtf_entry_confirmation_is_confirmed"],
        )
        self.assertFalse(
            signal.metadata["mtf_entry_confirmation_applied"],
        )
        self.assertEqual(signal.score, plain_signal.score)

    # -- no signal, no scoring metadata --------------------------------

    async def test_no_signal_does_not_create_scoring_metadata(self) -> None:
        signal = await self.strategy.analyze_with_entry_candles(
            make_snapshot([]),
            entry_candles=[
                flat_candle(100.0, day_index=0),
            ],
        )

        self.assertIsNone(signal)


if __name__ == "__main__":
    unittest.main()
