"""Replay selected MarketHunter strategies over historical candles."""

from __future__ import annotations

from dataclasses import dataclass

from backtesting.trade_simulator import ExecutionAssumptions, TradeSimulator
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
    fee_bps_per_side: float = 4.0
    slippage_bps_per_side: float = 2.0
    ambiguous_candle_policy: str = "stop_first"
    allow_overlapping_positions: bool = False


class StrategyReplayEngine:
    """Deterministic replay using next-candle entry and explicit execution assumptions."""

    def __init__(self, assumptions: ReplayAssumptions | None = None) -> None:
        self.assumptions = assumptions or ReplayAssumptions()
        self.snapshot_builder = SnapshotBuilder()
        self.simulator = TradeSimulator(
            ExecutionAssumptions(
                fee_bps_per_side=self.assumptions.fee_bps_per_side,
                slippage_bps_per_side=self.assumptions.slippage_bps_per_side,
                ambiguous_candle_policy=self.assumptions.ambiguous_candle_policy,
            )
        )

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
        index = self.assumptions.warmup_candles

        while index < len(candles) - 1:
            history = candles[: index + 1]
            snapshot = self.snapshot_builder.build(symbol, history)
            signal = await strategy.analyze(snapshot)
            if signal is None:
                index += 1
                continue

            entry_index = index + 1
            next_candle = candles[entry_index]
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
                index += 1
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
            future = candles[entry_index:]
            result = (
                self.simulator.long(position, future)
                if side == "LONG"
                else self.simulator.short(position, future)
            )
            profits.append(float(result.pnl))

            if self.assumptions.allow_overlapping_positions:
                index += 1
            else:
                exit_index = entry_index + result.exit_offset
                index = max(index + 1, exit_index + 1)

        return profits
