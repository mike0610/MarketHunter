"""
MarketHunter

models/signal.py
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Signal:
    """
    Trading signal.
    """

    symbol: str
    market: str
    timeframe: str

    strategy: str

    direction: str

    score: float = 0.0

    reasons: list[str] = field(default_factory=list)

    metadata: dict = field(default_factory=dict)

    def add_reason(self, text: str) -> None:
        self.reasons.append(text)

    @property
    def passed(self) -> bool:
        return self.score >= 90