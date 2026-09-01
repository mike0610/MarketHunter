from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol

from experiment1.market_source import BinanceExperiment1QuoteSource
from experiment1.models import AccountKind


class CostEvidenceStatus(str, Enum):
    """
    EXPLICIT_POLICY: a governed, caller-configured value - never
    silently invented. This is the existing, verified contract for fee
    and slippage: BinanceExperiment1QuoteSource takes fee_bps/
    slippage_bps as explicit constructor arguments (default zero only
    because zero is itself an explicit, non-fabricated policy choice,
    never an unverified guess), and MarketQuote rejects a negative
    value for either at construction.

    NOT_MODELED: this cost category has no implementation anywhere in
    this engine. The absence itself is the auditable fact - it must
    never be read as "verified zero cost", only as "not yet evidenced,
    not applied, not charged".
    """

    EXPLICIT_POLICY = "EXPLICIT_POLICY"
    NOT_MODELED = "NOT_MODELED"


@dataclass(frozen=True, slots=True)
class CostProvenance:
    """One read-only, auditable statement of where a cost category's value comes from."""

    category: str
    status: CostEvidenceStatus
    detail: str


def fee_slippage_provenance(quote_source: BinanceExperiment1QuoteSource) -> tuple[CostProvenance, CostProvenance]:
    """
    Read the exact fee_bps/slippage_bps policy a live quote source is
    configured with, for audit/statistics - never re-derives or
    estimates them. Both are always EXPLICIT_POLICY: this engine has no
    code path where a fee or slippage value is fabricated or silently
    defaulted without the caller having chosen it.
    """
    fee = CostProvenance(
        category="fee",
        status=CostEvidenceStatus.EXPLICIT_POLICY,
        detail=f"fee_bps={quote_source.fee_bps} - explicit caller-configured policy, not fetched or fabricated",
    )
    slippage = CostProvenance(
        category="slippage",
        status=CostEvidenceStatus.EXPLICIT_POLICY,
        detail=f"slippage_bps={quote_source.slippage_bps} - explicit caller-configured policy, not fetched or fabricated",
    )
    return fee, slippage


# Futures funding has no verified, evidence-backed source anywhere in
# this repository (no credentials, no funding-rate provider, no
# governed rule) - see UnavailableFundingProvider. This constant makes
# that absence a single, auditable, always-available fact for any
# caller that wants to report cost provenance without first having to
# construct a provider instance.
FUNDING_NOT_MODELED = CostProvenance(
    category="funding",
    status=CostEvidenceStatus.NOT_MODELED,
    detail=(
        "Futures funding rates have no verified, evidence-backed source in this "
        "environment - this engine applies no funding charge of any kind, and that "
        "absence must never be read as a verified zero funding rate"
    ),
)

# FX is not relevant to any currently supported asset/account path: the
# verified crypto path trades Binance USDT-quoted pairs (already
# USD-denominated) into USD-denominated paper accounts, and every
# non-crypto asset class is BLOCKED-EVIDENCE with no live quotes at
# all (see market_data_providers.py) - so there is no cross-currency
# instrument anywhere to convert. This constant documents that finding
# rather than adding unused conversion plumbing for a currently
# nonexistent need.
FX_NOT_APPLICABLE = CostProvenance(
    category="fx",
    status=CostEvidenceStatus.NOT_MODELED,
    detail=(
        "No currently supported asset/account path involves a currency other than "
        "USD (crypto pairs are USDT-quoted, non-crypto classes are BLOCKED-EVIDENCE "
        "with no live quotes) - FX conversion is not relevant yet, not silently assumed"
    ),
)


@dataclass(frozen=True, slots=True)
class FundingCharge:
    account: AccountKind
    symbol: str
    rate_bps: Decimal
    observed_at: datetime
    source: str
    source_reference: str


class FundingEvidenceProvider(Protocol):
    async def funding_for(self, account: AccountKind, symbol: str) -> FundingCharge | None: ...


class UnavailableFundingProvider:
    """
    Read-only, fail-closed placeholder proving Futures funding has no
    evidence-backed source in this environment - the same pattern as
    UnavailableQuoteProvider (market_data_providers.py). funding_for()
    always returns None; this is intentionally not wired into
    Experiment1Engine's fill or equity logic, since doing so would
    require either a real funding-rate source (none exists) or a
    scheduler to apply it periodically (no VPS access exists in this
    session to run one). Wiring an unevidenced number into position
    accounting would be exactly the fabrication this slice exists to
    prevent, so this stays an explicit, tested, unwired extension
    point until real evidence and scheduling authority both exist.
    """

    def __init__(self, reason: str | None = None) -> None:
        self.reason = reason or FUNDING_NOT_MODELED.detail

    async def funding_for(self, account: AccountKind, symbol: str) -> FundingCharge | None:
        return None
