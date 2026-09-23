"""Out-of-sample validation runner for VolumeConfirmedBreakout.

Research only. Uses public Binance spot candles, a chronological 70/30 split,
next-candle-open entry, the strategy's own stop/target, conservative stop-first
OHLC ambiguity, and 4 bps fee + 2 bps slippage per side.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
import httpx

from backtesting.trade_simulator import ExecutionAssumptions, TradeSimulator
from exchange.binance_client import BinanceClient
from models.position import Position
from services.snapshot_builder import SnapshotBuilder
from strategies.volume_confirmed_breakout import VolumeConfirmedBreakoutStrategy


class LegacyVolumeConfirmedBreakoutStrategy(VolumeConfirmedBreakoutStrategy):
    """Frozen pre-entry-quality eligibility rules for A/B comparison."""

    def _candidate(self, snapshot, trigger, direction, level, vol_ratio, trade_ratio):
        extreme = trigger.low if direction == "LONG" else trigger.high
        buffer = max(snapshot.atr14 * 0.10, trigger.close * 0.0005)
        stop = extreme - buffer if direction == "LONG" else extreme + buffer
        risk = trigger.close - stop if direction == "LONG" else stop - trigger.close
        if risk <= 0:
            return None
        target = trigger.close + 3 * risk if direction == "LONG" else trigger.close - 3 * risk
        from models.signal import Signal
        signal = Signal(symbol=snapshot.symbol, market="", timeframe="", strategy=self.name, direction=direction, score=95.0)
        signal.metadata.update({"entry": trigger.close, "stop_loss": stop, "take_profit": target, "rr": 3.0})
        return signal

SYMBOLS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT", "AVAXUSDT", "LTCUSDT")
MARKETS = ("spot", "futures")
INTERVAL = "1h"
LIMIT = 8760
ARCHIVE_LOOKBACK_DAYS = 400
WARMUP = 200
DEVELOPMENT_FRACTION = 0.70


@dataclass(frozen=True, slots=True)
class ValidationStats:
    signals: int
    wins: int
    losses: int
    net_pnl: float
    profit_factor: float | None


async def _history(client: BinanceClient, symbol: str, market: str):
    futures = market == "futures"
    try:
        return await client.get_klines(symbol, interval=INTERVAL, limit=LIMIT, futures=futures)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 451:
            raise

        from models.candle import Candle

        if not futures:
            # Spot REST caps klines per request. Walk backward with endTime so
            # the one-year regime run uses the same native Binance candles.
            rows = []
            end_time = None
            async with httpx.AsyncClient(timeout=30.0) as public:
                while len(rows) < LIMIT:
                    params = {"symbol": symbol, "interval": INTERVAL, "limit": 1000}
                    if end_time is not None:
                        params["endTime"] = end_time
                    response = await public.get(
                        "https://data-api.binance.vision/api/v3/klines", params=params
                    )
                    response.raise_for_status()
                    batch = response.json()
                    if not batch:
                        break
                    rows = batch + rows
                    end_time = int(batch[0][0]) - 1
                    if len(batch) < 1000:
                        break
            return [Candle.from_binance(row) for row in rows[-LIMIT:]]

        # GitHub-hosted runners can receive HTTP 451 from Binance Futures REST.
        # Use Binance's public historical-data archive instead. Daily futures
        # klines preserve the native Binance kline schema without changing the
        # frozen validation rules.
        from datetime import datetime, timedelta, timezone
        from io import BytesIO
        from zipfile import ZipFile
        import csv

        rows = []
        day = datetime.now(timezone.utc).date() - timedelta(days=1)
        async with httpx.AsyncClient(timeout=30.0) as public:
            for _ in range(ARCHIVE_LOOKBACK_DAYS):
                url = (
                    "https://data.binance.vision/data/futures/um/daily/klines/"
                    f"{symbol}/{INTERVAL}/{symbol}-{INTERVAL}-{day.isoformat()}.zip"
                )
                response = await public.get(url)
                if response.status_code == 200:
                    with ZipFile(BytesIO(response.content)) as archive:
                        name = archive.namelist()[0]
                        text = archive.read(name).decode("utf-8")
                        reader = csv.reader(text.splitlines())
                        for row in reader:
                            if row and row[0].isdigit():
                                row[0] = int(row[0])
                                row[6] = int(row[6])
                                rows.append(row)
                elif response.status_code not in {404, 451}:
                    response.raise_for_status()
                if len(rows) >= LIMIT:
                    break
                day -= timedelta(days=1)

        if not rows:
            raise RuntimeError(f"No Binance Vision futures candles for {symbol}")
        rows.sort(key=lambda row: int(row[0]))
        return [Candle.from_binance(row) for row in rows[-LIMIT:]]


async def _replay(candles, start: int, end: int, strategy_cls=VolumeConfirmedBreakoutStrategy) -> ValidationStats:
    strategy = strategy_cls()
    builder = SnapshotBuilder()
    simulator = TradeSimulator(ExecutionAssumptions())
    notional = 100.0
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
            symbol="VALIDATION", market="spot", side=side, quantity=notional / entry,
            entry=entry, stop_loss=stop, take_profit=target,
            opened_at=0.0, current_price=entry,
        )
        future = candles[entry_i:end]
        initial_risk = abs(entry - stop)
        breakeven_trigger = entry + initial_risk if side == "LONG" else entry - initial_risk
        active_stop = stop
        result = None
        for offset, candle in enumerate(future):
            # Existing stop/target always resolves before a newly earned
            # breakeven move, so the move can only protect the next candle.
            if side == "LONG":
                stop_hit = candle.low <= active_stop
                target_hit = candle.high >= target
                earned_1r = candle.high >= breakeven_trigger
            else:
                stop_hit = candle.high >= active_stop
                target_hit = candle.low <= target
                earned_1r = candle.low <= breakeven_trigger
            if stop_hit or target_hit:
                raw_exit = active_stop if stop_hit else target
                reason = "stop" if stop_hit else "target"
                result = simulator._result(pos, raw_exit, offset, reason)
                break
            if active_stop != entry and earned_1r:
                active_stop = entry
        if result is None:
            result = simulator._result(pos, future[-1].close, len(future) - 1, "window_close")
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
    for market in MARKETS:
        for symbol in SYMBOLS:
            try:
                candles = await _history(client, symbol, market)
            except httpx.HTTPStatusError as exc:
                print(market.upper(), symbol, "SKIP", exc.response.status_code)
                continue
            split = int(len(candles) * DEVELOPMENT_FRACTION)
            dev = await _replay(candles, WARMUP, split)
            oos = await _replay(candles, split, len(candles))
            legacy_dev = await _replay(candles, WARMUP, split, LegacyVolumeConfirmedBreakoutStrategy)
            legacy_oos = await _replay(candles, split, len(candles), LegacyVolumeConfirmedBreakoutStrategy)
            total_dev.append(dev); total_oos.append(oos)
            print(market.upper(), symbol, "NEW_DEV", asdict(dev), "NEW_OOS", asdict(oos),
                  "LEGACY_DEV", asdict(legacy_dev), "LEGACY_OOS", asdict(legacy_oos))
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
