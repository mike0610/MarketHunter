from __future__ import annotations

import asyncio
import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from typing import Callable

from market_data.foundation import MarketDataUnavailable
from market_data.twelve_data_provider import ENV_TWELVE_DATA_API_KEY


@dataclass(frozen=True, slots=True)
class EarningsEvent:
    symbol: str
    earnings_date: date
    provider: str
    source_reference: str


class TwelveDataEarningsProvider:
    """Read-only historical earnings-date evidence.

    Twelve Data earnings dates are treated as date-only evidence. This provider
    deliberately makes no claim about announcement time. Consumers must not use
    an event to trade the same session; the first eligible action is the next
    completed trading session/bar.
    """

    PROVIDER = "TWELVE_DATA"
    BASE_URL = "https://api.twelvedata.com/earnings"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        fetch_text: Callable[[str], str] | None = None,
    ) -> None:
        key = (api_key if api_key is not None else os.getenv(ENV_TWELVE_DATA_API_KEY, "")).strip()
        if not key:
            raise ValueError("TWELVE_DATA_API_KEY is required")
        self._api_key = key
        self._fetch_text = fetch_text or self._http_get_text

    async def history(self, symbol: str) -> tuple[EarningsEvent, ...]:
        symbol = symbol.strip().upper()
        if not symbol:
            raise ValueError("symbol must be non-empty")
        params = urllib.parse.urlencode({"symbol": symbol, "apikey": self._api_key})
        raw = await asyncio.to_thread(self._fetch_text, f"{self.BASE_URL}?{params}")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise MarketDataUnavailable(f"invalid Twelve Data earnings JSON for {symbol}") from exc
        if not isinstance(payload, dict) or payload.get("status") == "error":
            message = payload.get("message", "provider error") if isinstance(payload, dict) else "provider error"
            raise MarketDataUnavailable(f"Twelve Data earnings error for {symbol}: {message}")

        rows = payload.get("earnings")
        if not isinstance(rows, list):
            raise MarketDataUnavailable(f"no Twelve Data earnings history for {symbol}")

        events: list[EarningsEvent] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            raw_date = row.get("date") or row.get("datetime")
            if raw_date is None:
                continue
            try:
                event_date = date.fromisoformat(str(raw_date)[:10])
            except ValueError:
                continue
            events.append(
                EarningsEvent(
                    symbol=symbol,
                    earnings_date=event_date,
                    provider=self.PROVIDER,
                    source_reference=f"twelve-data:earnings:{symbol}:{event_date.isoformat()}",
                )
            )
        events.sort(key=lambda x: x.earnings_date)
        return tuple(events)

    @staticmethod
    def _http_get_text(url: str) -> str:
        req = urllib.request.Request(url, headers={"User-Agent": "MarketHunter/1.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as response:
            return response.read().decode("utf-8")
