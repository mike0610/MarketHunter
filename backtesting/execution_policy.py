"""
MarketHunter

backtesting/execution_policy.py

Module:
The smallest execution-realism baseline: a research-local
ExecutionPolicyVersion layer, kept explicitly separate from
StrategyVersion (alpha/signal) logic. This module never generates a
signal and never mutates a strategy's rules or a backtest's own
verdict - it only decides, given an already-chosen entry attempt
(side, requested price, and the OHLC evidence available at that
candle), how that attempt would actually have been filled under one of
two baseline execution modes, then reuses the existing, unmodified
exit-resolution logic (backtesting.trade_simulator.resolve_exit) for
the resulting position - the existing TradeSimulator "remains the
simple comparator, not deleted."

Two baseline modes:

AGGRESSIVE_TAKER matches TradeSimulator's own existing, already-tested
assumption exactly: a requested entry always fills, adjusted by
adverse slippage. This is not new logic - it is today's existing
default behavior, now explicitly labeled and measured through this
policy's own stats layer (see summarize_execution_policy) rather than
silently assumed. It is never treated as a depth-aware guarantee: this
baseline reports FULL_FILL because that is TradeSimulator's own
existing assumption, not because arbitrary size is actually verified
fillable against real depth evidence (no such evidence exists in this
repository - see docs/backtesting-execution-realism-baseline.md).

PASSIVE_MAKER_SIMPLE never assumes touch == fill. The only OHLC-
derivable rule that does not fabricate queue position or liquidity is
a strict trade-through test: a resting limit price is only ever
treated as filled if the candle's range genuinely traded through it
(a strict inequality, not merely touching the exact boundary) - a bar
that only touches a level offers no real evidence that a resting order
ahead of ours in the queue would have let ours fill at all. A maker
fill also never incurs the adverse entry slippage TradeSimulator
applies to a market/taker entry - the whole point of a resting order
is executing at its own price, not a slipped one; the exit leg (a
market action once stop/target is breached) still incurs the usual
adverse exit slippage, matching TradeSimulator's own exit convention
exactly. A maker/taker fee-rate differential is NOT modeled - the same
fee_bps_per_side is reused for both, a documented simplification
rather than a fabricated fee schedule.

FillOutcome.PARTIAL_FILL exists as a structurally-supported case a
FUTURE L2/event-replay-capable execution policy could produce - this
OHLC-only baseline NEVER returns it. Queue-aware partial-fill
probability cannot be derived from OHLC data alone (no book depth, no
queue position), so this module does not invent one; a real gap here
is reported as such (NEEDS-DATA), never papered over with an assumed
number.

A NO_FILL is reported as a missed-opportunity counterfactual only -
its `simulation` field stays None, and it never contributes to
realized gross/net P&L in summarize_execution_policy.

compute_post_fill_markout is an execution-QUALITY diagnostic only, per
the dispatch's own "not alpha" framing - the signed forward price move
over a predeclared horizon following a fill. It is never fed back into
a strategy's own signal/rules, and returns None (not a fabricated
partial-horizon number) when fewer than horizon_bars candles remain.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from backtesting.trade_simulator import ExecutionAssumptions, SimulationResult, resolve_exit
from models.candle import Candle
from models.position import Position


class ExecutionMode(str, Enum):
    AGGRESSIVE_TAKER = "AGGRESSIVE_TAKER"
    PASSIVE_MAKER_SIMPLE = "PASSIVE_MAKER_SIMPLE"


class FillOutcome(str, Enum):
    """
    FULL_FILL / NO_FILL are OHLC-derivable and genuinely produced by
    this module's baseline. PARTIAL_FILL is a structurally-supported
    case for a future execution policy with L2/event-replay evidence -
    this OHLC-only baseline never returns it (see module docstring).
    EXECUTION_BLOCKED means the required market evidence (candles) was
    missing, never a guessed outcome.
    """

    FULL_FILL = "FULL_FILL"
    PARTIAL_FILL = "PARTIAL_FILL"
    NO_FILL = "NO_FILL"
    EXECUTION_BLOCKED = "EXECUTION_BLOCKED"


class EvidenceLevel(str, Enum):
    """How the fill decision was actually derived - never claimed higher than the real input data supports."""

    OHLC = "OHLC"
    # QUOTE / L1 / L2 / EVENT_REPLAY are intentionally not offered by
    # this baseline - see FillOutcome's own docstring on PARTIAL_FILL.


@dataclass(frozen=True, slots=True)
class ExecutionAttemptResult:
    mode: ExecutionMode
    outcome: FillOutcome
    evidence_level: EvidenceLevel
    filled_quantity: float
    residual_quantity: float
    simulation: SimulationResult | None = None  # set only when outcome is FULL_FILL
    detail: str | None = None


def attempt_aggressive_taker_entry(
    position: Position,
    candles: Sequence[Candle],
    assumptions: ExecutionAssumptions | None = None,
) -> ExecutionAttemptResult:
    """A requested entry always fills (adjusted by adverse slippage) - TradeSimulator's own existing, unmodified assumption."""
    if not candles:
        return ExecutionAttemptResult(
            ExecutionMode.AGGRESSIVE_TAKER,
            FillOutcome.EXECUTION_BLOCKED,
            EvidenceLevel.OHLC,
            filled_quantity=0.0,
            residual_quantity=position.quantity,
            detail="no candle evidence available for this entry attempt",
        )
    assumptions = assumptions or ExecutionAssumptions()
    raw_exit, offset, reason = resolve_exit(
        position.side, position.stop_loss, position.take_profit, candles, assumptions.ambiguous_candle_policy
    )
    simulation = _fill_result(position, assumptions, entry_price=position.entry, apply_entry_slippage=True, raw_exit=raw_exit, exit_offset=offset, exit_reason=reason)
    return ExecutionAttemptResult(
        ExecutionMode.AGGRESSIVE_TAKER,
        FillOutcome.FULL_FILL,
        EvidenceLevel.OHLC,
        filled_quantity=position.quantity,
        residual_quantity=0.0,
        simulation=simulation,
    )


