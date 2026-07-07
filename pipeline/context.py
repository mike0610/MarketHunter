"""
MarketHunter

Pipeline context passed through signal handlers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from models.market_snapshot import MarketSnapshot
from models.probability_result import ProbabilityResult
from models.risk_result import RiskResult
from models.signal import Signal
from research.models.trade import ResearchTrade


@dataclass(slots=True)
class SignalContext:
    """
    Shared state for processing one signal through the pipeline.
    """

    signal: Signal
    snapshot: MarketSnapshot

    probability: ProbabilityResult | None = None
    risk: RiskResult | None = None
    research_trade: ResearchTrade | None = None

    accepted: bool = True
    rejected_reason: str | None = None

    metadata: dict[str, Any] = field(
        default_factory=dict,
    )

    handled_by: list[str] = field(
        default_factory=list,
    )

    def reject(
        self,
        reason: str,
    ) -> None:
        """
        Stop all remaining pipeline handlers.
        """

        self.accepted = False
        self.rejected_reason = reason
        self.metadata["pipeline_rejected_reason"] = reason