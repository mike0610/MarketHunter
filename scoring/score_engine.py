"""
MarketHunter

scoring/score_engine.py
"""

from __future__ import annotations

from models.market_snapshot import MarketSnapshot
from scoring.breakout_score import BreakoutScore


class ScoreEngine:

    def __init__(self) -> None:
        self.breakout_score = BreakoutScore()

    def breakout(
        self,
        snapshot: MarketSnapshot,
    ) -> tuple[int, list[str]]:

        return self.breakout_score.calculate(snapshot)