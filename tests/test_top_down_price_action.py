from __future__ import annotations

import unittest
from dataclasses import replace

from research.price_action.context import (
    MarketRegime,
    PriceActionContext,
)
from research.price_action.top_down import TopDownPriceActionEngine


def ctx(regime, confidence=0.8):
    return PriceActionContext(
        regime=regime,
        confidence=confidence,
        swing_highs=(),
        swing_lows=(),
        support_zones=(),
        resistance_zones=(),
        structure_sequence=(),
        structure_events=(),
        zone_behaviors=(),
        structural_lines=(),
    )


class TopDownPriceActionEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = TopDownPriceActionEngine()

    def test_monthly_weekly_bullish_define_broad_bull_regime(self):
        regime, confidence = self.engine._broad_regime(
            ctx(MarketRegime.BULLISH, 0.9),
            ctx(MarketRegime.BULLISH, 0.7),
        )
        self.assertEqual(regime, MarketRegime.BULLISH)
        self.assertAlmostEqual(confidence, 0.8)

    def test_daily_bearish_inside_broad_bull_is_correction(self):
        phase = self.engine._daily_phase(
            MarketRegime.BULLISH,
            MarketRegime.BEARISH,
        )
        self.assertEqual(phase, "countertrend_correction")

    def test_hourly_bullish_inside_broad_bull_is_with_trend(self):
        value = self.engine._hourly_context(
            MarketRegime.BULLISH,
            ctx(MarketRegime.BULLISH),
        )
        self.assertEqual(value, "with_broad_trend")

    def test_full_alignment_requires_daily_and_hourly_agreement(self):
        value = self.engine._alignment(
            MarketRegime.BEARISH,
            MarketRegime.BEARISH,
            MarketRegime.BEARISH,
        )
        self.assertEqual(value, "full_alignment")

    def test_monthly_weekly_opposition_is_transition_not_forced_vote(self):
        regime, confidence = self.engine._broad_regime(
            ctx(MarketRegime.BULLISH),
            ctx(MarketRegime.BEARISH),
        )
        self.assertEqual(regime, MarketRegime.TRANSITION)
        self.assertLess(confidence, 0.5)


if __name__ == "__main__":
    unittest.main()
