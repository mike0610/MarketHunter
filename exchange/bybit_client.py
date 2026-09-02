"""
MarketHunter

exchange/bybit_client.py

Module:
Bybit Client (public market data only) + a narrow, research-only
cross-venue historical price unblocker.

Responsibilities:
- Request PUBLIC Bybit V5 kline (candle) data for USDT perpetual
  futures ("linear" category) - no authentication, no account, no
  order/trading endpoint anywhere in this module. Zero cost, zero
  paid entitlement, matching the current "no paid services" standing
  constraint exactly.
- Normalize the raw response into BybitPerpetualCandle, UTC-aware,
  with explicit raw symbol/contract provenance. This is deliberately
  NOT models.candle.Candle: Bybit's public kline response does not
  provide a trade count or a taker-buy volume breakdown the way
  Binance's does, and fabricating those as 0 would misrepresent "not
  provided by this venue" as "genuinely zero" - this module defines
  its own honest, minimal shape instead.
- Detect gaps (missing candles) and duplicate timestamps in a
  returned batch explicitly, rather than silently presenting a series
  with a hole or a repeat.

Scope, exactly as dispatched: this is a narrow, free, public, read-
only PRICE data connector for the already-requested Quiet-RV cross-
venue PRICE portability research object. It is NOT wired into any
production runtime, scheduler, or live trading path -
MultiAssetQuoteSource's execution-grade provider mapping
(experiment1/market_data_providers.py) is completely untouched by this
module, and no funding rate/basis/open-interest data is requested or
substituted anywhere here - price candles only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Protocol

from exchange.base_client import BaseClient

BYBIT_BASE_URL = "https://api.bybit.com"
KLINE_ENDPOINT = "/v5/market/kline"

# Bybit's own interval vocabulary (minutes, or D/W/M) - "240" is 4
# hours, the timeframe the Quiet-RV cross-venue PRICE portability
# object needs.
INTERVAL_4H = "240"

_MAX_LIMIT = 1000  # Bybit's own documented cap for this endpoint


class BybitAPIError(Exception):
    """
    Raised when Bybit's V5 API reports a logical failure (non-zero
    retCode) - Bybit returns HTTP 200 even for many such errors (an
    unknown symbol, a bad interval, ...), embedding the real error in
    the response body rather than the HTTP status. BaseClient.get()'s
    own raise_for_status() only ever catches genuine HTTP-level
    failures (rate limiting, 5xx) - this exception covers the other,
    Bybit-specific failure mode explicitly, never silently absorbed.
    """


class KlineHttpClient(Protocol):
    async def get(self, endpoint: str, params: dict | None = None) -> dict: ...


class BybitClient(BaseClient):
    """Real Bybit V5 public market-data client - thin HTTP wrapper, mirrors exchange/binance_client.py's BinanceClient exactly."""

    def __init__(self) -> None:
        super().__init__(BYBIT_BASE_URL)


@dataclass(frozen=True, slots=True)
class BybitPerpetualCandle:
    """
    One Bybit V5 linear (USDT perpetual futures) kline, normalized to
    UTC. Deliberately a distinct, narrower shape than
    models.candle.Candle - see module docstring.
    """

    venue: str  # always "BYBIT" - explicit provenance, never assumed implicit by a caller
    category: str  # the raw Bybit category this candle came from (e.g. "linear")
    symbol: str  # Bybit's own raw contract symbol, e.g. "BTCUSDT"
    open_time: datetime  # UTC
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal  # base-asset volume
    turnover: Decimal  # quote-asset volume

    @classmethod
    def from_bybit_row(cls, category: str, symbol: str, row: list) -> "BybitPerpetualCandle":
        """row = [startTime_ms_str, open, high, low, close, volume, turnover] - Bybit's own documented kline row shape."""
        return cls(
            venue="BYBIT",
            category=category,
            symbol=symbol,
            open_time=datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc),
            open=Decimal(str(row[1])),
            high=Decimal(str(row[2])),
            low=Decimal(str(row[3])),
            close=Decimal(str(row[4])),
            volume=Decimal(str(row[5])),
            turnover=Decimal(str(row[6])),
        )


