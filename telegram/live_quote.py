"""Best-effort public Binance futures top-of-book observation for Telegram.

Top-of-book spread is NOT proof of executable depth or a trade authorization.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
from urllib.parse import urlencode
from urllib.request import urlopen
import json

from models.signal import Signal


def observe_futures_quote(signal: Signal, *, now: datetime | None = None,
                          fetch=None) -> None:
    """Attach a timestamp-checked quote; fail closed on any unavailable evidence."""
    metadata = signal.metadata
    metadata["market_data_fresh"] = False
    metadata["execution_liquidity_verified"] = False
    metadata.pop("live_quote", None)
    if signal.market.lower() != "futures":
        metadata["quote_blocker"] = "Live quote verification supports futures only."
        return

    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        metadata["quote_blocker"] = "Clock must be timezone-aware."
        return
    try:
        if fetch is None:
            def fetch(symbol):
                url = "https://fapi.binance.com/fapi/v1/ticker/bookTicker?" + urlencode({"symbol": symbol})
                with urlopen(url, timeout=3) as response:
                    return json.load(response)
        quote = fetch(signal.symbol)
        if not isinstance(quote, dict) or quote.get("symbol") != signal.symbol:
            raise ValueError("Symbol mismatch")
        bid, ask = float(quote["bidPrice"]), float(quote["askPrice"])
        bid_qty, ask_qty = float(quote["bidQty"]), float(quote["askQty"])
        timestamp_ms = int(quote["time"])
        observed = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
        age_seconds = (clock - observed).total_seconds()
        spread_pct = (ask - bid) / ((ask + bid) / 2) * 100
        if not (all(math.isfinite(v) and v > 0 for v in (bid, ask, bid_qty, ask_qty))
                and bid <= ask and 0 <= age_seconds <= 10):
            raise ValueError("Stale, future-dated or invalid top-of-book quote")
        metadata["live_quote"] = {
            "bid": bid, "ask": ask, "bid_qty": bid_qty, "ask_qty": ask_qty,
            "exchange_time": observed.isoformat(), "age_seconds": round(age_seconds, 2),
            "spread_percent": round(spread_pct, 4),
        }
        metadata["market_data_fresh"] = True
        metadata["quote_blocker"] = (
            "Top-of-book is observed, but executable depth and slippage "
            "for the proposed position have not been verified."
        )
    except (ValueError, TypeError, KeyError, OverflowError, OSError, TimeoutError, json.JSONDecodeError) as exc:
        metadata["quote_blocker"] = f"Live quote unavailable or invalid: {exc}"
