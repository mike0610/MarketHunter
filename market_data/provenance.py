"""
MarketHunter

market_data/provenance.py

Module:
Market Data Source Provenance Foundation - Slice 1: immutable
Market/Data Evidence-owned identity/declaration/reference/
observation-ref/provenance-record/result contracts and pure
deterministic validation only

Responsibilities:
- Define MarketVenueIdentity, MarketDataSourceIdentity,
  MarketDataSourceDeclaration, MarketDataSourceReference,
  MarketDataObservationRef, MarketDataProvenanceRecord,
  MarketDataProvenanceDisposition, and MarketDataProvenanceResult:
  the immutable value objects that describe one exact governed
  Market/Data evidence source and one exact prospective provenance
  fact bound to it.

Non-goals (frozen by MH-VENUE-PROVENANCE-LEAD-001 Council decision):
- Constructing any of these value objects is validation only - it is
  NOT governed source issuance. This module introduces no runtime
  issuer, registry, manifest, history, or persistence of any kind.
- No current/latest/default/winner/fallback source selector. No
  SemVer/order/code-SHA/class/module/config/base-URL inference.
  opaque_version is opaque, caller-supplied text - never parsed or
  ordered.
- venue, provider, logical source, and market (product type such as
  spot/futures) are distinct facts. market MUST NOT imply or be
  conflated with venue.
- No execution/account/order-routing venue semantics or aliases.
  This foundation represents market-data evidence source only, never
  an execution venue.
- No REST-vs-WebSocket precedence, multi-source arbitration,
  freshness/stale policy, or Data Quality admissibility/quality
  authority. No quality claim is implied by KNOWN provenance.
- No wall clock, random, or scheduler usage. observed_at and
  available_at are explicit, caller-supplied, timezone-aware governed
  facts, preserved exactly. Council froze their semantic roles, not a
  chronology rule between them - no observed_at <= available_at
  invariant is invented here. Neither is EVENT_TIME, persistence/
  RECORDED_TIME, Research created_at, Trend Context availability, or
  CandidateProvenance OBSERVED_TIME.
- No exchange client, services/market_data.py, MarketSnapshot,
  Scanner, Signal, pipeline, Strategy, Research, Simulation, Data
  Quality, persistence, or API/UI import or wiring of any kind.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class MarketDataProvenanceError(Exception):
    """Base error for Market Data Source Provenance Foundation failures."""


class MarketDataInvariantError(MarketDataProvenanceError):
    """A contract violates a disposition/record or evidence invariant."""


class MarketDataSourceConflictError(MarketDataProvenanceError):
    """An observation ref does not belong to the exact record source_reference."""


def _require_nonblank(value: object, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a str")

    if not value.strip():
        raise ValueError(f"{field_name} must be non-blank")


@dataclass(frozen=True, slots=True)
class MarketVenueIdentity:
    """
    Exact opaque nonblank venue identifier. No normalization or
    execution/order-routing venue semantics of any kind.
    """

    venue_id: str

    def __post_init__(self) -> None:
        _require_nonblank(self.venue_id, "venue_id")


@dataclass(frozen=True, slots=True)
class MarketDataSourceIdentity:
    """
    Exact (venue, provider, logical source) triple. venue, provider,
    and source are kept distinct - no conflation or inference between
    them.
    """

    venue: MarketVenueIdentity
    provider_id: str
    source_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.venue, MarketVenueIdentity):
            raise TypeError("venue must be a MarketVenueIdentity")

        _require_nonblank(self.provider_id, "provider_id")
        _require_nonblank(self.source_id, "source_id")


@dataclass(frozen=True, slots=True)
class MarketDataSourceDeclaration:
    """
    Exact pairing of one MarketDataSourceIdentity with one opaque,
    unordered version. Constructing this value object is validation
    only - it is NOT governed source issuance.
    """

    identity: MarketDataSourceIdentity
    opaque_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.identity, MarketDataSourceIdentity):
            raise TypeError(
                "identity must be a MarketDataSourceIdentity"
            )

        _require_nonblank(self.opaque_version, "opaque_version")


@dataclass(frozen=True, slots=True)
class MarketDataSourceReference:
    """
    Exact wrapper around one MarketDataSourceDeclaration. Delegates
    identity/opaque_version directly - it never copies them into
    parallel authority fields.
    """

    declaration: MarketDataSourceDeclaration

    def __post_init__(self) -> None:
        if not isinstance(self.declaration, MarketDataSourceDeclaration):
            raise TypeError(
                "declaration must be a MarketDataSourceDeclaration"
            )

    @property
    def identity(self) -> MarketDataSourceIdentity:
        return self.declaration.identity

    @property
    def opaque_version(self) -> str:
        return self.declaration.opaque_version


@dataclass(frozen=True, slots=True)
class MarketDataObservationRef:
    """
    Exact, source-bound, immutable observation/evidence reference.
    Preserved exactly - this module does not fetch, reconstruct, or
    interpret candles or evidence.
    """

    source_reference: MarketDataSourceReference
    observation_id: str

    def __post_init__(self) -> None:
        if not isinstance(
            self.source_reference, MarketDataSourceReference
        ):
            raise TypeError(
                "source_reference must be a MarketDataSourceReference"
            )

        _require_nonblank(self.observation_id, "observation_id")


@dataclass(frozen=True, slots=True)
class MarketDataProvenanceRecord:
    """
    One exact, immutable prospective Market/Data provenance fact for
    one exact scope (symbol/market/timeframe), bound to one exact
    source_reference.

    market is a product type (for example spot/futures) only - it
    never implies or is validated against venue. observation_refs is
    a tuple only, order preserved; every observation ref must
    reference this record's exact same source_reference, otherwise
    MarketDataSourceConflictError; an exact duplicate observation ref
    within this record is a deterministic MarketDataInvariantError,
    never silently deduplicated. An empty observation tuple is
    permitted. observed_at and available_at are mandatory,
    timezone-aware, caller-supplied governed facts, preserved exactly
    - no chronology invariant is enforced between them.
    """

    source_reference: MarketDataSourceReference
    symbol: str
    market: str
    timeframe: str
    observation_refs: tuple[MarketDataObservationRef, ...]
    observed_at: datetime
    available_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(
            self.source_reference, MarketDataSourceReference
        ):
            raise TypeError(
                "source_reference must be a MarketDataSourceReference"
            )

        _require_nonblank(self.symbol, "symbol")
        _require_nonblank(self.market, "market")
        _require_nonblank(self.timeframe, "timeframe")

        if not isinstance(self.observation_refs, tuple) or not all(
            isinstance(item, MarketDataObservationRef)
            for item in self.observation_refs
        ):
            raise TypeError(
                "observation_refs must be a tuple of "
                "MarketDataObservationRef"
            )

        for observation_ref in self.observation_refs:
            if observation_ref.source_reference != self.source_reference:
                raise MarketDataSourceConflictError(
                    "observation_ref.source_reference must exactly "
                    "match the record's source_reference"
                )

        if len(set(self.observation_refs)) != len(self.observation_refs):
            raise MarketDataInvariantError(
                "observation_refs must not contain an exact duplicate "
                "observation ref"
            )

        for field_name, value in (
            ("observed_at", self.observed_at),
            ("available_at", self.available_at),
        ):
            if not isinstance(value, datetime):
                raise TypeError(f"{field_name} must be a datetime")

            if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
                raise ValueError(f"{field_name} must be timezone-aware")


class MarketDataProvenanceDisposition(str, Enum):
    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"
    CONFLICT = "CONFLICT"


@dataclass(frozen=True, slots=True)
class MarketDataProvenanceResult:
    """
    KNOWN requires exactly one record. UNKNOWN, UNAVAILABLE, and
    CONFLICT all require record=None - no fake unknown record is ever
    fabricated.
    """

    disposition: MarketDataProvenanceDisposition
    record: MarketDataProvenanceRecord | None

    def __post_init__(self) -> None:
        if not isinstance(
            self.disposition, MarketDataProvenanceDisposition
        ):
            raise TypeError(
                "disposition must be a MarketDataProvenanceDisposition"
            )

        if self.record is not None and not isinstance(
            self.record, MarketDataProvenanceRecord
        ):
            raise TypeError(
                "record must be a MarketDataProvenanceRecord or None"
            )

        if self.disposition == MarketDataProvenanceDisposition.KNOWN:
            if self.record is None:
                raise MarketDataInvariantError(
                    "KNOWN disposition requires exactly one record"
                )
        elif self.record is not None:
            raise MarketDataInvariantError(
                f"{self.disposition.value} disposition requires "
                "record=None"
            )
