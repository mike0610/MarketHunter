"""
MarketHunter

research/setup/reaction_quality.py
"""

from __future__ import annotations

from dataclasses import dataclass

from indicators.bos_filter import BOSFilter
from indicators.breakout_filter import BreakoutFilter
from indicators.choch_filter import CHoCHFilter
from indicators.false_breakout_filter import FalseBreakoutFilter
from indicators.double_pattern import DoublePatternDetector
from indicators.liquidity_filter import LiquidityFilter
from models.market_snapshot import MarketSnapshot


@dataclass(slots=True)
class ReactionQualityAssessment:
    direction: str
    confirmed: bool
    score: int
    reasons: list[str]
    atr_body_ratio: float
    summary: str


class ReactionQualityDetector:
    def __init__(
        self,
        *,
        atr_impulse_multiplier: float = 0.8,
        minimum_score: int = 1,
    ) -> None:
        if atr_impulse_multiplier <= 0:
            raise ValueError(
                "ATR impulse multiplier must be positive."
            )

        if minimum_score < 1:
            raise ValueError(
                "Minimum reaction score must be at least 1."
            )

        self.atr_impulse_multiplier = atr_impulse_multiplier
        self.minimum_score = minimum_score

        self.bos = BOSFilter()
        self.choch = CHoCHFilter()
        self.breakout = BreakoutFilter()
        self.false_breakout = FalseBreakoutFilter()
        self.liquidity = LiquidityFilter()
        self.double_pattern = DoublePatternDetector()

    def assess(
        self,
        *,
        snapshot: MarketSnapshot,
        direction: str,
    ) -> ReactionQualityAssessment:
        normalized_direction = direction.strip().upper()

        if normalized_direction == "SHORT":
            checks = [
                ("Bearish BOS", self.bos.bearish(snapshot)),
                ("Bearish CHoCH", self.choch.bearish(snapshot)),
                ("Bearish Breakout", self.breakout.bearish(snapshot)),
                (
                    "Bearish False Breakout",
                    self.false_breakout.bearish(snapshot),
                ),
                (
                    "Bearish Liquidity Sweep",
                    self.liquidity.bearish(snapshot),
                ),
                (
                    "Double Top",
                    self.double_pattern.bearish(snapshot.candles),
                ),
            ]
        else:
            normalized_direction = "LONG"

            checks = [
                ("Bullish BOS", self.bos.bullish(snapshot)),
                ("Bullish CHoCH", self.choch.bullish(snapshot)),
                ("Bullish Breakout", self.breakout.bullish(snapshot)),
                (
                    "Bullish False Breakout",
                    self.false_breakout.bullish(snapshot),
                ),
                (
                    "Bullish Liquidity Sweep",
                    self.liquidity.bullish(snapshot),
                ),
                (
                    "Double Bottom",
                    self.double_pattern.bullish(snapshot.candles),
                ),
            ]

        reasons = [
            name
            for name, passed in checks
            if passed
        ]

        atr_body_ratio = self._atr_body_ratio(snapshot)

        if self._atr_impulse_confirmed(
            snapshot=snapshot,
            direction=normalized_direction,
            atr_body_ratio=atr_body_ratio,
        ):
            reasons.append("ATR Impulse")

        score = len(reasons)
        confirmed = score >= self.minimum_score

        if confirmed:
            summary = (
                "Reaction confirmed: "
                + ", ".join(reasons)
                + "."
            )
        else:
            summary = (
                "No confirmed reaction: missing BOS/CHoCH, "
                "breakout, false breakout, liquidity sweep, double top/bottom or "
                "ATR impulse."
            )

        return ReactionQualityAssessment(
            direction=normalized_direction,
            confirmed=confirmed,
            score=score,
            reasons=reasons,
            atr_body_ratio=atr_body_ratio,
            summary=summary,
        )

    def _atr_body_ratio(
        self,
        snapshot: MarketSnapshot,
    ) -> float:
        if snapshot.atr14 <= 0:
            return 0.0

        last = snapshot.candles[-1]

        body = abs(
            last.close
            - last.open
        )

        return body / snapshot.atr14

    def _atr_impulse_confirmed(
        self,
        *,
        snapshot: MarketSnapshot,
        direction: str,
        atr_body_ratio: float,
    ) -> bool:
        if atr_body_ratio < self.atr_impulse_multiplier:
            return False

        last = snapshot.candles[-1]

        if direction == "SHORT":
            return last.close < last.open

        return last.close > last.open
