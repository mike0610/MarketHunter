from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from trading_scanner.models import SetupFamily


class StrategyDecisionOutcome(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NO_TRADE = "NO_TRADE"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class StrategyDecisionRecord:
    decision_id: str
    candidate_dedupe_key: str
    symbol: str
    setup_family: SetupFamily
    strategy_id: str
    strategy_version: str
    outcome: StrategyDecisionOutcome
    decided_at: datetime
    reason_stack: tuple[str, ...]
    candidate_scan_cycle_id: str
    candidate_discovered_at: datetime
    candidate_evidence_status: str
    candidate_freshness_note: str | None

    def __post_init__(self) -> None:
        for value, name in (
            (self.decision_id, "decision_id"),
            (self.candidate_dedupe_key, "candidate_dedupe_key"),
            (self.symbol, "symbol"),
            (self.strategy_id, "strategy_id"),
            (self.strategy_version, "strategy_version"),
            (self.candidate_scan_cycle_id, "candidate_scan_cycle_id"),
            (self.candidate_evidence_status, "candidate_evidence_status"),
        ):
            if not value.strip():
                raise ValueError(f"{name} must be non-blank")
        if self.decided_at.tzinfo is None or self.candidate_discovered_at.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        if not self.reason_stack:
            raise ValueError("reason_stack must be non-empty")
