"""
MarketHunter

models/probability_result.py
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ProbabilityResult:
    """
    Final trade probability.
    """

    probability: int

    score: int

    confidence: str

    reasons: list[str] = field(default_factory=list)

    @property
    def tradable(self) -> bool:

        return self.probability >= 70