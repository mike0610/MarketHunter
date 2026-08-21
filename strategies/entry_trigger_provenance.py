"""
MarketHunter

strategies/entry_trigger_provenance.py

Module:
Entry Trigger Provenance Foundation - Slice 1: immutable
Strategy-owned Entry Trigger declaration/reference/evidence/result
contracts and pure deterministic validation only

Responsibilities:
- Define EntryTriggerIdentity, EntryTriggerDeclaration,
  EntryTriggerReference, EntryTriggerEvidenceRef,
  EntryTriggerProvenanceRecord, EntryTriggerProvenanceDisposition,
  and EntryTriggerProvenanceResult: the immutable value objects that
  describe one exact governed Entry Trigger provenance assessment,
  subordinate to and bound to one exact already-issued
  StrategyReleaseDeclaration.
- Define validate_entry_trigger_binding(): a pure function that
  checks an exact StrategyExecutionBinding.release against the
  parent StrategyReleaseDeclaration carried by an
  EntryTriggerReference/EntryTriggerProvenanceRecord.

Non-goals (frozen by MH-ENTRY-TRIGGER-PROVENANCE-ARCH-001 Council
decision):
- Constructing an EntryTriggerDeclaration/EntryTriggerReference/
  EntryTriggerProvenanceRecord is validation only - it is NOT
  governed issuance. This module introduces no durable declaration
  manifest, history, source, or writer of any kind.
- No runtime KNOWN issuer, producer, or rule evaluation. Nothing
  here decides whether a trigger fired - callers supply the exact
  disposition/record.
- No current/latest/nearest/SemVer/name/class/file/module/time
  inference of any kind. opaque_version is opaque, caller-supplied
  text - never parsed or ordered.
- No cross-record conflict arbitration, multi-trigger composition,
  or runtime conflict winner selection. Same trigger text under a
  different exact parent StrategyReleaseDeclaration is a distinct
  governed declaration - never overwritten or selected as winner.
- No wall clock, random, or scheduler usage. available_at is an
  explicit, caller-supplied, timezone-aware governed fact - decision-
  path availability of this trigger provenance only. It is never
  candle/event time, Research created_at, persistence time, Trend
  Context available_at, or CandidateProvenance OBSERVED_TIME.
- No Signal, Scanner, pipeline, Research, Simulation, market-data,
  Trend Context, persistence, API/UI, or Strategy Lab import or
  wiring of any kind.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from strategies.execution_binding import StrategyExecutionBinding
from strategies.runtime_release_manifest import StrategyReleaseDeclaration


class EntryTriggerProvenanceError(Exception):
    """Base error for Entry Trigger Provenance Foundation failures."""


class EntryTriggerInvariantError(EntryTriggerProvenanceError):
    """A contract violates a disposition/record or evidence invariant."""


class EntryTriggerParentReleaseMismatchError(EntryTriggerProvenanceError):
    """identity.strategy_id does not match strategy_release.identity.strategy_id."""


class EntryTriggerBindingConflictError(EntryTriggerProvenanceError):
    """binding.release does not match the exact parent StrategyReleaseDeclaration."""


def _require_nonblank(value: object, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a str")

    if not value.strip():
        raise ValueError(f"{field_name} must be non-blank")


@dataclass(frozen=True, slots=True)
class EntryTriggerIdentity:
    """
    Exact opaque (strategy_id, trigger_id) pair. No normalization or
    name/class/file/module inference of any kind.
    """

    strategy_id: str
    trigger_id: str

    def __post_init__(self) -> None:
        _require_nonblank(self.strategy_id, "strategy_id")
        _require_nonblank(self.trigger_id, "trigger_id")


@dataclass(frozen=True, slots=True)
class EntryTriggerDeclaration:
    """
    Exact pairing of one EntryTriggerIdentity, one opaque trigger
    version, and the exact already-issued parent
    StrategyReleaseDeclaration it is subordinate to. Constructing
    this value object is validation only - it is NOT governed
    issuance.
    """

    identity: EntryTriggerIdentity
    opaque_version: str
    strategy_release: StrategyReleaseDeclaration

    def __post_init__(self) -> None:
        if not isinstance(self.identity, EntryTriggerIdentity):
            raise TypeError("identity must be an EntryTriggerIdentity")

        _require_nonblank(self.opaque_version, "opaque_version")

        if not isinstance(self.strategy_release, StrategyReleaseDeclaration):
            raise TypeError(
                "strategy_release must be a StrategyReleaseDeclaration"
            )

        if (
            self.identity.strategy_id
            != self.strategy_release.identity.strategy_id
        ):
            raise EntryTriggerParentReleaseMismatchError(
                "identity.strategy_id must exactly match "
                "strategy_release.identity.strategy_id"
            )

    @property
    def declaration_key(self) -> tuple[str, str, str, str]:
        """
        Deterministic comparison/testing key only:
        (strategy_id, trigger_id, parent release version,
        opaque_version). The parent StrategyReleaseDeclaration OBJECT
        remains part of semantic equality and authority - a changed
        parent release payload is never collapsed merely because
        this text key matches.
        """

        return (
            self.identity.strategy_id,
            self.identity.trigger_id,
            self.strategy_release.version.version,
            self.opaque_version,
        )


@dataclass(frozen=True, slots=True)
class EntryTriggerReference:
    """
    Exact wrapper around one EntryTriggerDeclaration. Delegates
    identity/opaque_version/strategy_release directly - it never
    copies strategy/trigger/version strings into parallel authority
    fields.
    """

    declaration: EntryTriggerDeclaration

    def __post_init__(self) -> None:
        if not isinstance(self.declaration, EntryTriggerDeclaration):
            raise TypeError(
                "declaration must be an EntryTriggerDeclaration"
            )

    @property
    def identity(self) -> EntryTriggerIdentity:
        return self.declaration.identity

    @property
    def opaque_version(self) -> str:
        return self.declaration.opaque_version

    @property
    def strategy_release(self) -> StrategyReleaseDeclaration:
        return self.declaration.strategy_release


@dataclass(frozen=True, slots=True)
class EntryTriggerEvidenceRef:
    """
    Exact, opaque (source_id, evidence_id) pair. Preserved exactly -
    this module does not fetch or interpret Signal.reasons/metadata
    or candles.
    """

    source_id: str
    evidence_id: str

    def __post_init__(self) -> None:
        _require_nonblank(self.source_id, "source_id")
        _require_nonblank(self.evidence_id, "evidence_id")


@dataclass(frozen=True, slots=True)
class EntryTriggerProvenanceRecord:
    """
    One exact, immutable governed Entry Trigger provenance
    assessment for one exact scope (symbol/market/timeframe).

    evidence_refs is a tuple only, order preserved; an exact
    duplicate evidence ref within one record is a deterministic
    invariant error, never silently deduplicated. An empty evidence
    tuple is permitted. available_at is a mandatory, timezone-aware,
    caller-supplied governed fact - preserved exactly and never
    derived from a wall clock.
    """

    reference: EntryTriggerReference
    symbol: str
    market: str
    timeframe: str
    evidence_refs: tuple[EntryTriggerEvidenceRef, ...]
    available_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.reference, EntryTriggerReference):
            raise TypeError(
                "reference must be an EntryTriggerReference"
            )

        _require_nonblank(self.symbol, "symbol")
        _require_nonblank(self.market, "market")
        _require_nonblank(self.timeframe, "timeframe")

        if not isinstance(self.evidence_refs, tuple) or not all(
            isinstance(item, EntryTriggerEvidenceRef)
            for item in self.evidence_refs
        ):
            raise TypeError(
                "evidence_refs must be a tuple of EntryTriggerEvidenceRef"
            )

        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise EntryTriggerInvariantError(
                "evidence_refs must not contain an exact duplicate "
                "evidence ref"
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


class EntryTriggerProvenanceDisposition(str, Enum):
    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"
    CONFLICT = "CONFLICT"


@dataclass(frozen=True, slots=True)
class EntryTriggerProvenanceResult:
    """
    KNOWN requires exactly one record. UNKNOWN, UNAVAILABLE, and
    CONFLICT all require record=None - no fake unknown record is ever
    fabricated.
    """

    disposition: EntryTriggerProvenanceDisposition
    record: EntryTriggerProvenanceRecord | None

    def __post_init__(self) -> None:
        if not isinstance(
            self.disposition, EntryTriggerProvenanceDisposition
        ):
            raise TypeError(
                "disposition must be an EntryTriggerProvenanceDisposition"
            )

        if self.record is not None and not isinstance(
            self.record, EntryTriggerProvenanceRecord
        ):
            raise TypeError(
                "record must be an EntryTriggerProvenanceRecord or None"
            )

        if self.disposition == EntryTriggerProvenanceDisposition.KNOWN:
            if self.record is None:
                raise EntryTriggerInvariantError(
                    "KNOWN disposition requires exactly one record"
                )
        elif self.record is not None:
            raise EntryTriggerInvariantError(
                f"{self.disposition.value} disposition requires "
                "record=None"
            )


def validate_entry_trigger_binding(
    reference_or_record: EntryTriggerReference | EntryTriggerProvenanceRecord,
    binding: StrategyExecutionBinding,
) -> None:
    """
    Pure validation only: check that binding.release is the exact
    same parent StrategyReleaseDeclaration carried by
    reference_or_record. Raises EntryTriggerBindingConflictError on
    mismatch. No lookup, minting, inference, time acquisition, rule
    evaluation, mutation, or result fabrication of any kind.
    """

    if isinstance(reference_or_record, EntryTriggerProvenanceRecord):
        reference = reference_or_record.reference
    elif isinstance(reference_or_record, EntryTriggerReference):
        reference = reference_or_record
    else:
        raise TypeError(
            "reference_or_record must be an EntryTriggerReference or "
            "EntryTriggerProvenanceRecord"
        )

    if not isinstance(binding, StrategyExecutionBinding):
        raise TypeError("binding must be a StrategyExecutionBinding")

    if binding.release != reference.strategy_release:
        raise EntryTriggerBindingConflictError(
            "binding.release does not match the exact parent "
            "StrategyReleaseDeclaration carried by reference_or_record"
        )
