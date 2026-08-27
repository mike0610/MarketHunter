"""
MarketHunter

data_quality/policy_provenance.py

Module:
Data Quality Policy Provenance Foundation - Slice 1: immutable
Data Quality-owned policy identity/declaration/reference/
availability/result contracts and pure deterministic constructor
validation only

Responsibilities:
- Define DataQualityPolicyIdentity, DataQualityPolicyDeclaration,
  DataQualityPolicyReference, DataQualityPolicyProvenanceRecord,
  DataQualityPolicyProvenanceDisposition, and
  DataQualityPolicyProvenanceResult: the immutable value objects that
  describe one exact governed Data Quality policy release and one
  exact prospective fact that it was available to a Data Quality
  assessment path at a caller-supplied instant.

Non-goals (frozen by MH-DATA-QUALITY-POLICY-PROVENANCE-LEAD-001
Council decision):
- Constructing any of these value objects is validation only - it is
  NOT governed policy issuance. This module introduces no runtime
  issuer, registry, manifest, history, or persistence of any kind.
- Policy provenance is distinct from Data Quality assessment/decision
  provenance. This module contains NO assessment/decision type,
  admissibility enum, pass/fail, score, reason vocabulary, evidence/
  source refs, evidence cardinality, assessment payload, or
  assessed_at. A DataQualityPolicyProvenanceRecord means only that
  the exact governed policy release was available to the relevant
  Data Quality assessment path at that instant - it does NOT prove an
  assessment happened and does NOT claim evidence admissibility.
- No missing-candle/gap/non-finite/duplicate/completeness/source-
  conflict rules or thresholds. No stale/freshness semantics - the
  disposition enum has no STALE member in Slice 1.
- No REST-vs-WS precedence, fallback, reconciliation, source-
  selection freshness, multi-source winner/arbitration, or any
  CORE-GAP-06 behavior.
- No current/latest/default/SemVer/class/file/module/config/
  environment/code-SHA inference of any kind. opaque_version is
  opaque, caller-supplied text - never parsed or ordered.
- No wall clock, random, or scheduler usage. available_at is an
  explicit, caller-supplied, timezone-aware governed fact, preserved
  exactly. It is never market EVENT_TIME, Market Data observed_at/
  available_at, Acquisition Policy available_at, persistence/
  RECORDED_TIME, Research created_at, Trend Context time, a future
  Data Quality assessed_at, or CandidateProvenance OBSERVED_TIME.
- No retrospective reconstruction/backfill from existing guards,
  loaders, config, present behavior, later rows, or Simulation.
- No market_data, exchange, services, models, Scanner, pipeline,
  Strategy, Research, Simulation, PI/Reports, persistence, API/UI, or
  runtime-clock import or wiring of any kind.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class DataQualityPolicyProvenanceError(Exception):
    """Base error for Data Quality Policy Provenance Foundation failures."""


class DataQualityPolicyInvariantError(DataQualityPolicyProvenanceError):
    """A contract violates a disposition/record invariant."""


def _require_nonblank(value: object, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a str")

    if not value.strip():
        raise ValueError(f"{field_name} must be non-blank")


@dataclass(frozen=True, slots=True)
class DataQualityPolicyIdentity:
    """
    Exact opaque nonblank policy identifier. Preserved exactly,
    including surrounding whitespace when nonblank - no
    normalization, case-folding, or parsing of any kind.
    """

    policy_id: str

    def __post_init__(self) -> None:
        _require_nonblank(self.policy_id, "policy_id")


@dataclass(frozen=True, slots=True)
class DataQualityPolicyDeclaration:
    """
    Exact pairing of one DataQualityPolicyIdentity with one opaque,
    unordered version. Constructing this value object is validation
    only - it is NOT governed policy issuance and creates no
    current/latest authority.
    """

    identity: DataQualityPolicyIdentity
    opaque_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.identity, DataQualityPolicyIdentity):
            raise TypeError(
                "identity must be a DataQualityPolicyIdentity"
            )

        _require_nonblank(self.opaque_version, "opaque_version")


@dataclass(frozen=True, slots=True)
class DataQualityPolicyReference:
    """
    Exact wrapper around one DataQualityPolicyDeclaration. Delegates
    identity/opaque_version directly - it never copies them into
    parallel authority fields.
    """

    declaration: DataQualityPolicyDeclaration

    def __post_init__(self) -> None:
        if not isinstance(
            self.declaration, DataQualityPolicyDeclaration
        ):
            raise TypeError(
                "declaration must be a DataQualityPolicyDeclaration"
            )

    @property
    def identity(self) -> DataQualityPolicyIdentity:
        return self.declaration.identity

    @property
    def opaque_version(self) -> str:
        return self.declaration.opaque_version


@dataclass(frozen=True, slots=True)
class DataQualityPolicyProvenanceRecord:
    """
    One exact, immutable fact: this exact governed
    DataQualityPolicyReference was available to the relevant Data
    Quality assessment path at this caller-supplied governed
    available_at instant. This does NOT prove an assessment occurred
    and does NOT claim evidence admissibility. available_at is
    mandatory, timezone-aware, preserved exactly - never derived from
    a wall clock.
    """

    policy_reference: DataQualityPolicyReference
    available_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(
            self.policy_reference, DataQualityPolicyReference
        ):
            raise TypeError(
                "policy_reference must be a DataQualityPolicyReference"
            )

        if not isinstance(self.available_at, datetime):
            raise TypeError("available_at must be a datetime")

        if self.available_at.tzinfo is None or (
            self.available_at.tzinfo.utcoffset(self.available_at)
            is None
        ):
            raise ValueError(
                "available_at must be timezone-aware"
            )


class DataQualityPolicyProvenanceDisposition(str, Enum):
    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"
    CONFLICT = "CONFLICT"


@dataclass(frozen=True, slots=True)
class DataQualityPolicyProvenanceResult:
    """
    KNOWN requires exactly one record. UNKNOWN, UNAVAILABLE, and
    CONFLICT all require record=None - no fake unknown record is ever
    fabricated. CONFLICT is a caller-supplied disposition only; this
    foundation does not itself detect or resolve conflicts.
    """

    disposition: DataQualityPolicyProvenanceDisposition
    record: DataQualityPolicyProvenanceRecord | None

    def __post_init__(self) -> None:
        if not isinstance(
            self.disposition, DataQualityPolicyProvenanceDisposition
        ):
            raise TypeError(
                "disposition must be a "
                "DataQualityPolicyProvenanceDisposition"
            )

        if self.record is not None and not isinstance(
            self.record, DataQualityPolicyProvenanceRecord
        ):
            raise TypeError(
                "record must be a DataQualityPolicyProvenanceRecord "
                "or None"
            )

        if (
            self.disposition
            == DataQualityPolicyProvenanceDisposition.KNOWN
        ):
            if self.record is None:
                raise DataQualityPolicyInvariantError(
                    "KNOWN disposition requires exactly one record"
                )
        elif self.record is not None:
            raise DataQualityPolicyInvariantError(
                f"{self.disposition.value} disposition requires "
                "record=None"
            )
