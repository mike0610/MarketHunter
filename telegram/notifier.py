"""
MarketHunter

telegram/notifier.py
"""

from __future__ import annotations

import requests


class TelegramNotifier:

    def __init__(
        self,
        token: str,
        chat_id: str,
    ) -> None:

        self.url = (
            f"https://api.telegram.org/bot{token}"
        )

        self.chat_id = chat_id

    def send(
        self,
        text: str,
    ) -> None:

        requests.post(

            self.url + "/sendMessage",

            json={

                "chat_id": self.chat_id,

                "text": text,

            },

            timeout=15,

        )