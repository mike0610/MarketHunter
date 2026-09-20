"""Render MarketHunter research observations without implying order authorization."""
from __future__ import annotations

from models.signal import Signal
from telegram.entry_readiness import assess_alert


class MessageBuilder:
    def build(self, signal: Signal) -> str:
        status, explanation = assess_alert(signal)
        risk = signal.metadata.get("risk") if isinstance(signal.metadata, dict) else None
        lines = [
            f"MarketHunter | {status} (НЕ BUY / НЕ SELL)",
            f"Strategy : {signal.strategy}",
            f"Market   : {signal.market.upper()}",
            f"Symbol   : {signal.symbol}",
            f"Timeframe: {signal.timeframe}",
            f"Direction: {signal.direction}",
            f"Score    : {signal.score} (internal score, not win probability)",
            f"Status   : {explanation}",
        ]
        if isinstance(risk, dict):
            for key, label in (
                ("entry", "Reference entry"),
                ("stop_loss", "Stop"),
                ("take_profit", "Target"),
                ("risk_reward", "RR"),
            ):
                if risk.get(key) is not None:
                    lines.append(f"{label}: {risk[key]}")
        lines.extend(["", "Reasons:"])
        lines.extend(f"• {reason}" for reason in signal.reasons)
        lines.extend(["", "Research alert only. No orders. Recheck live price and liquidity."])
        return "\n".join(lines)
