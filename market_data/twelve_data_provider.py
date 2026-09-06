from __future__ import annotations

import asyncio
import json
import os
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

ENV_TWELVE_DATA_API_KEY = "TWELVE_DATA_API_KEY"


class TwelveDataDailyProvider(AsyncMarketDataProvider):
    """Read-only Twelve Data daily OHLCV provider for bounded US stock/ETF discovery."""

    PROVIDER = "TWELVE_DATA"
    BASE_URL = "https://api.twelvedata.com/time_series"

    def __init__(
        self,
        symbols: tuple[str, ...],
        *,
        api_key: str | None = None,
        max_age_seconds: int = 4 * 24 * 3600,
        history_limit: int = 120,
        fetch_text: Callable[[str], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        cleaned = tuple(s.strip().upper() for s in symbols if s.strip())
        if not cleaned:
            raise ValueError("symbols must be non-empty")
        key = (api_key if api_key is not None else os.getenv(ENV_TWELVE_DATA_API_KEY, "")).strip()
        if not key:
            raise ValueError("TWELVE_DATA_API_KEY is required")
        if history_limit < 50:
            raise ValueError("history_limit must be >= 50")
        self._symbols = cleaned
        self._api_key = key
        self._max_age_seconds = max_age_seconds
        self._history_limit = history_limit
        self._fetch_text = fetch_text or self._http_get_text
        self._clock = clock or (lambda: datetime.now(timezone.utc))
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
            raise MarketDataUnavailable("Twelve Data scanner adapter supports only 1d history")
        if limit <= 0:
            raise ValueError("limit must be positive")

        cached = self._cache.get(instrument.symbol)
        if cached is not None and len(cached.bars) >= limit:
            return MarketSeries(
                instrument=instrument,
                timeframe="1d",
                bars=cached.bars[-limit:],
                provider=cached.provider,
                source_reference=cached.source_reference,
                observed_at=cached.observed_at,
                available_at=cached.available_at,
            )

        outputsize = max(limit, self._history_limit)
        params = urllib.parse.urlencode(
            {
                "symbol": instrument.symbol,
                "interval": "1day",
                "outputsize": outputsize,
                "order": "ASC",
                "apikey": self._api_key,
            }
        )
        url = f"{self.BASE_URL}?{params}"
        raw = await asyncio.to_thread(self._fetch_text, url)

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise MarketDataUnavailable(f"invalid Twelve Data JSON for {instrument.symbol}") from exc
        if not isinstance(payload, dict) or payload.get("status") == "error":
            message = payload.get("message", "provider error") if isinstance(payload, dict) else "provider error"
            raise MarketDataUnavailable(f"Twelve Data error for {instrument.symbol}: {message}")
        values = payload.get("values")
        if not isinstance(values, list) or not values:
            raise MarketDataUnavailable(f"no Twelve Data history for {instrument.symbol}")

        parsed: list[MarketBar] = []
        for row in values:
            if not isinstance(row, dict):
                continue
            try:
                stamp = datetime.fromisoformat(str(row["datetime"]).replace("Z", "+00:00"))
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=timezone.utc)
                else:
                    stamp = stamp.astimezone(timezone.utc)
                parsed.append(
                    MarketBar(
                        timestamp=stamp,
                        open=Decimal(str(row["open"])),
                        high=Decimal(str(row["high"])),
                        low=Decimal(str(row["low"])),
                        close=Decimal(str(row["close"])),
                        volume=Decimal(str(row.get("volume") or 0)),
                    )
                )
            except (KeyError, ValueError, TypeError, ArithmeticError):
                continue

        if not parsed:
            raise MarketDataUnavailable(f"no valid Twelve Data OHLCV bars for {instrument.symbol}")
        parsed.sort(key=lambda bar: bar.timestamp)
        all_bars = tuple(parsed[-outputsize:])
        newest = all_bars[-1].timestamp
        now = self._clock()
        age = (now - newest).total_seconds()
        if age < 0 or age > self._max_age_seconds:
            raise MarketDataStale(
                f"{instrument.symbol} Twelve Data daily evidence age={int(age)}s exceeds max={self._max_age_seconds}s"
            )

        # Never persist or expose a URL containing the API key.
        safe_reference = f"twelve-data:time_series:{instrument.symbol}:1day:{newest.date().isoformat()}"
        full = MarketSeries(
            instrument=instrument,
            timeframe="1d",
            bars=all_bars,
            provider=self.PROVIDER,
            source_reference=safe_reference,
            observed_at=newest,
            available_at=now,
        )
        self._cache[instrument.symbol] = full
        return MarketSeries(
            instrument=instrument,
            timeframe="1d",
            bars=all_bars[-limit:],
            provider=full.provider,
            source_reference=full.source_reference,
            observed_at=full.observed_at,
            available_at=full.available_at,
        )

    async def liquidity(self, instrument: MarketInstrument) -> LiquidityEvidence:
        # Fetch the scanner's full bounded history on the first call so the
        # subsequent setup-classification call is cache-only. Five symbols
        # therefore consume five provider calls, staying under the free 8/min tier.
        series = await self.history(instrument, timeframe="1d", limit=self._history_limit)
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
            headers={"User-Agent": "MarketHunter/1.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            return response.read().decode("utf-8")
