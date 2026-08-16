"""
MarketHunter

time_semantics/foundation.py

Module:
CORE-GAP-04 Time Semantics - Slice 1 (domain-neutral immutable
semantics + pure relation assessment only)

Responsibilities:
- Define TemporalRole: the canonical, non-interchangeable meanings of
  a timestamp (EVENT_TIME, OBSERVED_TIME, RECORDED_TIME) plus
  LINEAGE_ORDER, which is explicitly not a clock.
- Define TemporalReference, TemporalFact, LineageRelation: immutable,
  caller-supplied facts about opaque domain objects.
- Define assess_temporal_relation(): a pure, deterministic function
  that orders two facts by explicit lineage first, then by same-role
  aware-instant comparison, and otherwise fails closed.

Non-goals (frozen by ARCH-REQ-CORE-GAP-04-TIME-SEMANTICS-001):
- No clock service, NTP lookup, or wall-clock read of any kind. Every
  timestamp and lineage relation is caller-supplied.
- No source-domain timestamp authority. This module never imports
  Strategy/Risk/Portfolio/TOP/Execution/Explainability/Research
  models - it receives opaque TemporalReference/TemporalFact objects
  from callers and returns semantic relation only.
- No "latest"/"current" selector. No total-order invention when only
  a partial order is evidenced.
- No domain-specific clock precedence, skew/drift tolerance, venue
  timestamp trust hierarchy, or REST/WebSocket reconciliation policy.
- No retroactive timestamp repair. Later observation/recording never
  overwrites an earlier event/decision fact.
- EVENT_TIME, OBSERVED_TIME, and RECORDED_TIME never substitute for
  one another. LINEAGE_ORDER is never inferred from timestamps, and
  timestamps never create lineage.
- Equal same-role timestamps prove only equal temporal values - never
  identity, simultaneity in every sense, revision equality, or
  causality.
- No persistence, repository, API, Dashboard, runtime, or deploy
  wiring of any kind.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


class TemporalRole(str, Enum):
    EVENT_TIME = "EVENT_TIME"
    OBSERVED_TIME = "OBSERVED_TIME"
    RECORDED_TIME = "RECORDED_TIME"
    LINEAGE_ORDER = "LINEAGE_ORDER"


class TemporalDisposition(str, Enum):
    """
    KNOWN is deliberately not named CURRENT - this vocabulary carries
    no current/latest semantics, only whether the caller asserts the
    fact's timestamp value is known.
    """

    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"
    CONFLICT = "CONFLICT"


class TemporalRelation(str, Enum):
    BEFORE = "BEFORE"
    AFTER = "AFTER"
    EQUAL = "EQUAL"
    UNKNOWN = "UNKNOWN"
    CONFLICT = "CONFLICT"
    NOT_COMPARABLE = "NOT_COMPARABLE"


class TemporalAssessmentReason(str, Enum):
    DIRECT_LINEAGE_PRECEDENCE = "DIRECT_LINEAGE_PRECEDENCE"
    LINEAGE_CONTRADICTION = "LINEAGE_CONTRADICTION"
    LINEAGE_ORDER_NOT_COMPARABLE = "LINEAGE_ORDER_NOT_COMPARABLE"
    ROLE_MISMATCH = "ROLE_MISMATCH"
    FACT_CONFLICT = "FACT_CONFLICT"
    FACT_UNKNOWN_OR_UNAVAILABLE = "FACT_UNKNOWN_OR_UNAVAILABLE"
    SAME_ROLE_CLOCK_COMPARISON = "SAME_ROLE_CLOCK_COMPARISON"


def _require_nonblank(value: object, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a str")

    if not value.strip():
        raise ValueError(f"{field_name} must be non-blank")


def _require_optional_nonblank(value: object, field_name: str) -> None:
    if value is not None:
        _require_nonblank(value, field_name)


def _require_aware_datetime(value: object, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")

    if value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class TemporalReference:
    """
    Opaque, locally-scoped identity of the object a temporal fact is
    about. Never resolved, fetched, or interpreted by this module.
    """

    reference_kind: str
    reference_id: str
    revision_or_version: str | None

    def __post_init__(self) -> None:
        _require_nonblank(self.reference_kind, "reference_kind")
        _require_nonblank(self.reference_id, "reference_id")
        _require_optional_nonblank(
            self.revision_or_version, "revision_or_version"
        )


@dataclass(frozen=True, slots=True)
class TemporalFact:
    """
    One caller-supplied temporal fact about a reference. A
    LINEAGE_ORDER fact never carries a timestamp - it is not a clock.
    For clock roles (EVENT_TIME/OBSERVED_TIME/RECORDED_TIME), a KNOWN
    disposition requires a timezone-aware timestamp; any other
    disposition requires the timestamp to be None, so an unusable
    fact never carries a stray value that could be misread as
    authoritative.
    """

    reference: TemporalReference
    role: TemporalRole
    timestamp: datetime | None
    disposition: TemporalDisposition

    def __post_init__(self) -> None:
        if not isinstance(self.reference, TemporalReference):
            raise TypeError("reference must be a TemporalReference")

        if not isinstance(self.role, TemporalRole):
            raise TypeError("role must be a TemporalRole")

        if not isinstance(self.disposition, TemporalDisposition):
            raise TypeError("disposition must be a TemporalDisposition")

        if self.role is TemporalRole.LINEAGE_ORDER:
            if self.timestamp is not None:
                raise ValueError(
                    "LINEAGE_ORDER facts must not carry a timestamp"
                )
            return

        if self.disposition is TemporalDisposition.KNOWN:
            if self.timestamp is None:
                raise ValueError(
                    "KNOWN clock-role fact requires a timestamp"
                )
            _require_aware_datetime(self.timestamp, "timestamp")
        else:
            if self.timestamp is not None:
                raise ValueError(
                    f"{self.disposition.value} fact must not carry a "
                    "timestamp"
                )


@dataclass(frozen=True, slots=True)
class LineageRelation:
    """
    An explicit, caller-supplied predecessor/successor relation
    between two exact references. Never inferred from timestamps.
    """

    predecessor: TemporalReference
    successor: TemporalReference

    def __post_init__(self) -> None:
        if not isinstance(self.predecessor, TemporalReference):
            raise TypeError("predecessor must be a TemporalReference")

        if not isinstance(self.successor, TemporalReference):
            raise TypeError("successor must be a TemporalReference")

        if self.predecessor == self.successor:
            raise ValueError("a lineage relation cannot self-reference")


@dataclass(frozen=True, slots=True)
class TemporalAssessment:
    relation: TemporalRelation
    reasons: tuple[TemporalAssessmentReason, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.relation, TemporalRelation):
            raise TypeError("relation must be a TemporalRelation")

        if not isinstance(self.reasons, tuple) or not all(
            isinstance(item, TemporalAssessmentReason) for item in self.reasons
        ):
            raise TypeError(
                "reasons must be a tuple of TemporalAssessmentReason"
            )

        if not self.reasons:
            raise ValueError(
                "reasons must contain at least one explanatory reason"
            )


def assess_temporal_relation(
    left: TemporalFact,
    right: TemporalFact,
    lineage_relations: tuple[LineageRelation, ...] = (),
) -> TemporalAssessment:
    """
    Determine the temporal relation between two facts. Explicit
    direct lineage between the exact references always wins, before
    any clock comparison; contradictory direct lineage (both
    directions supplied) is CONFLICT. Without a direct lineage
    relation, only same-role, both-KNOWN, aware-instant facts can be
    ordered - everything else fails closed to UNKNOWN, CONFLICT, or
    NOT_COMPARABLE. No transitive or latest inference of any kind.
    """

    if not isinstance(left, TemporalFact):
        raise TypeError("left must be a TemporalFact")

    if not isinstance(right, TemporalFact):
        raise TypeError("right must be a TemporalFact")

    if not isinstance(lineage_relations, tuple) or not all(
        isinstance(item, LineageRelation) for item in lineage_relations
    ):
        raise TypeError(
            "lineage_relations must be a tuple of LineageRelation"
        )

    left_precedes_right = any(
        relation.predecessor == left.reference
        and relation.successor == right.reference
        for relation in lineage_relations
    )
    right_precedes_left = any(
        relation.predecessor == right.reference
        and relation.successor == left.reference
        for relation in lineage_relations
    )

    if left_precedes_right and right_precedes_left:
        return TemporalAssessment(
            relation=TemporalRelation.CONFLICT,
            reasons=(TemporalAssessmentReason.LINEAGE_CONTRADICTION,),
        )

    if left_precedes_right:
        return TemporalAssessment(
            relation=TemporalRelation.BEFORE,
            reasons=(TemporalAssessmentReason.DIRECT_LINEAGE_PRECEDENCE,),
        )

    if right_precedes_left:
        return TemporalAssessment(
            relation=TemporalRelation.AFTER,
            reasons=(TemporalAssessmentReason.DIRECT_LINEAGE_PRECEDENCE,),
        )

    if (
        left.role is TemporalRole.LINEAGE_ORDER
        or right.role is TemporalRole.LINEAGE_ORDER
    ):
        return TemporalAssessment(
            relation=TemporalRelation.NOT_COMPARABLE,
            reasons=(TemporalAssessmentReason.LINEAGE_ORDER_NOT_COMPARABLE,),
        )

    if left.role is not right.role:
        return TemporalAssessment(
            relation=TemporalRelation.NOT_COMPARABLE,
            reasons=(TemporalAssessmentReason.ROLE_MISMATCH,),
        )

    if (
        left.disposition is TemporalDisposition.CONFLICT
        or right.disposition is TemporalDisposition.CONFLICT
    ):
        return TemporalAssessment(
            relation=TemporalRelation.CONFLICT,
            reasons=(TemporalAssessmentReason.FACT_CONFLICT,),
        )

    if (
        left.disposition is not TemporalDisposition.KNOWN
        or right.disposition is not TemporalDisposition.KNOWN
    ):
        return TemporalAssessment(
            relation=TemporalRelation.UNKNOWN,
            reasons=(TemporalAssessmentReason.FACT_UNKNOWN_OR_UNAVAILABLE,),
        )

    left_instant = left.timestamp.astimezone(timezone.utc)
    right_instant = right.timestamp.astimezone(timezone.utc)

    if left_instant < right_instant:
        relation = TemporalRelation.BEFORE
    elif left_instant > right_instant:
        relation = TemporalRelation.AFTER
    else:
        relation = TemporalRelation.EQUAL

    return TemporalAssessment(
        relation=relation,
        reasons=(TemporalAssessmentReason.SAME_ROLE_CLOCK_COMPARISON,),
    )
