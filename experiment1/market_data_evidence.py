"""
MarketHunter

experiment1/market_data_evidence.py

Module:
The generic, provider-independent Market Data Evidence Contract v1.
A bare price (see experiment1.models.MarketQuote) is never, on its
own, sufficient evidence for a paper fill or a mark - this module adds
the richer evidence record (experiment1.models.MarketDataEvidence) and
the single, deterministic, fail-closed judgment of whether a given
piece of evidence is good enough to execute against
(EXECUTION_EVIDENCE_OK) versus merely good enough to value a position
against (VALUATION_EVIDENCE_OK - a distinct, broader bar).

This module adds no provider integration and requires no credentials -
it is the foundation a concrete adapter (a future Alpaca SIP, Tiingo,
or Twelve Data integration) builds on, and is intentionally usable and
fully testable today with only a fake AsyncEvidenceSource. The existing
Binance crypto path (experiment1/market_source.py,
experiment1/market_data_providers.py) is untouched - this module does
not replace MarketQuote/AsyncQuoteSource, it bridges into them (see
EvidenceGuardedQuoteSource) so a future provider composes with
run_market_cycle/run_mtm_cycle exactly like BinanceExperiment1QuoteSource
already does, with no change to either cycle function.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Callable, Protocol

from experiment1.models import (
    EvidenceValidationStatus,
    MarketDataEvidence,
    MarketQuote,
    OrderIntent,
    PriceType,
    QuoteMode,
    SessionState,
)

# The only price types that represent a live, currently-executable
# market observation. EOD_CLOSE/DERIVED can be excellent valuation
# evidence but can never satisfy execution-grade evidence - a fill
# must never be priced off yesterday's close or a computed value.
_EXECUTION_ELIGIBLE_PRICE_TYPES = (PriceType.TRADE, PriceType.BID, PriceType.ASK, PriceType.MID)


@dataclass(frozen=True, slots=True)
class EvidenceEvaluation:
    validation_status: EvidenceValidationStatus
    execution_evidence_ok: bool
    valuation_evidence_ok: bool
    detail: str | None = None


def evaluate_market_data_evidence(
    evidence: MarketDataEvidence | None,
    *,
    expected_instrument: str,
    expected_currency: str,
    expected_exchange: str | None = None,
    execution_max_age: timedelta,
    valuation_max_age: timedelta,
    now: datetime | None = None,
) -> EvidenceEvaluation:
    """
    The single place this contract's fail-closed judgment lives.
    Deterministic and pure - no I/O, no fabrication: `evidence` is
    exactly what a provider adapter already observed, `now` is the only
    other input.

    validation_status is VALID only when the evidence genuinely
    describes the instrument/currency/(optionally) listing a caller
    expected, and is not missing/stale beyond valuation_max_age.

    valuation_evidence_ok is True whenever validation_status is VALID -
    the broader bar: a matched, not-too-stale mark, delayed/EOD/derived
    modes and any session state all still acceptable for marking a
    position, per this contract's own "VALUATION_EVIDENCE_OK remains
    separate and may be broader" requirement.

    execution_evidence_ok is True only when, additionally, the evidence
    is within the (normally tighter) execution_max_age, its price_type
    is a live TRADE/BID/ASK/MID observation (never EOD_CLOSE/DERIVED),
    its mode is REALTIME (never DELAYED/EOD/DERIVED), and the session
    is REGULAR - a reference or derived feed, or one outside regular
    trading hours, can never satisfy execution-grade evidence no matter
    how fresh it is.
    """
    moment = now or datetime.now(timezone.utc)

    if evidence is None:
        return EvidenceEvaluation(EvidenceValidationStatus.MISSING, False, False, "no evidence supplied")

    if evidence.instrument != expected_instrument:
        return EvidenceEvaluation(
            EvidenceValidationStatus.INSTRUMENT_MISMATCH,
            False,
            False,
            f"evidence instrument {evidence.instrument!r} does not match expected {expected_instrument!r}",
        )

    if evidence.currency != expected_currency:
        return EvidenceEvaluation(
            EvidenceValidationStatus.CURRENCY_MISMATCH,
            False,
            False,
            f"evidence currency {evidence.currency!r} does not match expected {expected_currency!r}",
        )

    if expected_exchange is not None and evidence.exchange != expected_exchange:
        return EvidenceEvaluation(
            EvidenceValidationStatus.LISTING_MISMATCH,
            False,
            False,
            f"evidence exchange {evidence.exchange!r} does not match expected {expected_exchange!r}",
        )

    age = moment - evidence.source_timestamp
    if age < timedelta(0):
        return EvidenceEvaluation(
            EvidenceValidationStatus.STALE, False, False, f"source_timestamp {evidence.source_timestamp} is in the future"
        )
    if age > valuation_max_age:
        return EvidenceEvaluation(
            EvidenceValidationStatus.STALE,
            False,
            False,
            f"evidence age {age} exceeds valuation_max_age {valuation_max_age}",
        )

    execution_evidence_ok = (
        age <= execution_max_age
        and evidence.mode is QuoteMode.REALTIME
        and evidence.price_type in _EXECUTION_ELIGIBLE_PRICE_TYPES
        and evidence.session_state is SessionState.REGULAR
    )

    return EvidenceEvaluation(EvidenceValidationStatus.VALID, execution_evidence_ok, True, None)


class EvidenceGrade(str, Enum):
    EXECUTION = "EXECUTION"
    VALUATION = "VALUATION"


class AsyncEvidenceSource(Protocol):
    async def evidence_for(self, instrument: str) -> MarketDataEvidence | None:
        """Provider-independent evidence lookup - implemented by a concrete adapter (e.g. a future Alpaca SIP client)."""
        ...


class EvidenceGuardedQuoteSource:
    """
    Adapts any AsyncEvidenceSource (rich MarketDataEvidence) to the
    existing AsyncQuoteSource contract (quote_for(intent) ->
    MarketQuote | None) that experiment1.runtime.run_market_cycle and
    experiment1.mtm.run_mtm_cycle already consume unmodified - so a
    future concrete evidence provider plugs directly into
    MultiAssetQuoteSource's provider mapping (see
    experiment1/market_data_providers.py) with no change to either
    cycle function.

    `grade` picks which of evaluate_market_data_evidence's two gates
    this instance enforces: EXECUTION for a fill-eligible quote source
    (wire into run_market_cycle's quote_source), VALUATION for a
    mark-eligible quote source (wire into run_mtm_cycle's
    quote_source) - the same underlying evidence, two different bars.
    A caller needing both for the same instrument constructs two
    instances around the same inner AsyncEvidenceSource, mirroring how
    FreshnessGuardedQuoteSource already composes around any
    AsyncQuoteSource without duplicating the fetch itself.

    Never fabricates a price: quote_for returns None (the existing
    WAITING_EVIDENCE contract) whenever evaluate_market_data_evidence
    does not grant this instance's grade, exactly as
    UnavailableQuoteProvider/FreshnessGuardedQuoteSource already do for
    the crypto path.
    """

    def __init__(
        self,
        inner: AsyncEvidenceSource,
        grade: EvidenceGrade,
        *,
        expected_currency: str,
        expected_exchange: str | None = None,
        execution_max_age: timedelta,
        valuation_max_age: timedelta,
        fee_bps: Decimal = Decimal("0"),
        slippage_bps: Decimal = Decimal("0"),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if fee_bps < 0 or slippage_bps < 0:
            raise ValueError("fee_bps/slippage_bps must be non-negative")
        self.inner = inner
        self.grade = grade
        self.expected_currency = expected_currency
        self.expected_exchange = expected_exchange
        self.execution_max_age = execution_max_age
        self.valuation_max_age = valuation_max_age
        self.fee_bps = fee_bps
        self.slippage_bps = slippage_bps
        # Injectable only for deterministic testing (see
        # tests/test_experiment1_market_data_evidence.py) - production
        # always uses the real wall clock.
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    async def quote_for(self, intent: OrderIntent) -> MarketQuote | None:
        evidence = await self.inner.evidence_for(intent.symbol)
        evaluation = evaluate_market_data_evidence(
            evidence,
            expected_instrument=intent.symbol,
            expected_currency=self.expected_currency,
            expected_exchange=self.expected_exchange,
            execution_max_age=self.execution_max_age,
            valuation_max_age=self.valuation_max_age,
            now=self.clock(),
        )
        ok = evaluation.execution_evidence_ok if self.grade is EvidenceGrade.EXECUTION else evaluation.valuation_evidence_ok
        if not ok or evidence is None:
            return None
        return MarketQuote(
            symbol=evidence.instrument,
            price=evidence.price,
            observed_at=evidence.source_timestamp,
            source=evidence.provider,
            source_reference=evidence.source_reference,
            fee_bps=self.fee_bps,
            slippage_bps=self.slippage_bps,
        )
