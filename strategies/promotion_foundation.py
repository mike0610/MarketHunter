"""
MarketHunter

strategies/promotion_foundation.py

Module:
StrategyVersion Promotion Decision Foundation - Slice 1: immutable
promotion candidate/decision structural contracts only

Responsibilities:
- Define StrategyPromotionReference: an opaque, locally-scoped
  kind+reference provenance pointer used across candidate/decision
  ref collections.
- Define StrategyPromotionCandidate: an exact, immutable proposal
  bundle for one canonical StrategyIdentity - a proposed_version plus
  exact governed reference collections. This is a proposal only; it
  is not a StrategyVersion and cannot mint one.
- Define StrategyPromotionOutcome: the exact final outcome
  vocabulary, APPROVED | REJECTED only.
- Define StrategyPromotionDecisionReference and
  StrategyPromotionDecision: an exact, immutable final semantic
  promotion decision over one candidate.

Non-goals (frozen by MH-STRATEGY-VERSION-PROMOTION-COUNCIL-001
Council reconciliation and MH-STRATEGY-VERSION-PROMOTION-DECISION-
LEAD-001 boundary):
- This module defines value objects and pure constructor validation
  only. It exposes no writer, evaluator, service, repository, or
  issuance function of any kind. The sole semantic writer is the
  Strategy domain / Strategy Promotion Authority, which does not yet
  exist here.
- Strategy Registry remains the separate, sole canonical issuer/
  persister of a real StrategyVersion. An APPROVED
  StrategyPromotionDecision is a prerequisite the Registry may later
  consume - it is never itself an issuance, and this module never
  constructs or references a real StrategyVersion.
- The final outcome vocabulary is exactly APPROVED | REJECTED.
  UNKNOWN, UNAVAILABLE, CONFLICT, identity/version mismatch, a
  missing mandatory governed reference, unresolved provenance, and
  incomplete external evidence are non-decidable prerequisites, not
  enum values and not aliases for REJECTED. Slice 1 represents their
  fail-closed state only as the absence of a valid final
  StrategyPromotionDecision - it never normalizes them into one.
- No quantitative promotion criteria, evidence completeness policy,
  candidate discovery, automatic evaluation, scoring, or backtest
  threshold logic of any kind.
- No current/latest/default/nearest/SemVer inference or ordering.
  proposed_version and every reference string are opaque,
  caller-supplied text - never parsed, ordered, or normalized.
- No mutation, backfill, or repair. No generated identifiers,
  versions, or timestamps - decided_at is mandatory, explicit,
  caller-supplied, timezone-aware input only.
- No Runtime Release Manifest, StrategyExecutionBinding, Scanner/
  services/pipeline, Research/Strategy Lab, backtests/Simulation,
  Risk, Portfolio, Trading, Execution, persistence/repositories, DB,
  API/UI, config/runtime/deploy, wall-clock, or Git/GitHub import or
  wiring of any kind.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from strategies.registry_foundation import StrategyIdentity


def _require_nonblank(value: object, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a str")

    if not value.strip():
        raise ValueError(f"{field_name} must be non-blank")


def _require_reference_tuple(value: object, field_name: str) -> None:
    if not isinstance(value, tuple) or not all(
        isinstance(item, StrategyPromotionReference) for item in value
    ):
        raise TypeError(
            f"{field_name} must be a tuple of StrategyPromotionReference"
        )


@dataclass(frozen=True, slots=True)
class StrategyPromotionReference:
    """
    Opaque, locally-scoped kind+reference provenance pointer.
    reference_kind and reference are caller-supplied contract
    vocabulary only - no dereference, scoring, schema interpretation,
    or normalization.
    """

    reference_kind: str
    reference: str

    def __post_init__(self) -> None:
        _require_nonblank(self.reference_kind, "reference_kind")
        _require_nonblank(self.reference, "reference")


@dataclass(frozen=True, slots=True)
class StrategyPromotionCandidate:
    """
    Exact, immutable proposal bundle for one canonical
    StrategyIdentity: a proposed opaque version plus exact governed
    reference collections. This is a proposal only - it is not a
    StrategyVersion and no method or function on this type mints one.
    Constructor performs structural validation only.
    """

    strategy_identity: StrategyIdentity
    proposed_version: str
    rules_config_refs: tuple[StrategyPromotionReference, ...]
    artifact_refs: tuple[StrategyPromotionReference, ...]
    evidence_refs: tuple[StrategyPromotionReference, ...]
    lineage_refs: tuple[StrategyPromotionReference, ...]
    provenance_refs: tuple[StrategyPromotionReference, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.strategy_identity, StrategyIdentity):
            raise TypeError(
                "strategy_identity must be a StrategyIdentity"
            )

        _require_nonblank(self.proposed_version, "proposed_version")

        for field_name in (
            "rules_config_refs",
            "artifact_refs",
            "evidence_refs",
            "lineage_refs",
            "provenance_refs",
        ):
            _require_reference_tuple(
                getattr(self, field_name), field_name
            )


class StrategyPromotionOutcome(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class StrategyPromotionDecisionReference:
    """
    Exact opaque (decision_id, decision_version) pair. No ordering,
    current/latest, or SemVer meaning.
    """

    decision_id: str
    decision_version: str

    def __post_init__(self) -> None:
        _require_nonblank(self.decision_id, "decision_id")
        _require_nonblank(self.decision_version, "decision_version")


@dataclass(frozen=True, slots=True)
class StrategyPromotionDecision:
    """
    Exact, immutable final semantic promotion decision over one
    StrategyPromotionCandidate. decided_at is mandatory, explicit,
    caller-supplied, timezone-aware input - never generated by this
    module. This is a structural value object only; it decides
    nothing and evaluates no evidence itself.
    """

    reference: StrategyPromotionDecisionReference
    candidate: StrategyPromotionCandidate
    outcome: StrategyPromotionOutcome
    decided_at: datetime
    decision_provenance_refs: tuple[StrategyPromotionReference, ...]

    def __post_init__(self) -> None:
        if not isinstance(
            self.reference, StrategyPromotionDecisionReference
        ):
            raise TypeError(
                "reference must be a StrategyPromotionDecisionReference"
            )

        if not isinstance(self.candidate, StrategyPromotionCandidate):
            raise TypeError(
                "candidate must be a StrategyPromotionCandidate"
            )

        if not isinstance(self.outcome, StrategyPromotionOutcome):
            raise TypeError(
                "outcome must be a StrategyPromotionOutcome"
            )

        if not isinstance(self.decided_at, datetime):
            raise TypeError("decided_at must be a datetime")

        if self.decided_at.tzinfo is None or (
            self.decided_at.tzinfo.utcoffset(self.decided_at) is None
        ):
            raise ValueError("decided_at must be timezone-aware")

        _require_reference_tuple(
            self.decision_provenance_refs, "decision_provenance_refs"
        )
