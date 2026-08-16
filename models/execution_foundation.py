"""
MarketHunter

models/execution_foundation.py

Module:
Unified TOP Foundation - Slice 1 (pure identity/provenance contracts)

Responsibilities:
- Define immutable, versioned Execution-domain value objects:
  ExecutionOrder, ExecutionFact, PositionProvenance.
- Define a pure relationship validator,
  assess_position_provenance(), proving the reference chain
  OrderIntent ref -> ExecutionOrder -> ExecutionFact set ->
  Position provenance is internally reference-consistent.

Non-goals (frozen by ARCH-REQ-UNIFIED-TOP-FOUNDATION-001):
- No canonical account/instrument registry or venue state machine.
  account_reference_kind/account_reference,
  instrument_reference_kind/instrument_reference, and
  venue_reference_kind/venue_reference are explicit, caller-supplied,
  locally-scoped contract vocabulary only.
- No first-class OrderIntent issuer. OrderIntent is referenced by
  identity only (order_intent_id/version/reference), never resolved
  or constructed here - only its KNOWN/UNKNOWN reference pairing on
  ExecutionOrder is validated.
- No fill-allocation math, no position quantity/lots/average price,
  no realized/unrealized PnL, no netting/hedging, no open/close
  semantics. PositionProvenance carries exact source ExecutionFact
  references only, never a computed economic state.
- No legacy models.trade_order.TradeOrder or
  models.trade_result.TradeResult import or promotion - those remain
  separate, untouched runtime request/result DTOs.
- No ResearchTrade promotion or fallback mapping of any kind.
- No persistence, repository, API, Dashboard, runtime, worker, or
  exchange-adapter wiring of any kind.
- No stale-age calculation. RelationshipDisposition is caller-
  supplied, never computed here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from models.risk_result_record import IdentityState


class RelationshipDisposition(str, Enum):
    """
    Caller-supplied disposition of one relationship read. Not a
    lifecycle and not a freshness calculation - this module never
    computes whether a relationship is current, unavailable,
    conflicting, superseded, or affected by a changed source; the
    caller must supply that classification.
    """

    CURRENT = "CURRENT"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"
    CONFLICT = "CONFLICT"
    SUPERSEDED = "SUPERSEDED"
    SOURCE_CHANGED = "SOURCE_CHANGED"


class RelationshipUsability(str, Enum):
    USABLE = "USABLE"
    NOT_USABLE = "NOT_USABLE"


class RelationshipReason(str, Enum):
    DISPOSITION_NOT_CURRENT = "DISPOSITION_NOT_CURRENT"
    MISSING_FACT_REFERENCE = "MISSING_FACT_REFERENCE"
    DUPLICATE_FACT_REFERENCE = "DUPLICATE_FACT_REFERENCE"
    EXECUTION_ORDER_REFERENCE_UNKNOWN = "EXECUTION_ORDER_REFERENCE_UNKNOWN"
    EXECUTION_ORDER_REFERENCE_UNRESOLVED = (
        "EXECUTION_ORDER_REFERENCE_UNRESOLVED"
    )
    ORDER_REVISION_MISMATCH = "ORDER_REVISION_MISMATCH"
    ACCOUNT_SCOPE_MISMATCH = "ACCOUNT_SCOPE_MISMATCH"
    INSTRUMENT_SCOPE_MISMATCH = "INSTRUMENT_SCOPE_MISMATCH"
    AMBIGUOUS_REFERENCE = "AMBIGUOUS_REFERENCE"


def _require_nonblank(value: object, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a str")

    if not value.strip():
        raise ValueError(f"{field_name} must be non-blank")


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


def _require_valid_supersession(
    supersedes_revision: object, revision: int, field_name: str
) -> None:
    if supersedes_revision is None:
        return

    if isinstance(supersedes_revision, bool) or not isinstance(
        supersedes_revision, int
    ):
        raise TypeError(f"{field_name} must be an int")

    if supersedes_revision <= 0:
        raise ValueError(f"{field_name} must be positive")

    if supersedes_revision >= revision:
        raise ValueError(f"{field_name} must be less than revision")


@dataclass(frozen=True, slots=True)
class ExecutionOrder:
    """
    Immutable, versioned Execution-domain order truth. Identity is
    stable and explicit; supersession is declared, never inferred
    from symbol+time or any other convenience field.
    """

    execution_order_id: str
    revision: int
    observed_at: datetime
    supersedes_revision: int | None

    venue_reference_kind: str
    venue_reference: str

    source_reference_kind: str
    source_reference: str

    account_reference_kind: str
    account_reference: str

    instrument_reference_kind: str
    instrument_reference: str

    order_intent_state: IdentityState
    order_intent_id: str | None
    order_intent_version: str | None
    order_intent_reference: str | None

    def __post_init__(self) -> None:
        _require_nonblank(self.execution_order_id, "execution_order_id")
        _require_positive_int(self.revision, "revision")
        _require_aware_datetime(self.observed_at, "observed_at")
        _require_valid_supersession(
            self.supersedes_revision, self.revision, "supersedes_revision"
        )

        _require_nonblank(self.venue_reference_kind, "venue_reference_kind")
        _require_nonblank(self.venue_reference, "venue_reference")
        _require_nonblank(self.source_reference_kind, "source_reference_kind")
        _require_nonblank(self.source_reference, "source_reference")
        _require_nonblank(
            self.account_reference_kind, "account_reference_kind"
        )
        _require_nonblank(self.account_reference, "account_reference")
        _require_nonblank(
            self.instrument_reference_kind, "instrument_reference_kind"
        )
        _require_nonblank(self.instrument_reference, "instrument_reference")

        if not isinstance(self.order_intent_state, IdentityState):
            raise TypeError("order_intent_state must be an IdentityState")

        if self.order_intent_state is IdentityState.KNOWN:
            for value, field_name in (
                (self.order_intent_id, "order_intent_id"),
                (self.order_intent_version, "order_intent_version"),
                (self.order_intent_reference, "order_intent_reference"),
            ):
                if value is None:
                    raise ValueError(
                        f"KNOWN order_intent_state requires {field_name}"
                    )
                _require_nonblank(value, field_name)
        else:
            if (
                self.order_intent_id is not None
                or self.order_intent_version is not None
                or self.order_intent_reference is not None
            ):
                raise ValueError(
                    "UNKNOWN order_intent_state requires order_intent_id, "
                    "order_intent_version, and order_intent_reference to "
                    "all be None"
                )


@dataclass(frozen=True, slots=True)
class ExecutionFact:
    """
    Immutable Execution-domain fact (e.g. a fill, acknowledgement,
    reject, or cancel). fact_kind is a local opaque string, not a
    venue lifecycle taxonomy. History is append-only - a fact is
    never rewritten to reflect later aggregate state.
    """

    execution_fact_id: str
    fact_kind: str
    fact_at: datetime

    venue_reference_kind: str
    venue_reference: str

    source_reference_kind: str
    source_reference: str

    execution_order_state: IdentityState
    execution_order_id: str | None
    execution_order_revision: int | None

    def __post_init__(self) -> None:
        _require_nonblank(self.execution_fact_id, "execution_fact_id")
        _require_nonblank(self.fact_kind, "fact_kind")
        _require_aware_datetime(self.fact_at, "fact_at")

        _require_nonblank(self.venue_reference_kind, "venue_reference_kind")
        _require_nonblank(self.venue_reference, "venue_reference")
        _require_nonblank(self.source_reference_kind, "source_reference_kind")
        _require_nonblank(self.source_reference, "source_reference")

        if not isinstance(self.execution_order_state, IdentityState):
            raise TypeError("execution_order_state must be an IdentityState")

        if self.execution_order_state is IdentityState.KNOWN:
            if self.execution_order_id is None:
                raise ValueError(
                    "KNOWN execution_order_state requires execution_order_id"
                )
            _require_nonblank(self.execution_order_id, "execution_order_id")

            if self.execution_order_revision is None:
                raise ValueError(
                    "KNOWN execution_order_state requires "
                    "execution_order_revision"
                )
            _require_positive_int(
                self.execution_order_revision, "execution_order_revision"
            )
        else:
            if (
                self.execution_order_id is not None
                or self.execution_order_revision is not None
            ):
                raise ValueError(
                    "UNKNOWN execution_order_state requires "
                    "execution_order_id and execution_order_revision to "
                    "both be None"
                )


@dataclass(frozen=True, slots=True)
class PositionProvenance:
    """
    Foundation position provenance: exact account+instrument scope
    plus the exact set of source ExecutionFact ids it was
    reconstructed from. Carries no quantity, lot, average price, or
    PnL - those policies remain deferred to a later, separately
    authorized slice.
    """

    position_id: str
    revision: int
    observed_at: datetime
    supersedes_revision: int | None

    account_reference_kind: str
    account_reference: str

    instrument_reference_kind: str
    instrument_reference: str

    execution_fact_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_nonblank(self.position_id, "position_id")
        _require_positive_int(self.revision, "revision")
        _require_aware_datetime(self.observed_at, "observed_at")
        _require_valid_supersession(
            self.supersedes_revision, self.revision, "supersedes_revision"
        )

        _require_nonblank(
            self.account_reference_kind, "account_reference_kind"
        )
        _require_nonblank(self.account_reference, "account_reference")
        _require_nonblank(
            self.instrument_reference_kind, "instrument_reference_kind"
        )
        _require_nonblank(self.instrument_reference, "instrument_reference")

        if not isinstance(self.execution_fact_ids, tuple) or not all(
            isinstance(item, str) for item in self.execution_fact_ids
        ):
            raise TypeError("execution_fact_ids must be a tuple of str")

        if not self.execution_fact_ids:
            raise ValueError("execution_fact_ids must be non-empty")

        for fact_id in self.execution_fact_ids:
            _require_nonblank(fact_id, "execution_fact_ids entry")


@dataclass(frozen=True, slots=True)
class RelationshipAssessment:
    usability: RelationshipUsability
    disposition: RelationshipDisposition
    reasons: tuple[RelationshipReason, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.usability, RelationshipUsability):
            raise TypeError("usability must be a RelationshipUsability")

        if not isinstance(self.disposition, RelationshipDisposition):
            raise TypeError("disposition must be a RelationshipDisposition")

        if not isinstance(self.reasons, tuple) or not all(
            isinstance(item, RelationshipReason) for item in self.reasons
        ):
            raise TypeError("reasons must be a tuple of RelationshipReason")

        if (
            self.usability is RelationshipUsability.NOT_USABLE
            and not self.reasons
        ):
            raise ValueError("NOT_USABLE requires at least one reason")

        if (
            self.usability is RelationshipUsability.USABLE
            and self.reasons
        ):
            raise ValueError(
                "USABLE must not carry reasons - reasons imply this "
                "relationship is not actually usable"
            )


def assess_position_provenance(
    position: PositionProvenance,
    execution_orders: tuple[ExecutionOrder, ...],
    execution_facts: tuple[ExecutionFact, ...],
    disposition: RelationshipDisposition,
) -> RelationshipAssessment:
    """
    Validate that the reference chain from a PositionProvenance
    through its ExecutionFact ids to their ExecutionOrder references
    is internally reference-consistent within the given account and
    instrument scope. Never reconstructs economic state, never
    infers a missing link, never mutates any input.
    """

    if not isinstance(position, PositionProvenance):
        raise TypeError("position must be a PositionProvenance")

    if not isinstance(execution_orders, tuple) or not all(
        isinstance(item, ExecutionOrder) for item in execution_orders
    ):
        raise TypeError("execution_orders must be a tuple of ExecutionOrder")

    if not isinstance(execution_facts, tuple) or not all(
        isinstance(item, ExecutionFact) for item in execution_facts
    ):
        raise TypeError("execution_facts must be a tuple of ExecutionFact")

    if not isinstance(disposition, RelationshipDisposition):
        raise TypeError("disposition must be a RelationshipDisposition")

    if disposition is not RelationshipDisposition.CURRENT:
        return RelationshipAssessment(
            usability=RelationshipUsability.NOT_USABLE,
            disposition=disposition,
            reasons=(RelationshipReason.DISPOSITION_NOT_CURRENT,),
        )

    fact_by_id: dict[str, ExecutionFact] = {}
    duplicate_fact_ids: set[str] = set()

    for fact in execution_facts:
        if fact.execution_fact_id in fact_by_id:
            duplicate_fact_ids.add(fact.execution_fact_id)
        else:
            fact_by_id[fact.execution_fact_id] = fact

    order_by_key: dict[tuple[str, int], ExecutionOrder] = {}
    duplicate_order_keys: set[tuple[str, int]] = set()

    for order in execution_orders:
        key = (order.execution_order_id, order.revision)
        if key in order_by_key:
            duplicate_order_keys.add(key)
        else:
            order_by_key[key] = order

    reasons: list[RelationshipReason] = []

    if duplicate_fact_ids:
        reasons.append(RelationshipReason.DUPLICATE_FACT_REFERENCE)

    if duplicate_order_keys:
        reasons.append(RelationshipReason.AMBIGUOUS_REFERENCE)

    missing_fact = False
    order_unknown = False
    order_unresolved = False
    revision_mismatch = False
    account_mismatch = False
    instrument_mismatch = False

    for fact_id in position.execution_fact_ids:
        if fact_id in duplicate_fact_ids or fact_id not in fact_by_id:
            missing_fact = True
            continue

        fact = fact_by_id[fact_id]

        if fact.execution_order_state is not IdentityState.KNOWN:
            order_unknown = True
            continue

        key = (fact.execution_order_id, fact.execution_order_revision)

        if key in duplicate_order_keys:
            continue

        order = order_by_key.get(key)

        if order is None:
            same_id_orders = [
                item
                for item in execution_orders
                if item.execution_order_id == fact.execution_order_id
            ]

            if same_id_orders:
                revision_mismatch = True
            else:
                order_unresolved = True

            continue

        if (
            order.account_reference_kind != position.account_reference_kind
            or order.account_reference != position.account_reference
        ):
            account_mismatch = True

        if (
            order.instrument_reference_kind
            != position.instrument_reference_kind
            or order.instrument_reference != position.instrument_reference
        ):
            instrument_mismatch = True

    if missing_fact:
        reasons.append(RelationshipReason.MISSING_FACT_REFERENCE)

    if order_unknown:
        reasons.append(RelationshipReason.EXECUTION_ORDER_REFERENCE_UNKNOWN)

    if order_unresolved:
        reasons.append(
            RelationshipReason.EXECUTION_ORDER_REFERENCE_UNRESOLVED
        )

    if revision_mismatch:
        reasons.append(RelationshipReason.ORDER_REVISION_MISMATCH)

    if account_mismatch:
        reasons.append(RelationshipReason.ACCOUNT_SCOPE_MISMATCH)

    if instrument_mismatch:
        reasons.append(RelationshipReason.INSTRUMENT_SCOPE_MISMATCH)

    if reasons:
        return RelationshipAssessment(
            usability=RelationshipUsability.NOT_USABLE,
            disposition=disposition,
            reasons=tuple(reasons),
        )

    return RelationshipAssessment(
        usability=RelationshipUsability.USABLE,
        disposition=disposition,
        reasons=(),
    )
