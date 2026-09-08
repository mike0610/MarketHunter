from __future__ import annotations
import unittest
from app.main import build_strategies

class StrategyTimeframeEligibilityTests(unittest.TestCase):
    def _names(self,timeframe):
        return {strategy.name for strategy in build_strategies(timeframe)}

    def test_session_range_is_1h_only(self):
        self.assertIn("SessionRange",self._names("1h"))
        self.assertNotIn("SessionRange",self._names("1d"))

    def test_daily_levels_is_1d_only(self):
        self.assertIn("DailyLevels",self._names("1d"))
        self.assertNotIn("DailyLevels",self._names("1h"))

    def test_common_strategy_universe_is_present_on_both_timeframes(self):
        one_hour=self._names("1h")
        one_day=self._names("1d")
        for name in {"Breakout","LiquiditySweep","StatisticalMeanReversion","VolumeConfirmedBreakout"}:
            self.assertIn(name,one_hour)
            self.assertIn(name,one_day)

if __name__=="__main__":
    unittest.main()
