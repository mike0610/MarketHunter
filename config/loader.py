"""
MarketHunter

config/loader.py
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from config.defaults import DEFAULTS
from config.settings import Settings


load_dotenv()


class ConfigLoader:

    def load(self) -> Settings:

        return Settings(

            timeframe=os.getenv(
                "TIMEFRAME",
                DEFAULTS["TIMEFRAME"],
            ),

            workers=int(
                os.getenv(
                    "WORKERS",
                    DEFAULTS["WORKERS"],
                )
            ),

            min_candles=int(
                os.getenv(
                    "MIN_CANDLES",
                    DEFAULTS["MIN_CANDLES"],
                )
            ),

            account_size=float(
                os.getenv(
                    "ACCOUNT_SIZE",
                    DEFAULTS["ACCOUNT_SIZE"],
                )
            ),

            risk_percent=float(
                os.getenv(
                    "RISK_PERCENT",
                    DEFAULTS["RISK_PERCENT"],
                )
            ),

            rr=float(
                os.getenv(
                    "RR",
                    DEFAULTS["RR"],
                )
            ),

            min_score=int(
                os.getenv(
                    "MIN_SCORE",
                    DEFAULTS["MIN_SCORE"],
                )
            ),

            enable_telegram=(
                os.getenv(
                    "ENABLE_TELEGRAM",
                    str(
                        DEFAULTS["ENABLE_TELEGRAM"]
                    ),
                ).lower()
                == "true"
            ),

            live_trading=(
                os.getenv(
                    "LIVE_TRADING",
                    str(
                        DEFAULTS["LIVE_TRADING"]
                    ),
                ).lower()
                == "true"
            ),

            use_testnet=(
                os.getenv(
                    "USE_TESTNET",
                    str(
                        DEFAULTS["USE_TESTNET"]
                    ),
                ).lower()
                == "true"
            ),

        )