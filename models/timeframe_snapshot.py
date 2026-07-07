"""
MarketHunter

models/timeframe_snapshot.py
"""

from __future__ import annotations

from dataclasses import dataclass

from models.market_snapshot import MarketSnapshot
from models.market_structure import MarketStructure


@dataclass(slots=True)
class TimeframeSnapshot:
    """
    Snapshot for one timeframe.
    """

    timeframe: str

    snapshot: MarketSnapshot

    structure: MarketStructure