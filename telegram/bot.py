"""
MarketHunter

telegram/bot.py
"""

from __future__ import annotations

from telegram.message_builder import (
    MessageBuilder,
)

from telegram.notifier import (
    TelegramNotifier,
)

from models.signal import Signal


class TelegramBot:

    def __init__(

        self,

        token: str,

        chat_id: str,

    ) -> None:

        self.builder = MessageBuilder()

        self.notifier = TelegramNotifier(

            token,

            chat_id,

        )

    def send_signal(

        self,

        signal: Signal,

    ) -> None:

        text = self.builder.build(
            signal,
        )

        self.notifier.send(
            text,
        )