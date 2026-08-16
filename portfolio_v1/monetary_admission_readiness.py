"""
MarketHunter

Module:
Portfolio Monetary Admission Contract - Slice 1 (readiness-only)

Responsibilities:
- Define a pure, immutable Portfolio-side readiness contract that
  preserves exact capital/risk/exposure/policy evidence identity and
  fails closed before any monetary admission.
- Define assess_monetary_admission_readiness(): a pure function that
  evaluates that evidence and returns a readiness result.

Non-goals (frozen by ARCH-REQ-PORTFOLIO-MONETARY-POLICY-001):
- No sizing formula, percentage, leverage, Kelly, concentration, or
  risk-budget policy of any kind.
- No PortfolioDecision or PositionSizingDecision is emitted or
  consumed here - those belong to the separate, pre-existing
  portfolio_v1.domain/assessment modules and are untouched.
- No promotion of legacy RiskResult monetary fields (account_size,
  position_size, risk_amount, risk_percent) to authoritative sizing
  status - this module never reads them.
- No ResearchTrade.notional mapping or fallback of any kind.
- No FX/base-currency handling, no stale-age/freshness calculation -
  evidence disposition (AdmissionEvidenceState) is caller-supplied,
  not computed here.
- Slice 1 invariant: no authoritative Risk sizing-proposal seam exists
  on current master, so assess_monetary_admission_readiness() always
  returns NOT_READY with RISK_SIZING_PROPOSAL_NOT_GOVERNED among its
  reasons. READY_FOR_ADMISSION is reserved contract vocabulary only
  and is structurally unreachable from this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from models.account_capital_snapshot import AccountCapitalSnapshot
from models.risk_result_record import IdentityState, RiskResultRecord
from portfolio.capital_snapshot import CapitalSnapshotUsability
from portfolio_v1.domain import ExposureState
from portfolio_v1.exposure_snapshot import PortfolioExposureSnapshot


class AdmissionReadiness(str, Enum):
    READY_FOR_ADMISSION = "READY_FOR_ADMISSION"
    NOT_READY = "NOT_READY"


class AdmissionEvidenceState(str, Enum):
    """
    Caller-supplied evidence disposition only. Not a lifecycle and
    not a freshness calculation - this module never computes whether
    evidence is current, stale, superseded, conflicting, or affected
    by a changed source; the caller must supply that classification.
    """

    CURRENT = "CURRENT"
    UNKNOWN = "UNKNOWN"
    STALE = "STALE"
    SUPERSEDED = "SUPERSEDED"
    CONFLICT = "CONFLICT"
    SOURCE_CHANGED = "SOURCE_CHANGED"


class AdmissionReadinessReason(str, Enum):
    CAPITAL_NOT_USABLE = "CAPITAL_NOT_USABLE"
    CAPITAL_REFERENCE_INCOMPLETE = "CAPITAL_REFERENCE_INCOMPLETE"
    RISK_EVIDENCE_NOT_CURRENT = "RISK_EVIDENCE_NOT_CURRENT"
    RISK_PROVENANCE_INCOMPLETE = "RISK_PROVENANCE_INCOMPLETE"
    EXPOSURE_EVIDENCE_NOT_CURRENT = "EXPOSURE_EVIDENCE_NOT_CURRENT"
    EXPOSURE_NOT_MEASURED = "EXPOSURE_NOT_MEASURED"
    EXPOSURE_REFERENCE_INCOMPLETE = "EXPOSURE_REFERENCE_INCOMPLETE"
    RISK_SIZING_PROPOSAL_NOT_GOVERNED = "RISK_SIZING_PROPOSAL_NOT_GOVERNED"


def _blank(value: str | None) -> bool:
    return value is None or not value.strip()


def _require_nonblank_str(value: object, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a str")

    if not value.strip():
        raise ValueError(f"{field_name} must be non-blank")


@dataclass(frozen=True, slots=True)
class MonetaryAdmissionPolicyRef:
    """
    Reference to the governing Portfolio monetary-admission policy.
    Provenance only - no policy content or threshold is interpreted
    here.
    """

    policy_id: str
    policy_version: str

    def __post_init__(self) -> None:
        _require_nonblank_str(self.policy_id, "policy_id")
        _require_nonblank_str(self.policy_version, "policy_version")


@dataclass(frozen=True, slots=True)
class MonetaryAdmissionReadinessInput:
    """
    Caller-supplied evidence for one monetary-admission readiness
    evaluation. Every referenced object must already be an instance
    of its governed type - this is a read-only composition boundary,
    never a lookup or inference point.
    """

    capital_snapshot: AccountCapitalSnapshot
    capital_usability: CapitalSnapshotUsability
    risk_result: RiskResultRecord
    risk_evidence_state: AdmissionEvidenceState
    exposure_snapshot: PortfolioExposureSnapshot
    exposure_evidence_state: AdmissionEvidenceState
    policy: MonetaryAdmissionPolicyRef
    evaluated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.capital_snapshot, AccountCapitalSnapshot):
            raise TypeError(
                "capital_snapshot must be an AccountCapitalSnapshot"
            )

        if not isinstance(self.capital_usability, CapitalSnapshotUsability):
            raise TypeError(
                "capital_usability must be a CapitalSnapshotUsability"
            )

        if not isinstance(self.risk_result, RiskResultRecord):
            raise TypeError("risk_result must be a RiskResultRecord")

        if not isinstance(self.risk_evidence_state, AdmissionEvidenceState):
            raise TypeError(
                "risk_evidence_state must be an AdmissionEvidenceState"
            )

        if not isinstance(self.exposure_snapshot, PortfolioExposureSnapshot):
            raise TypeError(
                "exposure_snapshot must be a PortfolioExposureSnapshot"
            )

        if not isinstance(
            self.exposure_evidence_state, AdmissionEvidenceState
        ):
            raise TypeError(
                "exposure_evidence_state must be an AdmissionEvidenceState"
            )

        if not isinstance(self.policy, MonetaryAdmissionPolicyRef):
            raise TypeError("policy must be a MonetaryAdmissionPolicyRef")

        if not isinstance(self.evaluated_at, datetime):
            raise TypeError("evaluated_at must be a datetime")

        if self.evaluated_at.tzinfo is None:
            raise ValueError("evaluated_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class MonetaryAdmissionReadinessResult:
    """
    The outcome of one readiness evaluation. Carries only enough
    provenance to reconstruct exactly what evidence and policy were
    evaluated - never a monetary amount, never a decision beyond
    readiness itself.
    """

    readiness: AdmissionReadiness
    reasons: tuple[AdmissionReadinessReason, ...]
    evaluated_at: datetime
    capital_snapshot_id: str | None
    risk_result_id: str
    risk_result_revision: int
    exposure_snapshot_id: str
    policy_id: str
    policy_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.readiness, AdmissionReadiness):
            raise TypeError("readiness must be an AdmissionReadiness")

        if not isinstance(self.reasons, tuple) or not all(
            isinstance(item, AdmissionReadinessReason) for item in self.reasons
        ):
            raise TypeError(
                "reasons must be a tuple of AdmissionReadinessReason"
            )

        if self.readiness is AdmissionReadiness.NOT_READY and not self.reasons:
            raise ValueError("NOT_READY requires at least one reason")

        if (
            self.readiness is AdmissionReadiness.READY_FOR_ADMISSION
            and self.reasons
        ):
            raise ValueError(
                "READY_FOR_ADMISSION must not carry reasons - reasons "
                "imply this result is not actually ready"
            )


def assess_monetary_admission_readiness(
    admission_input: MonetaryAdmissionReadinessInput,
) -> MonetaryAdmissionReadinessResult:
    """
    Evaluate whether the supplied evidence is ready for monetary
    admission. On current master there is no authoritative Risk
    sizing-proposal seam, so this always returns NOT_READY with
    RISK_SIZING_PROPOSAL_NOT_GOVERNED among the reasons - regardless
    of how complete every other piece of evidence is.
    """

    if not isinstance(admission_input, MonetaryAdmissionReadinessInput):
        raise TypeError(
            "admission_input must be a MonetaryAdmissionReadinessInput"
        )

    reasons: list[AdmissionReadinessReason] = []

    capital_snapshot = admission_input.capital_snapshot

    if admission_input.capital_usability is not CapitalSnapshotUsability.USABLE:
        reasons.append(AdmissionReadinessReason.CAPITAL_NOT_USABLE)
    elif (
        _blank(capital_snapshot.source_snapshot_id)
        or _blank(capital_snapshot.account_id)
        or _blank(capital_snapshot.environment)
        or _blank(capital_snapshot.currency)
        or capital_snapshot.as_of is None
    ):
        reasons.append(AdmissionReadinessReason.CAPITAL_REFERENCE_INCOMPLETE)

    risk_result = admission_input.risk_result

    if admission_input.risk_evidence_state is not AdmissionEvidenceState.CURRENT:
        reasons.append(AdmissionReadinessReason.RISK_EVIDENCE_NOT_CURRENT)

    if (
        risk_result.source_state is not IdentityState.KNOWN
        or risk_result.risk_policy_state is not IdentityState.KNOWN
    ):
        reasons.append(AdmissionReadinessReason.RISK_PROVENANCE_INCOMPLETE)

    exposure_snapshot = admission_input.exposure_snapshot

    if (
        admission_input.exposure_evidence_state
        is not AdmissionEvidenceState.CURRENT
    ):
        reasons.append(AdmissionReadinessReason.EXPOSURE_EVIDENCE_NOT_CURRENT)

    if exposure_snapshot.state is not ExposureState.MEASURED:
        reasons.append(AdmissionReadinessReason.EXPOSURE_NOT_MEASURED)

    if (
        _blank(exposure_snapshot.snapshot_id)
        or _blank(exposure_snapshot.provenance)
        or _blank(exposure_snapshot.generated_at)
    ):
        reasons.append(AdmissionReadinessReason.EXPOSURE_REFERENCE_INCOMPLETE)

    # Slice-1 invariant: no authoritative Risk sizing-proposal seam
    # exists on current master. This reason is always present, and
    # readiness is hardcoded to NOT_READY below - READY_FOR_ADMISSION
    # is unreachable from this function by construction, not merely
    # by the current data.
    reasons.append(AdmissionReadinessReason.RISK_SIZING_PROPOSAL_NOT_GOVERNED)

    return MonetaryAdmissionReadinessResult(
        readiness=AdmissionReadiness.NOT_READY,
        reasons=tuple(reasons),
        evaluated_at=admission_input.evaluated_at,
        capital_snapshot_id=capital_snapshot.source_snapshot_id,
        risk_result_id=risk_result.risk_result_id,
        risk_result_revision=risk_result.revision,
        exposure_snapshot_id=exposure_snapshot.snapshot_id,
        policy_id=admission_input.policy.policy_id,
        policy_version=admission_input.policy.policy_version,
    )
