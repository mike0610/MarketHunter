"""
MarketHunter

explainability/foundation.py

Module:
Explainability Layer - Slice 1 (provenance/binding foundation only)

Responsibilities:
- Define ExplanationRecord: an immutable, versioned artifact record
  identifying that a specific explanation revision was produced
  against exact target and evidence references.
- Define ExplanationTargetReference, ExplanationEvidenceReference,
  ExplanationGeneratorReference: exact, locally-scoped provenance
  pointers.
- Define assess_explanation_binding(): a pure, deterministic function
  that validates caller-supplied target/evidence reference
  consistency, disposition, and explicit lineage only.

Non-goals (frozen by ARCH-REQ-EXPLAINABILITY-FOUNDATION-001):
- No persistence, repository, service, or runtime writer of any
  kind. Slice 1 defines contracts and pure validation only.
- No automatic explanation generation, LLM/model/provider
  invocation, or generation runtime. ExplanationGeneratorReference is
  provenance only - it never implies AI/model decision authority.
- No free-text explanation body, claim, confidence, recommendation,
  or canonical reason taxonomy of any kind.
- No current-explanation selector, no "latest" ExplanationRecord
  lookup, no name/time-nearest fallback. Whether a live consumer
  requires the current revision is caller-supplied context
  (require_current), never computed here.
- Explanation is never decision/fact authority. This module never
  mints, repairs, approves, rejects, resizes, cancels, executes, or
  supersedes any Strategy/Risk/Portfolio/Trading/Execution/Research
  object - it validates caller-supplied reference consistency only,
  and never imports or touches those domains' models at all.
- No global evidence/artifact registry, no unified audit/event/
  read-model composition (CORE-GAP-03), no cross-clock precedence
  policy (CORE-GAP-04), no Manual Review permissions (CORE-GAP-07).
- No wiring into API, Dashboard, Reports, runtime, or deploy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ExplanationDisposition(str, Enum):
    """
    Caller-supplied disposition of one target/evidence binding read.
    Not a lifecycle and not a freshness calculation - this module
    never computes whether a reference is current, unavailable,
    stale, conflicting, or affected by a changed source; the caller
    must supply that classification.
    """

    CURRENT = "CURRENT"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"
    STALE = "STALE"
    CONFLICT = "CONFLICT"
    SUPERSEDED = "SUPERSEDED"
    SOURCE_CHANGED = "SOURCE_CHANGED"


class ExplanationUsability(str, Enum):
    USABLE = "USABLE"
    NOT_USABLE = "NOT_USABLE"


class ExplanationAssessmentReason(str, Enum):
    TARGET_UNRESOLVED = "TARGET_UNRESOLVED"
    TARGET_AMBIGUOUS = "TARGET_AMBIGUOUS"
    TARGET_DISPOSITION_NOT_USABLE = "TARGET_DISPOSITION_NOT_USABLE"
    TARGET_CURRENT_REQUIRED = "TARGET_CURRENT_REQUIRED"
    EVIDENCE_UNRESOLVED = "EVIDENCE_UNRESOLVED"
    EVIDENCE_AMBIGUOUS = "EVIDENCE_AMBIGUOUS"
    EVIDENCE_DISPOSITION_NOT_USABLE = "EVIDENCE_DISPOSITION_NOT_USABLE"
    EVIDENCE_CURRENT_REQUIRED = "EVIDENCE_CURRENT_REQUIRED"
    PREDECESSOR_UNRESOLVED = "PREDECESSOR_UNRESOLVED"
    PREDECESSOR_AMBIGUOUS = "PREDECESSOR_AMBIGUOUS"
    CROSS_EXPLANATION_SUPERSESSION = "CROSS_EXPLANATION_SUPERSESSION"


def _require_nonblank(value: object, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a str")

    if not value.strip():
        raise ValueError(f"{field_name} must be non-blank")


def _require_optional_nonblank(value: object, field_name: str) -> None:
    if value is not None:
        _require_nonblank(value, field_name)


def _require_positive_int(value: object, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an int")

    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _require_aware_datetime(value: object, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")

    if value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ExplanationTargetReference:
    """
    Exact, stable reference to the domain object an explanation is
    about. Never inferred from a display name, latest row, or
    nearest-time lookup - target_revision_or_version is opaque
    caller-supplied text when the target domain exposes one.
    """

    target_domain: str
    target_type: str
    target_id: str
    target_revision_or_version: str | None

    def __post_init__(self) -> None:
        _require_nonblank(self.target_domain, "target_domain")
        _require_nonblank(self.target_type, "target_type")
        _require_nonblank(self.target_id, "target_id")
        _require_optional_nonblank(
            self.target_revision_or_version, "target_revision_or_version"
        )


@dataclass(frozen=True, slots=True)
class ExplanationEvidenceReference:
    """
    Exact, opaque, locally-scoped reference to a piece of evidence
    consumed while producing an explanation. Not a global evidence
    registry - source_kind/source_id are caller-supplied contract
    vocabulary only.
    """

    source_kind: str
    source_id: str
    source_revision_or_version: str | None

    def __post_init__(self) -> None:
        _require_nonblank(self.source_kind, "source_kind")
        _require_nonblank(self.source_id, "source_id")
        _require_optional_nonblank(
            self.source_revision_or_version, "source_revision_or_version"
        )


@dataclass(frozen=True, slots=True)
class ExplanationGeneratorReference:
    """
    Optional provenance for whatever produced the explanation
    artifact. This is provenance only - it never implies AI/LLM
    decision authority, and it is intentionally kept separate from
    StrategyVersion and Risk policy identity.
    """

    generator_kind: str
    generator_id: str
    generator_version: str | None

    def __post_init__(self) -> None:
        _require_nonblank(self.generator_kind, "generator_kind")
        _require_nonblank(self.generator_id, "generator_id")
        _require_optional_nonblank(
            self.generator_version, "generator_version"
        )


@dataclass(frozen=True, slots=True)
class ExplanationRecord:
    """
    Immutable, versioned explanation-artifact record. Canonical only
    for the historical fact that this explanation revision was
    produced against exactly these target/evidence/generator
    references - never for the underlying target's truth. Revisions
    are append-only; a later revision never rewrites an earlier one.
    """

    explanation_id: str
    revision: int
    generated_at: datetime
    supersedes_revision: int | None
    target: ExplanationTargetReference
    evidence_references: tuple[ExplanationEvidenceReference, ...]
    generator_reference: ExplanationGeneratorReference | None

    def __post_init__(self) -> None:
        _require_nonblank(self.explanation_id, "explanation_id")
        _require_positive_int(self.revision, "revision")
        _require_aware_datetime(self.generated_at, "generated_at")

        if self.supersedes_revision is not None:
            if (
                not isinstance(self.supersedes_revision, int)
                or isinstance(self.supersedes_revision, bool)
            ):
                raise TypeError("supersedes_revision must be an int")

            if self.supersedes_revision <= 0:
                raise ValueError("supersedes_revision must be positive")

            if self.supersedes_revision == self.revision:
                raise ValueError(
                    "supersedes_revision cannot self-reference the same "
                    "revision"
                )

        if not isinstance(self.target, ExplanationTargetReference):
            raise TypeError("target must be an ExplanationTargetReference")

        if not isinstance(self.evidence_references, tuple) or not all(
            isinstance(item, ExplanationEvidenceReference)
            for item in self.evidence_references
        ):
            raise TypeError(
                "evidence_references must be a tuple of "
                "ExplanationEvidenceReference"
            )

        if not self.evidence_references:
            raise ValueError("evidence_references must be non-empty")

        if len(self.evidence_references) != len(set(self.evidence_references)):
            raise ValueError(
                "evidence_references must not contain duplicate references"
            )

        if self.generator_reference is not None and not isinstance(
            self.generator_reference, ExplanationGeneratorReference
        ):
            raise TypeError(
                "generator_reference must be an ExplanationGeneratorReference "
                "or None"
            )


@dataclass(frozen=True, slots=True)
class ExplanationTargetBinding:
    """
    Pairs one exact target reference with its caller-supplied
    disposition. Deliberately not a dict/positional-list pairing -
    each binding is a self-contained fact, so there is no alignment
    ambiguity between separate reference and disposition sequences.
    """

    reference: ExplanationTargetReference
    disposition: ExplanationDisposition

    def __post_init__(self) -> None:
        if not isinstance(self.reference, ExplanationTargetReference):
            raise TypeError("reference must be an ExplanationTargetReference")

        if not isinstance(self.disposition, ExplanationDisposition):
            raise TypeError("disposition must be an ExplanationDisposition")


@dataclass(frozen=True, slots=True)
class ExplanationEvidenceBinding:
    """
    Pairs one exact evidence reference with its caller-supplied
    disposition. Deliberately not a dict/positional-list pairing -
    see ExplanationTargetBinding.
    """

    reference: ExplanationEvidenceReference
    disposition: ExplanationDisposition

    def __post_init__(self) -> None:
        if not isinstance(self.reference, ExplanationEvidenceReference):
            raise TypeError(
                "reference must be an ExplanationEvidenceReference"
            )

        if not isinstance(self.disposition, ExplanationDisposition):
            raise TypeError("disposition must be an ExplanationDisposition")


@dataclass(frozen=True, slots=True)
class ExplanationBindingAssessment:
    usability: ExplanationUsability
    reasons: tuple[ExplanationAssessmentReason, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.usability, ExplanationUsability):
            raise TypeError("usability must be an ExplanationUsability")

        if not isinstance(self.reasons, tuple) or not all(
            isinstance(item, ExplanationAssessmentReason)
            for item in self.reasons
        ):
            raise TypeError(
                "reasons must be a tuple of ExplanationAssessmentReason"
            )

        if (
            self.usability is ExplanationUsability.NOT_USABLE
            and not self.reasons
        ):
            raise ValueError("NOT_USABLE requires at least one reason")

        if self.usability is ExplanationUsability.USABLE and self.reasons:
            raise ValueError(
                "USABLE must not carry reasons - reasons imply this "
                "explanation is not actually usable"
            )


def _resolve_disposition(
    reference: object,
    bindings: tuple,
) -> tuple[int, ExplanationDisposition | None]:
    matches = [b for b in bindings if b.reference == reference]
    if len(matches) == 1:
        return 1, matches[0].disposition
    return len(matches), None


def assess_explanation_binding(
    record: ExplanationRecord,
    records: tuple[ExplanationRecord, ...],
    target_bindings: tuple[ExplanationTargetBinding, ...],
    evidence_bindings: tuple[ExplanationEvidenceBinding, ...],
    require_current: bool,
) -> ExplanationBindingAssessment:
    """
    Validate that record's target and every evidence reference
    resolve unambiguously within the supplied bindings and carry a
    usable disposition, and that any declared predecessor resolves
    exactly once within the same explanation_id. Never fetches,
    infers, or mutates any source-domain object or historical
    ExplanationRecord.
    """

    if not isinstance(record, ExplanationRecord):
        raise TypeError("record must be an ExplanationRecord")

    if not isinstance(records, tuple) or not all(
        isinstance(item, ExplanationRecord) for item in records
    ):
        raise TypeError("records must be a tuple of ExplanationRecord")

    if not isinstance(target_bindings, tuple) or not all(
        isinstance(item, ExplanationTargetBinding) for item in target_bindings
    ):
        raise TypeError(
            "target_bindings must be a tuple of ExplanationTargetBinding"
        )

    if not isinstance(evidence_bindings, tuple) or not all(
        isinstance(item, ExplanationEvidenceBinding)
        for item in evidence_bindings
    ):
        raise TypeError(
            "evidence_bindings must be a tuple of ExplanationEvidenceBinding"
        )

    if not isinstance(require_current, bool):
        raise TypeError("require_current must be a bool")

    reasons: list[ExplanationAssessmentReason] = []

    target_match_count, target_disposition = _resolve_disposition(
        record.target, target_bindings
    )

    if target_match_count == 0:
        reasons.append(ExplanationAssessmentReason.TARGET_UNRESOLVED)
    elif target_match_count > 1:
        reasons.append(ExplanationAssessmentReason.TARGET_AMBIGUOUS)
    elif target_disposition is ExplanationDisposition.CURRENT:
        pass
    elif target_disposition is ExplanationDisposition.SUPERSEDED:
        if require_current:
            reasons.append(ExplanationAssessmentReason.TARGET_CURRENT_REQUIRED)
    else:
        reasons.append(ExplanationAssessmentReason.TARGET_DISPOSITION_NOT_USABLE)

    evidence_unresolved = False
    evidence_ambiguous = False
    evidence_not_usable = False
    evidence_current_required = False

    for evidence_reference in record.evidence_references:
        match_count, disposition = _resolve_disposition(
            evidence_reference, evidence_bindings
        )

        if match_count == 0:
            evidence_unresolved = True
        elif match_count > 1:
            evidence_ambiguous = True
        elif disposition is ExplanationDisposition.CURRENT:
            continue
        elif disposition is ExplanationDisposition.SUPERSEDED:
            if require_current:
                evidence_current_required = True
        else:
            evidence_not_usable = True

    if evidence_unresolved:
        reasons.append(ExplanationAssessmentReason.EVIDENCE_UNRESOLVED)

    if evidence_ambiguous:
        reasons.append(ExplanationAssessmentReason.EVIDENCE_AMBIGUOUS)

    if evidence_not_usable:
        reasons.append(
            ExplanationAssessmentReason.EVIDENCE_DISPOSITION_NOT_USABLE
        )

    if evidence_current_required:
        reasons.append(ExplanationAssessmentReason.EVIDENCE_CURRENT_REQUIRED)

    if record.supersedes_revision is not None:
        same_explanation_predecessors = [
            item
            for item in records
            if item.explanation_id == record.explanation_id
            and item.revision == record.supersedes_revision
        ]

        if len(same_explanation_predecessors) == 0:
            other_explanation_predecessors = [
                item
                for item in records
                if item.explanation_id != record.explanation_id
                and item.revision == record.supersedes_revision
            ]

            if other_explanation_predecessors:
                reasons.append(
                    ExplanationAssessmentReason.CROSS_EXPLANATION_SUPERSESSION
                )
            else:
                reasons.append(
                    ExplanationAssessmentReason.PREDECESSOR_UNRESOLVED
                )
        elif len(same_explanation_predecessors) > 1:
            reasons.append(
                ExplanationAssessmentReason.PREDECESSOR_AMBIGUOUS
            )

    if reasons:
        return ExplanationBindingAssessment(
            usability=ExplanationUsability.NOT_USABLE,
            reasons=tuple(reasons),
        )

    return ExplanationBindingAssessment(
        usability=ExplanationUsability.USABLE,
        reasons=(),
    )
