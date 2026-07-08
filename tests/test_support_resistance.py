"""
MarketHunter

Tests for support / resistance setup analysis.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from research.setup.support_resistance import (
    SupportResistanceDetector,
    calculate_rr_target,
)


def make_candle(
    *,
    index: int,
    high: float,
    low: float,
    close: float,
) -> SimpleNamespace:
    """
    Create candle-like object for tests.
    """

    return SimpleNamespace(
        high=high,
        low=low,
        close=close,
        open_time=(
            datetime(
                2026,
                1,
                1,
                tzinfo=UTC,
            )
            + timedelta(hours=index)
        ),
    )


class SupportResistanceDetectorTests(unittest.TestCase):
    """
    Test pivot zone detection and target blocking.
    """

    def test_calculates_long_rr_target(self) -> None:
        """
        LONG RR target is above entry.
        """

        target = calculate_rr_target(
            direction="LONG",
            entry_price=100.0,
            stop_loss=90.0,
            risk_reward=3.0,
        )

        self.assertEqual(
            target,
            130.0,
        )

    def test_calculates_short_rr_target(self) -> None:
        """
        SHORT RR target is below entry.
        """

        target = calculate_rr_target(
            direction="SHORT",
            entry_price=100.0,
            stop_loss=110.0,
            risk_reward=2.0,
        )

        self.assertEqual(
            target,
            80.0,
        )

    def test_long_target_is_blocked_by_resistance(self) -> None:
        """
        LONG 1:3 target is blocked by resistance before TP.
        """

        candles = [
            make_candle(index=0, high=101, low=96, close=99),
            make_candle(index=1, high=106, low=98, close=103),
            make_candle(index=2, high=119, low=100, close=110),
            make_candle(index=3, high=108, low=99, close=104),
            make_candle(index=4, high=103, low=95, close=99),
            make_candle(index=5, high=110, low=97, close=106),
            make_candle(index=6, high=121, low=101, close=113),
            make_candle(index=7, high=109, low=98, close=104),
            make_candle(index=8, high=102, low=94, close=98),
            make_candle(index=9, high=107, low=96, close=101),
        ]

        detector = SupportResistanceDetector(
            lookback_candles=30,
            pivot_window=1,
            min_touches=1,
        )

        assessment = detector.assess_rr_target(
            candles,
            direction="LONG",
            entry_price=100.0,
            stop_loss=90.0,
            target_rr=3.0,
        )

        self.assertFalse(
            assessment.target_clear,
        )
        self.assertEqual(
            assessment.target_price,
            130.0,
        )
        self.assertGreaterEqual(
            len(assessment.blocking_zones),
            1,
        )
        self.assertEqual(
            assessment.blocking_zones[0].zone_type,
            "resistance",
        )

    def test_long_target_is_clear_when_resistance_is_above_target(
        self,
    ) -> None:
        """
        LONG target is clear when resistance is above target.
        """

        candles = [
            make_candle(index=0, high=101, low=96, close=99),
            make_candle(index=1, high=106, low=98, close=103),
            make_candle(index=2, high=145, low=100, close=120),
            make_candle(index=3, high=108, low=99, close=104),
            make_candle(index=4, high=103, low=95, close=99),
            make_candle(index=5, high=110, low=97, close=106),
            make_candle(index=6, high=146, low=101, close=123),
            make_candle(index=7, high=109, low=98, close=104),
            make_candle(index=8, high=102, low=94, close=98),
            make_candle(index=9, high=107, low=96, close=101),
        ]

        detector = SupportResistanceDetector(
            lookback_candles=30,
            pivot_window=1,
            min_touches=1,
        )

        assessment = detector.assess_rr_target(
            candles,
            direction="LONG",
            entry_price=100.0,
            stop_loss=90.0,
            target_rr=3.0,
        )

        self.assertTrue(
            assessment.target_clear,
        )
        self.assertEqual(
            assessment.blocking_zones,
            [],
        )

    def test_short_target_is_blocked_by_support(self) -> None:
        """
        SHORT 1:2 target is blocked by support before TP.
        """

        candles = [
            make_candle(index=0, high=112, low=98, close=105),
            make_candle(index=1, high=109, low=94, close=101),
            make_candle(index=2, high=106, low=88, close=94),
            make_candle(index=3, high=110, low=96, close=103),
            make_candle(index=4, high=113, low=99, close=107),
            make_candle(index=5, high=111, low=95, close=102),
            make_candle(index=6, high=107, low=87, close=93),
            make_candle(index=7, high=112, low=97, close=106),
            make_candle(index=8, high=115, low=100, close=109),
            make_candle(index=9, high=111, low=98, close=104),
        ]

        detector = SupportResistanceDetector(
            lookback_candles=30,
            pivot_window=1,
            min_touches=1,
        )

        assessment = detector.assess_rr_target(
            candles,
            direction="SHORT",
            entry_price=100.0,
            stop_loss=110.0,
            target_rr=2.0,
        )

        self.assertFalse(
            assessment.target_clear,
        )
        self.assertEqual(
            assessment.target_price,
            80.0,
        )
        self.assertGreaterEqual(
            len(assessment.blocking_zones),
            1,
        )
        self.assertEqual(
            assessment.blocking_zones[0].zone_type,
            "support",
        )


if __name__ == "__main__":
    unittest.main()