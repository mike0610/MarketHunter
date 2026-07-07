"""
MarketHunter

config/validator.py
"""

from __future__ import annotations

from config.settings import Settings


class ConfigValidator:

    def validate(
        self,
        settings: Settings,
    ) -> None:

        if settings.workers < 1:

            raise ValueError(
                "Workers must be > 0."
            )

        if settings.risk_percent <= 0:

            raise ValueError(
                "Risk must be > 0."
            )

        if settings.rr <= 0:

            raise ValueError(
                "RR must be > 0."
            )

        if settings.account_size <= 0:

            raise ValueError(
                "Account size must be > 0."
            )