def attempt_passive_maker_entry(
    position: Position,
    entry_candle: Candle,
    remaining_candles: Sequence[Candle],
    assumptions: ExecutionAssumptions | None = None,
) -> ExecutionAttemptResult:
    """
    A resting limit order at position.entry, evaluated against
    entry_candle only - touch does NOT guarantee a fill. FULL_FILL
    only if entry_candle's range genuinely traded through the limit;
    otherwise NO_FILL (missed-opportunity counterfactual, never a
    realized trade). remaining_candles must start at entry_candle
    (inclusive) - it feeds the same resolve_exit() logic
    AGGRESSIVE_TAKER uses, once a genuine fill has happened, so both
    modes are compared on identical exit rules.
    """
    if position.side == "LONG":
        filled = entry_candle.low < position.entry
    else:
        filled = entry_candle.high > position.entry

    if not filled:
        return ExecutionAttemptResult(
            ExecutionMode.PASSIVE_MAKER_SIMPLE,
            FillOutcome.NO_FILL,
            EvidenceLevel.OHLC,
            filled_quantity=0.0,
            residual_quantity=position.quantity,
            detail="entry candle did not trade through the resting limit price - missed-opportunity counterfactual only",
        )

    if not remaining_candles:
        return ExecutionAttemptResult(
            ExecutionMode.PASSIVE_MAKER_SIMPLE,
            FillOutcome.EXECUTION_BLOCKED,
            EvidenceLevel.OHLC,
            filled_quantity=0.0,
            residual_quantity=position.quantity,
            detail="fill triggered but no candle evidence available to simulate the resulting exit",
        )

    assumptions = assumptions or ExecutionAssumptions()
    raw_exit, offset, reason = resolve_exit(
        position.side, position.stop_loss, position.take_profit, remaining_candles, assumptions.ambiguous_candle_policy
    )
    simulation = _fill_result(
        position, assumptions, entry_price=position.entry, apply_entry_slippage=False, raw_exit=raw_exit, exit_offset=offset, exit_reason=reason
    )
    return ExecutionAttemptResult(
        ExecutionMode.PASSIVE_MAKER_SIMPLE,
        FillOutcome.FULL_FILL,
        EvidenceLevel.OHLC,
        filled_quantity=position.quantity,
        residual_quantity=0.0,
        simulation=simulation,
    )


