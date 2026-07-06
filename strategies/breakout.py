"""
MarketHunter

strategies/breakout.py
"""

from __future__ import annotations

from models.market_snapshot import MarketSnapshot
from models.signal import Signal
from scoring.score_engine import ScoreEngine
from strategies.base_strategy import BaseStrategy


class BreakoutStrategy(BaseStrategy):
    """
    Breakout strategy.
    """

    name = "Breakout"

    def __init__(self) -> None:
        self.score_engine = ScoreEngine()

    async def analyze(
        self,
        snapshot: MarketSnapshot,
    ) -> Signal | None:
        """
        Analyze breakout.
        """

        score, reasons = self.score_engine.breakout(
            snapshot
        )

        if score < 90:
            return None

        signal = Signal(
            symbol=snapshot.symbol,
            market="",
            timeframe="1d",
            strategy=self.name,
            direction="LONG",
            score=score,
        )

        signal.reasons.extend(reasons)

        return signal