"""Replay selected MarketHunter strategies over historical candles."""

from __future__ import annotations

from dataclasses import dataclass

from backtesting.trade_simulator import TradeSimulator
from models.candle import Candle
from models.position import Position
from services.snapshot_builder import SnapshotBuilder
from strategies.base_strategy import BaseStrategy


@dataclass(slots=True)
class ReplayAssumptions:
    warmup_candles: int = 200
    stop_atr: float = 1.0
    target_atr: float = 2.0
    quantity: float = 1.0


class StrategyReplayEngine:
    """Deterministic v1 replay using next-candle entry and ATR exits."""

    def __init__(self, assumptions: ReplayAssumptions | None = None) -> None:
        self.assumptions = assumptions or ReplayAssumptions()
        self.snapshot_builder = SnapshotBuilder()
        self.simulator = TradeSimulator()

    async def run(
        self,
        strategy: BaseStrategy,
        symbol: str,
        market: str,
        candles: list[Candle],
    ) -> list[float]:
        if len(candles) <= self.assumptions.warmup_candles + 1:
            raise ValueError("Not enough candles for strategy replay.")

        profits: list[float] = []
        start = self.assumptions.warmup_candles

        for index in range(start, len(candles) - 1):
            history = candles[: index + 1]
            snapshot = self.snapshot_builder.build(symbol, history)
            signal = await strategy.analyze(snapshot)
            if signal is None:
                continue

            next_candle = candles[index + 1]
            entry = next_candle.open
            atr = snapshot.atr14
            side = str(signal.direction or "").upper()

            if side == "LONG":
                stop = entry - atr * self.assumptions.stop_atr
                target = entry + atr * self.assumptions.target_atr
            elif side == "SHORT":
                stop = entry + atr * self.assumptions.stop_atr
                target = entry - atr * self.assumptions.target_atr
            else:
                continue

            position = Position(
                symbol=symbol,
                market=market,
                side=side,
                quantity=self.assumptions.quantity,
                entry=entry,
                stop_loss=stop,
                take_profit=target,
                opened_at=0.0,
                current_price=entry,
            )
            future = candles[index + 1 :]
            pnl = (
                self.simulator.long(position, future)
                if side == "LONG"
                else self.simulator.short(position, future)
            )
            profits.append(float(pnl))

        return profits