def _fill_result(
    position: Position,
    assumptions: ExecutionAssumptions,
    *,
    entry_price: float,
    apply_entry_slippage: bool,
    raw_exit: float,
    exit_offset: int,
    exit_reason: str,
) -> SimulationResult:
    slippage_rate = assumptions.slippage_bps_per_side / 10_000.0
    fee_rate = assumptions.fee_bps_per_side / 10_000.0

    if apply_entry_slippage:
        entry_fill = entry_price * (1.0 + slippage_rate) if position.side == "LONG" else entry_price * (1.0 - slippage_rate)
    else:
        # A maker fill executes at its own resting price - no adverse
        # entry slippage. The exit leg is still a market action, so it
        # keeps the usual adverse exit slippage below.
        entry_fill = entry_price

    exit_fill = raw_exit * (1.0 - slippage_rate) if position.side == "LONG" else raw_exit * (1.0 + slippage_rate)

    quantity = position.quantity
    gross = (exit_fill - entry_fill) * quantity if position.side == "LONG" else (entry_fill - exit_fill) * quantity
    fees = (entry_fill + exit_fill) * quantity * fee_rate

    return SimulationResult(
        pnl=float(gross - fees),
        gross_pnl=float(gross),
        fees=float(fees),
        exit_offset=exit_offset,
        exit_reason=exit_reason,
        entry_fill=float(entry_fill),
        exit_fill=float(exit_fill),
    )


@dataclass(frozen=True, slots=True)
class ExecutionPolicySummary:
    mode: ExecutionMode
    attempted: int
    full_fill: int
    partial_fill: int
    no_fill: int
    blocked: int
    fill_ratio: float
    gross_pnl: float
    net_pnl: float
    total_fees: float


def summarize_execution_policy(results: Sequence[ExecutionAttemptResult]) -> ExecutionPolicySummary:
    """
    Aggregate stats across one policy's attempts for one candidate:
    attempted/full-fill/partial-fill/no-fill/blocked counts, fill
    ratio, and gross vs net P&L decomposed from each attempt's own
    SimulationResult. A NO_FILL/EXECUTION_BLOCKED attempt (no
    `simulation`) contributes zero to P&L - a missed opportunity is
    never counted as a realized trade.
    """
    if not results:
        raise ValueError("summarize_execution_policy requires at least one result")
    modes = {r.mode for r in results}
    if len(modes) != 1:
        raise ValueError("all results must share the same ExecutionMode")

    full_fill = sum(1 for r in results if r.outcome is FillOutcome.FULL_FILL)
    partial_fill = sum(1 for r in results if r.outcome is FillOutcome.PARTIAL_FILL)
    no_fill = sum(1 for r in results if r.outcome is FillOutcome.NO_FILL)
    blocked = sum(1 for r in results if r.outcome is FillOutcome.EXECUTION_BLOCKED)
    attempted = len(results)

    filled = [r.simulation for r in results if r.simulation is not None]

    return ExecutionPolicySummary(
        mode=modes.pop(),
        attempted=attempted,
        full_fill=full_fill,
        partial_fill=partial_fill,
        no_fill=no_fill,
        blocked=blocked,
        fill_ratio=(full_fill / attempted) if attempted else 0.0,
        gross_pnl=sum(s.gross_pnl for s in filled),
        net_pnl=sum(s.pnl for s in filled),
        total_fees=sum(s.fees for s in filled),
    )


def compute_post_fill_markout(
    side: str,
    fill_price: float,
    candles_after_fill: Sequence[Candle],
    horizon_bars: int,
) -> float | None:
    """
    Execution-quality diagnostic only - never alpha, never fed back
    into strategy rules. The signed price change over exactly
    horizon_bars candles following a fill, in the trade's own
    direction (positive = price moved favorably after the fill,
    negative = adverse markout - see Alpaca-maker-fill-adverse-markout
    research finding in the dispatch this module implements). Returns
    None (NEEDS-DATA) if fewer than horizon_bars candles are
    available - never a partial-horizon approximation presented as the
    full-horizon figure.
    """
    if horizon_bars <= 0:
        raise ValueError("horizon_bars must be positive")
    if len(candles_after_fill) < horizon_bars:
        return None
    reference_close = candles_after_fill[horizon_bars - 1].close
    return (reference_close - fill_price) if side == "LONG" else (fill_price - reference_close)
