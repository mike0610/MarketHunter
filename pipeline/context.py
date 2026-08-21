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
from strategies.execution_binding import StrategyExecutionBinding


@dataclass(slots=True)
class SignalContext:
    """
    Shared state for processing one signal through the pipeline.

    strategy_execution_binding carries the exact governed
    StrategyExecutionBinding for this signal, when the originating
    Scanner strategy was bound to an issued release. It is assigned
    exactly once by Scanner and is otherwise untouched by normal
    context mutation - handlers must never overwrite it. None means
    this signal came from a legacy unbound strategy and is explicitly
    NON-PROVENANCE-ELIGIBLE.
    """

    signal: Signal
    snapshot: MarketSnapshot

    probability: ProbabilityResult | None = None
    risk: RiskResult | None = None
    research_trade: ResearchTrade | None = None

    accepted: bool = True
    rejected_reason: str | None = None

    strategy_execution_binding: StrategyExecutionBinding | None = None

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