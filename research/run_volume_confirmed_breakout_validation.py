"""Out-of-sample validation runner for VolumeConfirmedBreakout.

Research only. Uses public Binance spot candles, a chronological 70/30 split,
next-candle-open entry, the strategy's own stop/target, conservative stop-first
OHLC ambiguity, and 4 bps fee + 2 bps slippage per side.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
import httpx
import hashlib
from datetime import date, datetime, timedelta, timezone

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
# Frozen UTC endpoint: never include an unfinished candle or slide the sample.
DATA_END_DAY = date(2026, 9, 23)
ARCHIVE_CONCURRENCY = 12
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
    # Always use the same dated archive window. The direct REST shortcut
    # previously ignored the cutoff and silently shifted samples each run.
    from models.candle import Candle
    if not futures:
        rows = []
        end_time = int(datetime.combine(
            DATA_END_DAY + timedelta(days=1), datetime.min.time(),
            tzinfo=timezone.utc,
        ).timestamp() * 1000) - 1
        async with httpx.AsyncClient(timeout=30.0) as public:
            while len(rows) < LIMIT:
                params = {"symbol": symbol, "interval": INTERVAL,
                          "limit": min(1000, LIMIT - len(rows)),
                          "endTime": end_time}
                response = await public.get(
                    "https://data-api.binance.vision/api/v3/klines", params=params
                )
                response.raise_for_status()
                batch = response.json()
                if not batch:
                    break
                rows = batch + rows
                end_time = int(batch[0][0]) - 1
        candles = [Candle.from_binance(row) for row in rows[-LIMIT:]]
        if len(candles) != LIMIT:
            raise RuntimeError(f"Incomplete frozen spot history: {symbol} {len(candles)}")
        return candles

        # GitHub-hosted runners can receive HTTP 451 from Binance Futures REST.
        # Use Binance's public historical-data archive instead. Daily futures
        # klines preserve the native Binance kline schema without changing the
        # frozen validation rules.
        from io import BytesIO
        from zipfile import ZipFile
        import csv

        rows = []
        last_day = DATA_END_DAY
        days = [last_day - timedelta(days=i) for i in range(ARCHIVE_LOOKBACK_DAYS)]

        async def fetch_day(public, day):
            url = (
                "https://data.binance.vision/data/futures/um/daily/klines/"
                f"{symbol}/{INTERVAL}/{symbol}-{INTERVAL}-{day.isoformat()}.zip"
            )
            response = await public.get(url)
            if response.status_code in {404, 451}:
                return []
            response.raise_for_status()
            with ZipFile(BytesIO(response.content)) as archive:
                name = archive.namelist()[0]
                text = archive.read(name).decode("utf-8")
            parsed = []
            for row in csv.reader(text.splitlines()):
                if row and row[0].isdigit():
                    row[0] = int(row[0])
                    row[6] = int(row[6])
                    parsed.append(row)
            return parsed

        async with httpx.AsyncClient(timeout=30.0) as public:
            for offset in range(0, len(days), ARCHIVE_CONCURRENCY):
                batch_days = days[offset:offset + ARCHIVE_CONCURRENCY]
                batches = await asyncio.gather(
                    *(fetch_day(public, day) for day in batch_days)
                )
                for batch in batches:
                    rows.extend(batch)
                if len(rows) >= LIMIT:
                    break

        if not rows:
            raise RuntimeError(f"No Binance Vision futures candles for {symbol}")
        rows.sort(key=lambda row: int(row[0]))
        candles = [Candle.from_binance(row) for row in rows[-LIMIT:]]
        if len(candles) != LIMIT:
            raise RuntimeError(f"Incomplete frozen futures history: {symbol} {len(candles)}")
        return candles


async def _replay(candles, start: int, end: int, strategy_cls=VolumeConfirmedBreakoutStrategy, *, blocks=None, market='spot') -> ValidationStats:
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
            symbol="VALIDATION", market=market, side=side, quantity=notional / entry,
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
        if blocks is not None:
            entered = candles[entry_i].open_time
            quarter = (entered.month - 1) // 3 + 1
            blocks.append((f'{entered.year}-Q{quarter}', float(result.pnl)))
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
    chronological = {}
    for market in MARKETS:
        for symbol in SYMBOLS:
            try:
                candles = await _history(client, symbol, market)
            except httpx.HTTPStatusError as exc:
                print(market.upper(), symbol, "SKIP", exc.response.status_code)
                continue
            digest = hashlib.sha256('\n'.join(
                f'{c.open_time.isoformat()}|{c.open}|{c.high}|{c.low}|{c.close}|{c.volume}'
                for c in candles
            ).encode()).hexdigest()
            print('DATASET', market, symbol, 'end_day', DATA_END_DAY.isoformat(),
                  'bars', len(candles), 'sha256', digest)
            split = int(len(candles) * DEVELOPMENT_FRACTION)
            dev = await _replay(candles, WARMUP, split, blocks=chronological.setdefault(('NEW', 'DEV'), []), market=market)
            oos = await _replay(candles, split, len(candles), blocks=chronological.setdefault(('NEW', 'OOS'), []), market=market)
            legacy_dev = await _replay(candles, WARMUP, split, LegacyVolumeConfirmedBreakoutStrategy, blocks=chronological.setdefault(('LEGACY', 'DEV'), []), market=market)
            legacy_oos = await _replay(candles, split, len(candles), LegacyVolumeConfirmedBreakoutStrategy, blocks=chronological.setdefault(('LEGACY', 'OOS'), []), market=market)
            total_dev.append(dev); total_oos.append(oos)
            print(market.upper(), symbol, "NEW_DEV", asdict(dev), "NEW_OOS", asdict(oos),
                  "LEGACY_DEV", asdict(legacy_dev), "LEGACY_OOS", asdict(legacy_oos))
    for (version, segment), trades in sorted(chronological.items()):
        for quarter in sorted({quarter for quarter, _ in trades}):
            values = [pnl for period, pnl in trades if period == quarter]
            print("QUARTER", version, segment, quarter, {
                "signals": len(values), "wins": sum(p > 0 for p in values),
                "losses": sum(p <= 0 for p in values), "net_pnl": sum(values),
            })
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
