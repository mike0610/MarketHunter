"""Render BTC-style 1h price-action research chart.

Research-only. Loads real candles, overlays detected support/resistance zones,
and writes a PNG for visual comparison with human chart reading.
"""
from __future__ import annotations

import asyncio
import sys

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from models.market_symbol import MarketSymbol
from research.price_action.context import PriceActionContextEngine
from services.market_data import MarketDataService


async def run(symbol_name: str = "BTCUSDT", market: str = "futures") -> str:
    symbol_name = symbol_name.upper().strip()
    market = market.lower().strip()

    symbol = MarketSymbol(
        symbol=symbol_name,
        base_asset=symbol_name.removesuffix("USDT") or symbol_name,
        quote_asset="USDT",
        market=market,
    )

    market_data = MarketDataService()
    try:
        candles = await market_data.load_candles(
            symbol=symbol,
            interval="1h",
            limit=500,
        )
    finally:
        await market_data.close()

    context = PriceActionContextEngine().analyze(candles)

    fig, ax = plt.subplots(figsize=(16, 8))

    width = 0.6
    for i, candle in enumerate(candles):
        ax.vlines(i, candle.low, candle.high, linewidth=0.7)
        lower = min(candle.open, candle.close)
        height = max(abs(candle.close - candle.open), 1e-9)
        ax.add_patch(
            Rectangle(
                (i - width / 2, lower),
                width,
                height,
                fill=False,
                linewidth=0.8,
            )
        )

    for zone in context.support_zones:
        ax.axhspan(zone.lower, zone.upper, alpha=0.10)
        ax.text(
            len(candles) - 1,
            (zone.lower + zone.upper) / 2,
            f"S {zone.touches}x",
            ha="right",
            va="center",
            fontsize=8,
        )

    for zone in context.resistance_zones:
        ax.axhspan(zone.lower, zone.upper, alpha=0.10)
        ax.text(
            len(candles) - 1,
            (zone.lower + zone.upper) / 2,
            f"R {zone.touches}x",
            ha="right",
            va="center",
            fontsize=8,
        )

    for line in context.structural_lines[:12]:
        start = line.first_index
        end = min(len(candles) - 1, line.last_index)
        y0 = line.intercept + line.slope_per_bar * start
        y1 = line.intercept + line.slope_per_bar * end
        ax.plot([start, end], [y0, y1], linewidth=1.2)

    ax.set_title(
        f"{symbol_name} 1h | regime={context.regime.value} "
        f"| confidence={context.confidence:.2f}"
    )
    ax.set_xlabel("Last 500 hourly candles")
    ax.set_ylabel("Price")
    ax.grid(True, alpha=0.2)

    output = f"/tmp/{symbol_name.lower()}_1h_price_action.png"
    fig.tight_layout()
    fig.savefig(output, dpi=160)
    plt.close(fig)

    return output


async def _main() -> None:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    market = sys.argv[2] if len(sys.argv) > 2 else "futures"
    print(await run(symbol, market))


if __name__ == "__main__":
    asyncio.run(_main())
