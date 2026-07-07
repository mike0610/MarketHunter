"""
MarketHunter

telegram/telegram_engine.py
"""

from __future__ import annotations

from models.signal import Signal

from telegram.bot import TelegramBot


class TelegramEngine:

    def __init__(

        self,

        token: str,

        chat_id: str,

    ) -> None:

        self.bot = TelegramBot(

            token,

            chat_id,

        )

    def notify(

        self,

        signal: Signal,

    ) -> None:

        self.bot.send_signal(
            signal,
        )