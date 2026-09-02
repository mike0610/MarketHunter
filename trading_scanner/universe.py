"""
MarketHunter

trading_scanner/universe.py

Module:
The IBKR-resolvable trading universe boundary - injectable, so the
rest of this package (gates, setup classification, the scan cycle) is
fully testable without a live IBKR session. See build_ibkr_universe_source()
for exactly why this returns None today rather than a fabricated live
proof.

V1 scope, exactly as dispatched: US stocks + liquid ETFs only, regular
session, no penny stocks/microcaps, non-crypto. This module resolves
*which contracts exist*; trading_scanner/gates.py separately decides
which of them are liquid/executable enough to scan at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from trading_scanner.models import IbkrContract, LiquidityContext


@dataclass(frozen=True, slots=True)
class ContractMarketData:
    """
    The market-data facts a resolved IbkrContract needs before any
    setup family can even be evaluated: recent OHLCV history (oldest
    first) plus optional catalyst evidence. Never fabricated - a
    missing or too-short history means DATA_FAIL, not a guessed trend.
    """

    conid: int
    closes: tuple[Decimal, ...]
    highs: tuple[Decimal, ...]
    lows: tuple[Decimal, ...]
    volumes: tuple[Decimal, ...]
    observed_at: datetime

    def __post_init__(self) -> None:
        lengths = {len(self.closes), len(self.highs), len(self.lows), len(self.volumes)}
        if len(lengths) != 1:
            raise ValueError("closes/highs/lows/volumes must all be the same length")
        if self.observed_at.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")


class AsyncIbkrUniverseSource(Protocol):
    """
    The scanner's own injectable evidence boundary - implemented by a
    real IBKR client in a future slice. Never returns a fabricated
    contract or history; a genuinely unavailable session/subscription
    is the caller's job to detect and report (see
    build_ibkr_universe_source()), not this protocol's.
    """

    async def resolve_universe(self) -> tuple[IbkrContract, ...]:
        """Every currently IBKR-resolvable US stock/liquid-ETF contract eligible for v1 scope."""
        ...

    async def market_data_for(self, contract: IbkrContract) -> ContractMarketData | None:
        """Recent OHLCV history for one contract, or None if genuinely unavailable - never a guessed candle."""
        ...

    async def liquidity_context_for(self, contract: IbkrContract) -> LiquidityContext | None:
        """Recent average-volume/price facts for one contract, or None if genuinely unavailable."""
        ...


def build_ibkr_universe_source() -> AsyncIbkrUniverseSource | None:
    """
    Always returns None today - this is a deliberate, honestly-reported
    boundary, not a credential check like
    experiment1.alpaca_sip_evidence.build_alpaca_sip_evidence_source or
    experiment1.gil_slack_adapter.build_gil_slack_reader (both of which
    return a real client the moment an env-var credential is set).

    IBKR's own API is not a stateless REST call an env-var API key can
    unlock the way Alpaca's or Bybit's public endpoints are: it
    requires an actively-running, already-logged-in TWS or IB Gateway
    process this session has no way to reach, verify, or safely start,
    plus a funded/entitled brokerage account. No real client
    implementation is attempted in this PR - building one without any
    way to test it against a genuine session would risk exactly the
    "fake a live proof" outcome this dispatch explicitly forbids.

    Terminal state for live proof: BLOCKED-IBKR-SESSION. Every other
    module in this package (gates, setups, store, scan orchestration)
    is fully built and fully tested against AsyncIbkrUniverseSource
    fakes, so a future slice can supply a real implementation here with
    zero change anywhere else.
    """
    return None
