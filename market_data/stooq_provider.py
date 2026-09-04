from __future__ import annotations

import asyncio
import csv
import io
import urllib.parse
import urllib.request
from datetime import datetime, time, timezone
from decimal import Decimal
from typing import Callable

from market_data.foundation import (
    AsyncMarketDataProvider,
    LiquidityEvidence,
    MarketBar,
    MarketDataStale,
    MarketDataUnavailable,
    MarketInstrument,
    MarketSeries,
)


class StooqDailyProvider(AsyncMarketDataProvider):
    """
    Broker-independent real daily OHLCV provider.

    Stage-1 scope deliberately accepts a configured symbol universe rather than
    pretending to provide broker-style security-master discovery. No orders,
    accounts or execution APIs exist in this adapter.
    """

    PROVIDER = "STOOQ"
    BASE_URL = "https://stooq.com/q/d/l/"

    def __init__(
        self,
        symbols: tuple[str, ...],
        *,
        max_age_seconds: int = 4 * 24 * 3600,
        fetch_text: Callable[[str], str] | None = None,
    ) -> None:
        cleaned = tuple(s.strip().upper() for s in symbols if s.strip())
        if not cleaned:
            raise ValueError("symbols must be non-empty")
        self._symbols = cleaned
        self._max_age_seconds = max_age_seconds
        self._fetch_text = fetch_text or self._http_get_text
        self._cache: dict[str, MarketSeries] = {}

    async def universe(self) -> tuple[MarketInstrument, ...]:
        return tuple(
            MarketInstrument(symbol=s, asset_class="US_STOCK_OR_ETF", currency="USD")
            for s in self._symbols
        )

    async def history(
        self,
        instrument: MarketInstrument,
        *,
        timeframe: str = "1d",
        limit: int = 120,
    ) -> MarketSeries:
        if timeframe != "1d":
            raise MarketDataUnavailable("Stooq Stage-1 adapter supports only 1d history")
        if limit <= 0:
            raise ValueError("limit must be positive")

        provider_symbol = self._provider_symbol(instrument.symbol)
        url = self.BASE_URL + "?" + urllib.parse.urlencode({"s": provider_symbol, "i": "d"})
        raw = await asyncio.to_thread(self._fetch_text, url)
        rows = list(csv.DictReader(io.StringIO(raw)))
        parsed: list[MarketBar] = []
        for row in rows:
            if not row.get("Date") or row.get("Close") in {None, "", "N/D"}:
                continue
            dt = datetime.combine(
                datetime.strptime(row["Date"], "%Y-%m-%d").date(),
                time(21, 0),
                tzinfo=timezone.utc,
            )
            parsed.append(
                MarketBar(
                    timestamp=dt,
                    open=Decimal(row["Open"]),
                    high=Decimal(row["High"]),
                    low=Decimal(row["Low"]),
                    close=Decimal(row["Close"]),
                    volume=Decimal(row.get("Volume") or "0"),
                )
            )
        if not parsed:
            raise MarketDataUnavailable(f"no Stooq history for {instrument.symbol}")

        bars = tuple(parsed[-limit:])
        newest = bars[-1].timestamp
        now = datetime.now(timezone.utc)
        age = (now - newest).total_seconds()
        if age < 0 or age > self._max_age_seconds:
            raise MarketDataStale(
                f"{instrument.symbol} Stooq daily evidence age={int(age)}s exceeds max={self._max_age_seconds}s"
            )

        series = MarketSeries(
            instrument=instrument,
            timeframe="1d",
            bars=bars,
            provider=self.PROVIDER,
            source_reference=url,
            observed_at=newest,
            available_at=now,
        )
        self._cache[instrument.symbol] = series
        return series

    async def liquidity(self, instrument: MarketInstrument) -> LiquidityEvidence:
        series = self._cache.get(instrument.symbol)
        if series is None:
            series = await self.history(instrument, timeframe="1d", limit=20)
        window = series.bars[-min(20, len(series.bars)):]
        avg_volume = sum((bar.volume for bar in window), Decimal("0")) / Decimal(len(window))
        last_price = window[-1].close
        return LiquidityEvidence(
            instrument=instrument,
            average_daily_volume=avg_volume,
            average_daily_dollar_volume=avg_volume * last_price,
            last_price=last_price,
            provider=self.PROVIDER,
            observed_at=series.observed_at,
            source_reference=series.source_reference,
        )

    @staticmethod
    def _provider_symbol(symbol: str) -> str:
        normalized = symbol.strip().lower()
        return normalized if normalized.endswith(".us") else f"{normalized}.us"

    @staticmethod
    def _http_get_text(url: str) -> str:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; MarketHunter/1.0; +https://github.com/mike0610/MarketHunter)",
                "Accept": "text/csv,text/plain;q=0.9,*/*;q=0.1",
                "Accept-Language": "en-US,en;q=0.8",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            return response.read().decode("utf-8")
