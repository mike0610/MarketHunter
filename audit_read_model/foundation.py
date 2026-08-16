"""
MarketHunter

audit_read_model/foundation.py

Module:
CORE-GAP-03 Audit / Read-Model - Slice 1 (non-authoritative immutable
composition foundation only)

Responsibilities:
- Define AuditSourceReference, AuditProjectionReference,
  AuditCompositionRecord: immutable, caller-supplied identity and
  membership for one audit/read-model composition.
- Define AuditTemporalPair: an explicit source-pair-to-TemporalFact
  mapping, never inferred from names or timestamps.
- Define compose_audit_projection(): a pure, deterministic function
  that resolves each requested source against caller-supplied
  bindings, propagates CORE-GAP-04 partial temporal order exactly,
  and fails closed - never repairing, choosing a winner, or
  inventing a total order.

Non-goals (frozen by ARCH-REQ-CORE-GAP-03-AUDIT-READMODEL-001):
- No second truth layer, no write-back to source domains. A composed
  entry is a projection of exact governed source references; its
  presence never proves the source fact is current or correct.
- No persistence, repository, runtime service, API, UI, Reports, or
  Manual Review authority of any kind.
- No global/universal event spine. This module never imports
  Strategy/Risk/Portfolio/TOP/Execution/Explainability/Research/
  Trading models - source identities remain opaque strings supplied
  by the caller.
- No name-based join, latest-row lookup, nearest-time binding,
  max-timestamp selection, or display-sort-as-chronology. Each
  requested source resolves only by full equality against the
  caller-supplied bindings.
- No cross-source dedupe or reconciliation beyond exact identity -
  distinct source identities are never merged, even if their other
  field values happen to look similar.
- CORE-GAP-04 (time_semantics) is consumed only as a semantic
  dependency for partial temporal order; this module never converts
  it into a total order, a clock authority, or a chronology engine.
  Item order in a composition follows request order only and is
  never chronology.
- No stale-age calculation. AuditSourceDisposition is caller-supplied
  only.
- No ResearchTrade.notional reference or inference of any kind.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from time_semantics.foundation import (
    LineageRelation,
    TemporalAssessment,
    TemporalFact,
    TemporalRelation,
    assess_temporal_relation,
)


class AuditSourceDisposition(str, Enum):
    """
    Caller-supplied disposition of one source binding. Not a
    lifecycle and not a freshness calculation - this module never
    computes whether a source is current, unavailable, stale,
    conflicting, superseded, or affected by a changed source; the
    caller must supply that classification.
    """

    CURRENT = "CURRENT"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"
    STALE = "STALE"
    CONFLICT = "CONFLICT"
    SUPERSEDED = "SUPERSEDED"
    SOURCE_CHANGED = "SOURCE_CHANGED"


class AuditCompositionUsability(str, Enum):
    USABLE = "USABLE"
    NOT_USABLE = "NOT_USABLE"


class AuditCompositionReason(str, Enum):
    SOURCE_UNRESOLVED = "SOURCE_UNRESOLVED"
    SOURCE_AMBIGUOUS = "SOURCE_AMBIGUOUS"
    SOURCE_DISPOSITION_NOT_USABLE = "SOURCE_DISPOSITION_NOT_USABLE"
    SOURCE_CURRENT_REQUIRED = "SOURCE_CURRENT_REQUIRED"
    TEMPORAL_SOURCE_NOT_IN_COMPOSITION = "TEMPORAL_SOURCE_NOT_IN_COMPOSITION"
    TEMPORAL_ORDER_REQUIRED_BUT_MISSING = "TEMPORAL_ORDER_REQUIRED_BUT_MISSING"
    TEMPORAL_RELATION_UNKNOWN = "TEMPORAL_RELATION_UNKNOWN"
    TEMPORAL_RELATION_CONFLICT = "TEMPORAL_RELATION_CONFLICT"
    TEMPORAL_RELATION_NOT_COMPARABLE = "TEMPORAL_RELATION_NOT_COMPARABLE"


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
class AuditSourceReference:
    """
    Opaque, exact identity of one source object. Resolution against
    caller-supplied bindings is always by full equality of these
    fields - never by name, partial id, or any other heuristic.
    """

    source_domain: str
    source_type: str
    source_id: str
    revision_or_version: str | None

    def __post_init__(self) -> None:
        _require_nonblank(self.source_domain, "source_domain")
        _require_nonblank(self.source_type, "source_type")
        _require_nonblank(self.source_id, "source_id")
        _require_optional_nonblank(
            self.revision_or_version, "revision_or_version"
        )


@dataclass(frozen=True, slots=True)
class AuditSourceBinding:
    reference: AuditSourceReference
    disposition: AuditSourceDisposition

    def __post_init__(self) -> None:
        if not isinstance(self.reference, AuditSourceReference):
            raise TypeError("reference must be an AuditSourceReference")

        if not isinstance(self.disposition, AuditSourceDisposition):
            raise TypeError("disposition must be an AuditSourceDisposition")


@dataclass(frozen=True, slots=True)
class AuditProjectionReference:
    """
    Identity of the audit projection/composition artifact itself.
    This is audit-artifact identity only - it never substitutes for,
    or proves the currentness of, any source identity.
    """

    projection_id: str
    revision: int

    def __post_init__(self) -> None:
        _require_nonblank(self.projection_id, "projection_id")
        _require_positive_int(self.revision, "revision")


@dataclass(frozen=True, slots=True)
class AuditCompositionRecord:
    """
    The exact set of source references one composition requests.
    Distinct source identities are never deduplicated even if their
    other field values look similar; only byte-for-byte identical
    requested references are rejected as duplicates.
    """

    projection: AuditProjectionReference
    source_references: tuple[AuditSourceReference, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.projection, AuditProjectionReference):
            raise TypeError("projection must be an AuditProjectionReference")

        if not isinstance(self.source_references, tuple) or not all(
            isinstance(item, AuditSourceReference)
            for item in self.source_references
        ):
            raise TypeError(
                "source_references must be a tuple of AuditSourceReference"
            )

        if not self.source_references:
            raise ValueError("source_references must be non-empty")

        if len(self.source_references) != len(set(self.source_references)):
            raise ValueError(
                "source_references must not contain duplicate exact "
                "references"
            )


@dataclass(frozen=True, slots=True)
class AuditTemporalPair:
    """
    An explicit source-to-TemporalFact mapping for one ordering
    question. Both sides are supplied together by the caller - this
    module never infers which TemporalFact belongs to which source by
    name or timestamp proximity.
    """

    left_source_reference: AuditSourceReference
    left_fact: TemporalFact
    right_source_reference: AuditSourceReference
    right_fact: TemporalFact

    def __post_init__(self) -> None:
        if not isinstance(self.left_source_reference, AuditSourceReference):
            raise TypeError(
                "left_source_reference must be an AuditSourceReference"
            )

        if not isinstance(self.left_fact, TemporalFact):
            raise TypeError("left_fact must be a TemporalFact")

        if not isinstance(self.right_source_reference, AuditSourceReference):
            raise TypeError(
                "right_source_reference must be an AuditSourceReference"
            )

        if not isinstance(self.right_fact, TemporalFact):
            raise TypeError("right_fact must be a TemporalFact")


@dataclass(frozen=True, slots=True)
class AuditProjectionItem:
    """
    One resolved composition entry: an exact source reference paired
    with the disposition it resolved to. Present only for sources
    that resolved to exactly one binding - unresolved/ambiguous
    requests surface via reasons instead, never as a fabricated item.
    """

    source_reference: AuditSourceReference
    disposition: AuditSourceDisposition

    def __post_init__(self) -> None:
        if not isinstance(self.source_reference, AuditSourceReference):
            raise TypeError("source_reference must be an AuditSourceReference")

        if not isinstance(self.disposition, AuditSourceDisposition):
            raise TypeError("disposition must be an AuditSourceDisposition")


@dataclass(frozen=True, slots=True)
class AuditTemporalPairAssessment:
    pair: AuditTemporalPair
    assessment: TemporalAssessment

    def __post_init__(self) -> None:
        if not isinstance(self.pair, AuditTemporalPair):
            raise TypeError("pair must be an AuditTemporalPair")

        if not isinstance(self.assessment, TemporalAssessment):
            raise TypeError("assessment must be a TemporalAssessment")


@dataclass(frozen=True, slots=True)
class AuditCompositionAssessment:
    usability: AuditCompositionUsability
    reasons: tuple[AuditCompositionReason, ...]
    items: tuple[AuditProjectionItem, ...]
    temporal_assessments: tuple[AuditTemporalPairAssessment, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.usability, AuditCompositionUsability):
            raise TypeError("usability must be an AuditCompositionUsability")

        if not isinstance(self.reasons, tuple) or not all(
            isinstance(item, AuditCompositionReason) for item in self.reasons
        ):
            raise TypeError(
                "reasons must be a tuple of AuditCompositionReason"
            )

        if not isinstance(self.items, tuple) or not all(
            isinstance(item, AuditProjectionItem) for item in self.items
        ):
            raise TypeError("items must be a tuple of AuditProjectionItem")

        if not isinstance(self.temporal_assessments, tuple) or not all(
            isinstance(item, AuditTemporalPairAssessment)
            for item in self.temporal_assessments
        ):
            raise TypeError(
                "temporal_assessments must be a tuple of "
                "AuditTemporalPairAssessment"
            )

        if (
            self.usability is AuditCompositionUsability.NOT_USABLE
            and not self.reasons
        ):
            raise ValueError("NOT_USABLE requires at least one reason")

        if (
            self.usability is AuditCompositionUsability.USABLE
            and self.reasons
        ):
            raise ValueError(
                "USABLE must not carry reasons - reasons imply this "
                "composition is not actually usable"
            )


def compose_audit_projection(
    record: AuditCompositionRecord,
    source_bindings: tuple[AuditSourceBinding, ...],
    temporal_pairs: tuple[AuditTemporalPair, ...] = (),
    lineage_relations: tuple[LineageRelation, ...] = (),
    require_current: bool = False,
    require_temporal_order: bool = False,
) -> AuditCompositionAssessment:
    """
    Resolve every source reference requested by record against
    source_bindings by full equality only, and propagate the exact
    CORE-GAP-04 partial temporal order for any supplied temporal
    pairs. Never fetches, infers, repairs, or mutates any input - a
    composition either resolves cleanly from exactly what the caller
    supplied, or it fails closed with explicit reasons.
    """

    if not isinstance(record, AuditCompositionRecord):
        raise TypeError("record must be an AuditCompositionRecord")

    if not isinstance(source_bindings, tuple) or not all(
        isinstance(item, AuditSourceBinding) for item in source_bindings
    ):
        raise TypeError(
            "source_bindings must be a tuple of AuditSourceBinding"
        )

    if not isinstance(temporal_pairs, tuple) or not all(
        isinstance(item, AuditTemporalPair) for item in temporal_pairs
    ):
        raise TypeError("temporal_pairs must be a tuple of AuditTemporalPair")

    if not isinstance(lineage_relations, tuple) or not all(
        isinstance(item, LineageRelation) for item in lineage_relations
    ):
        raise TypeError(
            "lineage_relations must be a tuple of LineageRelation"
        )

    if not isinstance(require_current, bool):
        raise TypeError("require_current must be a bool")

    if not isinstance(require_temporal_order, bool):
        raise TypeError("require_temporal_order must be a bool")

    reasons: list[AuditCompositionReason] = []
    items: list[AuditProjectionItem] = []

    source_unresolved = False
    source_ambiguous = False
    source_disposition_not_usable = False
    source_current_required = False

    for source_reference in record.source_references:
        matches = [
            binding
            for binding in source_bindings
            if binding.reference == source_reference
        ]

        if len(matches) == 0:
            source_unresolved = True
            continue

        if len(matches) > 1:
            source_ambiguous = True
            continue

        disposition = matches[0].disposition
        items.append(
            AuditProjectionItem(
                source_reference=source_reference, disposition=disposition
            )
        )

        if disposition is AuditSourceDisposition.CURRENT:
            continue
        elif disposition is AuditSourceDisposition.SUPERSEDED:
            if require_current:
                source_current_required = True
        else:
            source_disposition_not_usable = True

    if source_unresolved:
        reasons.append(AuditCompositionReason.SOURCE_UNRESOLVED)

    if source_ambiguous:
        reasons.append(AuditCompositionReason.SOURCE_AMBIGUOUS)

    if source_disposition_not_usable:
        reasons.append(AuditCompositionReason.SOURCE_DISPOSITION_NOT_USABLE)

    if source_current_required:
        reasons.append(AuditCompositionReason.SOURCE_CURRENT_REQUIRED)

    composition_source_set = set(record.source_references)

    temporal_source_not_in_composition = False
    temporal_relation_unknown = False
    temporal_relation_conflict = False
    temporal_relation_not_comparable = False
    temporal_assessments: list[AuditTemporalPairAssessment] = []

    for pair in temporal_pairs:
        if (
            pair.left_source_reference not in composition_source_set
            or pair.right_source_reference not in composition_source_set
        ):
            temporal_source_not_in_composition = True

        assessment = assess_temporal_relation(
            pair.left_fact, pair.right_fact, lineage_relations
        )
        temporal_assessments.append(
            AuditTemporalPairAssessment(pair=pair, assessment=assessment)
        )

        if assessment.relation is TemporalRelation.UNKNOWN:
            temporal_relation_unknown = True
        elif assessment.relation is TemporalRelation.CONFLICT:
            temporal_relation_conflict = True
        elif assessment.relation is TemporalRelation.NOT_COMPARABLE:
            temporal_relation_not_comparable = True

    if temporal_source_not_in_composition:
        reasons.append(
            AuditCompositionReason.TEMPORAL_SOURCE_NOT_IN_COMPOSITION
        )

    if require_temporal_order:
        if not temporal_pairs:
            reasons.append(
                AuditCompositionReason.TEMPORAL_ORDER_REQUIRED_BUT_MISSING
            )

        if temporal_relation_unknown:
            reasons.append(AuditCompositionReason.TEMPORAL_RELATION_UNKNOWN)

        if temporal_relation_conflict:
            reasons.append(AuditCompositionReason.TEMPORAL_RELATION_CONFLICT)

        if temporal_relation_not_comparable:
            reasons.append(
                AuditCompositionReason.TEMPORAL_RELATION_NOT_COMPARABLE
            )

    if reasons:
        return AuditCompositionAssessment(
            usability=AuditCompositionUsability.NOT_USABLE,
            reasons=tuple(reasons),
            items=tuple(items),
            temporal_assessments=tuple(temporal_assessments),
        )

    return AuditCompositionAssessment(
        usability=AuditCompositionUsability.USABLE,
        reasons=(),
        items=tuple(items),
        temporal_assessments=tuple(temporal_assessments),
    )
