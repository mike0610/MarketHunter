"""Run one real-symbol top-down price-action research probe.

Example:
    python -m scripts.price_action_probe BTCUSDT futures

This is research-only. It does not create signals, trades, orders, or mutations.
"""
from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import asdict
from enum import Enum

from models.market_symbol import MarketSymbol
from research.price_action.loader import TopDownPriceActionLoader
from services.market_data import MarketDataService


def _jsonable(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


async def run(symbol_name: str, market: str) -> dict:
    symbol_name = symbol_name.strip().upper()
    market = market.strip().lower()

    if market not in {"spot", "futures"}:
        raise ValueError("market must be 'spot' or 'futures'")

    if not symbol_name:
        raise ValueError("symbol cannot be empty")

    base_asset = symbol_name.removesuffix("USDT") or symbol_name

    symbol = MarketSymbol(
        symbol=symbol_name,
        base_asset=base_asset,
        quote_asset="USDT",
        market=market,
    )

    market_data = MarketDataService()

    try:
        context = await TopDownPriceActionLoader(
            market_data,
        ).analyze_symbol(symbol)
    finally:
        await market_data.close()

    payload = _jsonable(asdict(context))

    return {
        "symbol": symbol_name,
        "market": market,
        "broad_regime": payload["broad_regime"],
        "broad_confidence": payload["broad_confidence"],
        "daily_phase": payload["daily_phase"],
        "hourly_context": payload["hourly_context"],
        "alignment": payload["alignment"],
        "monthly": {
            "regime": payload["monthly"]["regime"],
            "confidence": payload["monthly"]["confidence"],
            "structure_sequence": payload["monthly"]["structure_sequence"],
            "structural_lines": payload["monthly"]["structural_lines"],
        },
        "weekly": {
            "regime": payload["weekly"]["regime"],
            "confidence": payload["weekly"]["confidence"],
            "structure_sequence": payload["weekly"]["structure_sequence"],
            "structural_lines": payload["weekly"]["structural_lines"],
        },
        "daily": {
            "regime": payload["daily"]["regime"],
            "confidence": payload["daily"]["confidence"],
            "structure_sequence": payload["daily"]["structure_sequence"],
            "support_zones": payload["daily"]["support_zones"],
            "resistance_zones": payload["daily"]["resistance_zones"],
            "structural_lines": payload["daily"]["structural_lines"],
        },
        "hourly": {
            "regime": payload["hourly"]["regime"],
            "confidence": payload["hourly"]["confidence"],
            "support_zones": payload["hourly"]["support_zones"],
            "resistance_zones": payload["hourly"]["resistance_zones"],
            "zone_behaviors": payload["hourly"]["zone_behaviors"],
        },
    }


async def _main() -> None:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    market = sys.argv[2] if len(sys.argv) > 2 else "futures"

    result = await run(symbol, market)

    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(_main())
