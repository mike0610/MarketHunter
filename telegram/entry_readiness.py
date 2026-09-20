"""Conservative, presentation-only readiness gate for Telegram research alerts.

Never authorizes orders. Missing evidence cannot be promoted to ENTRY_READY.
"""
from __future__ import annotations

import math
from models.signal import Signal


def assess_alert(signal: Signal) -> tuple[str, str]:
    meta = signal.metadata or {}
    risk = meta.get("risk")
    if not isinstance(risk, dict):
        return "NO_TRADE", "Entry, stop and target are unavailable."

    try:
        entry = float(risk["entry"])
        stop = float(risk["stop_loss"])
        target = float(risk["take_profit"])
        rr = float(risk["risk_reward"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return "NO_TRADE", "Incomplete or invalid risk geometry."

    if not all(math.isfinite(x) and x > 0 for x in (entry, stop, target, rr)):
        return "NO_TRADE", "Invalid entry, stop, target or RR."
    direction = signal.direction.upper()
    if not ((direction == "LONG" and stop < entry < target)
            or (direction == "SHORT" and target < entry < stop)):
        return "NO_TRADE", "Entry, stop and target contradict trade direction."
    calculated_rr = abs(target - entry) / abs(entry - stop)
    if not math.isclose(rr, calculated_rr, rel_tol=0.02):
        return "NO_TRADE", "Reported RR differs from price geometry."

    for key, label in (
        ("risk_geometry_valid", "Risk geometry"),
        ("target_clear", "Target clearance"),
        ("reaction_confirmed", "Entry reaction"),
    ):
        if meta.get(key) is False:
            return "NO_TRADE", f"{label} check failed."
        if meta.get(key) is not True:
            return "WATCH", f"{label} has not been verified."

    if meta.get("research_skipped"):
        return "NO_TRADE", str(meta["research_skipped"])
    if not meta.get("research_trade_id"):
        return "WATCH", "No qualified research trade is linked."
    if meta.get("market_data_fresh") is not True:
        return "WATCH", "Current executable price and data freshness are not verified."
    if meta.get("execution_liquidity_verified") is not True:
        return "WATCH", "Executable liquidity and spread are not verified."
    return "ENTRY_READY", "Research checks passed; alert only, no order authorization."
