"""
MarketHunter

trend_context/foundation.py

Module:
Trend Context Foundation - Slice 1: immutable Trend Context
contracts, pure deterministic lineage/conflict validation, and an
immutable exact-history read model only

Responsibilities:
- Define the immutable value objects that identify and describe one
  exact governed Trend Context assessment: TrendContextReleaseRef,
  TrendContextIdentity, TrendContextReference, TrendEvidenceRef,
  TrendContextRecord.
- Define TrendContextHistory: an immutable container that validates
  pure lineage/conflict semantics over a caller-supplied tuple of
  TrendContextRecord and exposes exact-key lookup only.

Non-goals (frozen by MH-TREND-CONTEXT-PRODUCER-FOUNDATION-ARCH-001
Council decision):
- No runtime producer, service, writer, persistence, schema, or
  repository of any kind. This module validates and reads
  caller-supplied immutable records only - it never issues them.
- No heuristic adapter and no reuse of structure/indicators/regime
  trend analyzers as a source of truth.
- No current/latest/nearest/winner/fallback selector of any kind.
  History lookup is exact (identity, revision) only.
- No STALE/freshness threshold. UNKNOWN/UNAVAILABLE/CONFLICT are the
  only non-KNOWN dispositions; none of them ever encode as NEUTRAL.
- No wall clock, random, or scheduler usage. available_at is an
  explicit, caller-supplied, timezone-aware governed fact - decision-
  path availability of that exact revision only. It is never market
  EVENT_TIME, producer input observation time, persistence/
  RECORDED_TIME, or CandidateProvenance OBSERVED_TIME.
- No Research, ResearchTrade, CandidateProvenance, Reports/PI,
  Simulation, market-data, pipeline, Scanner, API/UI, persistence, or
  Strategy Lab import or wiring of any kind.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class TrendContextFoundationError(Exception):
    """Base error for Trend Context Foundation failures."""


class TrendContextInvariantError(TrendContextFoundationError):
    """A TrendContextRecord violates a disposition/direction invariant."""


class TrendContextConflictError(TrendContextFoundationError):
    """Same exact (identity, revision) already recorded with a different payload."""


class TrendContextNotFoundError(TrendContextFoundationError):
    """No record exists for the exact requested (identity, revision)."""


class TrendContextLineageError(TrendContextFoundationError):
    """A revision is present without its required preceding revision."""


def _require_nonblank(value: object, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a str")

    if not value.strip():
        raise ValueError(f"{field_name} must be non-blank")


class TrendContextDisposition(str, Enum):
    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"
    CONFLICT = "CONFLICT"


class TrendDirection(str, Enum):
    UP = "UP"
    DOWN = "DOWN"
    NEUTRAL = "NEUTRAL"


@dataclass(frozen=True, slots=True)
class TrendContextReleaseRef:
    """
    Exact, opaque (release_id, opaque_version) pair. Used separately
    for the producer release and the model/policy release. version is
    never parsed, normalized, or ordered.
    """

    release_id: str
    opaque_version: str

    def __post_init__(self) -> None:
        _require_nonblank(self.release_id, "release_id")
        _require_nonblank(self.opaque_version, "opaque_version")


@dataclass(frozen=True, slots=True)
class TrendContextIdentity:
    """
    Exact caller-supplied scope + governance identity for one Trend
    Context lineage: symbol, market, timeframe, producer release, and
    model/policy release. No normalization or inference of any kind.
    """

    symbol: str
    market: str
    timeframe: str
    producer_ref: TrendContextReleaseRef
    model_policy_ref: TrendContextReleaseRef

    def __post_init__(self) -> None:
        _require_nonblank(self.symbol, "symbol")
        _require_nonblank(self.market, "market")
        _require_nonblank(self.timeframe, "timeframe")

        if not isinstance(self.producer_ref, TrendContextReleaseRef):
            raise TypeError(
                "producer_ref must be a TrendContextReleaseRef"
            )

        if not isinstance(self.model_policy_ref, TrendContextReleaseRef):
            raise TypeError(
                "model_policy_ref must be a TrendContextReleaseRef"
            )


@dataclass(frozen=True, slots=True)
class TrendContextReference:
    """
    One exact TrendContextIdentity at one positive integer revision.
    No revision is ever minted here - callers supply it.
    """

    identity: TrendContextIdentity
    revision: int

    def __post_init__(self) -> None:
        if not isinstance(self.identity, TrendContextIdentity):
            raise TypeError("identity must be a TrendContextIdentity")

        if isinstance(self.revision, bool) or not isinstance(
            self.revision, int
        ):
            raise TypeError("revision must be an int")

        if self.revision < 1:
            raise ValueError("revision must be >= 1")


@dataclass(frozen=True, slots=True)
class TrendEvidenceRef:
    """
    Exact, opaque (source_id, evidence_id) pair. Preserved exactly -
    this module does not inspect candles or reconstruct evidence.
    """

    source_id: str
    evidence_id: str

    def __post_init__(self) -> None:
        _require_nonblank(self.source_id, "source_id")
        _require_nonblank(self.evidence_id, "evidence_id")


@dataclass(frozen=True, slots=True)
class TrendContextRecord:
    """
    One exact, immutable governed Trend Context assessment.

    KNOWN requires a non-null direction. UNKNOWN, UNAVAILABLE, and
    CONFLICT all require direction=None - UNKNOWN is never encoded as
    NEUTRAL. evidence_refs is a tuple only; an empty tuple is
    permitted. available_at is a mandatory, timezone-aware,
    caller-supplied governed fact - it is preserved exactly and is
    never derived from a wall clock.
    """

    reference: TrendContextReference
    disposition: TrendContextDisposition
    direction: TrendDirection | None
    evidence_refs: tuple[TrendEvidenceRef, ...]
    available_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.reference, TrendContextReference):
            raise TypeError(
                "reference must be a TrendContextReference"
            )

        if not isinstance(self.disposition, TrendContextDisposition):
            raise TypeError(
                "disposition must be a TrendContextDisposition"
            )

        if self.direction is not None and not isinstance(
            self.direction, TrendDirection
        ):
            raise TypeError(
                "direction must be a TrendDirection or None"
            )

        if not isinstance(self.evidence_refs, tuple) or not all(
            isinstance(item, TrendEvidenceRef)
            for item in self.evidence_refs
        ):
            raise TypeError(
                "evidence_refs must be a tuple of TrendEvidenceRef"
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

        if self.disposition == TrendContextDisposition.KNOWN:
            if self.direction is None:
                raise TrendContextInvariantError(
                    "KNOWN disposition requires a non-null direction"
                )
        elif self.direction is not None:
            raise TrendContextInvariantError(
                f"{self.disposition.value} disposition requires "
                "direction=None"
            )


@dataclass(frozen=True, slots=True)
class TrendContextHistory:
    """
    Immutable, exact-history container over a caller-supplied tuple
    of TrendContextRecord.

    Lineage/conflict semantics, keyed by exact
    (record.reference.identity, record.reference.revision):
    - identical key + identical record: idempotent replay, accepted.
    - identical key + changed payload: hard TrendContextConflictError,
      no overwrite or winner selection.
    - for each identity, every recorded revision N > 1 requires
      revision N - 1 to also be present for that exact same identity,
      so lineage forms a contiguous run starting at revision 1;
      otherwise TrendContextLineageError.
    - a changed symbol/market/timeframe/producer_ref/model_policy_ref
      is a distinct identity and may independently start at
      revision 1.

    Lookup is exact-key only via get_exact()/require_exact() - there
    is no latest/current/nearest/winner/fallback selector.
    """

    records: tuple[TrendContextRecord, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.records, tuple) or not all(
            isinstance(item, TrendContextRecord)
            for item in self.records
        ):
            raise TypeError(
                "records must be a tuple of TrendContextRecord"
            )

        seen: dict[
            tuple[TrendContextIdentity, int], TrendContextRecord
        ] = {}

        for record in self.records:
            key = (
                record.reference.identity,
                record.reference.revision,
            )
            existing = seen.get(key)

            if existing is not None:
                if existing != record:
                    raise TrendContextConflictError(
                        f"identity {key[0]!r} revision {key[1]} "
                        "already recorded with a different payload"
                    )

                continue

            seen[key] = record

        revisions_by_identity: dict[TrendContextIdentity, set[int]] = {}

        for identity, revision in seen.keys():
            revisions_by_identity.setdefault(
                identity, set()
            ).add(revision)

        for identity, revisions in revisions_by_identity.items():
            for revision in revisions:
                if revision > 1 and (revision - 1) not in revisions:
                    raise TrendContextLineageError(
                        f"identity {identity!r} revision {revision} "
                        f"has no preceding revision {revision - 1}"
                    )

    def get_exact(
        self,
        identity: TrendContextIdentity,
        revision: int,
    ) -> TrendContextRecord | None:
        if not isinstance(identity, TrendContextIdentity):
            raise TypeError("identity must be a TrendContextIdentity")

        if isinstance(revision, bool) or not isinstance(
            revision, int
        ):
            raise TypeError("revision must be an int")

        if revision < 1:
            raise ValueError("revision must be >= 1")

        for record in self.records:
            if (
                record.reference.identity == identity
                and record.reference.revision == revision
            ):
                return record

        return None

    def require_exact(
        self,
        identity: TrendContextIdentity,
        revision: int,
    ) -> TrendContextRecord:
        record = self.get_exact(identity, revision)

        if record is None:
            raise TrendContextNotFoundError(
                f"no record for identity {identity!r} "
                f"revision {revision}"
            )

        return record