@dataclass(frozen=True, slots=True)
class GapDuplicateReport:
    """
    Explicit missing/duplicate detection over one fetched, ascending-
    sorted batch of candles, for one declared interval - never
    silently absorbed. An empty report (no gaps, no duplicates) is
    itself meaningful evidence that the batch is contiguous and clean.
    """

    duplicate_open_times: tuple[datetime, ...]
    gaps: tuple[tuple[datetime, datetime], ...]  # (candle before the gap, candle after the gap)

    @property
    def is_clean(self) -> bool:
        return not self.duplicate_open_times and not self.gaps


def detect_gaps_and_duplicates(candles: list[BybitPerpetualCandle], interval_minutes: int) -> GapDuplicateReport:
    """
    `candles` must already be sorted ascending by open_time (see
    BybitPerpetualCandleLoader.get_perpetual_klines, which sorts
    before returning - Bybit's own API returns rows newest-first).
    Any consecutive pair whose gap is not exactly interval_minutes is
    reported; any repeated open_time is reported as a duplicate.
    Never interpolates a missing candle, never drops a duplicate
    silently.
    """
    if interval_minutes <= 0:
        raise ValueError("interval_minutes must be positive")
    expected_delta = timedelta(minutes=interval_minutes)

    duplicates: list[datetime] = []
    gaps: list[tuple[datetime, datetime]] = []
    for previous, current in zip(candles, candles[1:]):
        delta = current.open_time - previous.open_time
        if delta == timedelta(0):
            duplicates.append(current.open_time)
        elif delta < timedelta(0):
            # A real ordering bug (the caller did not sort ascending) -
            # never silently reported as a "gap" or "duplicate", since
            # neither is an honest description of what actually
            # happened here.
            raise ValueError(f"candles are not sorted ascending: {previous.open_time} then {current.open_time}")
        elif delta > expected_delta:
            gaps.append((previous.open_time, current.open_time))

    return GapDuplicateReport(duplicate_open_times=tuple(duplicates), gaps=tuple(gaps))


class BybitPerpetualCandleLoader:
    """
    Composable, fully-testable loader: takes an injectable client (any
    object exposing async get(endpoint, params=...) -> dict, matching
    exchange.base_client.BaseClient.get()'s own signature; defaults to
    a real BybitClient()) and turns its raw kline response into
    normalized BybitPerpetualCandle records - mirroring
    experiment1.market_source.BinanceExperiment1QuoteSource's own
    injectable-client pattern exactly, so this is testable with a fake
    client double rather than a live network call or an httpx-level
    mock.
    """

    def __init__(self, client: KlineHttpClient | None = None) -> None:
        self.client = client or BybitClient()

    async def get_perpetual_klines(
        self,
        symbol: str,
        interval: str = INTERVAL_4H,
        limit: int = 200,
        *,
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> list[BybitPerpetualCandle]:
        """
        Fetch up to `limit` (max 1000, Bybit's own documented cap)
        linear (USDT perpetual futures) klines for `symbol`, sorted
        ascending by open_time (Bybit's own API returns them newest-
        first - reordered here for any downstream consumer, never
        left implicit). Raises BybitAPIError on a non-zero retCode -
        never returns a partial/guessed result for a failed request.
        """
        if limit > _MAX_LIMIT:
            raise ValueError(f"Bybit's public kline endpoint caps limit at {_MAX_LIMIT}")
        if limit < 1:
            raise ValueError("limit must be positive")

        params: dict = {"category": "linear", "symbol": symbol, "interval": interval, "limit": limit}
        if start_ms is not None:
            params["start"] = start_ms
        if end_ms is not None:
            params["end"] = end_ms

        payload = await self.client.get(KLINE_ENDPOINT, params=params)

        if payload.get("retCode") != 0:
            raise BybitAPIError(f"Bybit kline request failed: retCode={payload.get('retCode')} retMsg={payload.get('retMsg')}")

        result = payload.get("result") or {}
        raw_rows = result.get("list") or []
        category = result.get("category", "linear")
        raw_symbol = result.get("symbol", symbol)

        candles = [BybitPerpetualCandle.from_bybit_row(category, raw_symbol, row) for row in raw_rows]
        candles.sort(key=lambda c: c.open_time)
        return candles
