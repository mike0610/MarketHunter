"""
MarketHunter

manual_review/foundation.py

Module:
CORE-GAP-07 Manual Review - Slice 1 (immutable governance contracts
+ pure authorization/target-usability assessment only)

Responsibilities:
- Define ReviewActorReference, ReviewAuthorizationAuthorityReference,
  ReviewCapabilityReference, ReviewActionReference,
  ReviewTargetReference: immutable, caller-supplied identity for the
  actor, authority, capability, review action, and target of one
  bounded review-layer request.
- Define ReviewActorEvidence, ReviewCapabilityGrant,
  ReviewTargetBinding: immutable, caller-supplied evidence bindings.
- Define ReviewActionRequest: one caller-supplied request to perform
  a bounded action class against one exact target, under one exact
  required capability.
- Define assess_review_authorization(): a pure, deterministic
  function that resolves the actor, the required capability grant,
  and the target - each by exact equality only - and fails closed on
  any unresolved, ambiguous, or not-usable evidence.

Non-goals (frozen by ARCH-REQ-CORE-GAP-07-MANUAL-REVIEW-AUTHORITY-001):
- No concrete grant lifecycle or authority validation policy. This
  module matches capability + issuing authority identity exactly; it
  never decides which authorities are globally valid or how grants
  are issued, renewed, or revoked.
- No RBAC/ABAC, user directory, role/title/email inference, or any
  identity lookup - every actor, grant, and target binding is
  supplied by the caller.
- No persistence, repository, runtime issuer, workflow engine, API,
  UI, Reports, or notification/escalation routing of any kind.
- No comment/content schema, separation-of-duties policy, or
  execution/trading authority.
- REQUEST_CHANGE is request provenance only - this module never
  writes back to, approves, rejects, resizes, cancels, executes, or
  overrides the target or any source domain.
- No AI delegation, retention policy, access control, or export.
- This module never imports Strategy/Risk/Portfolio/TOP/Execution/
  Explainability/Research/Trading models - only the two opaque
  reference types exported by audit_read_model.foundation.
- No wall clock, random, DB, filesystem, or network usage anywhere.
- No ResearchTrade.notional reference or inference of any kind.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from audit_read_model.foundation import AuditProjectionReference, AuditSourceReference


class ReviewEvidenceDisposition(str, Enum):
    """
    Caller-supplied disposition of one actor or grant evidence
    binding. Not a lookup and not computed by this module - the
    caller must supply the classification.
    """

    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"
    CONFLICT = "CONFLICT"


class ReviewActionClass(str, Enum):
    INSPECT = "INSPECT"
    ACKNOWLEDGE = "ACKNOWLEDGE"
    COMMENT = "COMMENT"
    ESCALATE = "ESCALATE"
    REQUEST_CHANGE = "REQUEST_CHANGE"


class ReviewTargetDisposition(str, Enum):
    """
    Caller-supplied disposition of one target binding. Not a
    freshness calculation - the caller must supply the
    classification.
    """

    CURRENT = "CURRENT"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"
    STALE = "STALE"
    CONFLICT = "CONFLICT"
    SUPERSEDED = "SUPERSEDED"
    SOURCE_CHANGED = "SOURCE_CHANGED"


class ReviewAuthorizationStatus(str, Enum):
    AUTHORIZED = "AUTHORIZED"
    NOT_AUTHORIZED = "NOT_AUTHORIZED"


class ReviewAuthorizationReason(str, Enum):
    ACTOR_UNRESOLVED = "ACTOR_UNRESOLVED"
    ACTOR_AMBIGUOUS = "ACTOR_AMBIGUOUS"
    ACTOR_EVIDENCE_NOT_USABLE = "ACTOR_EVIDENCE_NOT_USABLE"
    GRANT_UNRESOLVED = "GRANT_UNRESOLVED"
    GRANT_AMBIGUOUS = "GRANT_AMBIGUOUS"
    GRANT_EVIDENCE_NOT_USABLE = "GRANT_EVIDENCE_NOT_USABLE"
    TARGET_UNRESOLVED = "TARGET_UNRESOLVED"
    TARGET_AMBIGUOUS = "TARGET_AMBIGUOUS"
    TARGET_DISPOSITION_NOT_USABLE = "TARGET_DISPOSITION_NOT_USABLE"
    TARGET_CURRENT_REQUIRED = "TARGET_CURRENT_REQUIRED"


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


@dataclass(frozen=True, slots=True)
class ReviewActorReference:
    """
    Opaque, exact identity of one actor. Resolution against
    caller-supplied evidence is always by full equality of these
    fields - never by name, partial id, or any other heuristic.
    """

    actor_kind: str
    actor_id: str
    revision_or_version: str | None

    def __post_init__(self) -> None:
        _require_nonblank(self.actor_kind, "actor_kind")
        _require_nonblank(self.actor_id, "actor_id")
        _require_optional_nonblank(
            self.revision_or_version, "revision_or_version"
        )


@dataclass(frozen=True, slots=True)
class ReviewAuthorizationAuthorityReference:
    """
    Opaque, exact identity of one capability-issuing authority. This
    slice matches authority identity exactly; it never decides which
    authorities are globally valid.
    """

    authority_kind: str
    authority_id: str
    revision_or_version: str | None

    def __post_init__(self) -> None:
        _require_nonblank(self.authority_kind, "authority_kind")
        _require_nonblank(self.authority_id, "authority_id")
        _require_optional_nonblank(
            self.revision_or_version, "revision_or_version"
        )


@dataclass(frozen=True, slots=True)
class ReviewCapabilityReference:
    capability_id: str
    revision_or_version: str | None

    def __post_init__(self) -> None:
        _require_nonblank(self.capability_id, "capability_id")
        _require_optional_nonblank(
            self.revision_or_version, "revision_or_version"
        )


@dataclass(frozen=True, slots=True)
class ReviewActorEvidence:
    actor: ReviewActorReference
    disposition: ReviewEvidenceDisposition

    def __post_init__(self) -> None:
        if not isinstance(self.actor, ReviewActorReference):
            raise TypeError("actor must be a ReviewActorReference")

        if not isinstance(self.disposition, ReviewEvidenceDisposition):
            raise TypeError(
                "disposition must be a ReviewEvidenceDisposition"
            )


@dataclass(frozen=True, slots=True)
class ReviewCapabilityRequirement:
    capability: ReviewCapabilityReference
    issuing_authority: ReviewAuthorizationAuthorityReference

    def __post_init__(self) -> None:
        if not isinstance(self.capability, ReviewCapabilityReference):
            raise TypeError(
                "capability must be a ReviewCapabilityReference"
            )

        if not isinstance(
            self.issuing_authority, ReviewAuthorizationAuthorityReference
        ):
            raise TypeError(
                "issuing_authority must be a "
                "ReviewAuthorizationAuthorityReference"
            )


@dataclass(frozen=True, slots=True)
class ReviewCapabilityGrant:
    actor: ReviewActorReference
    capability: ReviewCapabilityReference
    issuing_authority: ReviewAuthorizationAuthorityReference
    disposition: ReviewEvidenceDisposition

    def __post_init__(self) -> None:
        if not isinstance(self.actor, ReviewActorReference):
            raise TypeError("actor must be a ReviewActorReference")

        if not isinstance(self.capability, ReviewCapabilityReference):
            raise TypeError(
                "capability must be a ReviewCapabilityReference"
            )

        if not isinstance(
            self.issuing_authority, ReviewAuthorizationAuthorityReference
        ):
            raise TypeError(
                "issuing_authority must be a "
                "ReviewAuthorizationAuthorityReference"
            )

        if not isinstance(self.disposition, ReviewEvidenceDisposition):
            raise TypeError(
                "disposition must be a ReviewEvidenceDisposition"
            )


@dataclass(frozen=True, slots=True)
class ReviewActionReference:
    review_id: str
    revision: int

    def __post_init__(self) -> None:
        _require_nonblank(self.review_id, "review_id")
        _require_positive_int(self.revision, "revision")


@dataclass(frozen=True, slots=True)
class ReviewTargetReference:
    """
    Exactly one of source_reference or projection_reference must be
    supplied - a review target is either an exact opaque source
    reference or an exact opaque audit projection reference, never
    both and never neither.
    """

    source_reference: AuditSourceReference | None
    projection_reference: AuditProjectionReference | None

    def __post_init__(self) -> None:
        if self.source_reference is not None and not isinstance(
            self.source_reference, AuditSourceReference
        ):
            raise TypeError(
                "source_reference must be an AuditSourceReference or None"
            )

        if self.projection_reference is not None and not isinstance(
            self.projection_reference, AuditProjectionReference
        ):
            raise TypeError(
                "projection_reference must be an AuditProjectionReference "
                "or None"
            )

        supplied_count = sum(
            1
            for value in (self.source_reference, self.projection_reference)
            if value is not None
        )
        if supplied_count != 1:
            raise ValueError(
                "exactly one of source_reference or projection_reference "
                "must be supplied"
            )


@dataclass(frozen=True, slots=True)
class ReviewTargetBinding:
    reference: ReviewTargetReference
    disposition: ReviewTargetDisposition

    def __post_init__(self) -> None:
        if not isinstance(self.reference, ReviewTargetReference):
            raise TypeError("reference must be a ReviewTargetReference")

        if not isinstance(self.disposition, ReviewTargetDisposition):
            raise TypeError(
                "disposition must be a ReviewTargetDisposition"
            )


@dataclass(frozen=True, slots=True)
class ReviewActionRequest:
    """
    One caller-supplied request to perform a bounded action class
    against one exact target, under one exact required capability.
    supersedes_review_revision, when supplied, must be strictly less
    than reference.revision - this module never looks up a
    predecessor or a "latest" prior revision.
    """

    reference: ReviewActionReference
    actor: ReviewActorReference
    target: ReviewTargetReference
    action_class: ReviewActionClass
    required_capability: ReviewCapabilityRequirement
    require_current_target: bool
    supersedes_review_revision: int | None

    def __post_init__(self) -> None:
        if not isinstance(self.reference, ReviewActionReference):
            raise TypeError("reference must be a ReviewActionReference")

        if not isinstance(self.actor, ReviewActorReference):
            raise TypeError("actor must be a ReviewActorReference")

        if not isinstance(self.target, ReviewTargetReference):
            raise TypeError("target must be a ReviewTargetReference")

        if not isinstance(self.action_class, ReviewActionClass):
            raise TypeError("action_class must be a ReviewActionClass")

        if not isinstance(
            self.required_capability, ReviewCapabilityRequirement
        ):
            raise TypeError(
                "required_capability must be a ReviewCapabilityRequirement"
            )

        if not isinstance(self.require_current_target, bool):
            raise TypeError("require_current_target must be a bool")

        if self.supersedes_review_revision is not None:
            _require_positive_int(
                self.supersedes_review_revision, "supersedes_review_revision"
            )
            if self.supersedes_review_revision >= self.reference.revision:
                raise ValueError(
                    "supersedes_review_revision must be strictly less "
                    "than reference.revision"
                )


@dataclass(frozen=True, slots=True)
class ReviewAuthorizationAssessment:
    status: ReviewAuthorizationStatus
    reasons: tuple[ReviewAuthorizationReason, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.status, ReviewAuthorizationStatus):
            raise TypeError("status must be a ReviewAuthorizationStatus")

        if not isinstance(self.reasons, tuple) or not all(
            isinstance(item, ReviewAuthorizationReason)
            for item in self.reasons
        ):
            raise TypeError(
                "reasons must be a tuple of ReviewAuthorizationReason"
            )

        if (
            self.status is ReviewAuthorizationStatus.NOT_AUTHORIZED
            and not self.reasons
        ):
            raise ValueError("NOT_AUTHORIZED requires at least one reason")

        if self.status is ReviewAuthorizationStatus.AUTHORIZED and self.reasons:
            raise ValueError(
                "AUTHORIZED must not carry reasons - reasons imply this "
                "request is not actually authorized"
            )


def assess_review_authorization(
    request: ReviewActionRequest,
    actor_evidence: tuple[ReviewActorEvidence, ...],
    grants: tuple[ReviewCapabilityGrant, ...],
    target_bindings: tuple[ReviewTargetBinding, ...],
) -> ReviewAuthorizationAssessment:
    """
    Resolve the requesting actor, the exact required capability
    grant, and the exact target - each by full equality only - and
    fail closed on any unresolved, ambiguous, or not-usable evidence.
    Never fetches, infers, repairs, or mutates any input, and never
    performs, executes, or writes back to the target.
    """

    if not isinstance(request, ReviewActionRequest):
        raise TypeError("request must be a ReviewActionRequest")

    if not isinstance(actor_evidence, tuple) or not all(
        isinstance(item, ReviewActorEvidence) for item in actor_evidence
    ):
        raise TypeError(
            "actor_evidence must be a tuple of ReviewActorEvidence"
        )

    if not isinstance(grants, tuple) or not all(
        isinstance(item, ReviewCapabilityGrant) for item in grants
    ):
        raise TypeError("grants must be a tuple of ReviewCapabilityGrant")

    if not isinstance(target_bindings, tuple) or not all(
        isinstance(item, ReviewTargetBinding) for item in target_bindings
    ):
        raise TypeError(
            "target_bindings must be a tuple of ReviewTargetBinding"
        )

    reasons: list[ReviewAuthorizationReason] = []

    actor_matches = [
        evidence
        for evidence in actor_evidence
        if evidence.actor == request.actor
    ]

    if len(actor_matches) == 0:
        reasons.append(ReviewAuthorizationReason.ACTOR_UNRESOLVED)
    elif len(actor_matches) > 1:
        reasons.append(ReviewAuthorizationReason.ACTOR_AMBIGUOUS)
    elif actor_matches[0].disposition is not ReviewEvidenceDisposition.KNOWN:
        reasons.append(ReviewAuthorizationReason.ACTOR_EVIDENCE_NOT_USABLE)

    grant_matches = [
        grant
        for grant in grants
        if grant.actor == request.actor
        and grant.capability == request.required_capability.capability
        and grant.issuing_authority
        == request.required_capability.issuing_authority
    ]

    if len(grant_matches) == 0:
        reasons.append(ReviewAuthorizationReason.GRANT_UNRESOLVED)
    elif len(grant_matches) > 1:
        reasons.append(ReviewAuthorizationReason.GRANT_AMBIGUOUS)
    elif grant_matches[0].disposition is not ReviewEvidenceDisposition.KNOWN:
        reasons.append(ReviewAuthorizationReason.GRANT_EVIDENCE_NOT_USABLE)

    target_matches = [
        binding
        for binding in target_bindings
        if binding.reference == request.target
    ]

    if len(target_matches) == 0:
        reasons.append(ReviewAuthorizationReason.TARGET_UNRESOLVED)
    elif len(target_matches) > 1:
        reasons.append(ReviewAuthorizationReason.TARGET_AMBIGUOUS)
    else:
        target_disposition = target_matches[0].disposition
        if target_disposition is ReviewTargetDisposition.CURRENT:
            pass
        elif target_disposition is ReviewTargetDisposition.SUPERSEDED:
            if request.require_current_target:
                reasons.append(
                    ReviewAuthorizationReason.TARGET_CURRENT_REQUIRED
                )
        else:
            reasons.append(
                ReviewAuthorizationReason.TARGET_DISPOSITION_NOT_USABLE
            )

    if reasons:
        return ReviewAuthorizationAssessment(
            status=ReviewAuthorizationStatus.NOT_AUTHORIZED,
            reasons=tuple(reasons),
        )

    return ReviewAuthorizationAssessment(
        status=ReviewAuthorizationStatus.AUTHORIZED,
        reasons=(),
    )
