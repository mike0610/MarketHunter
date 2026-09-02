"""
MarketHunter

experiment1/alpaca_sip_evidence.py

Module:
A read-only Alpaca Market Data API (SIP feed / Algo Trader Plus)
AsyncEvidenceSource implementation for the generic Market Data Evidence
Contract v1 (experiment1/market_data_evidence.py) - the first concrete
US stocks/ETF execution-grade provider, per the latest GIL research
direction (Alpaca SIP superseding the earlier Tiingo direction; Tiingo
remains a valuation/trigger-grade candidate elsewhere).

Hard boundaries, exactly as dispatched:
  - Market Data API only (`data.alpaca.markets`). No Alpaca trading
    endpoint (orders, positions, account) is ever called - the market
    clock endpoint lives on the Trading API host, so session state is
    derived instead from NYSE/Nasdaq's own well-established regular-
    session hours (see _derive_session_state), never from a second API
    surface this module has no business touching.
  - No live orders, no real capital, ever - this module only produces
    MarketDataEvidence; nothing here calls submit_intent/execute_pending.
  - No fabricated quotes: any acquisition failure (network error,
    non-200, missing/invalid bid or ask, an unparseable timestamp, an
    entitlement/feed rejection) returns None - the existing
    WAITING_EVIDENCE contract - never a guessed price.
  - Credentials are secret/env driven only (see
    build_alpaca_sip_evidence_source/ENV_ALPACA_API_KEY_ID/
    ENV_ALPACA_API_SECRET_KEY) - never logged, never committed.
  - Provider-independent design preserved: this module implements
    AsyncEvidenceSource exactly as any other provider would; nothing
    in experiment1/market_data_evidence.py changed to accommodate it.

Product Owner has NOT authorized any paid Alpaca subscription/account
purchase - build_alpaca_sip_evidence_source() returns None (fail closed
by omission, the same pattern already used for the Slack GIL adapter
and every unregistered non-crypto asset class) unless a genuine
Algo Trader Plus API key pair has separately been provisioned. This
module ships fully built and fully tested against a fake HTTP
transport; it has never been exercised against a live Alpaca account.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable
from zoneinfo import ZoneInfo

import httpx

from experiment1.market_data_evidence import AsyncEvidenceSource
from experiment1.models import MarketDataEvidence, PriceType, QuoteMode, SessionState

ALPACA_DATA_BASE_URL = "https://data.alpaca.markets"

ENV_ALPACA_API_KEY_ID = "EXPERIMENT1_ALPACA_API_KEY_ID"
ENV_ALPACA_API_SECRET_KEY = "EXPERIMENT1_ALPACA_API_SECRET_KEY"

_NY_TZ = ZoneInfo("America/New_York")

# Alpaca returns RFC3339 timestamps with nanosecond precision
# (e.g. "2021-04-20T13:01:57.822866956Z") - Python's datetime.fromisoformat
# only supports up to microsecond precision, so the fractional-seconds
# part is truncated to 6 digits before parsing. This is an honest
# precision loss (still genuinely sub-millisecond), never a fabrication.
_FRACTIONAL_SECONDS_RE = re.compile(r"(\.\d{1,6})\d*")


def _parse_alpaca_timestamp(raw: str) -> datetime:
    normalized = raw.replace("Z", "+00:00")
    normalized = _FRACTIONAL_SECONDS_RE.sub(r"\1", normalized)
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError(f"Alpaca timestamp {raw!r} did not include a UTC offset")
    return parsed


def _derive_session_state(moment_utc: datetime) -> SessionState:
    """
    Derived from NYSE/Nasdaq's standard regular-session hours
    (9:30-16:00 ET) and standard pre/post-market windows (4:00-9:30 ET,
    16:00-20:00 ET) on a weekday - real, public, non-fabricated market-
    structure fact, not a value read from any API response (the
    market-clock endpoint that WOULD give ground truth lives on
    Alpaca's Trading API host, which this module never calls - see
    module docstring). Does NOT account for market holidays - no
    verified holiday-calendar evidence source is wired into this
    adapter, so a market holiday within these weekday hours is a known,
    documented gap, never silently hidden.
    """
    local = moment_utc.astimezone(_NY_TZ)
    if local.weekday() >= 5:
        return SessionState.CLOSED
    minutes = local.hour * 60 + local.minute
    if 4 * 60 <= minutes < 9 * 60 + 30:
        return SessionState.PRE_MARKET
    if 9 * 60 + 30 <= minutes < 16 * 60:
        return SessionState.REGULAR
    if 16 * 60 <= minutes < 20 * 60:
        return SessionState.POST_MARKET
    return SessionState.CLOSED


class AlpacaSipEvidenceSource:
    """
    Read-only AsyncEvidenceSource for Alpaca's SIP (consolidated US
    exchange) latest-quote endpoint. Every acquisition failure - a
    network error, a non-200 response (including a 403 for missing SIP
    entitlement), a quote missing a valid bid or ask, or an unparseable
    timestamp - returns None rather than raising or guessing, matching
    this contract's "fail closed to WAITING_EVIDENCE" requirement
    exactly. Never calls an Alpaca trading endpoint.
    """

    def __init__(
        self,
        api_key_id: str,
        api_secret_key: str,
        client: httpx.AsyncClient,
        *,
        currency: str = "USD",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not api_key_id or not api_key_id.strip():
            raise ValueError("api_key_id must be non-blank")
        if not api_secret_key or not api_secret_key.strip():
            raise ValueError("api_secret_key must be non-blank")
        self._api_key_id = api_key_id
        self._api_secret_key = api_secret_key
        self._client = client
        self._currency = currency
        # Injectable only for deterministic testing (see
        # tests/test_experiment1_alpaca_sip_evidence.py) - production
        # always uses the real wall clock.
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def _headers(self) -> dict:
        return {"APCA-API-KEY-ID": self._api_key_id, "APCA-API-SECRET-KEY": self._api_secret_key}

    async def evidence_for(self, instrument: str) -> MarketDataEvidence | None:
        try:
            response = await self._client.get(
                f"{ALPACA_DATA_BASE_URL}/v2/stocks/{instrument}/quotes/latest",
                params={"feed": "sip"},
                headers=self._headers,
            )
        except httpx.HTTPError:
            return None

        if response.status_code != 200:
            # Covers a 403 (SIP entitlement/subscription not permitted),
            # a 404 (unknown symbol), and any other non-success - all
            # fail closed identically, never guessed apart without
            # stronger evidence than an HTTP status code alone provides.
            return None

        try:
            payload = response.json()
        except ValueError:
            return None

        quote = payload.get("quote") if isinstance(payload, dict) else None
        if not isinstance(quote, dict):
            return None

        bid_raw = quote.get("bp")
        ask_raw = quote.get("ap")
        if bid_raw is None or ask_raw is None:
            return None
        try:
            bid = Decimal(str(bid_raw))
            ask = Decimal(str(ask_raw))
        except (ArithmeticError, ValueError, TypeError):
            return None
        if bid <= 0 or ask <= 0:
            return None

        raw_timestamp = quote.get("t")
        if not isinstance(raw_timestamp, str):
            return None
        try:
            source_timestamp = _parse_alpaca_timestamp(raw_timestamp)
        except ValueError:
            return None

        receive_timestamp = self._clock()
        mid_price = (bid + ask) / 2

        return MarketDataEvidence(
            provider="ALPACA_SIP",
            instrument=instrument,
            provider_symbol=payload.get("symbol", instrument) if isinstance(payload, dict) else instrument,
            # SIP consolidates every US exchange into one feed - no
            # single-exchange listing code is meaningful for a SIP
            # quote, so the feed identity itself is the exchange value.
            exchange="ALPACA_SIP",
            currency=self._currency,
            price=mid_price,
            price_type=PriceType.MID,
            source_timestamp=source_timestamp,
            receive_timestamp=receive_timestamp,
            session_state=_derive_session_state(receive_timestamp),
            mode=QuoteMode.REALTIME,
            source_reference=f"alpaca-sip-quote:{instrument}:{raw_timestamp}",
        )


def build_alpaca_sip_evidence_source(*, client: httpx.AsyncClient | None = None) -> AsyncEvidenceSource | None:
    """
    Returns a real AlpacaSipEvidenceSource only when BOTH
    EXPERIMENT1_ALPACA_API_KEY_ID and EXPERIMENT1_ALPACA_API_SECRET_KEY
    are set. Product Owner has NOT authorized any paid Alpaca
    subscription/account purchase - until real credentials are
    genuinely provisioned, this returns None so a caller skips wiring
    this provider entirely, the same fail-closed-by-omission pattern
    already used for the Slack GIL adapter
    (experiment1/gil_slack_adapter.py's build_gil_slack_reader) and
    every unregistered asset class in MultiAssetQuoteSource. Never
    logs either credential.
    """
    key_id = os.environ.get(ENV_ALPACA_API_KEY_ID)
    secret_key = os.environ.get(ENV_ALPACA_API_SECRET_KEY)
    if not key_id or not secret_key:
        return None
    return AlpacaSipEvidenceSource(key_id, secret_key, client or httpx.AsyncClient())
