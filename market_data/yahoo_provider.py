from __future__ import annotations

import asyncio
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
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


class YahooChartDailyProvider(AsyncMarketDataProvider):
    """Broker-independent read-only daily OHLCV adapter using Yahoo chart data."""

    PROVIDER = "YAHOO_CHART"
    BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/"

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
            raise MarketDataUnavailable("Yahoo chart Stage-2 adapter supports only 1d history")
        if limit <= 0:
            raise ValueError("limit must be positive")

        symbol = urllib.parse.quote(instrument.symbol, safe="")
        params = urllib.parse.urlencode(
            {"range": "1y", "interval": "1d", "events": "history", "includeAdjustedClose": "true"}
        )
        url = f"{self.BASE_URL}{symbol}?{params}"
        raw = await asyncio.to_thread(self._fetch_text, url)

        try:
            payload = json.loads(raw)
            chart = payload["chart"]
            if chart.get("error"):
                raise MarketDataUnavailable(f"Yahoo chart error for {instrument.symbol}: {chart['error']}")
            result = chart["result"][0]
            timestamps = result["timestamp"]
            quote = result["indicators"]["quote"][0]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise MarketDataUnavailable(f"invalid Yahoo chart response for {instrument.symbol}") from exc

        parsed: list[MarketBar] = []
        for idx, ts in enumerate(timestamps):
            values = {key: quote.get(key, [None] * len(timestamps))[idx] for key in ("open", "high", "low", "close", "volume")}
            if any(values[key] is None for key in ("open", "high", "low", "close")):
                continue
            parsed.append(
                MarketBar(
                    timestamp=datetime.fromtimestamp(int(ts), tz=timezone.utc),
                    open=Decimal(str(values["open"])),
                    high=Decimal(str(values["high"])),
                    low=Decimal(str(values["low"])),
                    close=Decimal(str(values["close"])),
                    volume=Decimal(str(values["volume"] or 0)),
                )
            )

        if not parsed:
            raise MarketDataUnavailable(f"no Yahoo chart history for {instrument.symbol}")

        bars = tuple(parsed[-limit:])
        newest = bars[-1].timestamp
        now = datetime.now(timezone.utc)
        age = (now - newest).total_seconds()
        if age < 0 or age > self._max_age_seconds:
            raise MarketDataStale(
                f"{instrument.symbol} Yahoo daily evidence age={int(age)}s exceeds max={self._max_age_seconds}s"
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
    def _http_get_text(url: str) -> str:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; MarketHunter/1.0)",
                "Accept": "application/json,text/plain;q=0.9,*/*;q=0.1",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            return response.read().decode("utf-8")
