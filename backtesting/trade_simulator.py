"""Historical trade simulation with explicit execution assumptions."""

from __future__ import annotations

from dataclasses import dataclass

from models.position import Position


@dataclass(frozen=True, slots=True)
class ExecutionAssumptions:
    """Research-only execution assumptions, expressed in basis points."""

    fee_bps_per_side: float = 4.0
    slippage_bps_per_side: float = 2.0
    ambiguous_candle_policy: str = "stop_first"

    def __post_init__(self) -> None:
        if self.fee_bps_per_side < 0 or self.slippage_bps_per_side < 0:
            raise ValueError("Execution costs cannot be negative.")
        if self.ambiguous_candle_policy not in {"stop_first", "target_first"}:
            raise ValueError("Unsupported ambiguous candle policy.")


@dataclass(frozen=True, slots=True)
class SimulationResult:
    pnl: float
    gross_pnl: float
    fees: float
    exit_offset: int
    exit_reason: str
    entry_fill: float
    exit_fill: float


class TradeSimulator:
    """OHLC replay with adverse slippage, fees and deterministic ambiguity rules."""

    def __init__(self, assumptions: ExecutionAssumptions | None = None) -> None:
        self.assumptions = assumptions or ExecutionAssumptions()

    @property
    def _fee_rate(self) -> float:
        return self.assumptions.fee_bps_per_side / 10_000.0

    @property
    def _slippage_rate(self) -> float:
        return self.assumptions.slippage_bps_per_side / 10_000.0

    def _entry_fill(self, position: Position) -> float:
        if position.side == "LONG":
            return position.entry * (1.0 + self._slippage_rate)
        return position.entry * (1.0 - self._slippage_rate)

    def _exit_fill(self, side: str, raw_price: float) -> float:
        if side == "LONG":
            return raw_price * (1.0 - self._slippage_rate)
        return raw_price * (1.0 + self._slippage_rate)

    def _result(
        self,
        position: Position,
        raw_exit: float,
        exit_offset: int,
        exit_reason: str,
    ) -> SimulationResult:
        entry_fill = self._entry_fill(position)
        exit_fill = self._exit_fill(position.side, raw_exit)
        quantity = position.quantity

        if position.side == "LONG":
            gross = (exit_fill - entry_fill) * quantity
        else:
            gross = (entry_fill - exit_fill) * quantity

        fees = (entry_fill + exit_fill) * quantity * self._fee_rate
        return SimulationResult(
            pnl=float(gross - fees),
            gross_pnl=float(gross),
            fees=float(fees),
            exit_offset=exit_offset,
            exit_reason=exit_reason,
            entry_fill=float(entry_fill),
            exit_fill=float(exit_fill),
        )

    def _choose_ambiguous_exit(self, stop: float, target: float) -> tuple[float, str]:
        if self.assumptions.ambiguous_candle_policy == "target_first":
            return target, "target"
        return stop, "stop"

    def long(self, position: Position, candles) -> SimulationResult:
        if not candles:
            raise ValueError("Trade simulation requires at least one candle.")

        for offset, candle in enumerate(candles):
            stop_hit = candle.low <= position.stop_loss
            target_hit = candle.high >= position.take_profit
            if stop_hit and target_hit:
                price, reason = self._choose_ambiguous_exit(
                    position.stop_loss,
                    position.take_profit,
                )
                return self._result(position, price, offset, reason)
            if stop_hit:
                return self._result(position, position.stop_loss, offset, "stop")
            if target_hit:
                return self._result(position, position.take_profit, offset, "target")

        return self._result(position, candles[-1].close, len(candles) - 1, "window_close")

    def short(self, position: Position, candles) -> SimulationResult:
        if not candles:
            raise ValueError("Trade simulation requires at least one candle.")

        for offset, candle in enumerate(candles):
            stop_hit = candle.high >= position.stop_loss
            target_hit = candle.low <= position.take_profit
            if stop_hit and target_hit:
                price, reason = self._choose_ambiguous_exit(
                    position.stop_loss,
                    position.take_profit,
                )
                return self._result(position, price, offset, reason)
            if stop_hit:
                return self._result(position, position.stop_loss, offset, "stop")
            if target_hit:
                return self._result(position, position.take_profit, offset, "target")

        return self._result(position, candles[-1].close, len(candles) - 1, "window_close")
