"""
MarketHunter

Tests for Timestamp alignment v1: DailyLevelsStrategy discards any
entry-timeframe (1h) candle whose open_time is not strictly after the
daily signal candle's own close_time (snapshot.candles[-2].close_time)
before anything else - including 1h Confirmation Context v1 scoring -
ever sees it.

This closes the gap left by 1h Confirmation Context v1: without
alignment, entry_candles[-2]/[-3] were read by raw list position only,
with no guarantee those candles actually opened after the daily setup
they are supposed to confirm.
"""

from __future__ import annotations

import unittest
from datetime import timedelta

from models.candle import Candle
from strategies.daily_levels import DailyLevelsStrategy

from .helpers import RESISTANCE, build_candles, make_candle, make_snapshot


def entry_candle_at(
    open_time,
    open_price: float = 100.0,
    high: float | None = None,
    low: float | None = None,
    close: float | None = None,
) -> Candle:
    """
    Build a 1h-shaped entry candle at an exact open_time, independent
    of helpers.make_candle's day-granularity day_index parameter -
    boundary tests here need sub-day precision relative to the daily
    signal candle's own close_time.
    """

    return Candle(
        open_time=open_time,
        open=open_price,
        high=high if high is not None else open_price + 0.5,
        low=low if low is not None else open_price - 0.5,
        close=close if close is not None else open_price + 0.2,
        volume=1000.0,
        close_time=open_time + timedelta(hours=1) - timedelta(seconds=1),
        quote_volume=100000.0,
        trades=100,
        taker_buy_base_volume=500.0,
        taker_buy_quote_volume=50000.0,
    )


