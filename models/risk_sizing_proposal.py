"""
MarketHunter

models/risk_sizing_proposal.py

Module:
RiskSizingProposal Contract - Slice 1 (pure contract/value objects)

Responsibilities:
- Define RiskSizingProposal: an immutable, versioned Risk-domain
  value object distinct from RiskResultRecord. RiskResultRecord is
  calculation/assessment provenance; RiskSizingProposal is a governed
  monetary sizing proposal - the two concepts are never conflated.
- Define assess_risk_sizing_proposal_consumability(): a pure function
  mapping a caller-supplied ProposalDisposition to a
  ProposalConsumability, with CURRENT the only consumable disposition.

Non-goals (frozen by ARCH-REQ-RISK-SIZING-PROPOSAL-001):
- No producer, sizing formula, or policy execution - this module
  defines the contract shape only, never generates a proposal.
- No persistence, repository, service, orchestrator, or runtime/API
  wiring of any kind.
- No canonical instrument or quantity-unit registry/shared kernel.
  instrument_reference_kind/instrument_reference/quantity_unit/
  notional_currency/reference_price_unit/reference_price_currency are
  explicit, caller-supplied, locally-scoped contract vocabulary -
  never a governed taxonomy.
- No promotion of legacy RiskResult monetary fields (position_size,
  risk_amount, risk_percent, account_size) - this module never reads
  RiskResultRecord at all, only references it by id+revision.
- No ResearchTrade.notional mapping or fallback of any kind.
- No FX/base-currency authority, no stale-age/freshness calculation -
  ProposalDisposition is caller-supplied, never computed here.
- A value object is not authoritative merely because it exists.
  Authority requires the caller to have obtained it from a governed
  Risk policy/ruleset - this contract records that provenance
  (policy_id/policy_version) but does not verify or enforce it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from models.risk_result_record import IdentityState


class ProposalDisposition(str, Enum):
    """
    Caller-supplied disposition of one proposal read. Not a lifecycle
    and not a freshness calculation - this module never computes
    whether a proposal is current, stale, superseded, conflicting, or
    affected by a changed source; the caller must supply that
    classification.
    """

    CURRENT = "CURRENT"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"
    STALE = "STALE"
    CONFLICT = "CONFLICT"
    SUPERSEDED = "SUPERSEDED"
    SOURCE_CHANGED = "SOURCE_CHANGED"


class ProposalConsumability(str, Enum):
    CONSUMABLE = "CONSUMABLE"
    NOT_CONSUMABLE = "NOT_CONSUMABLE"


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


def _require_decimal(value: object, field_name: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal")


def _require_aware_datetime(value: object, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")

    if value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class RiskSizingProposal:
    """
    Immutable, versioned Risk-domain sizing proposal. One lineage is
    identified by proposal_id; supersession is always explicit and
    declared by the caller, never inferred by this contract.
    """

    proposal_id: str
    revision: int
    generated_at: datetime
    supersedes_revision: int | None

    instrument_reference_kind: str
    instrument_reference: str
    direction: str

    quantity: Decimal
    quantity_unit: str

    notional: Decimal
    notional_currency: str

    reference_price: Decimal
    reference_price_currency: str
    reference_price_unit: str
    reference_price_source_kind: str
    reference_price_source_reference: str

    risk_result_id: str
    risk_result_revision: int

    policy_id: str
    policy_version: str

    candidate_state: IdentityState
    candidate_reference_kind: str | None
    candidate_reference: str | None

    strategy_reference_state: IdentityState
    strategy_reference: str | None

    strategy_version_state: IdentityState
    strategy_version: str | None

    risk_amount: Decimal | None = None
    risk_amount_currency: str | None = None
    risk_amount_unit: str | None = None

    def __post_init__(self) -> None:
        _require_nonblank(self.proposal_id, "proposal_id")
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

            if self.supersedes_revision >= self.revision:
                raise ValueError(
                    "supersedes_revision must be less than revision"
                )

        _require_nonblank(
            self.instrument_reference_kind, "instrument_reference_kind"
        )
        _require_nonblank(self.instrument_reference, "instrument_reference")
        _require_nonblank(self.direction, "direction")

        _require_decimal(self.quantity, "quantity")
        _require_nonblank(self.quantity_unit, "quantity_unit")

        _require_decimal(self.notional, "notional")
        _require_nonblank(self.notional_currency, "notional_currency")

        _require_decimal(self.reference_price, "reference_price")
        _require_nonblank(
            self.reference_price_currency, "reference_price_currency"
        )
        _require_nonblank(self.reference_price_unit, "reference_price_unit")
        _require_nonblank(
            self.reference_price_source_kind, "reference_price_source_kind"
        )
        _require_nonblank(
            self.reference_price_source_reference,
            "reference_price_source_reference",
        )

        _require_nonblank(self.risk_result_id, "risk_result_id")
        _require_positive_int(self.risk_result_revision, "risk_result_revision")

        _require_nonblank(self.policy_id, "policy_id")
        _require_nonblank(self.policy_version, "policy_version")

        _require_optional_nonblank(
            self.candidate_reference_kind, "candidate_reference_kind"
        )
        _require_optional_nonblank(
            self.candidate_reference, "candidate_reference"
        )

        if not isinstance(self.candidate_state, IdentityState):
            raise TypeError("candidate_state must be an IdentityState")

        if self.candidate_state is IdentityState.KNOWN:
            if (
                self.candidate_reference_kind is None
                or self.candidate_reference is None
            ):
                raise ValueError(
                    "KNOWN candidate_state requires candidate_reference_kind "
                    "and candidate_reference"
                )
        else:
            if (
                self.candidate_reference_kind is not None
                or self.candidate_reference is not None
            ):
                raise ValueError(
                    "UNKNOWN candidate_state requires "
                    "candidate_reference_kind and candidate_reference to "
                    "be None"
                )

        _require_optional_nonblank(
            self.strategy_reference, "strategy_reference"
        )

        if not isinstance(self.strategy_reference_state, IdentityState):
            raise TypeError("strategy_reference_state must be an IdentityState")

        if self.strategy_reference_state is IdentityState.KNOWN:
            if self.strategy_reference is None:
                raise ValueError(
                    "KNOWN strategy_reference_state requires "
                    "strategy_reference"
                )
        else:
            if self.strategy_reference is not None:
                raise ValueError(
                    "UNKNOWN strategy_reference_state requires "
                    "strategy_reference to be None"
                )

        _require_optional_nonblank(self.strategy_version, "strategy_version")

        if not isinstance(self.strategy_version_state, IdentityState):
            raise TypeError("strategy_version_state must be an IdentityState")

        if self.strategy_version_state is IdentityState.KNOWN:
            if self.strategy_version is None:
                raise ValueError(
                    "KNOWN strategy_version_state requires strategy_version"
                )
        else:
            if self.strategy_version is not None:
                raise ValueError(
                    "UNKNOWN strategy_version_state requires "
                    "strategy_version to be None"
                )

        risk_amount_fields = (
            self.risk_amount,
            self.risk_amount_currency,
            self.risk_amount_unit,
        )
        none_count = sum(1 for field in risk_amount_fields if field is None)

        if none_count not in (0, len(risk_amount_fields)):
            raise ValueError(
                "risk_amount, risk_amount_currency, and risk_amount_unit "
                "must be all present or all None"
            )

        if self.risk_amount is not None:
            _require_decimal(self.risk_amount, "risk_amount")
            _require_nonblank(self.risk_amount_currency, "risk_amount_currency")
            _require_nonblank(self.risk_amount_unit, "risk_amount_unit")


def assess_risk_sizing_proposal_consumability(
    proposal: RiskSizingProposal,
    disposition: ProposalDisposition,
) -> ProposalConsumability:
    """
    Evaluate whether a proposal read is consumable. CURRENT is the
    only consumable disposition; every other disposition fails
    closed to NOT_CONSUMABLE. CONSUMABLE means disposition-level
    usability only - it does not prove governed issuer authority,
    Portfolio APPROVED/PROCEED, or execution authority.

    Never mutates the proposal - historical proposal objects remain
    unchanged by this assessment.
    """

    if not isinstance(proposal, RiskSizingProposal):
        raise TypeError("proposal must be a RiskSizingProposal")

    if not isinstance(disposition, ProposalDisposition):
        raise TypeError("disposition must be a ProposalDisposition")

    if disposition is ProposalDisposition.CURRENT:
        return ProposalConsumability.CONSUMABLE

    return ProposalConsumability.NOT_CONSUMABLE
