"""
MarketHunter

probability/probability_engine.py
"""

from __future__ import annotations

from models.market_snapshot import MarketSnapshot
from models.probability_result import ProbabilityResult

from indicators.trend import TrendFilter
from indicators.bos_filter import BOSFilter
from indicators.choch_filter import CHoCHFilter
from indicators.breakout_filter import BreakoutFilter
from indicators.order_block_filter import OrderBlockFilter
from indicators.fvg_filter import FVGFilter
from indicators.liquidity_filter import LiquidityFilter

from probability.weights import ProbabilityWeights
from regime.market_regime_engine import (
    MarketRegimeEngine,
)


class ProbabilityEngine:

    def __init__(self) -> None:

        self.trend = TrendFilter()
        self.bos = BOSFilter()
        self.choch = CHoCHFilter()
        self.breakout = BreakoutFilter()
        self.order_block = OrderBlockFilter()
        self.fvg = FVGFilter()
        self.liquidity = LiquidityFilter()
        self.regime = MarketRegimeEngine()

    def evaluate(
        self,
        snapshot: MarketSnapshot,
        mtf_score: int = 0,
    ) -> ProbabilityResult:

        score = 0

        reasons: list[str] = []

        if self.trend.bullish(snapshot):

            score += ProbabilityWeights.TREND
            reasons.append("Trend")

        if self.bos.bullish(snapshot):

            score += ProbabilityWeights.BOS
            reasons.append("BOS")

        if self.choch.bullish(snapshot):

            score += ProbabilityWeights.CHOCH
            reasons.append("CHoCH")

        if self.breakout.bullish(snapshot):

            score += ProbabilityWeights.BREAKOUT
            reasons.append("Breakout")

        if self.order_block.bullish(snapshot):

            score += ProbabilityWeights.ORDER_BLOCK
            reasons.append("Order Block")

        if self.fvg.bullish(snapshot):

            score += ProbabilityWeights.FVG
            reasons.append("FVG")

        if self.liquidity.bullish(snapshot):

            score += ProbabilityWeights.LIQUIDITY
            reasons.append("Liquidity")

        regime = self.regime.analyze(snapshot)

        if regime.tradable:

            score += ProbabilityWeights.REGIME
            reasons.append(regime.name)

        score += min(
            mtf_score,
            ProbabilityWeights.MTF,
        )

        probability = min(score, 100)

        if probability >= 90:

            confidence = "A+"

        elif probability >= 80:

            confidence = "A"

        elif probability >= 70:

            confidence = "B"

        elif probability >= 60:

            confidence = "C"

        else:

            confidence = "D"

        return ProbabilityResult(
            probability=probability,
            score=score,
            confidence=confidence,
            reasons=reasons,
        )