"""
MarketHunter

engine/confluence_engine.py
"""

from __future__ import annotations

from models.timeframe_snapshot import (
    TimeframeSnapshot,
)


class ConfluenceEngine:
    """
    Multi TimeFrame Confluence Engine.
    """

    def bullish(
        self,
        snapshots: list[TimeframeSnapshot],
    ) -> bool:

        if not snapshots:
            return False

        return all(
            tf.structure.bullish
            for tf in snapshots
        )

    def bearish(
        self,
        snapshots: list[TimeframeSnapshot],
    ) -> bool:

        if not snapshots:
            return False

        return all(
            tf.structure.bearish
            for tf in snapshots
        )

    def score(
        self,
        snapshots: list[TimeframeSnapshot],
    ) -> int:

        score = 0

        for tf in snapshots:

            if tf.structure.bullish:
                score += 20

            elif tf.structure.bearish:
                score += 20

        return min(score, 100)