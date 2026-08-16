"""
MarketHunter

research/validation/contracts.py

Slice 1 immutable boundary/value objects for strategy mathematical
validation: a validation run request, per-check evidence, and the
overall evidence record. No canonical lifecycle, persistence, or API
ownership is introduced here - these are pure input/output value
objects only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

_MANDATORY_CHECK_IDS = frozenset(
    {
        "WFV_PREDECLARATION",
        "PROSPECTIVE_SELECTION",
        "PURGING",
        "EMBARGO",
        "FINAL_OOS_ACCEPTANCE",
    }
)


class ReferenceState(str, Enum):
    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"


class CheckApplicability(str, Enum):
    APPLICABLE = "APPLICABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN = "UNKNOWN"


class CheckOutcome(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ValidationCheckId(str, Enum):
    WFV_PREDECLARATION = "WFV_PREDECLARATION"
    PROSPECTIVE_SELECTION = "PROSPECTIVE_SELECTION"
    PURGING = "PURGING"
    EMBARGO = "EMBARGO"
    FINAL_OOS_ACCEPTANCE = "FINAL_OOS_ACCEPTANCE"


def _require_nonblank(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-blank string")


def _require_optional_nonblank(value: str | None, field_name: str) -> None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise ValueError(f"{field_name} must be a non-blank string when provided")


def _require_aware_datetime(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")


def _require_tuple_of_str(value: tuple, field_name: str) -> None:
    if not isinstance(value, tuple) or not all(
        isinstance(item, str) for item in value
    ):
        raise TypeError(f"{field_name} must be a tuple of str")


def _require_nonempty_tuple_of_nonblank_str(value: tuple, field_name: str) -> None:
    _require_tuple_of_str(value, field_name)
    if len(value) == 0:
        raise ValueError(f"{field_name} must be non-empty")
    for item in value:
        _require_nonblank(item, f"{field_name} entry")


@dataclass(frozen=True, slots=True)
class ValidationPolicyRef:
    """
    Reference to the governing validation policy and the canonical
    claims it derives from. Provenance only - no policy content is
    interpreted here.
    """

    policy_id: str
    policy_version: str
    source_claim_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_nonblank(self.policy_id, "policy_id")
        _require_nonblank(self.policy_version, "policy_version")
        _require_nonempty_tuple_of_nonblank_str(
            self.source_claim_ids, "source_claim_ids"
        )


@dataclass(frozen=True, slots=True)
class ValidationRunRequest:
    """
    Caller-supplied request to run strategy mathematical validation.
    Input contract only - no lookup, inference, or orchestration.
    """

    run_id: str
    requested_at: datetime
    strategy_id: str
    strategy_version_state: ReferenceState
    strategy_version: str | None
    dataset_reference: str
    time_range_reference: str
    configuration_reference: str
    policy: ValidationPolicyRef

    def __post_init__(self) -> None:
        _require_nonblank(self.run_id, "run_id")
        _require_aware_datetime(self.requested_at, "requested_at")
        _require_nonblank(self.strategy_id, "strategy_id")

        if not isinstance(self.strategy_version_state, ReferenceState):
            raise TypeError("strategy_version_state must be a ReferenceState")

        if self.strategy_version_state is ReferenceState.KNOWN:
            if self.strategy_version is None:
                raise ValueError(
                    "KNOWN strategy_version_state requires strategy_version"
                )
            _require_nonblank(self.strategy_version, "strategy_version")
        else:
            if self.strategy_version is not None:
                raise ValueError(
                    "UNKNOWN strategy_version_state requires strategy_version "
                    "to be None"
                )

        _require_nonblank(self.dataset_reference, "dataset_reference")
        _require_nonblank(self.time_range_reference, "time_range_reference")
        _require_nonblank(self.configuration_reference, "configuration_reference")

        if not isinstance(self.policy, ValidationPolicyRef):
            raise TypeError("policy must be a ValidationPolicyRef")


@dataclass(frozen=True, slots=True)
class ValidationCheckEvidence:
    """
    Evidence for a single mandatory validation check. Uncertainty
    fails closed: an UNKNOWN or NOT_APPLICABLE applicability must
    carry an explicit reason and the matching outcome, never a
    success/current/canonical outcome.
    """

    check_id: ValidationCheckId
    applicability: CheckApplicability
    outcome: CheckOutcome
    reason: str | None
    evidence_references: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.check_id, ValidationCheckId):
            raise TypeError("check_id must be a ValidationCheckId")

        if not isinstance(self.applicability, CheckApplicability):
            raise TypeError("applicability must be a CheckApplicability")

        if not isinstance(self.outcome, CheckOutcome):
            raise TypeError("outcome must be a CheckOutcome")

        _require_tuple_of_str(self.evidence_references, "evidence_references")
        _require_optional_nonblank(self.reason, "reason")

        if self.applicability is CheckApplicability.NOT_APPLICABLE:
            if self.outcome is not CheckOutcome.NOT_APPLICABLE:
                raise ValueError(
                    "NOT_APPLICABLE applicability requires NOT_APPLICABLE outcome"
                )
            if self.reason is None:
                raise ValueError(
                    "NOT_APPLICABLE applicability requires an explicit reason"
                )
        elif self.applicability is CheckApplicability.UNKNOWN:
            if self.outcome is not CheckOutcome.UNKNOWN:
                raise ValueError(
                    "UNKNOWN applicability requires UNKNOWN outcome"
                )
            if self.reason is None:
                raise ValueError(
                    "UNKNOWN applicability requires an explicit reason"
                )
        else:
            if self.outcome not in (CheckOutcome.PASS, CheckOutcome.FAIL):
                raise ValueError(
                    "APPLICABLE applicability requires PASS or FAIL outcome"
                )

            if self.outcome is CheckOutcome.PASS and len(
                self.evidence_references
            ) == 0:
                raise ValueError("PASS outcome requires at least one evidence reference")

            if self.outcome is CheckOutcome.FAIL and self.reason is None:
                raise ValueError("FAIL outcome requires an explicit reason")


@dataclass(frozen=True, slots=True)
class ValidationEvidence:
    """
    The full evidence record for one validation run: one entry per
    mandatory check, plus provenance for the dataset, configuration,
    chronology, and reproducibility inputs. Historical evidence is
    immutable; supersedes/refines are references only, never
    mutation.
    """

    evidence_id: str
    run_id: str
    created_at: datetime
    strategy_id: str
    strategy_version_state: ReferenceState
    strategy_version: str | None
    policy: ValidationPolicyRef
    dataset_reference: str
    time_range_reference: str
    configuration_reference: str
    chronology_basis_reference: str
    train_test_origin_references: tuple[str, ...]
    parameter_freeze_state: ReferenceState
    parameter_freeze_at: datetime | None
    checks: tuple[ValidationCheckEvidence, ...]
    reproducibility_reference: str
    warnings: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    invalidations: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    supersedes_evidence_id: str | None = None
    refines_evidence_id: str | None = None

    def __post_init__(self) -> None:
        _require_nonblank(self.evidence_id, "evidence_id")
        _require_nonblank(self.run_id, "run_id")
        _require_aware_datetime(self.created_at, "created_at")
        _require_nonblank(self.strategy_id, "strategy_id")

        if not isinstance(self.strategy_version_state, ReferenceState):
            raise TypeError("strategy_version_state must be a ReferenceState")

        if self.strategy_version_state is ReferenceState.KNOWN:
            if self.strategy_version is None:
                raise ValueError(
                    "KNOWN strategy_version_state requires strategy_version"
                )
            _require_nonblank(self.strategy_version, "strategy_version")
        else:
            if self.strategy_version is not None:
                raise ValueError(
                    "UNKNOWN strategy_version_state requires strategy_version "
                    "to be None"
                )

        if not isinstance(self.policy, ValidationPolicyRef):
            raise TypeError("policy must be a ValidationPolicyRef")

        _require_nonblank(self.dataset_reference, "dataset_reference")
        _require_nonblank(self.time_range_reference, "time_range_reference")
        _require_nonblank(self.configuration_reference, "configuration_reference")
        _require_nonblank(
            self.chronology_basis_reference, "chronology_basis_reference"
        )
        _require_nonempty_tuple_of_nonblank_str(
            self.train_test_origin_references, "train_test_origin_references"
        )

        if not isinstance(self.parameter_freeze_state, ReferenceState):
            raise TypeError("parameter_freeze_state must be a ReferenceState")

        if self.parameter_freeze_state is ReferenceState.KNOWN:
            if self.parameter_freeze_at is None:
                raise ValueError(
                    "KNOWN parameter_freeze_state requires parameter_freeze_at"
                )
            _require_aware_datetime(self.parameter_freeze_at, "parameter_freeze_at")
        else:
            if self.parameter_freeze_at is not None:
                raise ValueError(
                    "UNKNOWN parameter_freeze_state requires parameter_freeze_at "
                    "to be None"
                )

        if not isinstance(self.checks, tuple) or not all(
            isinstance(item, ValidationCheckEvidence) for item in self.checks
        ):
            raise TypeError("checks must be a tuple of ValidationCheckEvidence")

        check_ids = [check.check_id.value for check in self.checks]

        if len(check_ids) != len(set(check_ids)):
            raise ValueError("checks must not contain a duplicate check_id")

        if set(check_ids) != _MANDATORY_CHECK_IDS:
            raise ValueError(
                "checks must contain each mandatory check_id exactly once: "
                f"{sorted(_MANDATORY_CHECK_IDS)}"
            )

        _require_nonblank(
            self.reproducibility_reference, "reproducibility_reference"
        )

        _require_tuple_of_str(self.warnings, "warnings")
        _require_tuple_of_str(self.unknowns, "unknowns")
        _require_tuple_of_str(self.invalidations, "invalidations")
        _require_tuple_of_str(self.conflicts, "conflicts")

        _require_optional_nonblank(
            self.supersedes_evidence_id, "supersedes_evidence_id"
        )
        _require_optional_nonblank(self.refines_evidence_id, "refines_evidence_id")
