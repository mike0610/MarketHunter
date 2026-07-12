"""
MarketHunter

Tests for MTF data contract v1: DailyLevelsStrategy.analyze_with_entry_candles()
observationally attaches entry-timeframe (1h) candle metadata to
whatever analyze() would have produced, without changing the
underlying signal.
"""

from __future__ import annotations

import unittest

from strategies.daily_levels import DailyLevelsStrategy

from .helpers import build_candles, make_candle, make_snapshot


class DailyLevelsMtfContractTests(unittest.IsolatedAsyncioTestCase):
    """
    Tests for MTF data contract v1 (observation-only).

    analyze_with_entry_candles() always defers to analyze() for
    direction/score/setup_type/reasons - it only adds mtf_* metadata
    describing the entry-timeframe candles that arrived alongside the
    primary 1D snapshot. No entry-timeframe trading logic exists yet.
    """

    def setUp(self) -> None:
        self.strategy = DailyLevelsStrategy()

    def test_entry_timeframe_and_candle_limit_are_configured(
        self,
    ) -> None:
        """
        DailyLevelsStrategy declares the MTF data contract v1 hook
        via entry_timeframe/entry_candle_limit class attributes.
        """

        self.assertEqual(self.strategy.entry_timeframe, "1h")
        self.assertEqual(self.strategy.entry_candle_limit, 200)

    async def test_returns_same_setup_score_and_direction_as_analyze(
        self,
    ) -> None:
        """
        A firing breakout signal from analyze_with_entry_candles()
        matches direction, score, setup_type, and reasons of a plain
        analyze() call on the same snapshot exactly.
        """

        signal_candle = make_candle(
            104.0, 106.5, 103.5, 106.0, day_index=61,
        )

        candles = build_candles(signal_candle)

        plain_signal = await self.strategy.analyze(
            make_snapshot(candles),
        )

        entry_candles = [
            make_candle(100.0, 100.5, 99.5, 100.2, day_index=i)
            for i in range(24)
        ]

        mtf_signal = await self.strategy.analyze_with_entry_candles(
            make_snapshot(candles),
            entry_candles=entry_candles,
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

    async def test_metadata_reports_entry_timeframe_and_candle_count(
        self,
    ) -> None:
        """
        A firing signal's metadata reports the MTF contract fields:
        version, primary/entry timeframe labels, and the exact number
        of entry candles that were passed in.
        """

        signal_candle = make_candle(
            104.0, 106.5, 103.5, 106.0, day_index=61,
        )

        candles = build_candles(signal_candle)

        entry_candles = [
            make_candle(100.0, 100.5, 99.5, 100.2, day_index=i)
            for i in range(37)
        ]

        signal = await self.strategy.analyze_with_entry_candles(
            make_snapshot(candles),
            entry_candles=entry_candles,
        )

        self.assertIsNotNone(signal)
        self.assertEqual(signal.metadata["mtf_context_version"], "v1")
        self.assertEqual(
            signal.metadata["mtf_primary_timeframe"], "1d",
        )
        self.assertEqual(signal.metadata["mtf_entry_timeframe"], "1h")
        self.assertEqual(
            signal.metadata["mtf_entry_candle_count"], 37,
        )
        self.assertTrue(signal.metadata["mtf_entry_data_available"])
        self.assertFalse(
            signal.metadata["mtf_entry_confirmation_applied"],
        )

    async def test_empty_entry_candles_does_not_raise_and_reports_unavailable(
        self,
    ) -> None:
        """
        A successfully loaded but empty entry_candles list does not
        raise, and reports mtf_entry_candle_count=0,
        mtf_entry_data_available=False,
        mtf_entry_confirmation_applied=False.
        """

        signal_candle = make_candle(
            104.0, 106.5, 103.5, 106.0, day_index=61,
        )

        candles = build_candles(signal_candle)

        signal = await self.strategy.analyze_with_entry_candles(
            make_snapshot(candles),
            entry_candles=[],
        )

        self.assertIsNotNone(signal)
        self.assertEqual(signal.metadata["mtf_entry_candle_count"], 0)
        self.assertFalse(signal.metadata["mtf_entry_data_available"])
        self.assertFalse(
            signal.metadata["mtf_entry_confirmation_applied"],
        )

    async def test_no_signal_returns_none_without_touching_entry_candles(
        self,
    ) -> None:
        """
        When analyze() would return None (e.g. too few candles),
        analyze_with_entry_candles() also returns None - no MTF
        metadata is fabricated for a non-existent signal.
        """

        signal = await self.strategy.analyze_with_entry_candles(
            make_snapshot([]),
            entry_candles=[
                make_candle(100.0, 100.5, 99.5, 100.2, day_index=0),
            ],
        )

        self.assertIsNone(signal)


if __name__ == "__main__":
    unittest.main()
