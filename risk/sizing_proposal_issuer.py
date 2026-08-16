"""
MarketHunter

risk/sizing_proposal_issuer.py

Module:
Risk Engine v1 - Slice 1 (pure deterministic RiskSizingProposal
issuer/evaluator)

Responsibilities:
- Define RiskPolicyReference: caller-supplied governing-policy
  identity used to authorize issuance, distinct from
  RiskSizingProposal.policy_id/policy_version (which is the
  proposal's own recorded provenance).
- Define RiskSizingEvaluationInput: the complete, unchanged
  RiskSizingProposal constructor field set, plus the governing
  policy reference and four caller-supplied ProposalDisposition
  gates.
- Define evaluate_risk_sizing_proposal(): a pure, deterministic
  function that constructs an existing RiskSizingProposal only when
  every required gate and reference is already complete, current,
  and authoritative - never by computing a missing value.

Non-goals (frozen by ARCH-REQ-RISK-ENGINE-ISSUER-001):
- No sizing formula, percentage-of-capital rule, leverage, Kelly,
  concentration, or risk-budget policy. This module never derives
  quantity, notional, reference price, or risk_amount - those are
  caller-supplied inputs, copied exactly or not issued at all.
- No AccountCapitalSnapshot input of any kind - capital remains on
  the Account Capital Authority -> Portfolio admission side only.
- No RiskManager or PositionSize import/reuse, and no read of
  RiskResultRecord.position_size/risk_amount/risk_percent/
  account_size - this evaluator only references RiskResult by exact
  id+revision, supplied by the caller.
- No ResearchTrade.notional mapping or fallback of any kind.
- No policy-registry lookup. RiskPolicyReference is caller-supplied
  authority identity only, never resolved against a registry.
- No persistence, repository, service, orchestrator, or runtime/API/
  execution wiring of any kind.
- No wall-clock (datetime.now), uuid/random, mutable global state, or
  hidden fallback - the same input always yields the same result.
- No PortfolioDecision or OrderIntent side effect - issuing a
  proposal never implies Portfolio APPROVED/PROCEED or execution
  authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from models.risk_result_record import IdentityState
from models.risk_sizing_proposal import ProposalDisposition, RiskSizingProposal


class RiskSizingIssuability(str, Enum):
    ISSUABLE = "ISSUABLE"
    NOT_ISSUABLE = "NOT_ISSUABLE"


class RiskSizingIssueReason(str, Enum):
    CANDIDATE_NOT_CURRENT = "CANDIDATE_NOT_CURRENT"
    PRICE_NOT_CURRENT = "PRICE_NOT_CURRENT"
    RISK_RESULT_NOT_CURRENT = "RISK_RESULT_NOT_CURRENT"
    POLICY_NOT_CURRENT = "POLICY_NOT_CURRENT"
    CANDIDATE_IDENTITY_NOT_KNOWN = "CANDIDATE_IDENTITY_NOT_KNOWN"
    POLICY_REFERENCE_INVALID = "POLICY_REFERENCE_INVALID"
    POLICY_MISMATCH = "POLICY_MISMATCH"
    INVALID_PROPOSAL_INPUT = "INVALID_PROPOSAL_INPUT"


def _blank(value: object) -> bool:
    return not isinstance(value, str) or not value.strip()


def _require_nonblank(value: object, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a str")

    if not value.strip():
        raise ValueError(f"{field_name} must be non-blank")


@dataclass(frozen=True, slots=True)
class RiskPolicyReference:
    """
    Caller-supplied governing-policy authority identity. This is an
    authorization reference only, never a registry lookup - the
    evaluator does not resolve it against any policy store.
    """

    policy_id: str
    policy_version: str

    def __post_init__(self) -> None:
        _require_nonblank(self.policy_id, "policy_id")
        _require_nonblank(self.policy_version, "policy_version")


@dataclass(frozen=True, slots=True, kw_only=True)
class RiskSizingEvaluationInput:
    """
    Carries the complete, unmodified RiskSizingProposal constructor
    field set, plus the governing policy reference and four
    caller-supplied disposition gates. Proposal-shaped fields are
    intentionally NOT re-validated here - RiskSizingProposal already
    owns that validation, and evaluate_risk_sizing_proposal() defers
    to its constructor rather than duplicating its semantics.
    """

    proposal_id: str
    revision: int
    generated_at: datetime
    supersedes_revision: int | None

    instrument_reference_kind: str
    instrument_reference: str
    direction: str

    quantity: Decimal
    quantity_unit: str

    notional: Decimal
    notional_currency: str

    reference_price: Decimal
    reference_price_currency: str
    reference_price_unit: str
    reference_price_source_kind: str
    reference_price_source_reference: str

    risk_result_id: str
    risk_result_revision: int

    policy_id: str
    policy_version: str

    candidate_state: IdentityState
    candidate_reference_kind: str | None
    candidate_reference: str | None

    strategy_reference_state: IdentityState
    strategy_reference: str | None

    strategy_version_state: IdentityState
    strategy_version: str | None

    risk_amount: Decimal | None
    risk_amount_currency: str | None
    risk_amount_unit: str | None

    governing_policy: RiskPolicyReference
    candidate_disposition: ProposalDisposition
    price_disposition: ProposalDisposition
    risk_result_disposition: ProposalDisposition
    policy_disposition: ProposalDisposition

    def __post_init__(self) -> None:
        if not isinstance(self.governing_policy, RiskPolicyReference):
            raise TypeError("governing_policy must be a RiskPolicyReference")

        for value, field_name in (
            (self.candidate_disposition, "candidate_disposition"),
            (self.price_disposition, "price_disposition"),
            (self.risk_result_disposition, "risk_result_disposition"),
            (self.policy_disposition, "policy_disposition"),
        ):
            if not isinstance(value, ProposalDisposition):
                raise TypeError(f"{field_name} must be a ProposalDisposition")


@dataclass(frozen=True, slots=True)
class RiskSizingEvaluationResult:
    """
    ISSUABLE always carries a constructed proposal and zero reasons.
    NOT_ISSUABLE always carries proposal=None and at least one
    reason. There is no other combination.
    """

    issuability: RiskSizingIssuability
    reasons: tuple[RiskSizingIssueReason, ...]
    proposal: RiskSizingProposal | None

    def __post_init__(self) -> None:
        if not isinstance(self.issuability, RiskSizingIssuability):
            raise TypeError("issuability must be a RiskSizingIssuability")

        if not isinstance(self.reasons, tuple) or not all(
            isinstance(item, RiskSizingIssueReason) for item in self.reasons
        ):
            raise TypeError("reasons must be a tuple of RiskSizingIssueReason")

        if self.proposal is not None and not isinstance(
            self.proposal, RiskSizingProposal
        ):
            raise TypeError("proposal must be a RiskSizingProposal or None")

        if self.issuability is RiskSizingIssuability.ISSUABLE:
            if self.proposal is None:
                raise ValueError("ISSUABLE requires a constructed proposal")

            if self.reasons:
                raise ValueError("ISSUABLE must not carry reasons")
        else:
            if self.proposal is not None:
                raise ValueError("NOT_ISSUABLE must not carry a proposal")

            if not self.reasons:
                raise ValueError("NOT_ISSUABLE requires at least one reason")


def evaluate_risk_sizing_proposal(
    evaluation_input: RiskSizingEvaluationInput,
) -> RiskSizingEvaluationResult:
    """
    Pure, deterministic evaluation. Preflight reasons are collected in
    a fixed order: candidate disposition, price disposition,
    risk-result disposition, policy disposition, candidate identity,
    policy-reference validity, policy mismatch. If any reason exists,
    RiskSizingProposal is never constructed. Otherwise it is
    constructed exactly once from the input's proposal-shaped fields;
    a deterministic TypeError/ValueError from that construction is
    converted to NOT_ISSUABLE + INVALID_PROPOSAL_INPUT rather than
    repaired.

    No wall-clock, random, or lookup participates - the same input
    always yields a field-equivalent result.
    """

    if not isinstance(evaluation_input, RiskSizingEvaluationInput):
        raise TypeError(
            "evaluation_input must be a RiskSizingEvaluationInput"
        )

    reasons: list[RiskSizingIssueReason] = []

    if evaluation_input.candidate_disposition is not ProposalDisposition.CURRENT:
        reasons.append(RiskSizingIssueReason.CANDIDATE_NOT_CURRENT)

    if evaluation_input.price_disposition is not ProposalDisposition.CURRENT:
        reasons.append(RiskSizingIssueReason.PRICE_NOT_CURRENT)

    if (
        evaluation_input.risk_result_disposition
        is not ProposalDisposition.CURRENT
    ):
        reasons.append(RiskSizingIssueReason.RISK_RESULT_NOT_CURRENT)

    if evaluation_input.policy_disposition is not ProposalDisposition.CURRENT:
        reasons.append(RiskSizingIssueReason.POLICY_NOT_CURRENT)

    if evaluation_input.candidate_state is not IdentityState.KNOWN:
        reasons.append(RiskSizingIssueReason.CANDIDATE_IDENTITY_NOT_KNOWN)

    governing_policy = evaluation_input.governing_policy

    if _blank(governing_policy.policy_id) or _blank(
        governing_policy.policy_version
    ):
        reasons.append(RiskSizingIssueReason.POLICY_REFERENCE_INVALID)
    elif (
        governing_policy.policy_id != evaluation_input.policy_id
        or governing_policy.policy_version != evaluation_input.policy_version
    ):
        reasons.append(RiskSizingIssueReason.POLICY_MISMATCH)

    if reasons:
        return RiskSizingEvaluationResult(
            issuability=RiskSizingIssuability.NOT_ISSUABLE,
            reasons=tuple(reasons),
            proposal=None,
        )

    try:
        proposal = RiskSizingProposal(
            proposal_id=evaluation_input.proposal_id,
            revision=evaluation_input.revision,
            generated_at=evaluation_input.generated_at,
            supersedes_revision=evaluation_input.supersedes_revision,
            instrument_reference_kind=evaluation_input.instrument_reference_kind,
            instrument_reference=evaluation_input.instrument_reference,
            direction=evaluation_input.direction,
            quantity=evaluation_input.quantity,
            quantity_unit=evaluation_input.quantity_unit,
            notional=evaluation_input.notional,
            notional_currency=evaluation_input.notional_currency,
            reference_price=evaluation_input.reference_price,
            reference_price_currency=evaluation_input.reference_price_currency,
            reference_price_unit=evaluation_input.reference_price_unit,
            reference_price_source_kind=(
                evaluation_input.reference_price_source_kind
            ),
            reference_price_source_reference=(
                evaluation_input.reference_price_source_reference
            ),
            risk_result_id=evaluation_input.risk_result_id,
            risk_result_revision=evaluation_input.risk_result_revision,
            policy_id=evaluation_input.policy_id,
            policy_version=evaluation_input.policy_version,
            candidate_state=evaluation_input.candidate_state,
            candidate_reference_kind=evaluation_input.candidate_reference_kind,
            candidate_reference=evaluation_input.candidate_reference,
            strategy_reference_state=evaluation_input.strategy_reference_state,
            strategy_reference=evaluation_input.strategy_reference,
            strategy_version_state=evaluation_input.strategy_version_state,
            strategy_version=evaluation_input.strategy_version,
            risk_amount=evaluation_input.risk_amount,
            risk_amount_currency=evaluation_input.risk_amount_currency,
            risk_amount_unit=evaluation_input.risk_amount_unit,
        )
    except (TypeError, ValueError):
        return RiskSizingEvaluationResult(
            issuability=RiskSizingIssuability.NOT_ISSUABLE,
            reasons=(RiskSizingIssueReason.INVALID_PROPOSAL_INPUT,),
            proposal=None,
        )

    return RiskSizingEvaluationResult(
        issuability=RiskSizingIssuability.ISSUABLE,
        reasons=(),
        proposal=proposal,
    )
