"""Out-of-sample validation runner for VolumeConfirmedBreakout.

Research only. Uses public Binance spot candles, a chronological 70/30 split,
next-candle-open entry, the strategy's own stop/target, conservative stop-first
OHLC ambiguity, and 4 bps fee + 2 bps slippage per side.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from decimal import Decimal

import httpx

from backtesting.trade_simulator import ExecutionAssumptions, TradeSimulator
from exchange.binance_client import BinanceClient
from models.position import Position
from services.snapshot_builder import SnapshotBuilder
from strategies.volume_confirmed_breakout import VolumeConfirmedBreakoutStrategy

SYMBOLS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT")
INTERVAL = "1h"
LIMIT = 1000
WARMUP = 200
DEVELOPMENT_FRACTION = 0.70


@dataclass(frozen=True, slots=True)
class ValidationStats:
    signals: int
    wins: int
    losses: int
    net_pnl: float
    profit_factor: float | None


async def _history(client: BinanceClient, symbol: str):
    try:
        return await client.get_klines(symbol, interval=INTERVAL, limit=LIMIT)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 451:
            raise
        # Binance documents data-api.binance.vision as a public-market-data
        # base endpoint. Keep the validation read-only and preserve the exact
        # /api/v3/klines payload shape used by Candle.from_binance.
        async with httpx.AsyncClient(timeout=30.0) as public:
            response = await public.get(
                "https://data-api.binance.vision/api/v3/klines",
                params={"symbol": symbol, "interval": INTERVAL, "limit": LIMIT},
            )
            response.raise_for_status()
            from models.candle import Candle
            return [Candle.from_binance(row) for row in response.json()]


async def _replay(candles, start: int, end: int) -> ValidationStats:
    strategy = VolumeConfirmedBreakoutStrategy()
    builder = SnapshotBuilder()
    simulator = TradeSimulator(ExecutionAssumptions())
    pnls: list[float] = []
    i = max(WARMUP, start)
    while i < end - 1:
        signal = await strategy.analyze(builder.build("VALIDATION", candles[: i + 1]))
        if signal is None:
            i += 1
            continue
        entry_i = i + 1
        entry = candles[entry_i].open
        side = str(signal.direction).upper()
        stop = float(signal.metadata["stop_loss"])
        target = float(signal.metadata["take_profit"])
        # Fail closed when a next-open gap has already crossed the structural
        # stop or target. The strategy did not have an executable entry there.
        if side == "LONG" and not (stop < entry < target):
            i += 1
            continue
        if side == "SHORT" and not (target < entry < stop):
            i += 1
            continue
        pos = Position(
            symbol="VALIDATION", market="spot", side=side, quantity=1.0,
            entry=entry, stop_loss=stop, take_profit=target,
            opened_at=0.0, current_price=entry,
        )
        future = candles[entry_i:end]
        result = simulator.long(pos, future) if side == "LONG" else simulator.short(pos, future)
        pnls.append(float(result.pnl))
        i = max(i + 1, entry_i + result.exit_offset + 1)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    return ValidationStats(
        len(pnls), len(wins), len(losses), sum(pnls),
        gross_win / gross_loss if gross_loss > 0 else None,
    )


async def main() -> None:
    client = BinanceClient()
    total_dev: list[ValidationStats] = []
    total_oos: list[ValidationStats] = []
    for symbol in SYMBOLS:
        candles = await _history(client, symbol)
        split = int(len(candles) * DEVELOPMENT_FRACTION)
        dev = await _replay(candles, WARMUP, split)
        oos = await _replay(candles, split, len(candles))
        total_dev.append(dev); total_oos.append(oos)
        print(symbol, "DEV", asdict(dev), "OOS", asdict(oos))
    for name, rows in (("DEV", total_dev), ("OOS", total_oos)):
        signals = sum(x.signals for x in rows)
        wins = sum(x.wins for x in rows)
        losses = sum(x.losses for x in rows)
        pnl = sum(x.net_pnl for x in rows)
        print(name, {"signals": signals, "wins": wins, "losses": losses,
                     "win_rate": wins / signals if signals else None,
                     "net_pnl": pnl})

if __name__ == "__main__":
    asyncio.run(main())
