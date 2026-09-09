"""
Thin adapter: run the existing Research strategy implementations over the
Active Trading scanner's broker-independent OHLCV feed.

It does not reimplement, tune, persist or execute strategy logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from market_data.foundation import AsyncMarketDataProvider
from models.candle import Candle
from models.signal import Signal
from services.snapshot_builder import SnapshotBuilder
from strategies.breakout import BreakoutStrategy
from strategies.compression import CompressionStrategy
from strategies.liquidity_sweep import LiquiditySweepStrategy
from strategies.order_block import OrderBlockStrategy
from strategies.premium_discount import PremiumDiscountStrategy


STRATEGIES = (
    PremiumDiscountStrategy,
    BreakoutStrategy,
    OrderBlockStrategy,
    CompressionStrategy,
    LiquiditySweepStrategy,
)


@dataclass(frozen=True, slots=True)
class PipedSignal:
    symbol: str
    strategy: str
    direction: str
    score: float
    reasons: tuple[str, ...]
    observed_at: datetime


def _candles(series) -> list[Candle]:
    bars = list(series.bars)
    return [
        Candle(
            open_time=bar.timestamp,
            open=float(bar.open),
            high=float(bar.high),
            low=float(bar.low),
            close=float(bar.close),
            volume=float(bar.volume),
            close_time=(bars[index + 1].timestamp if index + 1 < len(bars) else bar.timestamp),
            quote_volume=float(bar.volume * bar.close),
            trades=0,
            taker_buy_base_volume=0.0,
            taker_buy_quote_volume=0.0,
        )
        for index, bar in enumerate(bars)
    ]


async def scan_existing_research_strategies(
    provider: AsyncMarketDataProvider,
    *,
    history_limit: int = 500,
) -> tuple[PipedSignal, ...]:
    if history_limit < 200:
        raise ValueError("history_limit must be at least 200")

    builder = SnapshotBuilder()
    found: list[PipedSignal] = []

    for instrument in await provider.universe():
        series = await provider.history(instrument, timeframe="1d", limit=history_limit)
        candles = _candles(series)
        if len(candles) < 200:
            continue
        snapshot = builder.build(instrument.symbol, candles)

        for strategy_type in STRATEGIES:
            signal: Signal | None = await strategy_type().analyze(snapshot)
            if signal is None:
                continue
            found.append(
                PipedSignal(
                    symbol=signal.symbol,
                    strategy=signal.strategy,
                    direction=signal.direction,
                    score=signal.score,
                    reasons=tuple(signal.reasons),
                    observed_at=series.observed_at,
                )
            )

    return tuple(found)
