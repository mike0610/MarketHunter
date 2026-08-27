"""
MarketHunter

portfolio_v1/monetary_authorization.py

Module:
Portfolio Monetary Authorization Record - Slice 1: immutable,
versioned final Portfolio monetary authorization structural record
and pure constructor validation only

Responsibilities:
- Define PortfolioMonetaryAuthorizationOutcome: the exact final
  outcome vocabulary, PROCEED | BLOCK only.
- Define PortfolioMonetaryAuthorizationRef: an opaque, locally-scoped
  kind+reference provenance pointer, reused for the exact capital,
  exposure, policy, and scope references this record carries.
- Define PortfolioMonetaryAuthorizationRecord: an exact, immutable
  final Portfolio monetary authorization over one exact
  RiskSizingProposal (referenced by id + revision only), structural
  validation only.

Non-goals (frozen by MH-PORTFOLIO-CAPITAL-SIZING-BOUNDARY-ARCH-001 /
MH-PORTFOLIO-AUTH-RECORD-LEAD-001 / MH-PORTFOLIO-AUTH-RECORD-HOLD-
PACK-001):
- Portfolio consumes the exact RiskSizingProposal/capital/exposure/
  policy/scope references supplied by the caller. It MUST NOT resize,
  cap, recalculate, derive, synthesize, or replace RiskSizingProposal
  monetary semantics - this module contains no arithmetic, sizing
  formula, or admissibility policy of any kind.
- Readiness/usability (e.g. a separate MonetaryAdmissionReadiness
  result) is not final monetary authorization. Constructing this
  record is validation only, never a runtime issuer, service,
  repository, or persistence writer.
- Unresolved/UNKNOWN/UNAVAILABLE/CONFLICT/NOT_APPLICABLE/STALE/
  SUPERSEDED/SOURCE_CHANGED evidence states are not represented here
  at all - no final PortfolioMonetaryAuthorizationRecord is minted
  for them, and they are never inferred into PROCEED or BLOCK.
- No current/latest/default/nearest/SemVer inference, lookup/
  resolver, repair, historical reconstruction, or backfill of any
  kind. authorization_id and authorization_version are exact, opaque,
  caller-supplied text - never generated, parsed, or ordered.
- Future Trading-owned OrderIntent may consume only the exact
  (authorization_id, authorization_version) of a PROCEED record.
  BLOCK is ineligible as a parent reference. This module does not
  import, construct, or issue OrderIntent or Execution behavior.
- No wall clock, random, or scheduler usage. evaluated_at is an
  explicit, caller-supplied, timezone-aware governed fact.
- No Portfolio domain/readiness/exposure implementation, Risk,
  AccountCapitalSnapshot, Trading, Execution, Research, Scanner,
  services, DB/repositories, API/UI, config, broker/exchange, clock,
  or open-PR (Entry Trigger / Market Data / Data Quality) import or
  wiring of any kind. References are stored as exact opaque strings/
  ints only - never as imported upstream payload objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


def _require_nonblank(value: object, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a str")

    if not value.strip():
        raise ValueError(f"{field_name} must be non-blank")


def _require_positive_int(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an int")

    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


class PortfolioMonetaryAuthorizationOutcome(str, Enum):
    PROCEED = "PROCEED"
    BLOCK = "BLOCK"


@dataclass(frozen=True, slots=True)
class PortfolioMonetaryAuthorizationRef:
    """
    Opaque, locally-scoped kind+reference provenance pointer. Used
    separately for the capital, exposure, policy, and scope
    references this record carries. reference_kind and reference are
    caller-supplied contract vocabulary only - no dereference,
    scoring, schema interpretation, or normalization.
    """

    reference_kind: str
    reference: str

    def __post_init__(self) -> None:
        _require_nonblank(self.reference_kind, "reference_kind")
        _require_nonblank(self.reference, "reference")


@dataclass(frozen=True, slots=True)
class PortfolioMonetaryAuthorizationRecord:
    """
    Exact, immutable, versioned final Portfolio monetary
    authorization over one exact RiskSizingProposal, identified by
    exact opaque (proposal_id, revision) reference only - never a
    resized/recalculated/synthesized replacement.

    PROCEED requires reasons == (). BLOCK requires at least one
    non-blank reason. evaluated_at is a mandatory, timezone-aware,
    caller-supplied governed fact - never derived from a wall clock.
    """

    authorization_id: str
    authorization_version: str
    risk_sizing_proposal_id: str
    risk_sizing_proposal_revision: int
    capital_ref: PortfolioMonetaryAuthorizationRef
    exposure_ref: PortfolioMonetaryAuthorizationRef
    policy_ref: PortfolioMonetaryAuthorizationRef
    scope_ref: PortfolioMonetaryAuthorizationRef
    outcome: PortfolioMonetaryAuthorizationOutcome
    reasons: tuple[str, ...]
    evaluated_at: datetime

    def __post_init__(self) -> None:
        _require_nonblank(self.authorization_id, "authorization_id")
        _require_nonblank(
            self.authorization_version, "authorization_version"
        )
        _require_nonblank(
            self.risk_sizing_proposal_id, "risk_sizing_proposal_id"
        )
        _require_positive_int(
            self.risk_sizing_proposal_revision,
            "risk_sizing_proposal_revision",
        )

        for ref, field_name in (
            (self.capital_ref, "capital_ref"),
            (self.exposure_ref, "exposure_ref"),
            (self.policy_ref, "policy_ref"),
            (self.scope_ref, "scope_ref"),
        ):
            if not isinstance(ref, PortfolioMonetaryAuthorizationRef):
                raise TypeError(
                    f"{field_name} must be a "
                    "PortfolioMonetaryAuthorizationRef"
                )

        if not isinstance(
            self.outcome, PortfolioMonetaryAuthorizationOutcome
        ):
            raise TypeError(
                "outcome must be a PortfolioMonetaryAuthorizationOutcome"
            )

        if not isinstance(self.reasons, tuple) or not all(
            isinstance(reason, str) for reason in self.reasons
        ):
            raise TypeError("reasons must be a tuple of str")

        for reason in self.reasons:
            _require_nonblank(reason, "reason")

        if not isinstance(self.evaluated_at, datetime):
            raise TypeError("evaluated_at must be a datetime")

        if self.evaluated_at.tzinfo is None or (
            self.evaluated_at.tzinfo.utcoffset(self.evaluated_at)
            is None
        ):
            raise ValueError("evaluated_at must be timezone-aware")

        if (
            self.outcome
            == PortfolioMonetaryAuthorizationOutcome.PROCEED
        ):
            if self.reasons != ():
                raise ValueError(
                    "PROCEED outcome requires reasons == ()"
                )
        elif len(self.reasons) < 1:
            raise ValueError(
                "BLOCK outcome requires at least one reason"
            )