class DailyLevelsMtfTimestampAlignmentTests(unittest.IsolatedAsyncioTestCase):
    """
    Tests for Timestamp alignment v1.
    """

    RESISTANCE = RESISTANCE

    def setUp(self) -> None:
        self.strategy = DailyLevelsStrategy()

        self.breakout_signal_candle = make_candle(
            104.0, 106.5, 103.5, 106.0, day_index=61,
        )
        self.snapshot = make_snapshot(
            build_candles(self.breakout_signal_candle),
        )
        # The exact boundary the strategy itself uses -
        # snapshot.candles[-2].close_time - not a re-derived/synthesized
        # value, so these tests exercise the real production boundary.
        self.daily_close_time = self.snapshot.candles[-2].close_time

    # -- pure filter: _entry_candles_after_daily_close() -----------

    def test_candle_before_daily_close_is_discarded(self) -> None:
        before = entry_candle_at(
            self.daily_close_time - timedelta(hours=1),
        )

        result = self.strategy._entry_candles_after_daily_close(
            [before], self.daily_close_time,
        )

        self.assertEqual(result, [])

    def test_candle_exactly_at_daily_close_is_discarded(self) -> None:
        """
        The boundary itself belongs to the daily candle, not to the
        following entry candle - strict >, not >=. In real production
        data this exact tie is unreachable (a millisecond gap always
        separates a daily close_time from the next hourly open_time),
        but the strict-> rule is verified directly here regardless.
        """

        at_boundary = entry_candle_at(self.daily_close_time)

        result = self.strategy._entry_candles_after_daily_close(
            [at_boundary], self.daily_close_time,
        )

        self.assertEqual(result, [])

    def test_candle_after_daily_close_is_kept(self) -> None:
        after = entry_candle_at(
            self.daily_close_time + timedelta(hours=1),
        )

        result = self.strategy._entry_candles_after_daily_close(
            [after], self.daily_close_time,
        )

        self.assertEqual(result, [after])

    def test_mixed_list_filtered_per_element_preserving_order(
        self,
    ) -> None:
        """
        The filter discards each stale candle individually rather
        than truncating a prefix/suffix of the list, and preserves
        the relative order of the candles that survive.
        """

        before_1 = entry_candle_at(
            self.daily_close_time - timedelta(hours=3),
        )
        after_1 = entry_candle_at(
            self.daily_close_time + timedelta(hours=1),
        )
        before_2 = entry_candle_at(
            self.daily_close_time - timedelta(hours=2),
        )
        after_2 = entry_candle_at(
            self.daily_close_time + timedelta(hours=2),
        )
        after_3 = entry_candle_at(
            self.daily_close_time + timedelta(hours=3),
        )

        result = self.strategy._entry_candles_after_daily_close(
            [before_1, after_1, before_2, after_2, after_3],
            self.daily_close_time,
        )

        self.assertEqual(result, [after_1, after_2, after_3])

    # -- full pipeline: analyze_with_entry_candles() ----------------

    async def test_old_candles_cannot_create_confirmation(self) -> None:
        """
        The time machine lock. Stale pre-close entry candles form a
        textbook-perfect breakout_close (decisive close clearing the
        0.05% threshold, previous candle still closed at/below the
        level) - if alignment did not discard them, this would
        confirm. The only entry candles that actually opened after
        the daily close are weak, so the real result must be
        is_confirmed=False.
        """

        stale_previous = entry_candle_at(
            self.daily_close_time - timedelta(hours=3),
            open_price=104.8,
            high=104.85,
            low=104.75,
            close=104.8,
        )
        stale_last = entry_candle_at(
            self.daily_close_time - timedelta(hours=2),
            open_price=105.0,
            high=105.5,
            low=104.9,
            close=105.3,
        )

        weak_previous = entry_candle_at(
            self.daily_close_time + timedelta(hours=1),
            open_price=104.8,
            high=104.85,
            low=104.75,
            close=104.8,
        )
        weak_last = entry_candle_at(
            self.daily_close_time + timedelta(hours=2),
            open_price=105.3,
            high=105.6,
            low=104.9,
            close=105.1,
        )
        trailing_unclosed = entry_candle_at(
            self.daily_close_time + timedelta(hours=3),
            open_price=105.1,
            high=105.2,
            low=105.0,
            close=105.15,
        )

        entry_candles = [
            stale_previous,
            stale_last,
            weak_previous,
            weak_last,
            trailing_unclosed,
        ]

        signal = await self.strategy.analyze_with_entry_candles(
            self.snapshot, entry_candles=entry_candles,
        )

        self.assertIsNotNone(signal)
        self.assertFalse(
            signal.metadata["mtf_entry_confirmation_is_confirmed"],
        )
        self.assertEqual(
            signal.metadata["mtf_entry_aligned_candle_count"], 3,
        )
        self.assertEqual(
            signal.metadata["mtf_entry_discarded_candle_count"], 2,
        )

    async def test_fewer_than_three_after_alignment_is_insufficient_data(
        self,
    ) -> None:
        """
        Two entry candles survive alignment but a third
        (entry_candles[-3]) never arrives - insufficient_data, exactly
        as when the raw list itself was short, just evaluated on the
        aligned list instead of the raw one.
        """

        entry_candles = [
            entry_candle_at(
                self.daily_close_time - timedelta(hours=1),
            ),
            entry_candle_at(
                self.daily_close_time + timedelta(hours=1),
            ),
            entry_candle_at(
                self.daily_close_time + timedelta(hours=2),
            ),
        ]

        signal = await self.strategy.analyze_with_entry_candles(
            self.snapshot, entry_candles=entry_candles,
        )

        self.assertIsNotNone(signal)
        self.assertEqual(
            signal.metadata["mtf_entry_aligned_candle_count"], 2,
        )
        self.assertEqual(
            signal.metadata["mtf_entry_confirmation_type"],
            "insufficient_data",
        )
        self.assertFalse(
            signal.metadata["mtf_entry_confirmation_is_confirmed"],
        )

    async def test_raw_aligned_and_discarded_counts_are_correct(
        self,
    ) -> None:
        entry_candles = [
            entry_candle_at(
                self.daily_close_time - timedelta(hours=2),
            ),
            entry_candle_at(
                self.daily_close_time - timedelta(hours=1),
            ),
            entry_candle_at(
                self.daily_close_time + timedelta(hours=1),
            ),
            entry_candle_at(
                self.daily_close_time + timedelta(hours=2),
            ),
            entry_candle_at(
                self.daily_close_time + timedelta(hours=3),
            ),
        ]

        signal = await self.strategy.analyze_with_entry_candles(
            self.snapshot, entry_candles=entry_candles,
        )

        self.assertIsNotNone(signal)
        self.assertEqual(
            signal.metadata["mtf_entry_raw_candle_count"], 5,
        )
        self.assertEqual(
            signal.metadata["mtf_entry_aligned_candle_count"], 3,
        )
        self.assertEqual(
            signal.metadata["mtf_entry_discarded_candle_count"], 2,
        )
        self.assertEqual(
            signal.metadata["mtf_entry_alignment_version"], "v1",
        )
        self.assertTrue(
            signal.metadata["mtf_entry_alignment_applied"],
        )

    async def test_entry_candle_count_and_data_available_reflect_alignment(
        self,
    ) -> None:
        """
        mtf_entry_candle_count / mtf_entry_data_available (the
        pre-existing MTF data contract v1 fields) now describe the
        ALIGNED candles, not the raw list that was passed in.
        """

        entry_candles = [
            entry_candle_at(
                self.daily_close_time - timedelta(hours=1),
            ),
            entry_candle_at(
                self.daily_close_time - timedelta(minutes=30),
            ),
        ]

        signal = await self.strategy.analyze_with_entry_candles(
            self.snapshot, entry_candles=entry_candles,
        )

        self.assertIsNotNone(signal)
        self.assertEqual(signal.metadata["mtf_entry_raw_candle_count"], 2)
        self.assertEqual(signal.metadata["mtf_entry_candle_count"], 0)
        self.assertFalse(signal.metadata["mtf_entry_data_available"])

    async def test_timestamp_metadata_fields_are_iso_strings(self) -> None:
        entry_candles = [
            entry_candle_at(
                self.daily_close_time + timedelta(hours=1),
                open_price=104.8,
                high=104.85,
                low=104.75,
                close=104.8,
            ),
            entry_candle_at(
                self.daily_close_time + timedelta(hours=2),
                open_price=105.0,
                high=105.5,
                low=104.9,
                close=105.3,
            ),
            entry_candle_at(
                self.daily_close_time + timedelta(hours=3),
            ),
        ]

        signal = await self.strategy.analyze_with_entry_candles(
            self.snapshot, entry_candles=entry_candles,
        )

        self.assertIsNotNone(signal)
        self.assertIsInstance(
            signal.metadata["mtf_daily_signal_close_time"], str,
        )
        self.assertEqual(
            signal.metadata["mtf_daily_signal_close_time"],
            self.daily_close_time.isoformat(),
        )
        self.assertIsInstance(
            signal.metadata["mtf_entry_confirmation_candle_open_time"],
            str,
        )

    async def test_alignment_does_not_change_direction_score_or_reasons(
        self,
    ) -> None:
        plain_signal = await self.strategy.analyze(
            make_snapshot(build_candles(self.breakout_signal_candle)),
        )

        entry_candles = [
            entry_candle_at(
                self.daily_close_time - timedelta(hours=1),
            ),
            entry_candle_at(
                self.daily_close_time + timedelta(hours=1),
                open_price=105.0,
                high=105.5,
                low=104.9,
                close=105.3,
            ),
            entry_candle_at(
                self.daily_close_time + timedelta(hours=2),
            ),
        ]

        mtf_signal = await self.strategy.analyze_with_entry_candles(
            self.snapshot, entry_candles=entry_candles,
        )

        self.assertIsNotNone(plain_signal)
        self.assertIsNotNone(mtf_signal)
        self.assertEqual(mtf_signal.direction, plain_signal.direction)
        self.assertEqual(mtf_signal.score, plain_signal.score)
        self.assertEqual(
            mtf_signal.metadata["setup_type"],
            plain_signal.metadata["setup_type"],
        )
        self.assertEqual(mtf_signal.reasons, plain_signal.reasons)

    async def test_no_signal_does_not_create_alignment_metadata(
        self,
    ) -> None:
        signal = await self.strategy.analyze_with_entry_candles(
            make_snapshot([]),
            entry_candles=[
                entry_candle_at(
                    self.daily_close_time + timedelta(hours=1),
                ),
            ],
        )

        self.assertIsNone(signal)


if __name__ == "__main__":
    unittest.main()
