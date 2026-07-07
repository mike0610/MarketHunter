"""
MarketHunter

telegram/message_builder.py
"""

from __future__ import annotations

from models.signal import Signal


class MessageBuilder:
    """
    Builds Telegram messages.
    """

    def build(
        self,
        signal: Signal,
    ) -> str:

        lines = [

            "📈 MarketHunter",

            "",

            f"Strategy : {signal.strategy}",

            f"Market   : {signal.market.upper()}",

            f"Symbol   : {signal.symbol}",

            f"Direction: {signal.direction}",

            f"Score    : {signal.score}",

            "",

            "Reasons:"

        ]

        for reason in signal.reasons:

            lines.append(
                f"• {reason}"
            )

        return "\n".join(lines)