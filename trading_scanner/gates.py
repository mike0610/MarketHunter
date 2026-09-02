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
from trading_scanner.models import LiquidityContext

# V1 thresholds, exactly as dispatched: no penny stocks, no microcaps,
# regular session only. These are the only two numeric floors this
# gate enforces - not a fabricated "liquidity score."
MIN_LAST_PRICE = Decimal("5")
MIN_AVERAGE_DAILY_DOLLAR_VOLUME = Decimal("5000000")


@dataclass(frozen=True, slots=True)
class GateResult:
    eligible: bool
    reasons: tuple[str, ...]  # always non-empty - explainable either way


def evaluate_liquidity_gate(liquidity: LiquidityContext, session_state: SessionState) -> GateResult:
    """
    Pure, deterministic eligibility check. Every failing condition is
    reported (not just the first) so a rejected candidate's
    reject_reason is genuinely explainable, never a single opaque
    "failed gate."
    """
    reasons: list[str] = []

    if session_state is not SessionState.REGULAR:
        reasons.append(f"session_state={session_state.value} - regular session only in v1")
    if liquidity.last_price < MIN_LAST_PRICE:
        reasons.append(f"last_price={liquidity.last_price} < minimum {MIN_LAST_PRICE} (penny-stock/microcap floor)")
    if liquidity.average_daily_dollar_volume < MIN_AVERAGE_DAILY_DOLLAR_VOLUME:
        reasons.append(
            f"average_daily_dollar_volume={liquidity.average_daily_dollar_volume} "
            f"< minimum {MIN_AVERAGE_DAILY_DOLLAR_VOLUME}"
        )

    if reasons:
        return GateResult(eligible=False, reasons=tuple(reasons))
    return GateResult(eligible=True, reasons=("session=REGULAR", "price/liquidity floors satisfied"))
