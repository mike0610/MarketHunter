"""
MarketHunter

Module:
Portfolio v1 Assessment (Slice 2)

Responsibilities:
- Turn existing, already-computed ResearchTrade facts into the
  Slice 1 Portfolio v1 domain objects (ExposureAssessment,
  PositionSizingDecision, PortfolioDecision).
- Stay a pure read-model: no mutation of inputs, no persistence, no
  API, no invented numbers.

Non-goals (see portfolio_v1/domain.py and project boundaries):
- No risk percentage, stop/TP, or position-sizing mathematics - this
  module only reads ResearchTrade.notional, never recalculates it.
- No RiskManager/RiskResult usage. Portfolio v1 does not run a second
  risk calculation; ResearchTrade already carries what it needs
  (`notional`).
- No capital_available value. No governed capital-availability or
  Portfolio approval policy exists anywhere in this codebase yet, so
  sizing decisions from this module are never APPROVED - only
  NOT_APPLICABLE, with an explicit reason. Marking something
  APPROVED merely because a notional number exists would fabricate a
  policy this module does not own.
- No scope/filtering logic. Which ResearchTrade records belong to a
  given scope (e.g. "active spot trades") is decided by the caller;
  this module only aggregates whatever explicit collection it is
  given.
"""

from __future__ import annotations

from research.models.trade import ResearchTrade

from portfolio_v1.domain import (
    ExposureAssessment,
    ExposureState,
    PortfolioDecision,
    PortfolioOutcome,
    PositionSizingDecision,
    SizingState,
)


NO_CAPITAL_POLICY_REASON = (
    "No governed Portfolio v1 capital-availability or sizing-approval "
    "policy exists yet; requested_notional is carried through "
    "unevaluated."
)


def assess_exposure(
    trades: list[ResearchTrade],
    *,
    scope: str,
    assessment_id: str,
    generated_at: str,
) -> ExposureAssessment:
    """
    Measure exposure over an explicitly supplied collection of
    ResearchTrade records.

    `trades` defines the scope directly - this function does not
    filter by status, market, or anything else. An empty list is a
    valid, fully-known scope (zero positions), not an unknown one.
    """

    return ExposureAssessment(
        assessment_id=assessment_id,
        scope=scope,
        provenance=f"research_trades:{scope}",
        generated_at=generated_at,
        state=ExposureState.MEASURED,
        position_count=len(trades),
        total_notional=sum(
            trade.notional
            for trade in trades
        ),
    )


def build_sizing_decision(
    trade: ResearchTrade,
    *,
    decision_id: str,
    decided_at: str,
) -> PositionSizingDecision:
    """
    Carry one candidate ResearchTrade's existing notional through as
    a read-only sizing reference.

    Never APPROVED: approving a size requires a governed capital/
    policy decision this module does not own. `capital_available`
    stays unset for the same reason.
    """

    return PositionSizingDecision(
        decision_id=decision_id,
        candidate_reference=trade.id,
        provenance=f"research_trade:{trade.id}:notional",
        decided_at=decided_at,
        state=SizingState.NOT_APPLICABLE,
        requested_notional=trade.notional,
        capital_available=None,
        reasons=(NO_CAPITAL_POLICY_REASON,),
    )


def compose_portfolio_decision(
    *,
    decision_id: str,
    candidate_reference: str,
    provenance: str,
    decided_at: str,
    exposure: ExposureAssessment,
    sizing: PositionSizingDecision,
) -> PortfolioDecision:
    """
    Combine one ExposureAssessment and one PositionSizingDecision.

    PROCEED is only reachable when the exposure is MEASURED and the
    sizing is APPROVED - both of Slice 1's own PortfolioDecision
    invariants. With today's assess_exposure/build_sizing_decision,
    sizing is always NOT_APPLICABLE, so this always resolves to
    NOT_APPLICABLE; the branches for BLOCKED/UNKNOWN/APPROVED are
    kept correct for whatever governed policy Slice 1's states
    already allow, rather than hard-coding today's only reachable
    case.
    """

    if (
        exposure.state == ExposureState.MEASURED
        and sizing.state == SizingState.APPROVED
    ):
        return PortfolioDecision(
            decision_id=decision_id,
            candidate_reference=candidate_reference,
            provenance=provenance,
            decided_at=decided_at,
            exposure=exposure,
            sizing=sizing,
            outcome=PortfolioOutcome.PROCEED,
        )

    if sizing.state == SizingState.NOT_APPLICABLE:
        outcome = PortfolioOutcome.NOT_APPLICABLE
    elif sizing.state == SizingState.BLOCKED:
        outcome = PortfolioOutcome.BLOCK
    else:
        outcome = PortfolioOutcome.UNKNOWN

    reasons = sizing.reasons or (
        "Exposure assessment is not MEASURED.",
    )

    return PortfolioDecision(
        decision_id=decision_id,
        candidate_reference=candidate_reference,
        provenance=provenance,
        decided_at=decided_at,
        exposure=exposure,
        sizing=sizing,
        outcome=outcome,
        reasons=reasons,
    )
