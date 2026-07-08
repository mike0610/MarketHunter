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
        direction: str = "LONG",
    ) -> ProbabilityResult:

        score = 0

        reasons: list[str] = []

        normalized_direction = direction.strip().upper()

        if normalized_direction == "SHORT":
            trend_confirmed = self.trend.bearish(snapshot)
            bos_confirmed = self.bos.bearish(snapshot)
            choch_confirmed = self.choch.bearish(snapshot)
            breakout_confirmed = self.breakout.bearish(snapshot)
            order_block_confirmed = self.order_block.bearish(snapshot)
            fvg_confirmed = self.fvg.bearish(snapshot)
            liquidity_confirmed = self.liquidity.bearish(snapshot)

            reason_prefix = "Bearish "

        else:
            trend_confirmed = self.trend.bullish(snapshot)
            bos_confirmed = self.bos.bullish(snapshot)
            choch_confirmed = self.choch.bullish(snapshot)
            breakout_confirmed = self.breakout.bullish(snapshot)
            order_block_confirmed = self.order_block.bullish(snapshot)
            fvg_confirmed = self.fvg.bullish(snapshot)
            liquidity_confirmed = self.liquidity.bullish(snapshot)

            reason_prefix = ""

        if trend_confirmed:

            score += ProbabilityWeights.TREND
            reasons.append(f"{reason_prefix}Trend")

        if bos_confirmed:

            score += ProbabilityWeights.BOS
            reasons.append(f"{reason_prefix}BOS")

        if choch_confirmed:

            score += ProbabilityWeights.CHOCH
            reasons.append(f"{reason_prefix}CHoCH")

        if breakout_confirmed:

            score += ProbabilityWeights.BREAKOUT
            reasons.append(f"{reason_prefix}Breakout")

        if order_block_confirmed:

            score += ProbabilityWeights.ORDER_BLOCK
            reasons.append(f"{reason_prefix}Order Block")

        if fvg_confirmed:

            score += ProbabilityWeights.FVG
            reasons.append(f"{reason_prefix}FVG")

        if liquidity_confirmed:

            score += ProbabilityWeights.LIQUIDITY
            reasons.append(f"{reason_prefix}Liquidity")

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