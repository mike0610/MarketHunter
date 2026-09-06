from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum

from experiment1.models import AccountKind
from investments.autonomous_loop import (
    AutonomousInvestmentStore,
    InvestmentResearchDecision,
    InvestmentResearchRecord,
)
from investments.research_worker import (
    ClaimedInvestmentResearch,
    InvestmentResearchWorker,
)
from investments.stage8_boundary import assert_investment_account


class GILResearchOutcome(str, Enum):
    DECISION = "DECISION"
    BLOCKED_EVIDENCE = "BLOCKED_EVIDENCE"


@dataclass(frozen=True, slots=True)
class GILResearchEvidence:
    reference: str
    observed_at: datetime

    def __post_init__(self) -> None:
        if not self.reference:
            raise ValueError("evidence reference required")
        if self.observed_at.tzinfo is None:
            raise ValueError("evidence observed_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class GILResearchRequest:
    candidate_id: str
    symbol: str
    evidence_reference: str
    priority: str
    claimed_at: datetime

    @classmethod
    def from_claim(
        cls,
        claim: ClaimedInvestmentResearch,
    ) -> "GILResearchRequest":
        return cls(
            candidate_id=claim.candidate_id,
            symbol=claim.symbol,
            evidence_reference=claim.evidence_reference,
            priority=claim.priority,
            claimed_at=claim.claimed_at,
        )


@dataclass(frozen=True, slots=True)
class GILResearchResult:
    candidate_id: str
    symbol: str
    outcome: GILResearchOutcome
    agent_reference: str
    completed_at: datetime
    evidence: tuple[GILResearchEvidence, ...]
    account: AccountKind | None = None
    decision: InvestmentResearchDecision | None = None
    investment_attractiveness: Decimal | None = None
    executability: Decimal | None = None
    thesis: str | None = None
    counter_thesis: str | None = None
    revisit_condition: str | None = None
    blocker: str | None = None

    def __post_init__(self) -> None:
        if not self.candidate_id or not self.symbol:
            raise ValueError("research result identity required")
        if not self.agent_reference:
            raise ValueError("agent_reference required")
        if self.completed_at.tzinfo is None:
            raise ValueError("completed_at must be timezone-aware")
        if not self.evidence:
            raise ValueError("evidence-backed result requires evidence")

        if self.outcome is GILResearchOutcome.BLOCKED_EVIDENCE:
            if not self.blocker:
                raise ValueError("BLOCKED_EVIDENCE requires blocker")
            if any(
                value is not None
                for value in (
                    self.account,
                    self.decision,
                    self.investment_attractiveness,
                    self.executability,
                    self.thesis,
                    self.counter_thesis,
                )
            ):
                raise ValueError(
                    "BLOCKED_EVIDENCE cannot carry investment decision"
                )
            return

        if self.blocker is not None:
            raise ValueError("decision result cannot carry blocker")
        if self.account is None or self.decision is None:
            raise ValueError("decision result requires account and decision")
        assert_investment_account(self.account)
        if self.investment_attractiveness is None or self.executability is None:
            raise ValueError("decision result requires scores")
        for score in (
            self.investment_attractiveness,
            self.executability,
        ):
            if score < 0 or score > 1:
                raise ValueError("research scores must be in [0,1]")
        if not self.thesis or not self.counter_thesis:
            raise ValueError("decision result requires thesis and counter-thesis")
        if (
            self.decision is InvestmentResearchDecision.WAIT
            and not self.revisit_condition
        ):
            raise ValueError("WAIT requires explicit revisit condition")


def _validated_evidence_reference(
    result: GILResearchResult,
    *,
    max_evidence_age: timedelta,
) -> str:
    if max_evidence_age <= timedelta(0):
        raise ValueError("max_evidence_age must be positive")
    latest = max(item.observed_at for item in result.evidence)
    if any(item.observed_at > result.completed_at for item in result.evidence):
        raise ValueError("future-dated evidence rejected")
    if result.completed_at - latest > max_evidence_age:
        raise ValueError("stale research evidence rejected")
    return "|".join(item.reference for item in result.evidence)


def ingest_gil_research_result(
    *,
    worker: InvestmentResearchWorker,
    store: AutonomousInvestmentStore,
    claim: ClaimedInvestmentResearch,
    result: GILResearchResult,
    max_evidence_age: timedelta,
) -> InvestmentResearchRecord | None:
    if result.candidate_id != claim.candidate_id:
        raise ValueError("candidate mismatch")
    if result.symbol != claim.symbol:
        raise ValueError("symbol mismatch")
    if result.completed_at < claim.claimed_at:
        raise ValueError("research result predates claim")

    evidence_reference = _validated_evidence_reference(
        result,
        max_evidence_age=max_evidence_age,
    )

    if result.outcome is GILResearchOutcome.BLOCKED_EVIDENCE:
        worker.complete(claim.candidate_id, "BLOCKED_EVIDENCE")
        return None

    record = InvestmentResearchRecord(
        object_id=result.candidate_id,
        symbol=result.symbol,
        account=result.account,
        decision=result.decision,
        decided_at=result.completed_at,
        investment_attractiveness=result.investment_attractiveness,
        executability=result.executability,
        evidence_reference=evidence_reference,
        thesis=result.thesis,
        counter_thesis=result.counter_thesis,
        revisit_condition=result.revisit_condition,
    )
    inserted = store.record(record)
    worker.complete(
        claim.candidate_id,
        "REJECTED"
        if result.decision is InvestmentResearchDecision.REJECT
        else "DECIDED",
    )
    return record if inserted else None
