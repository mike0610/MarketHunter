"""
MarketHunter

trading_scanner/gates.py

Module:
The liquidity/executability gate - deterministic, evidence-backed
thresholds only. No queue-position/depth/fill-probability claim is
made anywhere here (that gap is already documented in
backtesting/execution_policy.py - this module makes no execution
claim at all, only a discovery-stage eligibility filter).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from experiment1.models import SessionState
from trading_scanner.models import IbkrContract, LiquidityContext


@dataclass(frozen=True, slots=True)
class LiquidityThresholds:
    """
    Conservative, configurable penny-stock/microcap/liquidity floors -
    never a fabricated "liquidity score," just two explicit numeric
    minimums a caller may override (e.g. per-account-tier policy in a
    future slice). The defaults are v1's own conservative baseline,
    exactly as dispatched.
    """

    min_last_price: Decimal = Decimal("5")
    min_average_daily_dollar_volume: Decimal = Decimal("5000000")

    def __post_init__(self) -> None:
        if self.min_last_price <= 0 or self.min_average_daily_dollar_volume <= 0:
            raise ValueError("thresholds must be positive")


DEFAULT_LIQUIDITY_THRESHOLDS = LiquidityThresholds()


@dataclass(frozen=True, slots=True)
class GateResult:
    eligible: bool
    reasons: tuple[str, ...]  # always non-empty - explainable either way


def evaluate_liquidity_gate(
    contract: IbkrContract,
    liquidity: LiquidityContext,
    session_state: SessionState,
    thresholds: LiquidityThresholds = DEFAULT_LIQUIDITY_THRESHOLDS,
) -> GateResult:
    """
    Pure, deterministic eligibility check. Every failing condition is
    reported (not just the first) so a rejected candidate's
    reject_reason is genuinely explainable, never a single opaque
    "failed gate." A restricted contract (e.g. halted, or on a
    restricted list per the source's own provenance - see
    IbkrContract.restricted) is never eligible, regardless of how
    liquid it otherwise is.
    """
    reasons: list[str] = []

    if contract.restricted:
        reasons.append("contract is flagged restricted by its source")
    if session_state is not SessionState.REGULAR:
        reasons.append(f"session_state={session_state.value} - regular session only in v1")
    if liquidity.last_price < thresholds.min_last_price:
        reasons.append(
            f"last_price={liquidity.last_price} < minimum {thresholds.min_last_price} (penny-stock/microcap floor)"
        )
    if liquidity.average_daily_dollar_volume < thresholds.min_average_daily_dollar_volume:
        reasons.append(
            f"average_daily_dollar_volume={liquidity.average_daily_dollar_volume} "
            f"< minimum {thresholds.min_average_daily_dollar_volume}"
        )

    if reasons:
        return GateResult(eligible=False, reasons=tuple(reasons))
    return GateResult(eligible=True, reasons=("session=REGULAR", "price/liquidity floors satisfied", "not restricted"))
