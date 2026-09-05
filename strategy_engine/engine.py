from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import re
from decimal import Decimal

from strategies.registry_foundation import StrategyUsability, StrategyVersionAssessment
from strategy_engine.models import StrategyDecisionOutcome, StrategyDecisionRecord
from trading_scanner.models import QueueState, SetupFamily, TradingCandidate


APPROVED_STAGE3_STRATEGY_ID = "MH-ACTIVE-TRADING-SETUP-CONFIRMATION"
APPROVED_STAGE3_VERSION = "1"

_STOP_VALUE_RE = re.compile(r"\(([-+]?[0-9]+(?:\.[0-9]+)?)\)\s*$")

def _structural_stop(candidate: TradingCandidate) -> tuple[Decimal | None, str | None]:
    ref = candidate.invalidation_reference
    if not ref:
        return None, None
    match = _STOP_VALUE_RE.search(ref)
    if not match:
        return None, None
    value = Decimal(match.group(1))
    return (value, ref) if value > 0 else (None, None)


def validate_candidate(
    candidate: TradingCandidate,
    *,
    strategy_assessment: StrategyVersionAssessment,
    strategy_id: str = APPROVED_STAGE3_STRATEGY_ID,
    strategy_version: str = APPROVED_STAGE3_VERSION,
    decided_at: datetime | None = None,
) -> StrategyDecisionRecord:
    """Stage 3 only: deterministic decision, never sizing or execution."""
    now = decided_at or datetime.now(timezone.utc)
    key = f"{candidate.dedupe_key}|{strategy_id}|{strategy_version}"
    decision_id = "strategy:" + sha256(key.encode()).hexdigest()

    if candidate.queue_state is not QueueState.CANDIDATE:
        outcome = StrategyDecisionOutcome.REJECTED
        reasons = (f"candidate queue_state={candidate.queue_state.value}; only CANDIDATE is accepted",)
    elif strategy_assessment.usability is not StrategyUsability.USABLE:
        outcome = StrategyDecisionOutcome.REJECTED
        reasons = ("approved strategy version is not usable",) + tuple(r.value for r in strategy_assessment.reasons)
    elif not candidate.eligible or candidate.evidence_status != "OK":
        outcome = StrategyDecisionOutcome.REJECTED
        reasons = ("candidate evidence/eligibility gate failed",)
    elif candidate.setup_family in (
        SetupFamily.MOMENTUM_RELATIVE_STRENGTH,
        SetupFamily.BREAKOUT_OR_PULLBACK_IN_TREND,
    ):
        outcome = StrategyDecisionOutcome.LONG
        reasons = ("approved v1 long-only structure confirmed from scanner evidence",) + candidate.reason_stack
    else:
        outcome = StrategyDecisionOutcome.NO_TRADE
        reasons = ("approved v1 has no directional rule for this setup family",)

    structural_stop, structural_stop_source = _structural_stop(candidate)

    return StrategyDecisionRecord(
        decision_id=decision_id,
        candidate_dedupe_key=candidate.dedupe_key,
        symbol=candidate.symbol,
        setup_family=candidate.setup_family,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        outcome=outcome,
        decided_at=now,
        reason_stack=reasons,
        candidate_scan_cycle_id=candidate.scan_cycle_id,
        candidate_discovered_at=candidate.discovered_at,
        candidate_evidence_status=candidate.evidence_status,
        candidate_freshness_note=candidate.freshness_note,
        reference_price=candidate.liquidity.last_price,
        structural_stop_price=structural_stop,
        structural_stop_source=structural_stop_source,
    )
