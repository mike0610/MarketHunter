"""
MarketHunter

config/defaults.py
"""

DEFAULTS = {

    #
    # Scanner
    #

    "TIMEFRAME": "1d",

    "WORKERS": 10,

    "MIN_CANDLES": 200,

    #
    # Risk
    #

    "ACCOUNT_SIZE": 10000,

    "RISK_PERCENT": 1.0,

    "RR": 2.0,

    #
    # Probability
    #

    "MIN_SCORE": 80,

    #
    # Telegram
    #

    "ENABLE_TELEGRAM": False,

    #
    # Live Trading
    #

    "LIVE_TRADING": False,

    #
    # Binance
    #

    "USE_TESTNET": True,

}