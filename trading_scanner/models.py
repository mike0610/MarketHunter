"""
MarketHunter

trading_scanner/models.py

Module:
The GIL Trading Scanner's own domain shapes - deliberately independent
of experiment1's models (an IBKR contract/candidate is not a GIL
decision, an OrderIntent, or an account-ledger concept; this package
never imports experiment1.engine - see trading_scanner/scan.py). Every
field the dispatch's output contract required is represented
explicitly - no magic score, no fabricated precision.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


def _nonblank(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-blank")


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")


class SetupFamily(str, Enum):
    """
    The exact three v1 setup families the dispatch scoped - do not add
    a fourth without a new dispatch. Each is a closed, deterministic
    classification rule (see trading_scanner/setups.py), never a
    learned/ranked score.
    """

    MOMENTUM_RELATIVE_STRENGTH = "MOMENTUM_RELATIVE_STRENGTH"
    ABNORMAL_VOLUME_CATALYST = "ABNORMAL_VOLUME_CATALYST"
    BREAKOUT_OR_PULLBACK_IN_TREND = "BREAKOUT_OR_PULLBACK_IN_TREND"


class QueueState(str, Enum):
    """
    The Trading Candidate Queue's own lifecycle state - exactly the
    six states the dispatch specified. A REJECTED/INELIGIBLE/DATA_FAIL/
    EXECUTION_BLOCKED candidate is preserved (never deleted) with its
    reason, for later paper-outcome statistics - see
    trading_scanner/store.py.
    """

    CANDIDATE = "CANDIDATE"
    WATCH = "WATCH"
    INELIGIBLE = "INELIGIBLE"
    DATA_FAIL = "DATA_FAIL"
    EXECUTION_BLOCKED = "EXECUTION_BLOCKED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class IbkrContract:
    """
    An IBKR-resolvable contract - the scanner's own canonical
    instrument identity. `conid` is IBKR's own unique integer contract
    identifier; `symbol`/`sec_type`/`exchange`/`currency` are preserved
    verbatim from whatever resolved this contract (never guessed or
    normalized beyond what the source actually returned). `restricted`
    is caller-supplied trading-restriction provenance (e.g. a halt or
    a restricted-list flag a real IBKR connector would report) -
    defaults to False, never inferred by this package itself.
    """

    conid: int
    symbol: str
    sec_type: str
    exchange: str
    currency: str
    primary_exchange: str | None = None
    restricted: bool = False

    def __post_init__(self) -> None:
        if self.conid <= 0:
            raise ValueError("conid must be a positive integer")
        _nonblank(self.symbol, "symbol")
        _nonblank(self.sec_type, "sec_type")
        _nonblank(self.exchange, "exchange")
        _nonblank(self.currency, "currency")


@dataclass(frozen=True, slots=True)
class LiquidityContext:
    """Deterministic, evidence-backed liquidity facts a gate/reader can cite - never a fabricated depth/spread estimate."""

    average_daily_volume: Decimal
    average_daily_dollar_volume: Decimal
    last_price: Decimal

    def __post_init__(self) -> None:
        if self.average_daily_volume < 0 or self.average_daily_dollar_volume < 0:
            raise ValueError("volume figures must be non-negative")
        if self.last_price <= 0:
            raise ValueError("last_price must be positive")


@dataclass(frozen=True, slots=True)
class VolatilityContext:
    """A simple, explainable volatility fact (e.g. a realized-range measure) - never an implied-vol figure this repo has no evidence source for."""

    realized_range_pct: Decimal  # e.g. (high-low)/close over the lookback window, as a percentage

    def __post_init__(self) -> None:
        if self.realized_range_pct < 0:
            raise ValueError("realized_range_pct must be non-negative")


@dataclass(frozen=True, slots=True)
class CatalystEvidence:
    """
    Explicit catalyst provenance - required, never inferred. A setup
    family that needs a catalyst (ABNORMAL_VOLUME_CATALYST) simply
    cannot classify a symbol without one of these actually being
    supplied by the caller; this repo has no news/filing feed of its
    own, so this is always an injected fact, never fabricated here.
    """

    description: str
    source: str
    source_reference: str
    observed_at: datetime

    def __post_init__(self) -> None:
        _nonblank(self.description, "description")
        _nonblank(self.source, "source")
        _nonblank(self.source_reference, "source_reference")
        _aware(self.observed_at, "observed_at")


@dataclass(frozen=True, slots=True)
class TradingCandidate:
    """
    One row of the persistent Trading Candidate Queue - the scanner's
    entire output contract. Every field the dispatch's output-contract
    list required is represented explicitly:

    conid/symbol/sec_type/exchange/currency: see IbkrContract.
    setup_family: see SetupFamily - always exactly one per candidate.
    reason_stack: an ordered tuple of short, human-readable reason
        strings explaining the classification - never a single opaque
        score.
    catalyst: present only for ABNORMAL_VOLUME_CATALYST; None for the
        other two families (they don't require one).
    liquidity/volatility: see LiquidityContext/VolatilityContext.
    evidence_status: "OK" once every required fact was genuinely
        available; freshness_note carries a human-readable explanation
        of the evidence window used (never fabricated freshness).
    eligible: whether the liquidity/executability gate passed.
    invalidation_reference: an obvious, deterministic structural level
        (e.g. "below the 20-day low") - only ever set when the setup
        itself deterministically defines one; GIL owns the actual
        stop/target/RR/sizing/thesis, never this scanner.
    reject_reason: set exactly when queue_state is
        INELIGIBLE/DATA_FAIL/EXECUTION_BLOCKED/REJECTED.
    discovered_at/scan_cycle_id: provenance for exactly which scan pass
        produced this row.
    dedupe_key: deterministic - (conid, setup_family, scan_cycle_id) by
        construction (see trading_scanner/scan.py) - never a randomly
        generated id, so a re-run of the same cycle never duplicates.
    queue_state: see QueueState.
    """

    conid: int
    symbol: str
    sec_type: str
    exchange: str
    currency: str
    setup_family: SetupFamily
    reason_stack: tuple[str, ...]
    liquidity: LiquidityContext
    volatility: VolatilityContext
    evidence_status: str
    eligible: bool
    discovered_at: datetime
    scan_cycle_id: str
    dedupe_key: str
    queue_state: QueueState
    catalyst: CatalystEvidence | None = None
    freshness_note: str | None = None
    invalidation_reference: str | None = None
    reject_reason: str | None = None

    def __post_init__(self) -> None:
        _nonblank(self.symbol, "symbol")
        _nonblank(self.sec_type, "sec_type")
        _nonblank(self.exchange, "exchange")
        _nonblank(self.currency, "currency")
        _nonblank(self.evidence_status, "evidence_status")
        _aware(self.discovered_at, "discovered_at")
        _nonblank(self.scan_cycle_id, "scan_cycle_id")
        _nonblank(self.dedupe_key, "dedupe_key")
        if not self.reason_stack:
            raise ValueError("reason_stack must be non-empty - every candidate must be explainable")
        if self.queue_state in (
            QueueState.INELIGIBLE,
            QueueState.DATA_FAIL,
            QueueState.EXECUTION_BLOCKED,
            QueueState.REJECTED,
        ) and not self.reject_reason:
            raise ValueError(f"{self.queue_state.value} requires reject_reason")
        if self.queue_state in (QueueState.CANDIDATE, QueueState.WATCH) and self.reject_reason:
            raise ValueError(f"{self.queue_state.value} must not carry a reject_reason")
